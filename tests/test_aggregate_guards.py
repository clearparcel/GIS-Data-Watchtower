"""Regression tests for shared-state integrity guards (review package 2).

Covers: empty and shrunken fleet reports, filtered reports and worker health,
future-dated reports, state-file robustness, the container's fail-closed
placeholder guard, and smaller correctness fixes.
"""
import datetime as dt
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import aggregate, cloud_job, watch
from clearparcel.datawatch.aggregate import merge_states, with_freshness
from clearparcel.datawatch.file_lock import atomic_write
from clearparcel.datawatch.hybrid_validation import candidate_manifest, validation_receipt
from clearparcel.datawatch.public_projection import sanitize_public_render_state

NOW = dt.datetime(2026, 10, 13, 12, 0, tzinfo=dt.timezone.utc)
# Merge clock for tests that are not about skew: after every fixture report.
LATER = NOW + dt.timedelta(hours=1)


def stamp(minutes=0):
    return (NOW + dt.timedelta(minutes=minutes)).isoformat()


def report(minutes, sources, scope="fleet", **extra):
    return {"generated_at": stamp(minutes), "overall": "ok", "scope": {"type": scope},
            "counts": {"ok": len(sources), "warn": 0, "error": 0},
            "sources": {sid: {"id": sid, "status": "ok", "checked_at": stamp(minutes)} for sid in sources}, **extra}


def _ok(source, timeout):
    return {"feature_count": 1, "problems": []}


class IsolatedEnv(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in list(os.environ):
            if name.startswith(("WATCHTOWER_", "CLEARPARCEL_WATCHTOWER_")):
                os.environ.pop(name, None)

    def config(self, sources):
        return {"state_file": str(self.root / "state.json"), "history_file": str(self.root / "history.jsonl"),
                "retries": 0, "sources": sources}


class EmptyRunTests(IsolatedEnv):
    sources = [{"id": "a", "name": "A", "adapter": "arcgis_layer", "url": "https://gis.example.gov/0",
                "execution_profiles": ["cloud"]}]

    def test_run_that_matches_no_sources_is_an_error_and_saves_nothing(self):
        config = self.config(self.sources)
        with patch.object(watch, "_source_check", side_effect=_ok):
            watch.check_sources(config, execution_profile="cloud")
        before = (self.root / "state.json").read_bytes()
        with patch.object(watch, "_source_check", side_effect=_ok) as check:
            result = watch.check_sources(config, execution_profile="local")  # nothing assigned to local
        check.assert_not_called()
        self.assertEqual(result["scope"], {"type": "empty"})
        self.assertEqual(result["overall"], "error")
        self.assertIn("local", result["error"])
        self.assertEqual((self.root / "state.json").read_bytes(), before)

    def test_empty_report_is_never_merged_or_published(self):
        with self.assertRaisesRegex(ValueError, "checked no sources"):
            merge_states({}, report(0, [], scope="empty"), "cloud", now=NOW)
        with patch.dict(os.environ, {"WATCHTOWER_AGGREGATE_OBJECT": "aggregate.json"}), \
                patch.object(cloud_job, "publish_partial") as publish:
            self.assertIsNone(cloud_job.publish_worker_result({}, {"scope": {"type": "empty"}}, "cloud"))
        publish.assert_not_called()

    def test_cloud_job_uploads_and_publishes_nothing_after_an_empty_run(self):
        cfg = self.root / "config.json"
        cfg.write_text(json.dumps({"state_file": "data/state.json", "history_file": "data/history.jsonl",
                                   "sources": self.sources}), encoding="utf-8")

        class Storage:
            def __init__(self):
                self.uploads = []

            def download_versioned(self, name, path):
                return False, None

            def upload_if_version(self, name, path, version):
                self.uploads.append(name)

        storage = Storage()
        os.environ.update({"WATCHTOWER_WORKDIR": str(self.root / "work"), "WATCHTOWER_EXECUTION_PROFILE": "local"})
        with patch.object(cloud_job, "backend_from_env", return_value=storage), \
                patch.object(cloud_job, "publish_worker_result") as publish, \
                patch.object(watch, "_source_check", side_effect=_ok):
            result = cloud_job.run_cloud_job(cfg)
        self.assertEqual(result["scope"], {"type": "empty"})
        self.assertEqual(storage.uploads, [])
        publish.assert_not_called()

    def test_cli_empty_run_exits_2_explains_why_and_publishes_nothing(self):
        import contextlib, io
        from clearparcel.datawatch import cli
        cfg = self.root / "config.json"
        cfg.write_text(json.dumps(self.config(self.sources)), encoding="utf-8")
        out = io.StringIO()
        with patch.object(watch, "_source_check", side_effect=_ok), \
                patch("clearparcel.datawatch.cloud_job.publish_partial") as publish, \
                patch.dict(os.environ, {"WATCHTOWER_AGGREGATE_OBJECT": "aggregate.json"}), \
                patch("sys.argv", ["watchtower", "--config", str(cfg), "check", "--execution-profile", "local"]), \
                contextlib.redirect_stdout(out):
            code = cli.main()
        self.assertEqual(code, 2)
        self.assertIn("Run error: no configured sources matched execution profile 'local'", out.getvalue())
        publish.assert_not_called()

    def test_aggregate_cli_refuses_an_empty_report(self):
        import contextlib, io
        from clearparcel.datawatch import cli
        base, part, out = self.root / "base.json", self.root / "part.json", self.root / "out.json"
        base.write_text("{}", encoding="utf-8")
        part.write_text(json.dumps(report(-5, [], scope="empty")), encoding="utf-8")
        cfg = self.root / "config.json"
        cfg.write_text(json.dumps(self.config([])), encoding="utf-8")
        with patch("sys.argv", ["watchtower", "--config", str(cfg), "aggregate", "--base", str(base),
                                "--partial", str(part), "--worker", "cloud", "--output", str(out)]), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(), cli.EXIT_TOOL_FAILURE)  # refused input, nothing written
        self.assertFalse(out.exists())

    def test_explicit_drain_produces_a_fleet_report_that_may_retire(self):
        os.environ["WATCHTOWER_ALLOW_INVENTORY_SHRINK"] = "1"
        with patch.object(watch, "_source_check", side_effect=_ok):
            result = watch.check_sources(self.config(self.sources), execution_profile="local")
        self.assertEqual(result["scope"], {"type": "fleet"})
        self.assertTrue(result["allow_inventory_shrink"])


