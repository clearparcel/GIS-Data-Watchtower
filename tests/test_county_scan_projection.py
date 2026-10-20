"""Synthetic WT-01 regression: county measurements share statewide schema."""
import copy
import csv
import io
import json
import re
import unittest
from unittest.mock import patch

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.dashboard_exports import _gac_xlsx_sheets, _snapshot_csv
from clearparcel.datawatch.gac_standards import load_gac_standard
from clearparcel.datawatch.gac_projection import county_field, project_gac
from clearparcel.datawatch.public_projection import sanitize_public_render_state


def observation(key="parcel"):
    schema = load_gac_standard(key)
    field = "STATE_PIN" if key == "parcel" else schema["fields"][0]["field"]
    data = {
        "standard_key": key, "standard": schema["standard"],
        "population_scope": "all" if key == "parcel" else "mandatory",
        "covered_counties": 1, "record_count": 51689,
        "fields": {field: {
            "present_in_source_schema": True, "population_scanned": True,
            "populated": 51689, "record_count": 51689, "percent": 100.0,
        }},
        "counties": {"Cass": {"record_count": 51689, "fields": {
            field: {"populated": 51689, "record_count": 51689, "percent": 100.0},
        }}},
    }
    return data, field


def state_for(data):
    return {"sources": {"synthetic": {"status": "ok", "gac_completeness": data}}}


def field_row(page, field):
    return next(row for row in re.findall(r"<tr\b.*?</tr>", page, re.S)
                if f"<code>{field}</code>" in row)


