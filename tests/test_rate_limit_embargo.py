"""A 429 backoff reaches shared storage the moment it arrives (audit WT31-02 remainder).

A cloud container killed outright never runs its failure-path state upload, so
the backoff is also written to a small version-conditional embargo object.
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import cloud_job, watch
from clearparcel.datawatch.storage import LocalStorage, StorageConflictError


def _config(root: Path):
    return {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
            "alerts_file": str(root / "alerts.json"), "retries": 0,
            "sources": [
                {"id": "a", "name": "Host A", "adapter": "arcgis_layer", "url": "https://a.example/0"},
                {"id": "b", "name": "Host B", "adapter": "arcgis_layer", "url": "https://b.example/0"},
            ]}


class Killed(BaseException):
    """Stands in for the container being killed: escapes every handler."""


def _later(seconds):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)).isoformat()


class EmbargoTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / "store").mkdir()
        self.storage = LocalStorage(self.root / "store")

    def tearDown(self):
        self._td.cleanup()

    def embargo(self):
        path = self.root / "store" / cloud_job.RATE_LIMIT_EMBARGO
        return json.loads(path.read_text(encoding="utf-8"))["rate_limits"] if path.is_file() else {}

    def run_job(self, workdir: Path, behavior):
        workdir.mkdir(parents=True, exist_ok=True)
        config = _config(workdir)
        calls = []

        def check(source, _timeout):
            calls.append(source["id"])
            return behavior(source)

        cloud_job._apply_embargo(self.storage, Path(config["state_file"]), workdir)
        with patch.object(watch, "_source_check", side_effect=check):
            try:
                watch.check_sources(config, save=True,
                                    rate_limit_sink=cloud_job._embargo_sink(self.storage, workdir))
            except Killed:
                pass
        return calls

    def test_killed_container_still_leaves_the_embargo_for_the_next_job(self):
        def first(source):
            if source["id"] == "a":
                raise watch.ProviderRateLimitError("86400", "a.example")
            raise Killed()

        self.assertEqual(self.run_job(self.root / "job1", first), ["a", "b"])
        # The first job's workdir and state are lost with the container.
        self.assertIn("a.example", self.embargo())

        def healthy(source):
            return {"status": "ok", "summary": "ok"}

        # A fresh job never contacts the embargoed host.
        self.assertEqual(self.run_job(self.root / "job2", healthy), ["b"])

    def test_embargo_write_failure_stops_the_run(self):
        calls = []

        def check(source, _timeout):
            calls.append(source["id"])
            raise watch.ProviderRateLimitError("60", "a.example")

        def broken(_rate_limits):
            raise OSError("bucket unavailable")

        config = _config(self.root)
        with patch.object(watch, "_source_check", side_effect=check), \
                self.assertRaises(watch.RateLimitPersistenceError):
            watch.check_sources(config, save=True, rate_limit_sink=broken)
        self.assertEqual(calls, ["a"])

    def test_unreadable_embargo_fails_closed(self):
        (self.root / "store" / cloud_job.RATE_LIMIT_EMBARGO).write_text("[]", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            cloud_job._apply_embargo(self.storage, self.root / "state.json", self.root)

    def test_concurrent_writers_keep_both_hosts(self):
        sink = cloud_job._embargo_sink(self.storage, self.root)
        original = self.storage.upload_if_version
        raced = []

        def racing(name, source, version):
            if not raced:
                raced.append(True)
                # Another job writes its own backoff between our read and write.
                other = self.root / "other.json"
                other.write_text(json.dumps({"schema_version": 1, "rate_limits": {
                    "b.example": {"not_before": _later(600)}}}), encoding="utf-8")
                original(name, other, version)
            return original(name, source, version)

        with patch.object(self.storage, "upload_if_version", side_effect=racing):
            sink({"a.example": {"not_before": _later(600)}})
        self.assertEqual(set(self.embargo()), {"a.example", "b.example"})

    def test_merge_keeps_the_longer_and_held_backoffs_and_drops_expired_ones(self):
        short, long_ = _later(60), _later(3600)
        merged = cloud_job._merge_backoffs(
            {"a": {"not_before": short}, "h": {"not_before": short, "hold_until_cleared": True}},
            {"a": {"not_before": long_}, "h": {"not_before": long_}},
        )
        self.assertEqual(merged["a"]["not_before"], long_)
        self.assertTrue(merged["h"]["hold_until_cleared"])
        path = self.root / "store" / cloud_job.RATE_LIMIT_EMBARGO
        path.write_text(json.dumps({"rate_limits": {"old": {"not_before": _later(-60)}}}), encoding="utf-8")
        active, _version = cloud_job._read_embargo(self.storage, self.root / "copy.json")
        self.assertEqual(active, {})

    def test_conflict_exhaustion_is_reported(self):
        sink = cloud_job._embargo_sink(self.storage, self.root)
        with patch.object(self.storage, "upload_if_version", side_effect=StorageConflictError("busy")), \
                self.assertRaises(StorageConflictError):
            sink({"a.example": {"not_before": _later(60)}})


if __name__ == "__main__":
    unittest.main()
