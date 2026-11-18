"""Provider controls fail closed on malformed input.

Review of ff9f9a7, findings 05, 06, 09, 14, 17, 24 and 25 (28 is covered in
test_dispatch_guard). Offline: synthetic sources, temporary local storage and
mocked provider calls only.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import cli, cloud_job, watch
from clearparcel.datawatch.storage import LocalStorage

NOW = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.timezone.utc)


def _source(**extra) -> dict:
    return {"id": "s", "name": "S", "adapter": "arcgis_layer", "url": "https://gis.example/0", **extra}


class ExecutionProfileValidationTests(unittest.TestCase):
    """05: execution_profiles must be a list of exact profile names."""

    def test_malformed_profiles_are_rejected_before_dispatch(self):
        for value in ("cloudy", "cloud", 5, ["cloudy"], ["Cloud"], [None], {"cloud": True}):
            with self.subTest(value=value), self.assertRaises(watch.InvalidSourceRegistryError):
                watch.validate_source_registry([_source(execution_profiles=value)])

    def test_supported_and_legacy_assignments_are_accepted(self):
        for value in (["cloud"], ["local"], ["any"], ["cloud", "local"], [], None):
            with self.subTest(value=value):
                watch.validate_source_registry([_source(execution_profiles=value)])
        watch.validate_source_registry([_source()])  # unassigned legacy entry

    def test_check_refuses_a_string_profile_without_a_request(self):
        with tempfile.TemporaryDirectory() as td:
            config = {"state_file": str(Path(td) / "state.json"), "history_file": str(Path(td) / "h.jsonl"),
                      "sources": [_source(execution_profiles="cloudy")]}
            with patch.object(watch, "_source_check") as check, \
                    self.assertRaises(watch.InvalidSourceRegistryError):
                watch.check_sources(config, execution_profile="cloud")
            check.assert_not_called()


class DamagedBackoffTests(unittest.TestCase):
    """06: a damaged stored backoff never releases its host."""

    def test_hold_with_unreadable_deadline_stays_active(self):
        active = watch._active_rate_limits(
            {"held.example": {"hold_until_cleared": True, "not_before": "garbage"}}, NOW)
        self.assertTrue(active["held.example"]["hold_until_cleared"])

    def test_damaged_entry_beside_a_valid_one(self):
        later = (NOW + dt.timedelta(hours=2)).isoformat()
        active = watch._active_rate_limits({"ok.example": {"not_before": later},
                                            "bad.example": {"not_before": "tomorrow"},
                                            "worse.example": "not an object"}, NOW)
        self.assertEqual(active["ok.example"]["not_before"], later)
        for host in ("bad.example", "worse.example"):
            self.assertTrue(active[host]["hold_until_cleared"])
            self.assertTrue(active[host]["invalid_backoff"])

    def test_restart_with_only_the_shared_embargo_keeps_the_hold(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = LocalStorage(root / "store")
            embargo = root / "embargo.json"
            embargo.write_text(json.dumps({"schema_version": 1, "rate_limits": {
                "held.example": {"hold_until_cleared": True, "not_before": "garbage"},
                "bad.example": {"not_before": None}}}), encoding="utf-8")
            storage.upload_if_version(cloud_job.RATE_LIMIT_EMBARGO, embargo, None)
            active, _version = cloud_job._read_embargo(storage, root / "read.json")
        self.assertEqual(set(active), {"held.example", "bad.example"})
        self.assertTrue(all(entry["hold_until_cleared"] for entry in active.values()))


class RetryAfterTests(unittest.TestCase):
    """09: any number of digits is valid delta-seconds."""

    def test_padded_and_long_durations(self):
        self.assertEqual(watch._retry_after_seconds("00000086400", NOW), 86400)
        self.assertEqual(watch._retry_after_seconds("0", NOW), watch._RATE_LIMIT_MIN_SECONDS)
        self.assertEqual(watch._retry_after_seconds("99999999999", NOW), watch._RATE_LIMIT_MAX_SECONDS)
        self.assertEqual(watch._retry_after_seconds("12x", NOW), watch._RATE_LIMIT_DEFAULT_SECONDS)

    def test_a_duration_above_the_cap_records_an_operator_hold(self):
        limits = {}
        with patch.object(watch, "_block_hosts"):
            watch._record_rate_limit(limits, "h.example", "0" + "9" * 20, "s", 3600)
        self.assertTrue(limits["h.example"]["hold_until_cleared"])


class LayerNameGuardTests(unittest.TestCase):
    """14: the layer-name guard is refused where it would be ignored."""

    def test_guard_only_on_layer_adapters(self):
        watch.validate_source_registry([_source(adapter="arcgis_layer", expected_layer_name="Parcels")])
        watch.validate_source_registry([_source(adapter="arcgis_service", discover_parcel_layer=True,
                                                expected_layer_name="Parcels")])
        for adapter in ("arcgis_county_catalog", "wms", "http_file"):
            with self.subTest(adapter=adapter), self.assertRaises(watch.InvalidSourceRegistryError):
                watch.validate_source_registry([_source(adapter=adapter, expected_layer_name="Parcels")])
        with self.assertRaises(watch.InvalidSourceRegistryError):
            watch.validate_source_registry([{"id": "s", "kind": "arcgis_county_catalog", "enabled": False,
                                             "expected_layer_name": "Catalog"}])


class RetryDelayTests(unittest.TestCase):
    """17: the retry delay must be finite and bounded before any request."""

    def test_non_finite_or_huge_delay_is_rejected(self):
        for value in ("inf", float("inf"), "nan", "1e309", 3601):
            with self.subTest(value=value), self.assertRaises(watch.InvalidSourceRegistryError):
                watch._validate_dispatch_options({"retry_delay_seconds": value}, "configuration",
                                                 watch._CONFIG_DISPATCH_OPTIONS)
        watch._validate_dispatch_options({"retry_delay_seconds": "2.5"}, "configuration",
                                         watch._CONFIG_DISPATCH_OPTIONS)

    def test_infinite_delay_never_reaches_a_provider(self):
        with tempfile.TemporaryDirectory() as td:
            config = {"state_file": str(Path(td) / "state.json"), "history_file": str(Path(td) / "h.jsonl"),
                      "retry_delay_seconds": "inf", "sources": [_source()]}
            with patch.object(watch, "_source_check") as check, \
                    self.assertRaises(watch.InvalidSourceRegistryError):
                watch.check_sources(config)
            check.assert_not_called()


class BackoffMergeTests(unittest.TestCase):
    """24: merged backoffs compare instants, not text."""

    def test_offsets_compare_as_instants_in_both_orders(self):
        central = {"not_before": "2026-11-18T10:00:00-06:00"}  # 16:00 UTC
        utc = {"not_before": "2026-11-18T11:00:00+00:00"}
        for order in ((central, utc), (utc, central)):
            merged = cloud_job._merge_backoffs({"h": order[0]}, {"h": order[1]})
            self.assertEqual(merged["h"]["not_before"], central["not_before"])

    def test_equivalent_instants_and_holds(self):
        first = {"not_before": "2026-11-18T10:00:00-06:00", "source_id": "a"}
        same = {"not_before": "2026-11-18T16:00:00+00:00", "source_id": "b"}
        self.assertEqual(cloud_job._merge_backoffs({"h": first}, {"h": same})["h"]["source_id"], "a")
        hold = {"not_before": "2026-11-18T09:00:00+00:00", "hold_until_cleared": True}
        for order in ((hold, first), (first, hold)):
            self.assertTrue(cloud_job._merge_backoffs({"h": order[0]}, {"h": order[1]})["h"].get("hold_until_cleared"))

    def test_unreadable_deadline_is_never_shortened_by_a_merge(self):
        bad = {"not_before": "soon"}
        merged = cloud_job._merge_backoffs({"h": bad}, {"h": {"not_before": "2026-11-18T10:00:00+00:00"}})
        self.assertEqual(merged["h"], bad)


class EmptyScopeJsonTests(unittest.TestCase):
    """25: CLI JSON keeps the empty-scope signal for an unmatched filter."""

    def run_check(self, result):
        config = Path(__file__).resolve().parents[1] / "config" / "example_sources.json"
        out = io.StringIO()
        env = {"WATCHTOWER_ALLOW_EXAMPLE_CONFIG": "1", "WATCHTOWER_EXECUTION_PROFILE": "", "WATCHTOWER_RUN_RECEIPTS": "0"}
        with patch.dict(os.environ, env), \
                patch("sys.argv", ["watchtower", "--config", str(config), "check", "--source", "nothing",
                                   "--no-save", "--json"]), \
                patch("clearparcel.datawatch.cli.check_sources", return_value=result), \
                contextlib.redirect_stdout(out):
            code = cli.main()
        return code, json.loads(out.getvalue())

    def test_empty_and_matching_filters(self):
        code, body = self.run_check({"overall": "error", "scope": {"type": "empty"}, "sources": {},
                                     "error": "no configured sources matched source filter 'nothing'"})
        self.assertEqual((code, body["scope"], body["source_filter"]), (cli.EXIT_SOURCE_ERROR, {"type": "empty"}, "nothing"))
        code, body = self.run_check({"overall": "ok", "scope": {"type": "source", "source_id": "nothing"}, "sources": {}})
        self.assertEqual((code, body["scope"]["type"]), (cli.EXIT_OK, "source_filter"))


if __name__ == "__main__":
    unittest.main()
