import datetime as dt
import http.client
import io
import importlib.util
import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch.county_admin import create_county_admin_server
from clearparcel.datawatch.county_admin_hosted import IapAdminAuth, IapVerifier, hosted_storage_settings
from clearparcel.datawatch.county_directory_store import CountyDirectoryStore
from clearparcel.datawatch.county_scanner import ClamdScanner
from clearparcel.datawatch.county_scanner_service import RunScannerClient, create_scanner_server, wait_for_scanner, serve_county_scanner
from clearparcel.datawatch.storage import LocalStorage


ORIGIN = "https://admin-staging.example.org"
AUDIENCE = "/projects/123/locations/us-central1/services/county-admin-staging"
ISSUER = "https://cloud.google.com/iap"


class HostedAuthTests(unittest.TestCase):
    def auth(self, verify):
        return IapAdminAuth(ORIGIN, AUDIENCE, {"editor-sub"}, bytes(range(32)), verify=verify)

    def test_subject_and_issuer_are_checked_and_csrf_is_replica_stable(self):
        def verify(assertion, audience):
            self.assertEqual(audience, AUDIENCE)
            return {"iss": ISSUER if assertion != "bad-issuer" else "foreign",
                    "sub": "editor-sub" if assertion != "foreign" else "unknown-sub"}
        auth = self.auth(verify)
        self.assertIsNone(auth.authorize(None))
        self.assertIsNone(auth.authorize("foreign"))
        self.assertIsNone(auth.authorize("bad-issuer"))
        token = auth.authorize("signed")
        self.assertTrue(token)
        self.assertEqual(token, self.auth(verify).authorize("signed"))
        self.assertIsNone(IapAdminAuth(ORIGIN, AUDIENCE, {"editor-sub"}, bytes(32),
                                      verify=lambda *_: (_ for _ in ()).throw(ValueError())).authorize("forged"))

    def test_hosted_http_requires_assertion_and_exact_https_origin(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            store = CountyDirectoryStore(LocalStorage(root / "private"), LocalStorage(root / "public"))
            auth = self.auth(lambda *_: {"iss": ISSUER, "sub": "editor-sub"})
            with create_county_admin_server(store, port=0, hosted_auth=auth) as server:
                worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
                worker.start()
                try:
                    def request(method, path, headers, body=None):
                        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                        try:
                            conn.request(method, path, body, headers)
                            response = conn.getresponse()
                            return response.status, json.loads(response.read())
                        finally:
                            conn.close()
                    host = {"Host": "admin-staging.example.org"}
                    self.assertEqual(request("GET", "/api/counties", {**host, "X-Goog-Authenticated-User-Email": "fake"})[0], 403)
                    iap = {**host, "X-Goog-IAP-JWT-Assertion": "verified-fixture"}
                    status, body = request("GET", "/api/counties", iap)
                    self.assertEqual(status, 200)
                    mutation = {**iap, "Content-Type": "application/json", "X-Watchtower-CSRF": body["csrf_token"]}
                    path = "/api/counties/aitkin"
                    payload = json.dumps({"draft": {"fips": "27001", "policy": {"text": "Synthetic public"}},
                                          "expected_revision": 0, "request_id": "staging-fixture"})
                    self.assertEqual(request("POST", path, {**mutation, "Origin": "http://admin-staging.example.org"}, payload)[0], 403)
                    self.assertEqual(request("POST", path, {**mutation, "Origin": ORIGIN}, payload)[1]["status"], "published")
                finally:
                    server.shutdown()
                    worker.join(3)

    def test_hosted_storage_requires_distinct_explicit_buckets(self):
        values = {"K_SERVICE": "county-admin-stage", "WATCHTOWER_COUNTY_PRIVATE_BUCKET": "private-stage",
                  "WATCHTOWER_COUNTY_PUBLIC_BUCKET": "public-stage"}
        self.assertEqual(hosted_storage_settings(values), ("private-stage", "public-stage"))
        for invalid in ({}, {**values, "WATCHTOWER_COUNTY_PUBLIC_BUCKET": "private-stage"}):
            with self.assertRaises(ValueError):
                hosted_storage_settings(invalid)

    @unittest.skipUnless(importlib.util.find_spec("google") and importlib.util.find_spec("cryptography"),
                         "hosted dependencies required")
    def test_real_es256_signature_audience_and_expiry(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from google.auth import crypt, jwt

        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        cert = key.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        signer = crypt.ES256Signer.from_string(pem, key_id="fixture")
        verifier = IapVerifier()
        auth = IapAdminAuth(ORIGIN, AUDIENCE, {"editor-sub"}, bytes(range(32)), verify=verifier)
        now = int(dt.datetime.now(dt.UTC).timestamp())
        claims = {"iss": ISSUER, "sub": "editor-sub", "aud": AUDIENCE, "iat": now - 10, "exp": now + 300}
        with patch("clearparcel.datawatch.county_admin_hosted.urlopen",
                   return_value=io.BytesIO(json.dumps({"fixture": cert}).encode())) as fetch:
            sign = lambda claim: jwt.encode(signer, claim).decode()
            self.assertTrue(auth.authorize(sign(claims)))
            self.assertIsNone(auth.authorize(sign({**claims, "aud": "/projects/999/global/backendServices/1"})))
            self.assertIsNone(auth.authorize(sign({**claims, "iat": now - 300, "exp": now - 90})))
            self.assertIsNone(auth.authorize(sign({**claims, "exp": now + 3600})))
            bad_signer = crypt.ES256Signer.from_string(ec.generate_private_key(ec.SECP256R1()).private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
                key_id="fixture")
            self.assertIsNone(auth.authorize(jwt.encode(bad_signer, claims).decode()))
            self.assertEqual(fetch.call_count, 1)


class ClamdScannerTests(unittest.TestCase):
    def scan(self, verdict, *, age_hours=0):
        listener = self.enterContext(socket.socket())
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(2)
        port = listener.getsockname()[1]
        now = dt.datetime(2026, 11, 6, 16, tzinfo=dt.UTC)
        database = now - dt.timedelta(hours=age_hours)
        messages = []

        def daemon():
            with listener.accept()[0] as conn:
                conn.settimeout(2)
                with conn.makefile("rb") as stream:
                    self.assertEqual(stream.read(9), b"zVERSION\0")
                    conn.sendall(database.strftime("ClamAV 1.4.3/100/%a %b %d %H:%M:%S %Y").encode() + b"\0")
            if age_hours <= 72:
                with listener.accept()[0] as conn:
                    conn.settimeout(2)
                    with conn.makefile("rb") as stream:
                        self.assertEqual(stream.read(10), b"zINSTREAM\0")
                        while count := struct.unpack("!I", stream.read(4))[0]:
                            messages.append(stream.read(count))
                        conn.sendall(verdict + b"\0")

        worker = threading.Thread(target=daemon)
        worker.start()
        scanner = ClamdScanner(port, clock=lambda: now, timeout=2)
        try:
            return scanner(b"synthetic PDF")
        finally:
            worker.join(3)
            if age_hours <= 72:
                self.assertEqual(messages, [b"synthetic PDF"])

    def test_only_authoritative_clamd_verdicts_are_accepted(self):
        self.assertIs(self.scan(b"stream: OK"), True)
        self.assertIs(self.scan(b"stream: Eicar-Signature FOUND"), False)
        with self.assertRaises(OSError):
            self.scan(b"INSTREAM size limit exceeded. ERROR")
        with self.assertRaises(OSError):
            self.scan(b"stream: OK", age_hours=73)

    def test_private_scanner_transport_requires_exact_target_and_verdict(self):
        url = "https://" + ".".join(("county-scanner-123", "us-central1", "run", "app"))
        captured = []
        def request(path, headers, body):
            captured.append((path, headers, body))
            return 200, b"rejected"
        client = RunScannerClient(url, request=request, token=lambda: "synthetic-id-token")
        self.assertFalse(client(b"fixture"))
        self.assertEqual(captured[0], (url + "/scan", {
            "Authorization": "Bearer synthetic-id-token", "Content-Type": "application/octet-stream",
        }, b"fixture"))
        with self.assertRaises(ValueError):
            RunScannerClient(url + ".example.org")
        with self.assertRaises(OSError):
            RunScannerClient(url, request=lambda *_: (302, b"clean"), token=lambda: "fixture")(b"data")
        with self.assertRaises(OSError):
            RunScannerClient(url, request=lambda *_: (200, b"clean-plus"), token=lambda: "fixture")(b"data")

    def test_scanner_http_returns_only_verdict_or_unavailable(self):
        def scan(raw):
            if raw == b"failure":
                raise OSError("synthetic private diagnostic")
            return raw == b"clean fixture"
        with create_scanner_server(0, scan, host="127.0.0.1") as server:
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            worker.start()
            try:
                for data, media, expected in [
                    (b"clean fixture", "application/octet-stream", (200, b"clean")),
                    (b"virus fixture", "application/octet-stream", (200, b"rejected")),
                    (b"failure", "application/octet-stream", (503, b"")),
                    (b"clean fixture", "text/plain", (415, b"")),
                ]:
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    try:
                        connection.request("POST", "/scan", data, {"Content-Type": media})
                        response = connection.getresponse()
                        self.assertEqual((response.status, response.read()), expected)
                    finally:
                        connection.close()
            finally:
                server.shutdown()
                worker.join(3)


class ScannerStartupTests(unittest.TestCase):
    def test_delayed_engine_is_retried_before_opening_ingress(self):
        from unittest.mock import Mock
        ticks = [0.0]
        attempts = Mock(side_effect=[OSError("not listening"), ValueError("stale"), True])
        wait_for_scanner(attempts, timeout=5, clock=lambda: ticks[0],
                         sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds))
        self.assertEqual(attempts.call_count, 3)
        self.assertEqual(ticks[0], 2.0)
        attempts.assert_called_with(b"")

    def test_unavailable_or_non_clean_engine_has_bounded_failure(self):
        for result in (False, None, "clean", OSError("unavailable")):
            ticks = [0.0]
            def scan(_):
                if isinstance(result, Exception):
                    raise result
                return result
            with self.assertRaises(OSError):
                wait_for_scanner(scan, timeout=3, clock=lambda: ticks[0],
                                 sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds))
            self.assertEqual(ticks[0], 3.0)

    def test_server_is_never_created_when_startup_fails(self):
        with patch.dict("os.environ", {"K_SERVICE": "synthetic", "PORT": "8080"}), \
             patch("clearparcel.datawatch.county_scanner_service.wait_for_scanner", side_effect=OSError), \
             patch("clearparcel.datawatch.county_scanner_service.create_scanner_server") as create:
            with self.assertRaises(OSError):
                serve_county_scanner()
            create.assert_not_called()

    def test_transport_allows_startup_and_still_bounds_response(self):
        from unittest.mock import MagicMock
        session = MagicMock()
        session.post.return_value.__enter__.return_value.status_code = 200
        session.post.return_value.__enter__.return_value.iter_content.return_value = [b"clean"]
        with patch("requests.Session") as factory:
            factory.return_value.__enter__.return_value = session
            self.assertEqual(RunScannerClient._post("https://synthetic.run.app/scan", {}, b"fixture"), (200, b"clean"))
        self.assertEqual(session.post.call_args.kwargs["timeout"], (3, 120))
