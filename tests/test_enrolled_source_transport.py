"""Offline checks for the public-only boundary on county-editor requests."""
import contextvars
import io
import os
import socket
import ssl
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from clearparcel.datawatch import transport, watch


PUBLIC = ((socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),)
URL = "https://provider.example/data.zip"


class EnrolledSourceTransportTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(watch, "_PUBLIC_SOURCE_REQUESTS",
            contextvars.ContextVar("test_public_source_requests", default=True)))
        self.enterContext(patch.object(transport, "effective_proxy", return_value=False))
        self.enterContext(patch.object(watch, "effective_proxy", return_value=False))

    def test_private_and_special_addresses_never_reach_a_transport(self):
        requests = (
            lambda: watch._request(URL, 2),
            lambda: watch._request(URL, 2, prefer_curl=True),
            lambda: watch._head_request(URL, 2),
            lambda: watch._post_json(URL, {}, 2),
            lambda: watch._urllib_request_once(URL, 2),
            lambda: watch._curl_request_once(URL, 2, transport="curl"),
        )
        for ip in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.0.1",
                   "169.254.169.254", "100.64.0.1", "0.0.0.0", "192.0.2.1",
                   "224.0.0.1", "::1", "fe80::1", "fec0::1", "fd00::1",
                   "::ffff:127.0.0.1", "ff02::1", "64:ff9b::7f00:1", "2002:7f00:1::"):
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            addresses = ((family, socket.SOCK_STREAM, 6, "", (ip, 443)),)
            for invoke in requests:
                with (self.subTest(ip=ip, request=invoke),
                      patch.object(watch, "resolve_addresses", return_value=addresses),
                      patch.object(transport.socket, "socket") as sock,
                      patch.object(watch.urllib.request, "build_opener") as opener,
                      patch.object(watch.subprocess, "run") as curl):
                    with self.assertRaisesRegex(RuntimeError, "not public"):
                        invoke()
                    sock.assert_not_called()
                    opener.assert_not_called()
                    curl.assert_not_called()

    def test_one_private_dns_answer_rejects_the_entire_address_set(self):
        addresses = PUBLIC + ((socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0)),)
        with (patch.object(watch, "resolve_addresses", return_value=addresses),
              patch.object(transport.socket, "socket") as sock):
            with self.assertRaisesRegex(RuntimeError, "not public"):
                watch._head_request(URL, 2)
            sock.assert_not_called()

    def test_empty_dns_answers_fail_closed(self):
        with (patch.object(watch, "resolve_addresses", return_value=()),
              patch.object(transport.socket, "socket") as sock):
            with self.assertRaisesRegex(RuntimeError, "no addresses"):
                watch._head_request(URL, 2)
            sock.assert_not_called()

    def test_six_to_four_is_rejected_even_with_older_ip_classification(self):
        # Early Python 3.12 classified 6to4 as global even when it embeds a
        # private IPv4 destination. Match patched runtimes explicitly.
        classified = SimpleNamespace(is_global=True, is_multicast=False,
            is_reserved=False, is_site_local=False, sixtofour="127.0.0.1")
        addresses = ((socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2002:7f00:1::", 443, 0, 0)),)
        with (patch.object(watch, "resolve_addresses", return_value=addresses),
              patch.object(watch.ipaddress, "ip_address", return_value=classified),
              patch.object(transport.socket, "socket") as sock):
            with self.assertRaisesRegex(RuntimeError, "not public"):
                watch._head_request(URL, 2)
            sock.assert_not_called()

    def test_initial_get_head_and_post_pin_dns_and_preserve_host_and_tls(self):
        for method in ("GET", "HEAD", "POST"):
            with self.subTest(method=method):
                sock = Mock()
                sock.makefile.return_value = io.BytesIO(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
                context = ssl.create_default_context()
                with (patch.object(watch, "resolve_addresses", return_value=PUBLIC) as resolve,
                      patch.object(transport, "resolve_addresses", side_effect=AssertionError("second DNS lookup")),
                      patch.object(transport.socket, "socket", return_value=sock),
                      patch.object(context, "wrap_socket", return_value=sock) as wrap,
                      patch("ssl._create_default_https_context", return_value=context)):
                    if method == "GET":
                        watch._request(URL, 2)
                    elif method == "HEAD":
                        watch._head_request(URL, 2)
                    else:
                        watch._post_json(URL, {}, 2)
                resolve.assert_called_once()
                sock.connect.assert_called_once_with(("93.184.216.34", 443))
                self.assertEqual(wrap.call_args.kwargs["server_hostname"], "provider.example")
                self.assertTrue(context.check_hostname)
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                sent = b"".join(call.args[0] for call in sock.sendall.call_args_list)
                self.assertIn(b"Host: provider.example\r\n", sent)

    def test_initial_curl_and_fallback_share_the_validated_dns_snapshot(self):
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            Path(command[command.index("-o") + 1]).write_bytes(b"{}")
            Path(command[command.index("-D") + 1]).write_text("", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout=b"__CP_HTTP__200\n__CP_REDIRECT__\n", stderr=b"")
        for mode in ("preferred", "fallback", "post-fallback"):
            with (self.subTest(mode=mode),
                  patch.object(watch, "resolve_addresses", return_value=PUBLIC) as resolve,
                  patch.object(transport, "resolve_addresses", side_effect=AssertionError("second DNS lookup")),
                  patch.object(watch.shutil, "which", return_value="curl"),
                  patch.object(watch.subprocess, "run", side_effect=run),
                  patch.object(watch, "_urllib_request_once", side_effect=urllib.error.URLError("network"))):
                if mode == "post-fallback":
                    watch._post_json(URL, {}, 2)
                else:
                    watch._request(URL, 2, prefer_curl=mode == "preferred")
                resolve.assert_called_once()
        self.assertEqual(len(commands), 3)
        for command in commands:
            self.assertEqual(command[1], "--disable")
            self.assertEqual(command[command.index("--resolve") + 1], "provider.example:443:93.184.216.34")
            self.assertEqual(command[command.index("--noproxy") + 1], "*")
            self.assertNotIn("--insecure", command)

    def test_effective_proxies_fail_closed_for_enrolled_requests(self):
        for invoke in (lambda: watch._request(URL, 2),
                       lambda: watch._request(URL, 2, prefer_curl=True),
                       lambda: watch._head_request(URL, 2),
                       lambda: watch._post_json(URL, {}, 2)):
            with (self.subTest(request=invoke),
                  patch.object(watch, "resolve_addresses", return_value=PUBLIC),
                  patch.object(transport, "effective_proxy", return_value=True),
                  patch.object(watch, "effective_proxy", return_value=True),
                  patch.object(watch.urllib.request, "build_opener") as opener,
                  patch.object(watch.subprocess, "run") as curl):
                with self.assertRaisesRegex(RuntimeError, "proxy"):
                    invoke()
                opener.assert_not_called()
                curl.assert_not_called()

    def test_public_ipv6_answers_are_pinned(self):
        addresses = ((socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),)
        with (patch.object(watch, "resolve_addresses", return_value=addresses) as resolve,
              patch.object(watch, "_curl_request_once", return_value=(b"{}", {"status": 200})) as curl):
            watch._request(URL, 2, prefer_curl=True)
        resolve.assert_called_once()
        self.assertEqual(curl.call_args.args[0].addresses, addresses)

    def test_redirect_allowlist_cannot_lift_the_enrolled_boundary(self):
        private = ((socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),)
        for target in (URL, "https://cdn.example/data.zip"):
            with (self.subTest(target=target),
                  patch.dict(os.environ, {"WATCHTOWER_REDIRECT_ALLOW_HOSTS": "provider.example,cdn.example"}),
                  patch.object(watch, "resolve_addresses", return_value=private)):
                with self.assertRaisesRegex(RuntimeError, "not public"):
                    watch._validated_redirect(URL, target, URL)

    def test_adapter_context_is_reset_after_success_and_failure(self):
        # Outside an enrolled adapter, operator-configured requests retain their
        # existing private endpoint/proxy behavior.
        token = watch._PUBLIC_SOURCE_REQUESTS.set(False)
        self.addCleanup(watch._PUBLIC_SOURCE_REQUESTS.reset, token)
        for failed in (False, True):
            def adapter(source, timeout):
                self.assertEqual(watch._PUBLIC_SOURCE_REQUESTS.get(), bool(source.get("_county_monitoring_revision")))
                if failed and source.get("_county_monitoring_revision"):
                    raise RuntimeError("synthetic adapter failure")
                return {}
            with self.subTest(failed=failed), patch.object(watch, "_http_file", side_effect=adapter):
                enrolled = {"kind": "http_file", "url": URL, "_county_monitoring_revision": 1}
                if failed:
                    with self.assertRaisesRegex(RuntimeError, "synthetic"):
                        watch._source_check(enrolled, 2)
                else:
                    watch._source_check(enrolled, 2)
                self.assertFalse(watch._PUBLIC_SOURCE_REQUESTS.get())
                watch._source_check({"kind": "http_file", "url": "http://127.0.0.1/data.zip"}, 2)
        with (patch.object(watch, "resolve_addresses", side_effect=AssertionError("operator DNS changed")),
              transport.RequestDeadline(2) as deadline):
            self.assertEqual(watch._public_request_url(URL, deadline), URL)
