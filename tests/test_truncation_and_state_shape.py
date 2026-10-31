"""Truncated provider results and malformed state (audit WT31-08, WT31-09)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch

META = {"status": 200, "transport": "test"}


class TransferLimitTests(unittest.TestCase):
    def test_duplicate_groups_under_a_provider_limit_are_marked_capped(self):
        page = {"features": [{"attributes": {"PIN": "1", "n": 3}}], "exceededTransferLimit": True}
        with patch.object(watch, "_json_request", return_value=(page, META)):
            summary = watch._arcgis_duplicate_id_summary("https://gis.example/0", "PIN", 5)
        self.assertTrue(summary["duplicate_scan_capped"])
        self.assertEqual(summary["duplicate_id_groups"], 1)

    def test_complete_duplicate_scans_stay_uncapped(self):
        for page in ({"features": [{"attributes": {"PIN": "1", "n": 2}}]},
                     {"features": [], "exceededTransferLimit": False}, {"features": []}):
            with self.subTest(page=page), patch.object(watch, "_json_request", return_value=(page, META)):
                self.assertFalse(watch._arcgis_duplicate_id_summary("https://gis.example/0", "PIN", 5)["duplicate_scan_capped"])

    def test_partial_county_catalog_page_is_not_reported_as_complete(self):
        page = {"features": [{"attributes": {"countyname": "Aitkin"}}], "exceededTransferLimit": True}
        source = {"id": "catalog", "adapter": "arcgis_county_catalog", "url": "https://gis.example/0"}
        with patch.object(watch, "_json_request", return_value=(page, META)) as request:
            with self.assertRaises(watch.PermanentProviderError):
                watch._arcgis_county_catalog(source, 5)
        self.assertEqual(request.call_count, 1)

    def test_truncated_catalog_keeps_the_last_complete_records_without_a_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
                      "retries": 2, "retry_delay_seconds": 0,
                      "sources": [{"id": "mn-parcel-county-catalog", "name": "Catalog",
                                   "adapter": "arcgis_county_catalog", "url": "https://gis.example/0"}]}
            complete = {"features": [{"attributes": {"countyname": "Aitkin"}},
                                     {"attributes": {"countyname": "Anoka"}}]}
            with patch.object(watch, "_json_request", return_value=(complete, META)):
                watch.check_sources(config, save=True)
            partial = {"features": [{"attributes": {"countyname": "Aitkin"}}], "exceededTransferLimit": True}
            with patch.object(watch, "_json_request", return_value=(partial, META)) as request:
                result = watch.check_sources(config, save=True)
            self.assertEqual(request.call_count, 1)
            record = result["sources"]["mn-parcel-county-catalog"]
            self.assertEqual(record["status"], "error")
            self.assertIn("transfer limit", record["error"])
            self.assertEqual(set(record["county_records"]), {"Aitkin", "Anoka"})
            self.assertTrue(record["catalog_retained"])

    def test_complete_catalog_is_unchanged(self):
        page = {"features": [{"attributes": {"countyname": "Aitkin"}}], "exceededTransferLimit": False}
        source = {"id": "catalog", "adapter": "arcgis_county_catalog", "url": "https://gis.example/0", "expected_count": 1}
        with patch.object(watch, "_json_request", return_value=(page, META)):
            result = watch._arcgis_county_catalog(source, 5)
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["county_record_count"], 1)


class StateShapeTests(unittest.TestCase):
    GOOD = {"schema_version": 2, "sources": {"a": {"status": "ok"}}}

    def write(self, path, value):
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")

    def test_valid_json_with_the_wrong_shape_falls_back_to_a_valid_backup(self):
        for bad in ([], None, "text", {"sources": []}, {"sources": {"a": "ok"}}, {"rate_limits": []}):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as td:
                path = Path(td) / "state.json"
                self.write(path, json.dumps(bad))
                self.write(path.with_suffix(".json.bak"), self.GOOD)
                state = watch.load_state(path)
                self.assertTrue(state["_state_recovered_from_backup"])
                self.assertEqual(state["sources"], self.GOOD["sources"])

    def test_malformed_primary_and_backup_are_refused_without_overwriting_either(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            backup = path.with_suffix(".json.bak")
            self.write(path, "[]")
            self.write(backup, "null")
            with self.assertRaises(RuntimeError):
                watch.load_state(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "[]")
            self.assertEqual(backup.read_text(encoding="utf-8"), "null")

    def test_save_never_rotates_a_malformed_primary_over_a_good_backup(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            backup = path.with_suffix(".json.bak")
            self.write(path, "[]")
            self.write(backup, self.GOOD)
            watch._save_json(path, {"schema_version": 2, "sources": {}})
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), self.GOOD)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"schema_version": 2, "sources": {}})

    def test_save_still_rotates_a_valid_primary_and_legacy_shapes_load(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            self.write(path, self.GOOD)
            watch._save_json(path, {"schema_version": 2, "sources": {}})
            self.assertEqual(json.loads(path.with_suffix(".json.bak").read_text(encoding="utf-8")), self.GOOD)
            # A v1 state without optional containers is still accepted.
            self.write(path, {"schema_version": 1, "sources": {}})
            self.assertEqual(watch.load_state(path), {"schema_version": 1, "sources": {}})


if __name__ == "__main__":
    unittest.main()
