"""Change detection and quality checks must not report a pass they cannot support.

Review of ff9f9a7, findings 02, 03, 08, 15, 18 and 21. Everything here is
offline: provider calls are mocked and state lives in a temporary directory.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.dashboard_summary import catalog_summary

META = {"status": 200, "transport": "test"}


def _config(root: Path, **extra) -> dict:
    source = {"id": "s", "name": "S", "kind": "arcgis_layer", "url": "https://gis.example/0"}
    source.update(extra)
    return {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
            "retries": 0, "sources": [source]}


def _run(config: dict, outcome) -> dict:
    def check(source, timeout):
        if isinstance(outcome, Exception):
            raise outcome
        return dict(outcome)
    with patch.object(watch, "_source_check", side_effect=check):
        return watch.check_sources(config)


class OutageBaselineTests(unittest.TestCase):
    """02: an outage must not erase the baseline for the next change."""

    def test_schema_and_count_changes_are_detected_after_failed_checks(self):
        with tempfile.TemporaryDirectory() as td:
            config = _config(Path(td), thresholds={"feature_count_change_percent": 10})
            first = _run(config, {"schema_hash": "A", "feature_count": 100, "problems": []})
            observed = first["sources"]["s"]["checked_at"]
            for _ in range(2):  # consecutive failures, each saved and reloaded
                failed = _run(config, RuntimeError("provider unavailable"))
                self.assertEqual(failed["sources"]["s"]["status"], "error")
                self.assertEqual(failed["sources"]["s"]["comparison_baseline"]["schema_hash"], "A")
            result = _run(config, {"schema_hash": "B", "feature_count": 47, "problems": []})
        source = result["sources"]["s"]
        changes = {change["type"]: change for change in source["changes"]}
        self.assertEqual(source["status"], "warn")
        self.assertEqual(changes["schema"]["previous"], "A")
        self.assertEqual(changes["schema"]["severity"], "warn")
        self.assertEqual(changes["feature_count"]["previous"], 100)
        self.assertEqual(changes["feature_count"]["severity"], "warn")
        self.assertEqual(changes["schema"]["previous_observed_at"], observed)
        self.assertNotIn("comparison_baseline", source)

    def test_an_unchanged_recovery_reports_no_change(self):
        with tempfile.TemporaryDirectory() as td:
            config = _config(Path(td))
            _run(config, {"schema_hash": "A", "feature_count": 100, "problems": []})
            _run(config, RuntimeError("provider unavailable"))
            result = _run(config, {"schema_hash": "A", "feature_count": 100, "problems": []})
        self.assertEqual(result["sources"]["s"]["status"], "ok")
        self.assertEqual(result["sources"]["s"]["changes"], [])


class ShortCatalogTests(unittest.TestCase):
    """03: a catalog missing counties is rejected and the complete one is kept."""

    def _catalog(self, root: Path) -> dict:
        return {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"), "retries": 0,
                "sources": [{"id": "mn-parcel-county-catalog", "name": "Catalog", "kind": "arcgis_county_catalog",
                             "url": "https://gis.example/0", "expected_count": 2}]}

    def test_short_catalog_keeps_the_complete_rows_and_observation_time(self):
        complete = {"features": [{"attributes": {"countyname": "Aitkin"}}, {"attributes": {"countyname": "Anoka"}}]}
        short = {"features": [{"attributes": {"countyname": "Anoka"}}]}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = self._catalog(root)
            with patch.object(watch, "_json_request", return_value=(complete, META)):
                first = watch.check_sources(config)
            with patch.object(watch, "_json_request", return_value=(short, META)) as request:
                result = watch.check_sources(config)
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(request.call_count, 1)  # rejected without a retry
        record = result["sources"]["mn-parcel-county-catalog"]
        self.assertEqual(record["status"], "error")
        self.assertIn("returned 1 county records; expected 2", record["error"])
        self.assertEqual(set(record["county_records"]), {"Aitkin", "Anoka"})
        self.assertTrue(record["catalog_retained"])
        self.assertEqual(record["catalog_observed_at"],
                         first["sources"]["mn-parcel-county-catalog"]["catalog_observed_at"])
        self.assertTrue(catalog_summary(state, ["Aitkin", "Anoka"])["retained"])

    def test_short_first_catalog_is_unavailable(self):
        short = {"features": [{"attributes": {"countyname": "Anoka"}}]}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(watch, "_json_request", return_value=(short, META)):
                watch.check_sources(self._catalog(root))
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        summary = catalog_summary(state, ["Aitkin", "Anoka"])
        self.assertFalse(summary["retained"])
        self.assertEqual(summary["buckets"]["Catalog unavailable"], 2)

    def test_fresh_catalog_with_rows_and_an_error_is_not_called_retained(self):
        state = {"sources": {"mn-parcel-county-catalog": {
            "status": "error", "catalog_retained": False, "county_records": {"Anoka": {}}}}}
        self.assertFalse(catalog_summary(state, ["Anoka"])["retained"])


class ErrorSeverityTests(unittest.TestCase):
    """08: a change configured as an error fails the source, alert and exit status."""

    def test_error_severity_schema_change_fails_the_source(self):
        with tempfile.TemporaryDirectory() as td:
            config = _config(Path(td), thresholds={"schema_change_severity": "error"})
            _run(config, {"schema_hash": "A", "problems": []})
            result = _run(config, {"schema_hash": "B", "problems": []})
        source = result["sources"]["s"]
        self.assertEqual(source["status"], "error")
        self.assertEqual(result["overall"], "error")
        self.assertIn("schema/capability fingerprint changed", source["problems"])
        self.assertEqual([alert["severity"] for alert in result["active_alerts"]], ["error"])
        self.assertIn("schema/capability fingerprint changed", result["active_alerts"][0]["message"])

    def test_unsupported_severity_is_rejected_before_any_request(self):
        for key, value in (("schema_change_severity", "critical"), ("extent_change_severity", "WARN"),
                           ("schema_change_severity", None)):
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as td:
                config = _config(Path(td), thresholds={key: value})
                with patch.object(watch, "_source_check") as check, \
                        self.assertRaises(watch.InvalidSourceRegistryError):
                    watch.check_sources(config)
                check.assert_not_called()
        with self.assertRaises(watch.InvalidSourceRegistryError):
            watch.validate_source_registry([{"id": "s", "name": "S", "url": "https://gis.example/0",
                                             "adapter": "arcgis_layer", "thresholds": ["warn"]}])


class ParcelSublayerSchemaTests(unittest.TestCase):
    """15: a parcel sublayer schema change keeps its configured warning."""

    def test_sublayer_change_warns_with_or_without_a_count_change(self):
        listing = {"schema_hash": "listing", "parcel_layer_id": 3, "problems": []}
        for count in (100, 90):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as td:
                config = _config(Path(td), kind="arcgis_service")
                _run(config, {**listing, "parcel_schema_hash": "fields-A", "feature_count": 100})
                result = _run(config, {**listing, "parcel_schema_hash": "fields-B", "feature_count": count})
                source = result["sources"]["s"]
                changes = {change["type"]: change for change in source["changes"]}
                self.assertEqual(source["status"], "warn")
                self.assertEqual(changes["parcel_schema"]["severity"], "warn")
                self.assertEqual(changes["parcel_schema"]["message"], "parcel layer schema fingerprint changed")

    def test_renumbered_sublayer_names_both_layers(self):
        previous = {"parcel_schema_hash": "A", "parcel_layer_id": 3}
        changes = watch._compare(previous, {"parcel_schema_hash": "B", "parcel_layer_id": 4}, {})
        self.assertIn("(layer 3 -> 4)", changes[0]["message"])


class SpatialReferenceTests(unittest.TestCase):
    """18: a configured WKID the layer no longer reports is never a pass."""

    def _layer(self, spatial_reference):
        metadata = {"name": "Parcels", "geometryType": "esriGeometryPolygon",
                    "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}]}
        if spatial_reference is not None:
            metadata["extent"] = {"spatialReference": spatial_reference}
        source = {"id": "s", "url": "https://gis.example/0", "count": False, "expected_wkid": 26915}
        with patch.object(watch, "_json_request", return_value=(metadata, META)):
            return watch._arcgis_layer(source, 5)

    def test_current_legacy_mismatched_and_missing_wkid(self):
        self.assertEqual(self._layer({"wkid": 26915}).get("quality_warnings"), None)
        self.assertEqual(self._layer({"wkid": 102100, "latestWkid": 26915}).get("quality_warnings"), None)
        mismatch = self._layer({"wkid": 4326})
        self.assertIn("WKID changed: expected 26915, got 4326", mismatch["problems"])
        missing = self._layer(None)
        self.assertEqual(missing["problems"], [])
        self.assertIn("WKID unavailable", missing["quality_warnings"][0])

    def test_missing_wkid_warns_the_source_and_alert(self):
        with tempfile.TemporaryDirectory() as td:
            result = _run(_config(Path(td)), {"wkid": None, "problems": [],
                                              "quality_warnings": ["WKID unavailable: expected 26915"]})
        self.assertEqual(result["sources"]["s"]["status"], "warn")
        self.assertIn("WKID unavailable", result["active_alerts"][0]["message"])


class InconsistentCountTests(unittest.TestCase):
    """21: a missing count above the total is not a measured 0%."""

    def test_inconsistent_counts_are_unavailable_with_raw_counts_kept(self):
        result = watch._completeness_from_missing("OWNER", 5, 6)
        self.assertIsNone(result["complete_percent"])
        self.assertIsNone(result["populated"])
        self.assertTrue(result["inconsistent_counts"])
        self.assertEqual((result["total"], result["missing"]), (5, 6))

    def test_real_zero_and_full_population_stay_measured(self):
        self.assertEqual(watch._completeness_from_missing("OWNER", 5, 5)["complete_percent"], 0.0)
        self.assertEqual(watch._completeness_from_missing("OWNER", 5, 0)["complete_percent"], 100.0)
        self.assertNotIn("inconsistent_counts", watch._completeness_from_missing("OWNER", 5, 5))


if __name__ == "__main__":
    unittest.main()
