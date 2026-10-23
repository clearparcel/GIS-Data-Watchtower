"""A structurally invalid public snapshot never replaces good data or passes health."""
import contextlib
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import public_dashboard
from clearparcel.datawatch.public_projection import InvalidSnapshotError, validate_snapshot_structure


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def populated() -> dict:
    now = _now()
    return {"schema_version": 3, "generated_at": now, "public_published_at": now, "overall": "ok",
            "counts": {"ok": 1, "warn": 0, "error": 0},
            "workers": {"cloud": {"overall": "ok", "source_count": 1, "last_report_at": now}},
            "sources": {"feed": {"id": "feed", "name": "Feed", "status": "ok", "worker": "cloud",
                                 "checked_at": now, "feature_count": 5}}}


def empty_fleet() -> dict:
    now = _now()
    return {"schema_version": 3, "generated_at": now, "public_published_at": now, "overall": "ok",
            "counts": {"ok": 0, "warn": 0, "error": 0}, "workers": {}, "sources": {}}


class FakeStorage:
    def __init__(self):
        self.document = populated()

    def download(self, name, destination):
        Path(destination).write_text(json.dumps(self.document), encoding="utf-8")
        return True


class SnapshotStructureTests(unittest.TestCase):
    def test_invalid_structures_are_rejected(self):
        now = _now()
        cases = {
            "only publication time": {"public_published_at": now},
            "not an object": [],
            "no schema": {**populated(), "schema_version": None},
            "bad generated_at": {**populated(), "generated_at": "yesterday"},
            "missing sources": {k: v for k, v in populated().items() if k != "sources"},
            "missing workers": {k: v for k, v in populated().items() if k != "workers"},
            "missing counts": {k: v for k, v in populated().items() if k != "counts"},
            "sources wrong type": {**populated(), "sources": []},
            "workers wrong type": {**populated(), "workers": "cloud"},
            "malformed source": {**populated(), "sources": {"feed": "ok"}},
            "malformed count": {**populated(), "counts": {"ok": "1"}},
        }
        for label, document in cases.items():
            with self.subTest(label), self.assertRaises(InvalidSnapshotError):
                validate_snapshot_structure(document)

    def test_valid_empty_and_populated_snapshots_are_accepted(self):
        validate_snapshot_structure(empty_fleet())
        validate_snapshot_structure(populated())


class PublicCacheValidationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.storage = FakeStorage()
        env = {"WATCHTOWER_PUBLIC_WORKDIR": self._tmp.name, "WATCHTOWER_PUBLIC_REFRESH_SECONDS": "5"}
        self._patches = [patch.dict("os.environ", env),
                         patch.object(public_dashboard, "backend_from_env", return_value=self.storage)]
        for item in self._patches:
            item.start()

    def tearDown(self):
        for item in reversed(self._patches):
            item.stop()
        self._tmp.cleanup()

    def healthz(self):
        captured = {}

        class Server:
            def __init__(self, addr, handler, **kwargs):
                captured["handler"] = handler

            def serve_forever(self):
                pass

            def server_close(self):
                pass

        with patch.object(public_dashboard, "_BoundedThreadingHTTPServer", Server), \
                contextlib.redirect_stdout(io.StringIO()):
            public_dashboard.serve_public()
        handler = object.__new__(captured["handler"])
        handler.headers, handler.wfile, handler.command, handler.path = {}, io.BytesIO(), "GET", "/healthz"
        sent = []
        handler.send_response = lambda status: sent.append(status)
        handler.send_header = lambda name, value: None
        handler.end_headers = lambda: None
        handler.do_GET()
        return sent[0], json.loads(handler.wfile.getvalue())

    def test_invalid_snapshot_keeps_last_good_state_and_fails_health(self):
        status, payload = self.healthz()
        self.assertEqual((status, payload["status"]), (200, "ok"))
        cache = public_dashboard._PublicStateCache()
        cache.refresh(force=True)
        good = cache.public_path.read_bytes()
        self.storage.document = {"public_published_at": _now()}
        cache.refresh(force=True)
        self.assertTrue(cache.stale)
        self.assertEqual(cache.public_path.read_bytes(), good)
        self.assertEqual(len(json.loads(good)["sources"]), 1)
        status, payload = self.healthz()
        self.assertEqual(status, 503)
        self.assertEqual(payload["status"], "stale")
        self.assertTrue(payload["refresh_failed"])
        # Recovery: a valid snapshot clears the failed refresh.
        self.storage.document = populated()
        cache.refresh(force=True)
        self.assertFalse(cache.stale)

    def test_invalid_first_snapshot_is_unavailable_not_empty(self):
        self.storage.document = {"public_published_at": _now(), "sources": {}}
        cache = public_dashboard._PublicStateCache()
        with self.assertRaises(InvalidSnapshotError):
            cache.refresh(force=True)
        # Nothing is accepted, so pages and /healthz stay unavailable (503).
        self.assertFalse(cache.public_path.exists())
        self.assertTrue(cache.stale)

    def test_valid_empty_fleet_is_accepted(self):
        self.storage.document = empty_fleet()
        cache = public_dashboard._PublicStateCache()
        cache.refresh(force=True)
        self.assertFalse(cache.stale)
        self.assertEqual(json.loads(cache.public_path.read_text(encoding="utf-8"))["sources"], {})

    def test_overview_shows_missing_counts_as_unavailable(self):
        document = populated()
        document["counts"] = {}
        self.storage.document = document
        cache = public_dashboard._PublicStateCache()
        cache.refresh(force=True)
        page = public_dashboard.render_public_dashboard(cache.config)
        self.assertIn('<div class="metric ok">—</div><span class="subtext">— had issues', page)


if __name__ == "__main__":
    unittest.main()