class ShrinkGuardTests(unittest.TestCase):
    def owned(self, n):
        return merge_states({}, report(0, [f"s{i}" for i in range(n)]), "cloud", now=LATER)

    def test_sharply_shrunken_fleet_report_does_not_retire_inventory(self):
        state = merge_states(self.owned(35), report(10, ["s0"]), "cloud", now=LATER)
        self.assertEqual(len(state["sources"]), 35)
        self.assertEqual(state["retired_sources"], {})
        self.assertEqual(state["workers"]["cloud"]["inventory_shrink_refused"], 34)

    def test_ordinary_retirement_still_works(self):
        state = merge_states(self.owned(35), report(10, [f"s{i}" for i in range(34)]), "cloud", now=LATER)
        self.assertEqual(len(state["sources"]), 34)
        self.assertIn("s34", state["retired_sources"])
        self.assertNotIn("inventory_shrink_refused", state["workers"]["cloud"])

    def test_explicit_allowance_permits_a_large_shrink(self):
        state = merge_states(self.owned(35), report(10, ["s0"], allow_inventory_shrink=True), "cloud", now=LATER)
        self.assertEqual(set(state["sources"]), {"s0"})

    def test_unrelated_or_renamed_ids_do_not_count_as_coverage(self):
        state = merge_states({}, report(0, ["l1", "l2", "l3", "l4"]), "local", now=LATER)
        state = merge_states(state, report(1, [f"c{i}" for i in range(31)]), "cloud", now=LATER)
        # The local worker runs against the wrong registry: cloud IDs plus renamed IDs.
        wrong = report(10, [f"c{i}" for i in range(31)] + ["x1", "x2"])
        state = merge_states(state, wrong, "local", now=LATER)
        self.assertTrue({"l1", "l2", "l3", "l4"} <= set(state["sources"]))
        self.assertEqual(state["workers"]["local"]["inventory_shrink_refused"], 4)

    def test_deliberately_skipped_sources_count_as_covered_and_retire(self):
        state = merge_states({}, report(0, ["a", "b", "c", "d"]), "local", now=LATER)
        parked = report(10, ["a"], skipped_sources={"b": "disabled", "c": "disabled", "d": "execution-profile"})
        state = merge_states(state, parked, "local", now=LATER)
        self.assertEqual(set(state["sources"]), {"a"})
        self.assertNotIn("inventory_shrink_refused", state["workers"]["local"])

    def test_unresolved_profile_skips_do_not_count_as_covered(self):
        state = merge_states({}, report(0, ["a", "b", "c", "d"]), "local", now=LATER)
        partial = report(10, ["a"], skipped_sources={"b": "execution-profile-unresolved",
                                                     "c": "execution-profile-unresolved", "d": "x"})
        state = merge_states(state, partial, "local", now=LATER)
        self.assertEqual(len(state["sources"]), 4)

    def test_filtered_report_does_not_clear_a_refused_shrink(self):
        state = merge_states(self.owned(10), report(5, ["s0"]), "cloud", now=LATER)
        state = merge_states(state, report(10, ["s0"], scope="source"), "cloud", now=LATER)
        self.assertEqual(state["workers"]["cloud"]["inventory_shrink_refused"], 9)

    def test_other_workers_sources_are_never_counted_or_retired(self):
        state = merge_states(self.owned(2), report(5, ["l0", "l1", "l2"]), "local", now=LATER)
        state = merge_states(state, report(10, ["s0"]), "cloud", now=LATER)
        self.assertTrue({"l0", "l1", "l2"} <= set(state["sources"]))
        self.assertNotIn("s1", state["sources"])  # 1 of 2 owned is >= 50%: retirement allowed