class CountyScanProjectionTests(unittest.TestCase):
    def test_projection_preserves_zero_unknown_unscanned_and_legacy(self):
        shared = {"present_in_source_schema": True, "population_scanned": True}
        cases = [
            ({"populated": 0, "record_count": 20, "percent": 0.0}, shared, True, 0.0),
            ({"populated": 0, "record_count": 0, "percent": None}, shared, True, None),
            ({"populated": 4, "record_count": 5, "percent": 80.0}, {}, True, 80.0),
            ({}, shared, None, None),
            ({}, {"population_scanned": False}, False, None),
            ({"record_count": True}, shared, None, None),
            ({"record_count": -1}, shared, None, None),
            ({"record_count": "5"}, shared, None, None),
            ({"record_count": 5, "percent": 80.0}, {"population_scanned": None}, None, None),
        ]
        for values, meta, expected, percent in cases:
            with self.subTest(values=values, meta=meta):
                result = county_field(values, meta)
                self.assertIs(result["population_scanned"], expected)
                self.assertEqual(result.get("percent"), percent)
        self.assertIsNone(county_field({}, shared, observed=False)["population_scanned"])

    def test_address_and_road_unscanned_fields_and_empty_county_stay_distinct(self):
        for key in ("address", "road"):
            data, field = observation(key)
            unscanned = load_gac_standard(key)["fields"][1]["field"]
            data["fields"][unscanned] = {
                "present_in_source_schema": True, "population_scanned": False,
            }
            data["counties"]["Cass"]["fields"][field].update(populated=0, percent=0.0)
            before = copy.deepcopy(data)
            with patch.object(dashboard, "_dashboard_state", return_value=state_for(data)):
                page = dashboard.render_mngac({}, key, county="cass")
                self.assertIn("<td>Scanned</td><td>0</td>", field_row(page, field))
                self.assertIn("0.00%", field_row(page, field))
                self.assertIn("<td>Present</td><td>Not scanned</td>", field_row(page, unscanned))
                self.assertNotIn("0.00%", field_row(page, unscanned))
                unavailable = dashboard.render_mngac({}, key, county="aitkin")
                self.assertIn("not represented in the current saved observation", unavailable)
            self.assertEqual(data, before)

    def test_all_county_routes_and_59_synthetic_parcel_projections(self):
        data, field = observation()
        template = data["counties"]["Cass"]
        for spec in load_gac_standard("parcel")["fields"]:
            name = spec["field"]
            if name == field:
                continue
            data["fields"][name] = {
                "present_in_source_schema": True, "population_scanned": True,
            }
            template["fields"][name] = {"populated": 0, "record_count": 51689, "percent": 0.0}
        counties = dashboard._load_counties()
        # Synthetic coverage count reproduces the audited shape, not live coverage.
        represented = [c["name"] for c in counties[:59]]
        data["counties"] = {name: copy.deepcopy(template) for name in represented}
        data["covered_counties"] = len(represented)
        original = state_for(data)
        state = sanitize_public_render_state(original)
        before = copy.deepcopy(state)
        projected = project_gac(state["sources"]["synthetic"]["gac_completeness"])
        self.assertEqual(len(projected["counties"]), 59)
        self.assertEqual(project_gac(projected), projected, "Projection must be idempotent")
        with patch.object(dashboard, "_dashboard_state", return_value=state):
            for public in (True, False):
                for county in counties:
                    with self.subTest(public=public, county=county["slug"]):
                        config = {"_public_mode": public}
                        profile = dashboard.render_county(config, county["slug"])
                        results = dashboard.render_mngac(config, "parcel", county=county["slug"])
                        for page in (profile, results):
                            if county["name"] in represented:
                                self.assertIn("<td>Present</td><td>Scanned</td>", field_row(page, field))
                            else:
                                self.assertIn("not represented", page)
                                self.assertNotIn(f"<code>{field}</code>", page)
            snapshot = dashboard._statewide_snapshot({})
            snapshot = json.loads(json.dumps(snapshot, allow_nan=False))
            self.assertEqual(snapshot["county_count"], 87)
            for name in represented:
                self.assertIs(snapshot["mngac"]["counties"][name]["fields"][field]["population_scanned"], True)
                self.assertIs(snapshot["gac"]["parcel"]["counties"][name]["fields"][field]["population_scanned"], True)
            detail = dict(_gac_xlsx_sheets(snapshot))["GAC Detail"]
            measured = [row for row in detail[1:] if row[2] == field]
            self.assertEqual(len(measured), 59)
            self.assertTrue(all(row[5:] == [True, 51689, 51689, 100.0] for row in measured))
            self.assertEqual(len(detail) - 1, 59 * 91)
            self.assertTrue(all(row[5] is True for row in detail[1:]))
            csv_rows = list(csv.DictReader(io.StringIO(_snapshot_csv(snapshot))))
            self.assertEqual(len(csv_rows), 1)  # Statewide CSV is a source summary.
            self.assertEqual(csv_rows[0]["source_id"], "synthetic")
        self.assertEqual(state, before)

    def test_cass_profile_and_county_results_agree_in_both_modes(self):
        data, field = observation()
        state = state_for(data)
        before = copy.deepcopy(state)
        with patch.object(dashboard, "_dashboard_state", return_value=state):
            for public in (True, False):
                config = {"_public_mode": public}
                profile = dashboard.render_county(config, "cass")
                results = dashboard.render_mngac(config, "parcel", county="cass")
                for page in (profile, results):
                    with self.subTest(public=public, profile=page is profile):
                        row = field_row(page, field)
                        self.assertIn("<td>Present</td><td>Scanned</td>", row)
                        self.assertIn("51,689", row)
                        self.assertIn("100.00%", row)
                payload = dashboard._county_snapshot(config, "cass")
                csv_row = next(csv.DictReader(io.StringIO(_snapshot_csv(payload))))
                self.assertEqual(csv_row["county"], "Cass")
                self.assertEqual(csv_row["mngac_record_count"], "51689")
                for county in (payload["mngac"]["county"], payload["gac"]["parcel"]["county"]):
                    self.assertIs(county["fields"][field]["population_scanned"], True)
                    self.assertIs(county["fields"][field]["present_in_source_schema"], True)
        self.assertEqual(state, before, "Rendering must not rewrite saved observations")

    def test_explicit_flags_override_shared_metadata_in_every_county_view(self):
        for flag in (False, None):
            data, field = observation()
            data["counties"]["Cass"]["fields"][field].update(
                population_scanned=flag, present_in_source_schema=flag)
            for state in (state_for(data), sanitize_public_render_state(state_for(data))):
                with patch.object(dashboard, "_dashboard_state", return_value=state):
                    for page in (dashboard.render_county({}, "cass"),
                                 dashboard.render_mngac({}, "parcel", county="cass")):
                        row = field_row(page, field)
                        self.assertIn("<td>Missing</td>" if flag is False else "<td>Unknown</td>", row)
                        self.assertIn("<td>Not scanned</td>" if flag is False else "<td>No data</td>", row)
                        self.assertNotIn("100.00%", row)

    def test_xlsx_does_not_claim_a_scan_from_statewide_metadata_alone(self):
        data, field = observation()
        data["counties"]["Cass"]["fields"] = {}
        rows = dict(_gac_xlsx_sheets({"gac": {"parcel": data}}))["GAC Detail"]
        row = next(row for row in rows[1:] if row[1:3] == ["Cass", field])
        self.assertIsNone(row[5])


if __name__ == "__main__":
    unittest.main()
