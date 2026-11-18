"""Provider controls from the follow-up review of f8f0997 (F02, F03, F04, F13).

F05 (cloud-job slot) is covered in test_dispatch_guard. Offline: synthetic
sources and mocked provider calls only.
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.hybrid_validation import candidate_manifest

NOW = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.timezone.utc)


def _source(**extra) -> dict:
    return {"id": "s", "name": "S", "adapter": "arcgis_layer", "url": "https://gis.example/0", **extra}


class PaddedRetryAfterTests(unittest.TestCase):
    """F02: a long zero-padded Retry-After keeps its full delay."""

    def test_padding_beyond_64_characters_keeps_the_delay(self):
        self.assertEqual(watch._retry_after_seconds("0" * 64 + "172800", NOW), 172800)
        self.assertEqual(watch._retry_after_seconds("0" * 200 + "172800", NOW), 172800)

    def test_padded_value_above_the_cap_becomes_the_maximum(self):
        seconds = watch._retry_after_seconds("0" * 64 + "99999999999", NOW)
        self.assertEqual(seconds, watch._RATE_LIMIT_MAX_SECONDS)

    def test_padded_delays_survive_persistence_and_a_restart(self):
        with patch.object(watch, "_block_hosts"):
            limits = {}
            watch._record_rate_limit(limits, "hold.example", "0" * 64 + "99999999999", "s", 3600)
            watch._record_rate_limit(limits, "two-day.example", "0" * 64 + "172800", "s", 3600)
        self.assertTrue(limits["hold.example"]["hold_until_cleared"])
        entry = limits["two-day.example"]
        wait = (dt.datetime.fromisoformat(entry["not_before"])
                - dt.datetime.fromisoformat(entry["recorded_at"]))
        self.assertEqual(wait, dt.timedelta(seconds=172800))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            path.write_text(json.dumps({"schema_version": 1, "sources": {}, "rate_limits": limits}),
                            encoding="utf-8")
            restored = watch.load_state(path)["rate_limits"]
        later = dt.datetime.fromisoformat(entry["recorded_at"]) + dt.timedelta(hours=47)
        active = watch._active_rate_limits(restored, later)
        self.assertIn("two-day.example", active)
        self.assertIn("hold.example", active)

    def test_long_non_numeric_text_uses_the_default(self):
        self.assertEqual(watch._retry_after_seconds("x" * 500, NOW), watch._RATE_LIMIT_DEFAULT_SECONDS)


class EnabledFlagTests(unittest.TestCase):
    """F03: only a JSON boolean may set ``enabled``."""

    def test_malformed_flags_are_rejected_before_dispatch(self):
        for value in ("false", "true", 0, 1, None, "", [], {}):
            with self.subTest(value=value), self.assertRaises(watch.InvalidSourceRegistryError):
                watch.validate_source_registry([_source(enabled=value)])

    def test_booleans_and_omission_are_accepted(self):
        for extra in ({}, {"enabled": True}, {"enabled": False}):
            with self.subTest(extra=extra):
                watch.validate_source_registry([_source(**extra)])

    def test_malformed_flag_is_never_read_as_enabled(self):
        for value in ("false", 0, None):
            with self.subTest(value=value):
                self.assertEqual(watch._profile_skip_reason(_source(enabled=value), None), "disabled")
        self.assertIsNone(watch._profile_skip_reason(_source(enabled=True), None))
        self.assertIsNone(watch._profile_skip_reason(_source(), None))
        manifest = candidate_manifest({"sources": [_source(enabled="false", execution_profiles=["cloud"])]})
        self.assertEqual(manifest["expected_sources"]["cloud"], [])

    def test_check_with_stringified_flag_makes_no_request(self):
        with tempfile.TemporaryDirectory() as td:
            config = {"state_file": str(Path(td) / "state.json"), "history_file": str(Path(td) / "h.jsonl"),
                      "sources": [_source(enabled="false")]}
            with patch.object(watch, "_source_check") as check, \
                    self.assertRaises(watch.InvalidSourceRegistryError):
                watch.check_sources(config)
            check.assert_not_called()
            self.assertFalse(watch.has_selected_sources(
                {"sources": [_source(enabled="false")]}, source_filter=None, execution_profile=None))


class LayerNameGuardAdapterTests(unittest.TestCase):
    """F04: the guard follows the canonical adapter and the service's layer selection."""

    def test_legacy_layer_alias_is_accepted(self):
        for adapter in ("arcgis-feature-layer", "arcgis-feature-service", "ArcGIS_Layer"):
            with self.subTest(adapter=adapter):
                watch.validate_source_registry([_source(adapter=adapter, expected_layer_name="Parcels")])
        watch.validate_source_registry([{"id": "s", "name": "S", "kind": "arcgis-map-service",
                                         "url": "https://gis.example/MapServer", "discover_parcel_layer": True,
                                         "expected_layer_name": "Parcels"}])

    def test_service_without_layer_discovery_is_rejected(self):
        for extra in ({}, {"discover_parcel_layer": False}):
            with self.subTest(extra=extra), self.assertRaises(watch.InvalidSourceRegistryError):
                watch.validate_source_registry([_source(adapter="arcgis_service", expected_layer_name="Parcels",
                                                        **extra)])
        with self.assertRaises(watch.InvalidSourceRegistryError):
            watch.validate_source_registry([_source(adapter="arcgis-map-service", expected_layer_name="Parcels")])

    def test_service_discovery_applies_the_guard_to_the_selected_layer(self):
        service = _source(adapter="arcgis_service", url="https://gis.example/MapServer",
                          discover_parcel_layer=True, expected_layer_name="Parcels")
        listing = {"mapName": "Svc", "layers": [{"id": 0, "name": "Tax Parcels"}]}
        layer = {"name": "Roads", "fields": []}
        responses = iter([(listing, {"status": 200}), (layer, {"status": 200})])
        with patch.object(watch, "_json_request", side_effect=lambda *a, **k: next(responses)), \
                self.assertRaises(watch.PermanentProviderError):
            watch._arcgis_service(service, 5)


class NumericThresholdTests(unittest.TestCase):
    """F13: change thresholds must be finite, nonnegative numbers."""

    def test_non_finite_and_non_numeric_thresholds_are_rejected(self):
        for key in ("feature_count_change_percent", "extent_shift_percent"):
            for value in ("NaN", "nan", "inf", float("nan"), float("inf"), -1, "ten", True, [5], {}):
                with self.subTest(key=key, value=value), self.assertRaises(watch.InvalidSourceRegistryError):
                    watch.validate_source_registry([_source(thresholds={key: value})])

    def test_ordinary_thresholds_are_accepted(self):
        for value in (0, 10, 2.5, "10", None):
            with self.subTest(value=value):
                watch.validate_source_registry([_source(thresholds={
                    "feature_count_change_percent": value, "extent_shift_percent": value})])


if __name__ == "__main__":
    unittest.main()
