"""County outreach permission: what Watchtower may check, and how pages say so."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.aggregate import merge_states
from clearparcel.datawatch.dashboard import _health_status, load_parcel_access
from clearparcel.datawatch.dashboard_counties import render_county
from clearparcel.datawatch.parcel_access import CountyPermission, validate_parcel_access
from clearparcel.datawatch.public_dashboard import render_public_source
from clearparcel.datawatch.run_evidence import expected_sources

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "clearparcel/datawatch/minnesota_county_parcel_access.json"
NOW = dt.datetime(2026, 10, 29, 12, tzinfo=dt.timezone.utc)


def research_copy():
    return json.loads(RESEARCH.read_text(encoding="utf-8"))


def names_for(decision):
    data = research_copy()
    return sorted(row["county"] for row in data["counties"] if row["monitoring"]["decision"] == decision)


class OutreachRecordTests(unittest.TestCase):
    def test_optional_outreach_fields_round_trip_and_contradictions_are_rejected(self):
        data = research_copy()
        aitkin = next(row for row in data["counties"] if row["county"] == "Aitkin")
        aitkin["monitoring"].update({
            "contacted_date": "2026-10-29", "reply": "permitted",
            "scope": "details-and-count", "stop_requested": False,
        })
        validate_parcel_access(data)
        record = CountyPermission.from_record(aitkin)
        self.assertEqual(record["contacted_date"], "2026-10-29")
        self.assertEqual(record["reply"], "permitted")
        self.assertEqual(record["scope"], "details-and-count")
        self.assertFalse(record["stop_requested"])

        for update in (
            {"reply": "granted"},
            {"scope": "everything"},
            {"stop_requested": "yes"},
            {"contacted_date": "October 29"},
            {"reply": "stop", "stop_requested": False, "scope": "none"},
            {"reply": "permitted", "scope": "full", "stop_requested": True},
            {"reply": "declined", "scope": "full"},
            {"reply": "no-reply", "scope": "details-and-count"},
        ):
            broken = research_copy()
            row = next(item for item in broken["counties"] if item["county"] == "Aitkin")
            row["monitoring"].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_parcel_access(broken)

    def test_missing_outreach_is_not_affirmative_permission(self):
        permission = CountyPermission.from_record(load_parcel_access()["Aitkin"])
        self.assertEqual(permission["terms_decision"], "not-assessed")
        self.assertIsNone(permission["scope"])
        self.assertIsNone(permission["reply"])
        self.assertFalse(permission["stop_requested"])
        self.assertIsNone(permission["contacted_date"])


class CheckRuleTests(unittest.TestCase):
    def config(self, root, sources):
        return {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
                "alerts_file": str(root / "alerts.json"), "alerts_text_file": str(root / "alerts.txt"),
                "retries": 0, "sources": sources}

    def sources(self):
        return [
            {"id": "parcels", "name": "County parcels", "adapter": "arcgis_layer",
             "url": "https://county.example/0", "county_slug": "aitkin", "category": "Parcels",
             "count": True, "parcel_quality": True, "geometry_sample": True,
             "gac_completeness": {"standard": "parcel"}},
            {"id": "roads", "name": "County roads", "adapter": "arcgis_layer",
             "url": "https://county.example/1", "county_slug": "aitkin", "category": "Roads"},
        ]

    def checked_sources(self, sources, research=None):
        with tempfile.TemporaryDirectory() as td:
            config = self.config(Path(td), sources)
            target = research if research is not None else load_parcel_access()
            with patch("clearparcel.datawatch.parcel_access.load_parcel_access", return_value=target), \
                    patch.object(watch, "_source_check", return_value={"problems": []}) as check:
                result = watch.check_sources(config, save=False)
        return result, [call.args[0] for call in check.call_args_list]

    def patched(self, county, **fields):
        data = load_parcel_access()
        data[county]["monitoring"].update(fields)
        return data

    def test_not_assessed_county_direct_is_not_checked_and_is_not_an_error(self):
        result, checked = self.checked_sources(self.sources())
        self.assertEqual([source["id"] for source in checked], ["roads"])
        self.assertEqual(result["skipped_sources"]["parcels"], "awaiting-permission")
        self.assertNotIn("parcels", result["sources"])
        self.assertEqual(result["overall"], "ok")
        self.assertNotEqual(result["sources"]["roads"]["status"], "error")

    def test_not_assessed_with_full_permission_is_checked(self):
        research = self.patched("Aitkin", contacted_date="2026-10-29", reply="permitted",
                                scope="full", stop_requested=False)
        result, checked = self.checked_sources(self.sources(), research)
        self.assertEqual([source["id"] for source in checked], ["parcels", "roads"])
        self.assertNotIn("parcels", result["skipped_sources"])

    def test_stop_requested_skips_every_source_for_the_county(self):
        research = self.patched("Aitkin", contacted_date="2026-10-29", reply="stop",
                                scope="none", stop_requested=True)
        result, checked = self.checked_sources(self.sources(), research)
        self.assertEqual(checked, [])
        self.assertEqual(result["skipped_sources"], {"parcels": "stop-requested", "roads": "stop-requested"})

    def test_hold_for_terms_still_blocks_parcels_when_a_scope_is_also_recorded(self):
        research = self.patched("Brown", contacted_date="2026-10-29", reply="permitted",
                                scope="full", stop_requested=False)
        sources = self.sources()
        for source in sources:
            source["county_slug"] = "brown"
        result, checked = self.checked_sources(sources, research)
        self.assertEqual([source["id"] for source in checked], ["roads"])
        self.assertEqual(result["skipped_sources"]["parcels"], "hold-for-terms")

    def test_assessed_candidate_without_a_new_reply_is_still_checked(self):
        sources = self.sources()
        for source in sources:
            source["county_slug"] = "todd"
        result, checked = self.checked_sources(sources)
        self.assertEqual([source["id"] for source in checked], ["parcels", "roads"])
        self.assertEqual(result["skipped_sources"], {})

    def test_explicit_scope_none_pauses_county_direct_checks(self):
        research = self.patched("Todd", contacted_date="2026-10-29", reply="declined",
                                scope="none", stop_requested=False)
        sources = self.sources()
        for source in sources:
            source["county_slug"] = "todd"
        result, checked = self.checked_sources(sources, research)
        self.assertEqual([source["id"] for source in checked], ["roads"])
        self.assertEqual(result["skipped_sources"]["parcels"], "awaiting-permission")

    def test_details_and_count_removes_every_query_past_metadata_and_a_count(self):
        research = self.patched("Todd", contacted_date="2026-10-29", reply="permitted",
                                scope="details-and-count", stop_requested=False)
        sources = self.sources()
        for source in sources:
            source["county_slug"] = "todd"
        _result, checked = self.checked_sources(sources, research)
        parcels = next(source for source in checked if source["id"] == "parcels")
        self.assertTrue(parcels.get("count"))
        for key in CountyPermission.EXTRA_QUERIES:
            self.assertNotIn(key, parcels)
        self.assertIn("parcel_quality", sources[0])

    def test_layer_check_does_not_run_the_extra_queries_after_they_are_removed(self):
        full = {"url": "https://county.example/0", "county_slug": "todd", "category": "Parcels",
                "count": True, "parcel_quality": True, "geometry_sample": True,
                "gac_completeness": {"standard": "parcel"}}
        limited = CountyPermission.constrain(full, {
            "scope": "details-and-count", "reply": "permitted", "stop_requested": False,
            "terms_decision": "candidate-low-frequency", "contacted_date": "2026-10-29",
        })
        metadata = {"name": "Parcels", "geometryType": "esriGeometryPolygon", "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "PIN", "type": "esriFieldTypeString"},
            {"name": "OWNER_NAME", "type": "esriFieldTypeString"},
        ], "objectIdField": "OBJECTID"}
        wheres = []

        def count_query(_url, where, _timeout, **_kwargs):
            wheres.append(where)
            return 4

        with patch.object(watch, "_json_request", return_value=(metadata, {"status": 200, "transport": "test"})), \
                patch.object(watch, "_arcgis_count_query", side_effect=count_query), \
                patch.object(watch, "_arcgis_geometry_sample", return_value={"geometry_sample_size": 1}) as geometry, \
                patch.object(watch, "_arcgis_gac_completeness", return_value={"fields": {}}) as gac, \
                patch.object(watch, "_arcgis_duplicate_id_summary", return_value={"duplicate_id_groups": 0}) as duplicates:
            watch._arcgis_layer(limited, 5)
        self.assertEqual(wheres, ["1=1"])
        geometry.assert_not_called()
        gac.assert_not_called()
        duplicates.assert_not_called()

        wheres.clear()
        with patch.object(watch, "_json_request", return_value=(metadata, {"status": 200, "transport": "test"})), \
                patch.object(watch, "_arcgis_count_query", side_effect=count_query), \
                patch.object(watch, "_arcgis_geometry_sample", return_value={"geometry_sample_size": 1}) as geometry, \
                patch.object(watch, "_arcgis_gac_completeness", return_value={"fields": {}}) as gac, \
                patch.object(watch, "_arcgis_duplicate_id_summary", return_value={"duplicate_id_groups": 0}) as duplicates:
            watch._arcgis_layer(full, 5)
        self.assertIn("1=1", wheres)
        self.assertGreater(len(wheres), 1)
        geometry.assert_called()
        gac.assert_called()
        duplicates.assert_called()


class CoverageAndPageTests(unittest.TestCase):
    def test_permission_skips_count_as_deliberate_coverage(self):
        base = merge_states({}, {"generated_at": NOW.isoformat(), "overall": "ok", "scope": {"type": "fleet"},
                                 "counts": {"ok": 3, "warn": 0, "error": 0},
                                 "sources": {sid: {"id": sid, "status": "ok", "checked_at": NOW.isoformat()}
                                             for sid in ("kept", "waiting", "stopped")}},
                            "cloud", now=NOW)
        later = NOW + dt.timedelta(hours=1)
        partial = {"generated_at": later.isoformat(), "overall": "ok", "scope": {"type": "fleet"},
                   "counts": {"ok": 1, "warn": 0, "error": 0},
                   "sources": {"kept": {"id": "kept", "status": "ok", "checked_at": later.isoformat()}},
                   "skipped_sources": {"waiting": "awaiting-permission", "stopped": "stop-requested"}}
        merged = merge_states(base, partial, "cloud", now=later)
        self.assertEqual(set(merged["sources"]), {"kept"})
        self.assertEqual(set(merged["retired_sources"]), {"waiting", "stopped"})

    def test_expected_alerts_follow_the_same_skip_rules(self):
        config = {"sources": [
            {"id": "waiting", "execution_profiles": ["cloud"], "county_slug": "aitkin", "category": "Parcels"},
            {"id": "roads", "execution_profiles": ["cloud"], "county_slug": "aitkin", "category": "Roads"},
            {"id": "candidate", "execution_profiles": ["cloud"], "county_slug": "todd", "category": "Parcels"},
        ]}
        self.assertEqual([row["source_id"] for row in expected_sources(config, "cloud")], ["roads", "candidate"])

    def test_public_county_page_shows_awaiting_permission_instead_of_a_failure(self):
        state = {"generated_at": NOW.isoformat(), "sources": {"mn-aitkin-parcels": {
            "id": "mn-aitkin-parcels", "name": "Aitkin parcels", "county_slug": "aitkin",
            "category": "Parcels", "status": "error", "checked_at": NOW.isoformat(),
            "problems": ["provider failed"]}}}
        page = render_county({"_render_state": state, "state_file": "unused.json"}, "aitkin")
        self.assertIn("Awaiting county permission", page)
        self.assertIn("Awaiting permission", page)
        self.assertNotIn("Check failed", page)
        self.assertNotIn(">Error<", page)
        self.assertEqual(_health_status("awaiting-permission"), "Awaiting permission")
        self.assertEqual(_health_status("paused"), "Paused")

    def test_public_source_page_for_a_limited_county_states_the_limit(self):
        research = load_parcel_access()
        research["Todd"]["monitoring"].update({
            "contacted_date": "2026-10-29", "reply": "permitted",
            "scope": "details-and-count", "stop_requested": False,
        })
        state = {"generated_at": NOW.isoformat(), "sources": {"mn-todd-parcels": {
            "id": "mn-todd-parcels", "name": "Todd parcels", "county_slug": "todd",
            "category": "Parcels", "status": "ok", "feature_count": 10,
            "checked_at": NOW.isoformat()}}}
        with patch("clearparcel.datawatch.public_dashboard.load_parcel_access", return_value=research), \
                patch("clearparcel.datawatch.public_dashboard._dashboard_state", return_value=state):
            page = render_public_source({"state_file": "unused.json"}, "mn-todd-parcels")
        self.assertIn("Limited check: service details and a record count only.", page)
        self.assertIn("Healthy", page)
        self.assertNotIn("Awaiting county permission", page)

    def test_counties_whose_direct_checks_change_are_the_not_assessed_counties(self):
        paused = names_for("not-assessed")
        self.assertIn("Aitkin", paused)
        self.assertIn("Wabasha", paused)
        self.assertNotIn("Todd", paused)
        self.assertNotIn("Brown", paused)
        self.assertGreaterEqual(len(paused), 14)
        for name in names_for("hold-for-terms"):
            permission = CountyPermission.from_record(load_parcel_access()[name])
            self.assertEqual(CountyPermission.skip_reason(
                {"county_slug": "x", "category": "Parcels"}, permission), "hold-for-terms")
            self.assertIsNone(CountyPermission.skip_reason(
                {"county_slug": "x", "category": "Roads"}, permission))
