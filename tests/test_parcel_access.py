import copy
import unittest

from clearparcel.datawatch.parcel_access import (
    CLASSIFICATIONS, INTERIM_LABEL, REVIEW_AREAS, access_label,
    load_parcel_access, statewide_access_label, validate_parcel_access,
)


def research_fixture():
    url = "https://county.example/gis"
    return {"schema_version": 2, "scope": "Parcel datasets", "counties": [{
        "county": "Example", "review_date": "2026-10-05",
        "county_direct_classification": "free-parcel-data", "research_complete": True,
        "official_county_url": url, "parcel_page_url": url,
        "download_or_service_url": url + "/FeatureServer/0", "viewer_url": None,
        "fee_policy_url": None, "parcel_dataset_fee": None, "fee_product": None,
        "evidence_note": "County publishes parcel polygons for public download.",
        "source_authority": "county", "usable_direct_machine_readable_source": True,
        "statewide_open_coverage": {"available": True, "source": "MnGeo Plan Parcels Open", "source_url": "https://gisdata.mn.gov/dataset/plan-parcels-open", "verified_date": "2026-10-05"},
        "monitoring": {"decision": "candidate-low-frequency", "reason": "Published open GIS API; bounded daily reads only.", "terms_urls": [url]},
        "evidence": [{"url": url, "authority": "county", "finding": "Public parcel download."}],
        "review_log": {area: {"status": "reviewed", "note": "Reviewed official source.", "urls": [url]} for area in REVIEW_AREAS},
    }]}


class ParcelAccessSchemaTests(unittest.TestCase):
    def test_accepts_supported_complete_record(self):
        validate_parcel_access(research_fixture())

    def test_rejects_incomplete_review_and_unverified_classification(self):
        for change in ("blocked", "pending"):
            data = research_fixture()
            data["counties"][0]["review_log"]["arcgis_services"]["status"] = change
            with self.assertRaises(ValueError):
                validate_parcel_access(data)
        data = research_fixture()
        data["counties"][0]["research_complete"] = False
        with self.assertRaises(ValueError):
            validate_parcel_access(data)

    def test_dataset_fee_requires_official_policy_product_and_fee(self):
        data = research_fixture()
        record = data["counties"][0]
        record.update(county_direct_classification="fee-based-parcel-data", fee_policy_url="https://county.example/fees", fee_product="Parcel shapefile", parcel_dataset_fee="$30")
        with self.assertRaises(ValueError):
            validate_parcel_access(data)
        record["evidence"].append({"url": record["fee_policy_url"], "authority": "county", "finding": "Parcel shapefile costs $30."})
        validate_parcel_access(data)
        for key in ("fee_policy_url", "fee_product", "parcel_dataset_fee"):
            invalid = copy.deepcopy(data)
            invalid["counties"][0][key] = None
            with self.assertRaises(ValueError):
                validate_parcel_access(invalid)

    def test_rejects_viewer_as_free_dataset_and_invalid_urls(self):
        data = research_fixture()
        data["counties"][0]["usable_direct_machine_readable_source"] = False
        with self.assertRaises(ValueError):
            validate_parcel_access(data)
        data = research_fixture()
        data["counties"][0]["official_county_url"] = "javascript:alert(1)"
        with self.assertRaises(ValueError):
            validate_parcel_access(data)

    def test_statewide_open_coverage_has_independent_typed_evidence(self):
        data = research_fixture()
        data["counties"][0]["statewide_open_coverage"]["available"] = "yes"
        with self.assertRaises(ValueError):
            validate_parcel_access(data)
        data = research_fixture()
        data["counties"][0]["statewide_open_coverage"]["verified_date"] = "not-a-date"
        with self.assertRaises(ValueError):
            validate_parcel_access(data)
        data = research_fixture()
        data["counties"][0]["statewide_open_coverage"]["source_url"] = "javascript:bad"
        with self.assertRaises(ValueError):
            validate_parcel_access(data)

    def test_no_direct_conclusion_requires_completed_review(self):
        data = research_fixture()
        data["counties"][0].update(county_direct_classification="no-direct-dataset-verified", research_complete=False)
        with self.assertRaises(ValueError):
            validate_parcel_access(data)

    def test_labels_are_neutral_until_complete(self):
        self.assertEqual(access_label(None), INTERIM_LABEL)
        self.assertEqual(access_label({"research_complete": False}), INTERIM_LABEL)
        for key, label in CLASSIFICATIONS.items():
            self.assertEqual(access_label({"county_direct_classification": key, "research_complete": True}), label)
        self.assertEqual(
            statewide_access_label({"statewide_open_coverage": {"available": True}}),
            "Available free through MnGeo Plan Parcels Open",
        )

    def test_minnesota_audit_contains_35_completed_evidence_backed_records(self):
        records = load_parcel_access()
        self.assertEqual(len(records), 35)
        self.assertTrue(all(record["research_complete"] for record in records.values()))
        self.assertTrue(all(record["evidence"] for record in records.values()))
        self.assertTrue(all(
            all(area["status"] not in {"pending", "blocked"} for area in record["review_log"].values())
            for record in records.values()
        ))
        counts = {}
        for record in records.values():
            key = record["county_direct_classification"]
            counts[key] = counts.get(key, 0) + 1
        self.assertEqual(counts, {
            "free-parcel-data": 13,
            "fee-based-parcel-data": 11,
            "parcel-viewer-only": 11,
        })
        statewide = [r for r in records.values() if r["statewide_open_coverage"]["available"]]
        self.assertEqual(len(statewide), 9)
        self.assertTrue(records["Winona"]["statewide_open_coverage"]["available"])
        self.assertEqual(
            records["Winona"]["county_direct_classification"],
            "fee-based-parcel-data",
        )

    def test_policy_conflict_endpoints_are_held_for_terms(self):
        records = load_parcel_access()
        held = {"Blue Earth", "Faribault", "Kandiyohi", "Lincoln"}
        self.assertEqual(
            {name for name, record in records.items() if record["monitoring"]["decision"] == "hold-for-terms"},
            held,
        )
        for name in held:
            record = records[name]
            self.assertEqual(record["county_direct_classification"], "fee-based-parcel-data")
            self.assertFalse(record["usable_direct_machine_readable_source"])
            self.assertTrue(record["download_or_service_url"])
            self.assertTrue(record["fee_policy_url"])
            self.assertTrue(record["parcel_dataset_fee"])

    def test_direct_sources_and_fee_records_remain_distinct(self):
        records = load_parcel_access()
        direct = [r for r in records.values() if r["usable_direct_machine_readable_source"]]
        self.assertEqual(len(direct), 13)
        self.assertTrue(all(r["county_direct_classification"] == "free-parcel-data" for r in direct))
        self.assertTrue(all(r["monitoring"]["decision"] == "candidate-low-frequency" for r in direct))
        fee_records = [r for r in records.values() if r["county_direct_classification"] == "fee-based-parcel-data"]
        self.assertEqual(len(fee_records), 11)
        self.assertTrue(all(r["fee_policy_url"] and r["parcel_dataset_fee"] and r["fee_product"] for r in fee_records))
        self.assertTrue(all(not r["usable_direct_machine_readable_source"] for r in fee_records))


if __name__ == "__main__":
    unittest.main()
