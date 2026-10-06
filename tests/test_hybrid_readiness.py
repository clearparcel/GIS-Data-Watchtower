import datetime as dt
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch.aggregate import merge_states, publish_partial, with_freshness
from clearparcel.datawatch.storage import GCSStorage, LocalStorage, StorageConflictError


def _fake_gcs_backend():
    """Build a GCSStorage instance backed by an in-memory fake bucket.

    Bypasses GCSStorage.__init__ (which requires the optional google-cloud-storage
    dependency) so the real download_versioned/upload_if_version generation-precondition
    logic can be exercised in CI without that dependency installed. A lock makes the
    conditional write atomic, mirroring GCS server-side precondition enforcement -
    without it, two threads could both read generation 0 and both "succeed", which
    would hide the exact race this test is meant to catch.
    """
    exceptions_mod = types.ModuleType("google.api_core.exceptions")

    class NotFound(Exception):
        pass

    class PreconditionFailed(Exception):
        pass

    exceptions_mod.NotFound = NotFound
    exceptions_mod.PreconditionFailed = PreconditionFailed

    class FakeBlob:
        def __init__(self, bucket, name):
            self._bucket = bucket
            self._name = name

        def reload(self, client=None):
            if self._name not in self._bucket.objects:
                raise NotFound(self._name)

        @property
        def generation(self):
            return self._bucket.objects[self._name]["generation"]

        def download_to_filename(self, path, if_generation_match=None):
            with self._bucket.lock:
                current = self._bucket.objects.get(self._name)
                if current is None:
                    raise NotFound(self._name)
                if if_generation_match is not None and if_generation_match != current["generation"]:
                    raise PreconditionFailed(self._name)
                Path(path).write_bytes(current["data"])

        def upload_from_filename(self, path, if_generation_match=None):
            with self._bucket.lock:
                current = self._bucket.objects.get(self._name)
                current_generation = current["generation"] if current else 0
                if if_generation_match is not None and if_generation_match != current_generation:
                    raise PreconditionFailed(self._name)
                self._bucket.objects[self._name] = {"data": Path(path).read_bytes(), "generation": current_generation + 1}

    class FakeBucket:
        def __init__(self):
            self.objects = {}
            self.lock = threading.Lock()

        def blob(self, name):
            return FakeBlob(self, name)

    backend = GCSStorage.__new__(GCSStorage)
    backend.client = object()
    backend.bucket = FakeBucket()
    backend.prefix = ""
    return backend, exceptions_mod