class WorkerHealthTests(unittest.TestCase):
    def test_filtered_report_keeps_fleet_level_worker_health(self):
        full = report(0, ["a", "b", "c"])
        full["overall"] = "warn"
        full["counts"] = {"ok": 2, "warn": 1, "error": 0}
        state = merge_states({}, full, "cloud", now=LATER)
        before = dict(state["workers"]["cloud"])
        state = merge_states(state, report(10, ["a"], scope="source"), "cloud", now=LATER)
        worker = state["workers"]["cloud"]
        for key in ("overall", "counts", "source_count", "last_success_at", "checked_at"):
            self.assertEqual(worker.get(key), before.get(key), key)
        self.assertEqual(worker["last_report_at"], stamp(10))
        self.assertEqual(worker["last_partial_report_at"], stamp(10))
        self.assertEqual(state["sources"]["a"]["checked_at"], stamp(10))  # the source itself still updates

    def test_first_report_from_a_worker_may_be_filtered(self):
        state = merge_states({}, report(0, ["a"], scope="source"), "cloud", now=LATER)
        self.assertEqual(state["workers"]["cloud"]["source_count"], 1)


class ClockSkewTests(unittest.TestCase):
    def test_future_dated_report_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "future"):
            merge_states({}, report(60, ["a"]), "cloud", now=NOW)

    def test_small_skew_is_tolerated_and_does_not_block_later_reports(self):
        state = merge_states({}, report(4, ["a"]), "cloud", now=NOW)
        later = NOW + dt.timedelta(minutes=10)
        state = merge_states(state, report(9, ["a"]), "cloud", now=later)
        self.assertEqual(state["workers"]["cloud"]["last_report_at"], stamp(9))

    def test_naive_now_is_treated_as_utc(self):
        state = merge_states({}, report(0, ["a"]), "cloud", now=NOW.replace(tzinfo=None))
        self.assertIn("a", state["sources"])
        with_freshness(state, now=NOW.replace(tzinfo=None))

    def test_freshness_flags_future_observations(self):
        state = {"workers": {"cloud": {"last_report_at": stamp(60)}}, "sources": {}}
        fresh = with_freshness(state, now=NOW)
        self.assertTrue(fresh["workers"]["cloud"]["clock_skew"])
        self.assertFalse(with_freshness({"workers": {"cloud": {"last_report_at": stamp(-5)}}}, now=NOW)["workers"]["cloud"]["clock_skew"])


class StateFileTests(IsolatedEnv):
    def test_undecodable_primary_state_recovers_from_backup(self):
        path = self.root / "state.json"
        path.write_bytes(b'{"sources": {"a": "\xff\xfe'),
        path.with_suffix(".json.bak").write_text('{"sources": {"a": {}}}', encoding="utf-8")
        state = watch.load_state(path)
        self.assertTrue(state["_state_recovered_from_backup"])
        self.assertIn("a", state["sources"])

    def test_save_keeps_previous_file_as_backup_and_leaves_no_scratch(self):
        path = self.root / "state.json"
        watch._save_json(path, {"v": 1})
        watch._save_json(path, {"v": 2})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"v": 2})
        self.assertEqual(json.loads(path.with_suffix(".json.bak").read_text(encoding="utf-8")), {"v": 1})
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["state.json", "state.json.bak"])

    def test_unserializable_value_leaves_existing_state_intact(self):
        path = self.root / "state.json"
        watch._save_json(path, {"v": 1})
        with self.assertRaises(TypeError):
            watch._save_json(path, {"v": object()})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"v": 1})

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_atomic_write_preserves_existing_mode_and_keeps_new_files_private(self):
        new = self.root / "new.json"
        atomic_write(new, b"{}")
        self.assertEqual(stat.S_IMODE(new.stat().st_mode), 0o600)
        existing = self.root / "existing.json"
        existing.write_bytes(b"{}")
        os.chmod(existing, 0o640)
        atomic_write(existing, b"{}")
        self.assertEqual(stat.S_IMODE(existing.stat().st_mode), 0o640)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_backup_inherits_the_primary_mode(self):
        path = self.root / "state.json"
        watch._save_json(path, {"v": 1})
        os.chmod(path, 0o600)
        watch._save_json(path, {"v": 2})
        self.assertEqual(stat.S_IMODE(path.with_suffix(".json.bak").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_unreadable_primary_never_overwrites_a_good_backup(self):
        path = self.root / "state.json"
        path.write_bytes(b"{truncated")
        backup = path.with_suffix(".json.bak")
        backup.write_text('{"v": 1}', encoding="utf-8")
        watch._save_json(path, {"v": 2})
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), {"v": 1})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"v": 2})


