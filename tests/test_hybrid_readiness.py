import datetime as dt
import json
import tempfile
import threading
import unittest
from pathlib import Path

from clearparcel.datawatch.aggregate import merge_states, publish_partial, with_freshness
from clearparcel.datawatch.storage import LocalStorage


class HybridReadinessTests(unittest.TestCase):
    def test_competing_publishers_preserve_both_workers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = LocalStorage(root / "objects")
            barrier = threading.Barrier(2)
            errors = []

            def run(worker, source):
                try:
                    barrier.wait()
                    publish_partial(
                        storage, "aggregate.json",
                        {"generated_at": "2026-10-04T20:00:00+00:00", "overall": "ok",
                         "counts": {"ok": 1, "warn": 0, "error": 0},
                         "sources": {source: {"id": source, "status": "ok"}}},
                        worker, root / worker,
                    )
                except Exception as exc:
                    errors.append(exc)

            a = threading.Thread(target=run, args=("cloud", "cloud-source"))
            b = threading.Thread(target=run, args=("local", "local-source"))
            a.start(); b.start(); a.join(); b.join()
            self.assertEqual(errors, [])
            state = json.loads((root / "objects" / "aggregate.json").read_text(encoding="utf-8"))
            self.assertEqual(set(state["sources"]), {"cloud-source", "local-source"})
            self.assertEqual(set(state["workers"]), {"cloud", "local"})

    def test_merge_tracks_source_and_worker_success(self):
        base = {"sources": {"a": {"id": "a", "status": "ok", "worker": "cloud", "last_success_at": "2026-10-04T10:00:00+00:00"}}}
        partial = {"generated_at": "2026-10-04T11:00:00+00:00", "overall": "error",
                   "counts": {"ok": 0, "warn": 0, "error": 1},
                   "sources": {"a": {"id": "a", "status": "error"}}}
        state = merge_states(base, partial, "cloud")
        self.assertEqual(state["sources"]["a"]["last_success_at"], "2026-10-04T10:00:00+00:00")
        self.assertEqual(state["workers"]["cloud"]["last_success_at"], "2026-10-04T11:00:00+00:00")

    def test_freshness_is_separate_from_source_health(self):
        now = dt.datetime(2026, 10, 4, 20, 0, tzinfo=dt.timezone.utc)
        state = {"workers": {"local": {"last_success_at": "2026-10-04T10:00:00+00:00"}},
                 "sources": {"a": {"status": "ok", "worker": "local", "last_success_at": "2026-10-04T19:30:00+00:00"},
                             "b": {"status": "error", "worker": "local", "last_success_at": "2026-10-04T19:30:00+00:00"}}}
        result = with_freshness(state, worker_stale_minutes=60, source_stale_minutes=60, now=now)
        self.assertEqual(result["sources"]["a"]["health"], "healthy")
        self.assertEqual(result["sources"]["a"]["reporting"], "stale")
        self.assertEqual(result["sources"]["b"]["health"], "unhealthy")
        self.assertTrue(result["workers"]["local"]["stale"])


if __name__ == "__main__":
    unittest.main()
