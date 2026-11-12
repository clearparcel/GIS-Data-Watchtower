"""The password-free loopback dashboard answers only to local Host names (DNS rebinding)."""
import contextlib
import http.client
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import dashboard


class LocalDashboardHostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "state.json").write_text(json.dumps({"generated_at": None, "sources": {"s": {
            "id": "s", "name": "Synthetic", "status": "ok", "url": "https://private.example.invalid/secret"}}}),
            encoding="utf-8")
        (root / "history.jsonl").write_text("", encoding="utf-8")
        self.config = {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
                       "sources": []}

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, password=""):
        captured = {}

        class Capture:
            def __init__(self, addr, handler, **kwargs):
                captured["handler"] = handler

            def serve_forever(self):
                pass

            def server_close(self):
                pass

        with patch.dict(os.environ, {"CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD": password}), \
                patch.object(dashboard, "_BoundedThreadingHTTPServer", Capture), \
                contextlib.redirect_stdout(io.StringIO()):
            dashboard.serve(self.config, read_only=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), captured["handler"])
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_port

    def get(self, port, hosts, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.putrequest("GET", "/", skip_host=True)
            for host in hosts:
                conn.putheader("Host", host)
            for key, value in (headers or {}).items():
                conn.putheader(key, value)
            conn.endheaders()
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def test_rebound_and_duplicate_hosts_are_rejected_before_any_page(self):
        port = self.start()
        for hosts in ([f"rebound.example:{port}"], [], [f"127.0.0.1:{port}", f"127.0.0.1:{port}"],
                      [f"127.0.0.1:{port + 1}"], ["127.0.0.1"]):
            with self.subTest(hosts=hosts):
                status, body = self.get(port, hosts)
                self.assertEqual(status, 421)
                self.assertNotIn("private.example.invalid", body)

    def test_local_names_are_served(self):
        port = self.start()
        for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"LOCALHOST:{port}"):
            with self.subTest(host=host):
                status, _ = self.get(port, [host])
                self.assertEqual(status, 200)

    def test_password_protected_bind_keeps_basic_auth_without_host_pinning(self):
        port = self.start(password="synthetic-password")
        status, _ = self.get(port, [f"dashboard.example:{port}"])
        self.assertEqual(status, 401)

    def test_local_host_names_cover_ipv6_and_default_port(self):
        self.assertIn("[::1]:8765", dashboard._local_host_names("::1", 8765))
        self.assertIn("localhost", dashboard._local_host_names("127.0.0.1", 80))
        self.assertNotIn("localhost", dashboard._local_host_names("127.0.0.1", 8765))


if __name__ == "__main__":
    unittest.main()
