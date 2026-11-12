"""An upload replies before its request deadline even while a permitted scan is still running."""
import base64
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from clearparcel.datawatch import county_admin
from clearparcel.datawatch.county_admin import create_county_admin_server
from clearparcel.datawatch.county_attachments import CountyAttachments
from clearparcel.datawatch.county_directory_store import CountyDirectoryStore
from clearparcel.datawatch.storage import LocalStorage

PDF = b"%PDF-1.4\nSYNTHETIC\n%%EOF\n"


class ScanDeadlineTests(unittest.TestCase):
    def start(self, scanner, scan_wait_seconds):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        private = LocalStorage(root / "private")
        self.attachments = CountyAttachments(private)
        server = self.enterContext(create_county_admin_server(
            CountyDirectoryStore(private, LocalStorage(root / "public")), port=0, username="editor",
            password="synthetic-password", attachments=self.attachments, scanner=scanner,
            monitoring_profiles=("cloud",), scan_wait_seconds=scan_wait_seconds))
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        worker.start()
        self.addCleanup(worker.join, 3)
        self.addCleanup(server.shutdown)
        self.port = server.server_port
        self.auth = {"Authorization": "Basic " + base64.b64encode(b"editor:synthetic-password").decode()}

    def call(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body, {**self.auth, **(headers or {})})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def upload(self):
        status, raw = self.call("GET", "/api/counties")
        token = json.loads(raw)["csrf_token"]
        headers = {"Content-Type": "application/pdf", "Origin": f"http://127.0.0.1:{self.port}",
                   "X-Watchtower-CSRF": token, "X-Watchtower-Filename": "p.pdf", "X-Watchtower-Upload-ID": "b" * 32}
        started = time.monotonic()
        status, raw = self.call("POST", "/api/counties/aitkin/attachments?kind=policy", PDF, headers)
        return status, json.loads(raw), time.monotonic() - started

    def wait_for(self, status):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.attachments.info("27001", "b" * 32)["status"] == status:
                return True
            time.sleep(0.02)
        return False

    def test_slow_scan_returns_pending_promptly_and_records_its_verdict_later(self):
        release = threading.Event()

        def slow_scanner(data):
            release.wait(5)
            return data == PDF

        self.start(slow_scanner, 0.2)
        status, body, elapsed = self.upload()
        self.assertEqual((status, body["status"], body["id"]), (201, "pending", "b" * 32))
        self.assertLess(elapsed, 2)
        self.assertEqual(self.attachments.info("27001", "b" * 32)["status"], "pending")
        release.set()
        self.assertTrue(self.wait_for("clean"))

    def test_fast_scan_still_answers_with_its_verdict(self):
        self.start(lambda data: data == PDF, 2)
        status, body, _ = self.upload()
        self.assertEqual((status, body["status"]), (201, "clean"))

    def test_scanner_failure_keeps_quarantine(self):
        def broken(data):
            raise RuntimeError("synthetic scanner failure")

        self.start(broken, 1)
        status, body, _ = self.upload()
        self.assertEqual((status, body["status"]), (201, "pending"))

    def test_scan_wait_must_fit_inside_the_request_deadline(self):
        self.assertLess(county_admin._HOSTED_REQUEST_TIMEOUT * 0.6, county_admin._HOSTED_REQUEST_TIMEOUT)
        with tempfile.TemporaryDirectory() as td:
            private = LocalStorage(Path(td) / "private")
            store = CountyDirectoryStore(private, LocalStorage(Path(td) / "public"))
            with self.assertRaises(ValueError):
                create_county_admin_server(store, port=0, username="editor", password="p",
                                           scan_wait_seconds=county_admin._LOCAL_REQUEST_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