class PlaceholderConfigTests(IsolatedEnv):
    def test_repository_example_config_is_a_placeholder(self):
        example = json.loads((Path(__file__).resolve().parents[1] / "config" / "example_sources.json").read_text(encoding="utf-8"))
        self.assertTrue(cloud_job.is_placeholder_config(example))
        self.assertFalse(cloud_job.is_placeholder_config({"sources": []}))
        self.assertFalse(cloud_job.is_placeholder_config({"sources": [{"url": "https://example.com/a"},
                                                                      {"url": "https://gis.co.example.mn.us/b"}]}))
        self.assertFalse(cloud_job.is_placeholder_config({"sources": [{"url": "https://notexample.com/a"}]}))

    def test_cloud_job_refuses_placeholder_config_unless_explicitly_allowed(self):
        cfg = Path(__file__).resolve().parents[1] / "config" / "example_sources.json"
        with patch.object(cloud_job, "backend_from_env") as backend:
            with self.assertRaisesRegex(RuntimeError, "placeholder"):
                cloud_job.run_cloud_job(cfg)
        backend.assert_not_called()


class SmallFixTests(unittest.TestCase):
    def test_optional_metric_diagnostics_do_not_change_the_fingerprint(self):
        a = {"feature_count": 5, "parcel_id_null_check_error": "timeout", "null_geometry_check_error": "x"}
        b = {"feature_count": 5, "parcel_id_null_check_error": "reset", "null_geometry_check_error": "y"}
        self.assertEqual(watch._observation_fingerprint(a), watch._observation_fingerprint(b))

    def test_nested_observed_at_does_not_change_the_fingerprint(self):
        a = {"feature_count": 5, "gac_completeness": {"percent": 50.0, "observed_at": stamp(0)}}
        b = {"feature_count": 5, "gac_completeness": {"percent": 50.0, "observed_at": stamp(60)}}
        c = {"feature_count": 5, "gac_completeness": {"percent": 51.0, "observed_at": stamp(60)}}
        self.assertEqual(watch._observation_fingerprint(a), watch._observation_fingerprint(b))
        self.assertNotEqual(watch._observation_fingerprint(a), watch._observation_fingerprint(c))

    def test_parcel_id_null_count_failure_does_not_fail_the_source(self):
        layer = {"fields": [{"name": "PARCEL_ID", "type": "esriFieldTypeString"}], "geometryType": "esriGeometryPolygon"}

        def count(url, where, timeout, prefer_curl=False):
            if "PARCEL_ID IS NULL" in where:
                raise RuntimeError("ArcGIS error: invalid where clause")
            return 0

        with patch.object(watch, "_json_request", return_value=(layer, {"status": 200})), \
                patch.object(watch, "_arcgis_count_query", side_effect=count), \
                patch.object(watch, "_arcgis_duplicate_id_summary", return_value={}), \
                patch.object(watch, "_field_completeness", return_value={}):
            result = watch._arcgis_layer({"url": "https://example.invalid/0", "parcel_quality": True}, 2)
        self.assertIsNone(result["parcel_id_null_count"])
        self.assertEqual(result["parcel_id_null_check"], "unsupported")

    def test_receipt_reports_rather_than_crashes_when_a_gac_check_failed(self):
        manifest = candidate_manifest({"sources": [{"id": "a", "execution_profiles": ["cloud"]}]}, {})
        rep = {"generated_at": stamp(0), "overall": "ok", "scope": {"type": "fleet"},
               "runtime_identity": manifest["runtime_identity"],
               "sources": {"a": {"id": "a", "checked_at": stamp(0), "status": "ok", "gac_completeness": None}}}
        state = merge_states({}, rep, "cloud", now=NOW)
        receipt = validation_receipt(manifest, {"cloud": rep}, state, sanitize_public_render_state(state))
        self.assertIn("GAC metric unavailable: a", receipt["problems"])


if __name__ == "__main__":
    unittest.main()
