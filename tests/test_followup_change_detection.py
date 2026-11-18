"""Change detection from the follow-up review of f8f0997 (F06, F07, F14).

Offline: provider calls are mocked and state lives in a temporary directory.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch

META = {"status": 200, "transport": "test"}
COUNTIES = [row["name"] for row in json.loads(
    (Path(watch.__file__).with_name("minnesota_counties.json")).read_text(encoding="utf-8"))["counties"]]


def _config(root: Path, **extra) -> dict:
    source = {"id": "s", "name": "S", "kind": "arcgis_service", "url": "https://gis.example/MapServer"}
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


class PartialObservationBaselineTests(unittest.TestCase):
    """F06: a partial service observation keeps the parcel-layer baseline."""

    LISTING = {"schema_hash": "listing-1", "problems": []}

    def test_parcel_changes_are_detected_across_a_partial_check(self):
        with tempfile.TemporaryDirectory() as td:
            config = _config(Path(td), thresholds={"feature_count_change_percent": 10})
            first = _run(config, {**self.LISTING, "parcel_layer_id": 3, "parcel_schema_hash": "A",
                                  "feature_count": 100})
            observed = first["sources"]["s"]["checked_at"]
            partial = _run(config, {"schema_hash": "listing-2", "problems": ["no parcel-like layer found in service"]})
            kept = partial["sources"]["s"]["comparison_baseline"]
            self.assertEqual((kept["parcel_schema_hash"], kept["feature_count"]), ("A", 100))
            self.assertEqual(kept["field_observed_at"]["feature_count"], observed)
            result = _run(config, {"schema_hash": "listing-2", "parcel_layer_id": 3, "parcel_schema_hash": "B",
                                   "feature_count": 47, "problems": []})
        source = result["sources"]["s"]
        changes = {change["type"]: change for change in source["changes"]}
        self.assertEqual(changes["parcel_schema"]["previous"], "A")
        self.assertEqual(changes["feature_count"]["previous"], 100)
        self.assertEqual(changes["feature_count"]["severity"], "warn")
        self.assertEqual(changes["parcel_schema"]["previous_observed_at"], observed)
        self.assertEqual(changes["feature_count"]["previous_observed_at"], observed)
        self.assertNotIn("schema", changes)  # the listing was observed by the partial check
        self.assertNotIn("comparison_baseline", source)

    def test_rate_limited_recovery_names_the_earlier_observation(self):
        with tempfile.TemporaryDirectory() as td:
            config = _config(Path(td))
            first = _run(config, {**self.LISTING, "parcel_schema_hash": "A", "feature_count": 100})
            observed = first["sources"]["s"]["checked_at"]
            limited = _run(config, watch.ProviderRateLimitError(retry_after="60", host="gis.example"))
            record = limited["sources"]["s"]
            self.assertTrue(record["rate_limited"])
            self.assertEqual(record["comparison_baseline"]["observed_at"], observed)
            state = json.loads((Path(td) / "state.json").read_text(encoding="utf-8"))
            state["rate_limits"] = {}
            (Path(td) / "state.json").write_text(json.dumps(state), encoding="utf-8")
            result = _run(config, {**self.LISTING, "parcel_schema_hash": "B", "feature_count": 47})
        changes = {change["type"]: change for change in result["sources"]["s"]["changes"]}
        self.assertEqual(changes["parcel_schema"]["previous_observed_at"], observed)
        self.assertEqual(changes["feature_count"]["previous_observed_at"], observed)

    def test_consecutive_full_observations_carry_no_extra_times(self):
        with tempfile.TemporaryDirectory() as td:
            config = _config(Path(td))
            _run(config, {**self.LISTING, "parcel_schema_hash": "A", "feature_count": 100})
            result = _run(config, {**self.LISTING, "parcel_schema_hash": "B", "feature_count": 100})
        change = result["sources"]["s"]["changes"][0]
        self.assertEqual(change["type"], "parcel_schema")
        self.assertNotIn("previous_observed_at", change)


class CatalogMembershipTests(unittest.TestCase):
    """F07: a full-sized Minnesota catalog must still name every county."""

    def _config(self, root: Path) -> dict:
        return {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"), "retries": 0,
                "sources": [{"id": "mn-parcel-county-catalog", "name": "Catalog", "kind": "arcgis_county_catalog",
                             "url": "https://gis.example/0", "expected_count": 87}]}

    @staticmethod
    def _catalog(names):
        return {"features": [{"attributes": {"countyname": name}} for name in names]}

    def test_replaced_county_keeps_the_complete_catalog(self):
        self.assertEqual(len(COUNTIES), 87)
        replaced = ["Aitkn" if name == "Aitkin" else name for name in COUNTIES]
        with tempfile.TemporaryDirectory() as td:
            config = self._config(Path(td))
            with patch.object(watch, "_json_request", return_value=(self._catalog(COUNTIES), META)):
                first = watch.check_sources(config)
            with patch.object(watch, "_json_request", return_value=(self._catalog(replaced), META)):
                result = watch.check_sources(config)
        record = result["sources"]["mn-parcel-county-catalog"]
        self.assertEqual(record["status"], "error")
        self.assertIn("unrecognized: Aitkn", record["error"])
        self.assertIn("Aitkin", record["county_records"])
        self.assertTrue(record["catalog_retained"])
        self.assertEqual(record["catalog_observed_at"],
                         first["sources"]["mn-parcel-county-catalog"]["catalog_observed_at"])

    def test_alias_spelling_that_duplicates_a_county_is_rejected(self):
        names = ["Saint Louis" if name == "Aitkin" else name for name in COUNTIES]  # St. Louis twice
        source = self._config(Path("."))["sources"][0]
        with patch.object(watch, "_json_request", return_value=(self._catalog(names), META)), \
                self.assertRaises(watch.PermanentProviderError):
            watch._arcgis_county_catalog(source, 5)

    def test_generic_catalog_keeps_other_membership_rules(self):
        source = {"id": "other-catalog", "url": "https://gis.example/0", "expected_count": 2}
        with patch.object(watch, "_json_request", return_value=(self._catalog(["North", "South"]), META)):
            self.assertEqual(watch._arcgis_county_catalog(source, 5)["county_record_count"], 2)


class MalformedStatisticsTests(unittest.TestCase):
    """F14: a reply without a features array, or a group without its count, is not a measured zero."""

    def test_duplicate_summary_rejects_malformed_replies(self):
        for reply in ({}, {"features": None}, {"features": {"a": 1}},
                      {"features": [{"attributes": {"PIN": "1"}}]}, {"features": [{"attributes": {"n": "2"}}]}):
            with self.subTest(reply=reply), \
                    patch.object(watch, "_json_request", return_value=(reply, META)), \
                    self.assertRaises((RuntimeError, ValueError)):
                watch._arcgis_duplicate_id_summary("https://gis.example/0", "PIN", 5)

    def test_duplicate_summary_keeps_a_real_empty_result(self):
        with patch.object(watch, "_json_request", return_value=({"features": []}, META)):
            summary = watch._arcgis_duplicate_id_summary("https://gis.example/0", "PIN", 5)
        self.assertEqual((summary["duplicate_id_groups"], summary["duplicate_id_extra_rows"]), (0, 0))
        with patch.object(watch, "_json_request", return_value=({"features": [{"attributes": {"n": 3}}]}, META)):
            summary = watch._arcgis_duplicate_id_summary("https://gis.example/0", "PIN", 5)
        self.assertEqual((summary["duplicate_id_groups"], summary["duplicate_id_extra_rows"]), (1, 2))

    def test_malformed_duplicate_reply_marks_the_check_unavailable(self):
        metadata = {"name": "Parcels", "geometryType": "esriGeometryPolygon",
                    "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"},
                               {"name": "PIN", "type": "esriFieldTypeString"}]}

        def reply(url, *args, **kwargs):
            if "groupByFieldsForStatistics" in url:
                return {}, META
            if "returnCountOnly" in url:
                return {"count": 100}, META
            if "returnGeometry=true" in url:
                return {"features": []}, META
            if "/query?" in url:
                return {"count": 0, "features": []}, META
            return metadata, META
        source = {"id": "s", "url": "https://gis.example/0", "count": True, "parcel_quality": True,
                  "parcel_id_field": "PIN"}
        with patch.object(watch, "_json_request", side_effect=reply):
            result = watch._arcgis_layer(source, 5)
        self.assertNotIn("duplicate_id_groups", result)
        self.assertNotIn("duplicate_id_extra_rows", result)
        self.assertEqual(result["duplicate_id_check"], "unsupported")

    def test_statistics_helpers_reject_a_missing_features_array(self):
        for label in ("GAC statistics", "ArcGIS geometry sample"):
            with self.subTest(label=label), self.assertRaises(RuntimeError):
                watch._response_features({"exceededTransferLimit": False}, label)
        self.assertEqual(watch._response_features({"features": []}, "x"), [])
        with patch.object(watch, "_json_request", return_value=({}, META)), self.assertRaises(RuntimeError):
            watch._arcgis_geometry_sample("https://gis.example/0", 5)


if __name__ == "__main__":
    unittest.main()
