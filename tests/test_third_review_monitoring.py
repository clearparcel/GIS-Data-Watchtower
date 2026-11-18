"""Provider options and change detection from the third review of 2310764 (T04-T08).

Offline: provider calls are mocked and state lives in a temporary directory.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch
from tests.catalog_fixtures import full_minnesota_catalog

META = {"status": 200, "transport": "test"}


def _source(**extra) -> dict:
    return {"id": "s", "name": "S", "adapter": "arcgis_layer", "url": "https://gis.example/FeatureServer/0", **extra}


def _config(root: Path, source: dict) -> dict:
    return {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
            "retries": 0, "sources": [source]}


def _run(config: dict, outcome: dict) -> dict:
    with patch.object(watch, "_source_check", side_effect=lambda source, timeout: dict(outcome)):
        return watch.check_sources(config)


class RequestFlagTests(unittest.TestCase):
    """T04: request-producing options must be JSON booleans before any request."""

    def test_stringified_or_numeric_flags_are_refused(self):
        for key in watch._REQUEST_FLAG_OPTIONS:
            for value in ("false", "true", 0, 1, "", [], {}):
                with self.subTest(key=key, value=value), \
                        self.assertRaisesRegex(watch.InvalidSourceRegistryError, f"{key} must be true or false"):
                    watch.validate_source_registry([_source(**{key: value})])

    def test_real_booleans_and_omitted_values_pass(self):
        for key in watch._REQUEST_FLAG_OPTIONS:
            for value in (True, False, None):
                with self.subTest(key=key, value=value):
                    watch.validate_source_registry([_source(**{key: value})])
        watch.validate_source_registry([_source()])

    def test_string_discovery_cannot_satisfy_the_layer_name_guard(self):
        service = _source(adapter="arcgis_service", url="https://gis.example/MapServer",
                          discover_parcel_layer="false", expected_layer_name="Parcels")
        with self.assertRaises(watch.InvalidSourceRegistryError):
            watch.validate_source_registry([service])

    def test_count_false_makes_only_the_metadata_request(self):
        layer = {"name": "Parcels", "fields": [], "geometryType": "esriGeometryPolygon"}
        with patch.object(watch, "_json_request", return_value=(layer, META)) as request:
            watch._arcgis_layer(_source(count=False), 5)
        self.assertEqual(request.call_count, 1)


class ThresholdTests(unittest.TestCase):
    """T08: an explicit null extent threshold is refused, and comparison never crashes on it."""

    def test_null_extent_threshold_is_refused(self):
        with self.assertRaisesRegex(watch.InvalidSourceRegistryError, "extent_shift_percent"):
            watch.validate_source_registry([_source(thresholds={"extent_shift_percent": None})])
        # A null count threshold keeps meaning "no warning".
        watch.validate_source_registry([_source(thresholds={"feature_count_change_percent": None})])

    def test_two_consecutive_extents_use_the_default(self):
        extent = {"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10, "wkid": 26915}
        source = _source(thresholds={"extent_shift_percent": None})
        self.assertEqual(watch._compare({"spatial_extent": extent}, {"spatial_extent": extent}, source), [])
        shifted = watch._compare({"spatial_extent": extent}, {"spatial_extent": {**extent, "xmax": 11}}, source)
        self.assertEqual([change["type"] for change in shifted], ["spatial_extent"])


class MinnesotaCatalogTests(unittest.TestCase):
    """T05: every raw row is a distinct Minnesota county, stored under its canonical name."""

    SOURCE = {"id": "mn-parcel-county-catalog", "adapter": "arcgis_county_catalog", "url": "https://gis.example/0"}

    def _catalog(self, page: dict) -> dict:
        with patch.object(watch, "_json_request", return_value=(page, META)):
            return watch._arcgis_county_catalog(dict(self.SOURCE), 5)

    def test_alias_is_stored_under_the_canonical_name(self):
        page = full_minnesota_catalog([{"attributes": {"countyname": "Saint Louis", "gac_open_approval": "yes"}}])
        page["features"] = [row for row in page["features"] if row["attributes"]["countyname"] != "St. Louis"]
        result = self._catalog(page)
        self.assertNotIn("Saint Louis", result["county_records"])
        self.assertEqual(result["county_records"]["St. Louis"]["gac_open_approval"], "yes")
        self.assertEqual(result["county_records"]["St. Louis"]["countyname"], "St. Louis")

    def test_duplicate_row_is_refused(self):
        page = full_minnesota_catalog([{"attributes": {"countyname": "Aitkin", "gac_open_approval": "yes"}}])
        page["features"].append({"attributes": {"countyname": "Aitkin", "gac_open_approval": "no"}})
        with self.assertRaisesRegex(watch.PermanentProviderError, "duplicated: Aitkin"):
            self._catalog(page)

    def test_incomplete_catalog_is_refused_without_expected_count(self):
        with self.assertRaisesRegex(watch.PermanentProviderError, "missing: 86"):
            self._catalog({"features": [{"attributes": {"countyname": "Aitkin"}}]})

    def test_complete_catalog_passes(self):
        self.assertEqual(self._catalog(full_minnesota_catalog([]))["county_record_count"], 87)


class StatisticsShapeTests(unittest.TestCase):
    """T06: malformed elements inside a present statistics array are not zero coverage."""

    def _gac(self, features: list[dict]) -> dict:
        with patch.object(watch, "load_gac_standard", return_value={"fields": [
                {"field": "CO_NAME", "inclusion": "Mandatory", "data_type": "Text"}]}), \
             patch.object(watch, "_json_request", return_value=({"features": features}, META)):
            return watch._arcgis_gac_completeness("https://example.invalid/0", ["OBJECTID", "CO_NAME", "CO_CODE"], "OBJECTID", 10)

    def test_group_without_county_attribute_is_malformed(self):
        for features in ([{}], [{"attributes": {"COUNTY": "Aitkin", "record_count": 10, "p0": 5}}]):
            with self.subTest(features=features), self.assertRaisesRegex(RuntimeError, "missing its CO_NAME"):
                self._gac(features)

    def test_null_group_and_empty_array_keep_their_meaning(self):
        self.assertEqual(self._gac([])["counties"], {})
        result = self._gac([{"attributes": {"CO_NAME": None, "record_count": 3, "p0": 1}},
                            {"attributes": {"CO_NAME": "Aitkin", "record_count": 10, "p0": 5}}])
        self.assertEqual(set(result["counties"]), {"Aitkin"})

    def test_duplicate_group_below_two_is_malformed(self):
        for size in (0, 1):
            page = {"features": [{"attributes": {"PIN": "x", "n": size}}]}
            with self.subTest(size=size), patch.object(watch, "_json_request", return_value=(page, META)), \
                    self.assertRaises(ValueError):
                watch._arcgis_duplicate_id_summary("https://gis.example/0", "PIN", 5)
        page = {"features": [{"attributes": {"PIN": "x", "n": 3}}]}
        with patch.object(watch, "_json_request", return_value=(page, META)):
            summary = watch._arcgis_duplicate_id_summary("https://gis.example/0", "PIN", 5)
        self.assertEqual((summary["duplicate_id_groups"], summary["duplicate_id_extra_rows"]), (1, 2))


class PartialComparisonTests(unittest.TestCase):
    """T07: unmeasured fields invent no change, and tracked values keep their own baseline."""

    def test_missing_parcel_layer_twice_invents_no_schema_change(self):
        service = _source(adapter="arcgis_service", url="https://gis.example/MapServer",
                          thresholds={"schema_change_severity": "error"})
        with tempfile.TemporaryDirectory() as td:
            config = _config(Path(td), service)
            _run(config, {"schema_hash": "L", "parcel_layer_id": 3, "parcel_schema_hash": "A", "problems": []})
            missing = {"schema_hash": "L", "problems": ["no parcel-like layer found in service"]}
            for attempt in range(2):
                changes = _run(config, missing)["sources"]["s"]["changes"]
                self.assertNotIn("parcel_schema", [change["type"] for change in changes])
                if attempt:
                    self.assertEqual(changes, [])  # no new evidence, no event
            result = _run(config, {"schema_hash": "L", "parcel_layer_id": 3, "parcel_schema_hash": "B", "problems": []})
        self.assertEqual([(c["type"], c["previous"]) for c in result["sources"]["s"]["changes"]], [("parcel_schema", "A")])

    def test_tracked_value_survives_a_missing_column(self):
        with tempfile.TemporaryDirectory() as td:
            config = _config(Path(td), _source(adapter="sda_query"))
            first = _run(config, {"schema_hash": "c1", "tracked_values": {"acres": 100, "rows": 5}, "problems": []})
            observed = first["sources"]["s"]["checked_at"]
            _run(config, {"schema_hash": "c2", "tracked_values": {"rows": 5},
                          "problems": ["expected SDA columns missing: acres"]})
            result = _run(config, {"schema_hash": "c1", "tracked_values": {"acres": 50, "rows": 5}, "problems": []})
        changes = {change["type"]: change for change in result["sources"]["s"]["changes"]}
        self.assertEqual((changes["tracked_value"]["previous"], changes["tracked_value"]["current"]), (100, 50))
        self.assertEqual(changes["tracked_value"]["previous_observed_at"], observed)
        self.assertIn("schema", changes)


if __name__ == "__main__":
    unittest.main()
