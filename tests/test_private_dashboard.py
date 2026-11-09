import contextlib
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.private_dashboard import HISTORY_OBJECT, StateSync, prepare_private_dashboard
from clearparcel.datawatch.storage import LocalStorage


def _aggregate():
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    return {"schema_version": 2, "generated_at": stamp, "overall": "ok", "counts": {"ok": 1, "warn": 0, "error": 0},
            "workers": {"cloud": {"overall": "ok", "last_report_at": stamp, "source_count": 1}},
            "sources": {"sample": {"id": "sample", "name": "Sample Parcels", "status": "ok", "worker": "cloud",
                                   "checked_at": stamp, "last_report_at": stamp}}}


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class _CountingStorage(LocalStorage):
    def __init__(self, root):
        super().__init__(root)
        self.downloads = 0

    def download(self, name, destination):
        self.downloads += 1
        return super().download(name, destination)


class StateSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "store").mkdir()
        (root / "store" / "aggregate-state.json").write_text(json.dumps(_aggregate()), encoding="utf-8")
        self.storage = _CountingStorage(root / "store")
        self.out = root / "out"
        self.clock = _Clock()
        self.sync = StateSync(self.storage, {"aggregate-state.json": self.out / "agg.json",
                                             HISTORY_OBJECT: self.out / "history.jsonl"},
                              interval=30, required=("aggregate-state.json",), clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sync_copies_present_objects_and_tolerates_missing_optional_ones(self):
        self.assertEqual(self.sync.sync(), {"aggregate-state.json": True, HISTORY_OBJECT: False})
        self.assertTrue((self.out / "agg.json").is_file())
        self.assertFalse((self.out / "history.jsonl").exists())
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["agg.json"])  # no temp files left

    def test_missing_required_object_fails(self):
        (Path(self.tmp.name) / "store" / "aggregate-state.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.sync.sync()

    def test_maybe_sync_is_rate_limited(self):
        self.sync.sync()
        first = self.storage.downloads
        self.clock.now = 10
        self.sync.maybe_sync()
        self.assertEqual(self.storage.downloads, first)
        self.clock.now = 31
        self.sync.maybe_sync()
        self.assertEqual(self.storage.downloads, first * 2)

    def test_failed_sync_still_restarts_the_interval(self):
        (Path(self.tmp.name) / "store" / "aggregate-state.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.sync.sync()
        attempts = self.storage.downloads
        self.clock.now = 5
        self.sync.maybe_sync()  # within the interval: no new storage read
        self.assertEqual(self.storage.downloads, attempts)

    def test_failed_download_keeps_the_last_good_copy(self):
        self.sync.sync()
        good = (self.out / "agg.json").read_bytes()

        def broken(name, destination):
            destination.write_text("partial", encoding="utf-8")
            raise OSError("network")

        self.storage.download = broken
        with self.assertRaises(OSError):
            self.sync.sync()
        self.assertEqual((self.out / "agg.json").read_bytes(), good)


class PreparePrivateDashboardTests(unittest.TestCase):
    def test_config_points_only_at_synced_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "store").mkdir()
            (root / "store" / "aggregate-state.json").write_text(json.dumps(_aggregate()), encoding="utf-8")
            (root / "store" / HISTORY_OBJECT).write_text("", encoding="utf-8")
            registry = root / "registry.json"
            registry.write_text(json.dumps({"state_file": "/elsewhere/state.json", "sources": []}), encoding="utf-8")
            config, sync, port = prepare_private_dashboard(
                {"WATCHTOWER_CONFIG": str(registry), "PORT": "9090", "WATCHTOWER_PRIVATE_SYNC_SECONDS": "1"},
                storage=LocalStorage(root / "store"), workdir=root / "work")
            self.assertEqual(port, 9090)
            self.assertEqual(sync.interval, 5.0)  # bounded below
            work = str(root / "work")
            for key in ("aggregate_state_file", "history_file", "state_file"):
                self.assertTrue(config[key].startswith(work), key)
            self.assertTrue(Path(config["aggregate_state_file"]).is_file())

    def test_bucket_is_required_without_injected_storage(self):
        with self.assertRaises(RuntimeError):
            prepare_private_dashboard({})


class ReadOnlyServeTests(unittest.TestCase):
    def test_failed_sync_is_visible_in_page_and_authenticated_health(self):
        handler, status, _, config = self.handler(environ={"K_SERVICE": "svc"}, read_only=True,
                                                trusted_frontend="cloud-run-iap")
        config["_sync_status"] = {"refresh_failed": True, "last_success_at": None}
        handler.do_GET()
        self.assertIn(b"Showing cached data", handler.wfile.getvalue())
        handler.path, handler.wfile = "/healthz", io.BytesIO()
        handler.do_GET()
        self.assertEqual(status[-1], 503)
        self.assertTrue(json.loads(handler.wfile.getvalue())["refresh_failed"])
        config["_sync_status"]["refresh_failed"] = False
        handler.wfile = io.BytesIO()
        handler.do_GET()
        self.assertEqual(status[-1], 200)

    def handler(self, *, environ, **kwargs):
        captured = {}

        class Server:
            def __init__(self, addr, handler, **kw):
                captured["addr"] = addr
                captured["handler"] = handler

            def serve_forever(self):
                pass

            def server_close(self):
                pass

        config = {"sources": [], "_render_state": _aggregate(), "state_file": "/nonexistent/state.json",
                  "history_file": "/nonexistent/history.jsonl"}
        with patch.object(dashboard, "_BoundedThreadingHTTPServer", Server), \
                patch.dict(dashboard.os.environ, environ, clear=True), \
                contextlib.redirect_stdout(io.StringIO()):
            dashboard.serve(config, host="0.0.0.0", port=8080, **kwargs)
        handler = object.__new__(captured["handler"])
        sent, status = {}, []
        handler.headers, handler.wfile, handler.path = {}, io.BytesIO(), "/"
        handler.send_response = status.append
        handler.send_header = lambda name, value: sent.__setitem__(name, value)
        handler.end_headers = lambda: None
        return handler, status, sent, config

    def test_cloud_run_iap_trust_requires_a_cloud_run_service(self):
        with self.assertRaises(RuntimeError):
            self.handler(environ={}, read_only=True, trusted_frontend="cloud-run-iap")
        with self.assertRaises(RuntimeError):
            self.handler(environ={"K_SERVICE": "svc"}, read_only=True, trusted_frontend="something-else")

    def test_trusted_frontend_refuses_a_writable_server(self):
        with self.assertRaises(RuntimeError):
            self.handler(environ={"K_SERVICE": "svc"}, read_only=False, trusted_frontend="cloud-run-iap")

    def test_read_only_exports_are_served(self):
        handler, status, sent, _ = self.handler(environ={"K_SERVICE": "svc"}, read_only=True,
                                                trusted_frontend="cloud-run-iap")
        handler.path = "/snapshot.json"
        handler.do_GET()
        self.assertEqual(status[-1], 200)
        self.assertIn("application/json", sent["Content-Type"])
        handler.path, handler.wfile = "/api/state", io.BytesIO()
        handler.do_GET()
        self.assertEqual(status[-1], 200)

    def test_wildcard_bind_without_trust_still_needs_a_password(self):
        with self.assertRaises(RuntimeError):
            self.handler(environ={"K_SERVICE": "svc"}, read_only=True)

    def test_read_only_server_has_no_refresh_form_and_refuses_post(self):
        handler, status, sent, config = self.handler(environ={"K_SERVICE": "svc"}, read_only=True,
                                                  trusted_frontend="cloud-run-iap")
        self.assertEqual(config["_csrf_token"], "")
        handler.do_GET()
        self.assertEqual(status[-1], 200)
        page = handler.wfile.getvalue().decode("utf-8")
        self.assertNotIn('action="/refresh"', page)
        self.assertNotIn("Check now", page)
        handler.path, handler.wfile = "/refresh", io.BytesIO()
        handler.do_POST()
        self.assertEqual(status[-1], 405)
        self.assertEqual(sent["Allow"], "GET")

    def test_before_request_runs_and_its_errors_are_ignored(self):
        calls = []

        def hook():
            calls.append(1)
            raise OSError("storage unavailable")

        handler, status, _, _ = self.handler(environ={"K_SERVICE": "svc"}, read_only=True,
                                             trusted_frontend="cloud-run-iap", before_request=hook)
        handler.do_GET()
        self.assertEqual(calls, [1])
        self.assertEqual(status[-1], 200)

    def test_ordinary_private_dashboard_keeps_its_refresh_form(self):
        handler, status, _, config = self.handler(environ={"CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD": "pw"})
        self.assertTrue(config["_csrf_token"])
        handler.headers = {"Authorization": "Basic " + __import__("base64").b64encode(b"watchtower:pw").decode()}
        handler.do_GET()
        self.assertIn('action="/refresh"', handler.wfile.getvalue().decode("utf-8"))


class CliWiringTests(unittest.TestCase):
    def test_private_dashboard_command_needs_no_config_argument(self):
        from clearparcel.datawatch import cli, private_dashboard
        with patch.object(private_dashboard, "serve_private_from_env") as serve, \
                patch("sys.argv", ["watchtower", "private-dashboard"]):
            self.assertEqual(cli.main(), 0)
        serve.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