class HybridReadinessTests(unittest.TestCase):
    def test_profile_coverage_preserves_stale_local_worker(self):
        from test_county_profiles import coverage_state, NOW
        from clearparcel.datawatch.county_profiles import compose_county_profiles, county_profile_counts, FreshnessPolicy
        state = coverage_state()
        direct_id = next(sid for sid in state['sources'] if sid != 'statewide')
        state['sources'][direct_id]['worker'] = 'local'
        state['workers'] = {'local': {'last_report_at': '2026-10-01T00:00:00+00:00'}}
        profiles = compose_county_profiles(state, {}, now=NOW, freshness_policy=FreshnessPolicy())
        self.assertEqual(county_profile_counts(profiles)['active'], 70)
        self.assertEqual(profiles[direct_id]['monitoring']['reporting'], 'overdue')
        self.assertEqual(profiles[direct_id]['monitoring']['health'], 'ok')

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

    def test_gcs_generation_precondition_rejects_stale_writes(self):
        backend, exceptions_mod = _fake_gcs_backend()
        with patch.dict(sys.modules, {"google.api_core.exceptions": exceptions_mod}):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                dest = root / "first.json"
                exists, version = backend.download_versioned("aggregate.json", dest)
                self.assertFalse(exists)
                self.assertIsNone(version)
                src = root / "upload.json"
                src.write_text('{"a": 1}', encoding="utf-8")
                backend.upload_if_version("aggregate.json", src, version)
                with self.assertRaises(StorageConflictError):
                    backend.upload_if_version("aggregate.json", src, version)


    def test_local_version_token_hashes_exact_downloaded_snapshot(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = LocalStorage(root / "objects")
            source = root / "objects" / "state.json"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"old-snapshot")
            copied = root / "copied.json"
            exists, version = storage.download_versioned("state.json", copied)
            self.assertTrue(exists)
            source.write_bytes(b"newer-snapshot")
            self.assertEqual(version, hashlib.sha256(copied.read_bytes()).hexdigest())
            self.assertNotEqual(version, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_gcs_versioned_download_rejects_generation_change(self):
        backend, exceptions_mod = _fake_gcs_backend()
        backend.bucket.objects["state.json"] = {"data": b'{"a":1}', "generation": 1}
        original_blob = backend.bucket.blob

        class RacingBlob:
            def __init__(self, inner):
                self.inner = inner
                self.changed = False
            def reload(self, client=None):
                return self.inner.reload(client=client)
            @property
            def generation(self):
                return self.inner.generation
            def download_to_filename(self, path, if_generation_match=None):
                if not self.changed:
                    self.changed = True
                    with backend.bucket.lock:
                        backend.bucket.objects["state.json"] = {"data": b'{"a":2}', "generation": 2}
                return self.inner.download_to_filename(path, if_generation_match=if_generation_match)

        backend.bucket.blob = lambda name: RacingBlob(original_blob(name))
        with patch.dict(sys.modules, {"google.api_core.exceptions": exceptions_mod}):
            with tempfile.TemporaryDirectory() as td:
                dest = Path(td) / "state.json"
                # The first generation-matched read conflicts; the retry obtains
                # generation 2 and returns bytes that match that exact token.
                exists, version = backend.download_versioned("state.json", dest)
                self.assertTrue(exists)
                self.assertEqual(version, 2)
                self.assertEqual(dest.read_bytes(), b'{"a":2}')

    def test_cloud_job_uses_cas_for_all_read_modify_write_artifacts(self):
        from clearparcel.datawatch import cloud_job
        class FakeStorage:
            def __init__(self):
                self.versions = {}
                self.conditional = []
                self.unconditional = []
            def download_versioned(self, name, destination):
                self.versions[name] = 7
                return False, 7
            def upload_if_version(self, name, source, version):
                self.conditional.append((name, version))
            def upload(self, name, source):
                self.unconditional.append(name)
        fake = FakeStorage()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = root / "config.json"
            cfg.write_text(json.dumps({
                "state_file": "data/state.json",
                "history_file": "data/history.jsonl",
                "alerts_file": "data/alerts.json",
                "alerts_text_file": "data/alerts.txt",
                "sources": [],
            }), encoding="utf-8")
            result = {
                "generated_at": "2026-10-04T20:00:00+00:00", "overall": "ok",
                "counts": {"ok": 0, "warn": 0, "error": 0}, "sources": {},
            }
            def fake_check(config, save=True, execution_profile=None):
                for key, content in (
                    ("state_file", "{}"), ("history_file", "{}\n"),
                    ("alerts_file", "{}"), ("alerts_text_file", "ok\n"),
                ):
                    Path(config[key]).parent.mkdir(parents=True, exist_ok=True)
                    Path(config[key]).write_text(content, encoding="utf-8")
                return result
            with patch.object(cloud_job, "backend_from_env", return_value=fake),                  patch.object(cloud_job, "check_sources", side_effect=fake_check),                  patch.object(cloud_job, "publish_worker_result", return_value=None),                  patch.dict(os.environ, {"WATCHTOWER_WORKDIR": str(root / "work")}, clear=False):
                cloud_job.run_cloud_job(cfg)
        self.assertFalse(fake.unconditional)
        self.assertEqual({name for name, _ in fake.conditional}, {"state.json","history.jsonl","alerts.json","alerts.txt"})
        self.assertTrue(all(version == 7 for _, version in fake.conditional))

    def test_competing_gcs_publishers_preserve_both_workers(self):
        backend, exceptions_mod = _fake_gcs_backend()
        with patch.dict(sys.modules, {"google.api_core.exceptions": exceptions_mod}):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                errors = []
                barrier = threading.Barrier(2)

                def run(worker, source):
                    try:
                        barrier.wait()
                        publish_partial(
                            backend, "aggregate.json",
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
                final = json.loads(backend.bucket.objects["aggregate.json"]["data"].decode("utf-8"))
                self.assertEqual(set(final["sources"]), {"cloud-source", "local-source"})
                self.assertEqual(set(final["workers"]), {"cloud", "local"})

    def test_publish_worker_result_is_opt_in_and_cloud_neutral(self):
        """A normal profiled check should be able to publish without a one-off script,
        but only when a shared aggregate object is actually configured."""
        from clearparcel.datawatch.cloud_job import publish_worker_result
        result = {
            "generated_at": "2026-10-04T20:00:00+00:00", "overall": "ok",
            "counts": {"ok": 1, "warn": 0, "error": 0},
            "sources": {"local-source": {"id": "local-source", "status": "ok"}},
        }
        env_keys = ("WATCHTOWER_AGGREGATE_OBJECT", "WATCHTOWER_STORAGE", "WATCHTOWER_STORAGE_ROOT", "WATCHTOWER_WORKDIR")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = {"state_file": str(root / "state.json"), "_root_dir": str(root)}
            with patch.dict(os.environ, {}, clear=False):
                for key in env_keys:
                    os.environ.pop(key, None)
                self.assertIsNone(publish_worker_result(config, result, "local"))
            self.assertFalse((root / "aggregate-state.json").exists())

            config["aggregate_object"] = "aggregate-state.json"
            with patch.dict(os.environ, {}, clear=False):
                for key in env_keys:
                    os.environ.pop(key, None)
                merged = publish_worker_result(config, result, "local")
            self.assertEqual(set(merged["sources"]), {"local-source"})
            self.assertEqual(merged["sources"]["local-source"]["worker"], "local")
            published = json.loads((root / "aggregate-state.json").read_text(encoding="utf-8"))
            self.assertEqual(set(published["workers"]), {"local"})

    def test_default_staleness_threshold_tolerates_documented_daily_cadence(self):
        """The default threshold must not flag a normal once-daily check as overdue;
        the project's own provider-compliance guidance recommends daily/multi-hour cadences."""
        now = dt.datetime(2026, 10, 4, 20, 0, tzinfo=dt.timezone.utc)
        checked_23_hours_ago = (now - dt.timedelta(hours=23)).isoformat()
        state = {
            "workers": {"local": {"last_success_at": checked_23_hours_ago}},
            "sources": {"a": {"status": "ok", "worker": "local", "last_success_at": checked_23_hours_ago}},
        }
        result = with_freshness(state, now=now)
        self.assertFalse(result["workers"]["local"]["stale"])
        self.assertFalse(result["sources"]["a"]["stale"])

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


    def test_statewide_exports_include_all_aggregate_sources(self):
        from clearparcel.datawatch import dashboard
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            aggregate = root / "aggregate.json"
            aggregate.write_text(json.dumps({
                "generated_at": "2026-10-04T20:00:00+00:00",
                "overall": "ok",
                "workers": {"cloud": {"last_success_at": "2026-10-04T20:00:00+00:00"}},
                "sources": {
                    "county-source": {"id": "county-source", "name": "County Source", "county_slug": "aitkin", "status": "ok", "worker": "cloud", "last_success_at": "2026-10-04T20:00:00+00:00"},
                    "statewide-source": {"id": "statewide-source", "name": "Statewide Source", "status": "ok", "worker": "cloud", "last_success_at": "2026-10-04T20:00:00+00:00"},
                },
            }), encoding="utf-8")
            config = {"state_file": str(root / "unused.json"), "aggregate_state_file": str(aggregate), "sources": []}
            snapshot = dashboard._statewide_snapshot(config)
            self.assertEqual(len(snapshot["counties"]), 87)
            self.assertTrue(all("parcel_source_profile" in row for row in snapshot["counties"]))
            self.assertEqual(snapshot["source_count"], 2)
            self.assertEqual({x["id"] for x in snapshot["sources"]}, {"county-source", "statewide-source"})
            csv_text = dashboard._snapshot_csv(snapshot)
            self.assertIn("source_id,source_name,county,status,feature_count,worker,reporting", csv_text)
            self.assertIn("county-source", csv_text)
            self.assertIn("statewide-source", csv_text)
            raw = dashboard._snapshot_xlsx(snapshot)
            import io, zipfile
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                source_xml = zf.read("xl/worksheets/sheet2.xml").decode("utf-8")
                workbook = zf.read("xl/workbook.xml").decode("utf-8")
                self.assertIn("County Access", workbook)
                self.assertIn("Parcel Sources", workbook)
            self.assertIn("County Source", source_xml)
            self.assertIn("Statewide Source", source_xml)
            self.assertIn("Worker", source_xml)
            self.assertIn("Stale source", source_xml)


if __name__ == "__main__":
    unittest.main()
