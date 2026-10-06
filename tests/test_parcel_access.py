import copy
import unittest
import json
from pathlib import Path

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
        "download_or_service_url": url + "/rest/services/Parcels/FeatureServer/0", "viewer_url": None,
        "fee_policy_url": None, "parcel_dataset_fee": None, "fee_product": None,
        "evidence_note": "County publishes parcel polygons for public download.",
        "source_authority": "county", "usable_direct_machine_readable_source": True,
        "statewide_open_coverage": {"available": True, "source": "MnGeo Plan Parcels Open", "source_url": "https://gisdata.mn.gov/dataset/plan-parcels-open", "verified_date": "2026-10-05"},
        "monitoring": {"decision": "candidate-low-frequency", "reason": "Published open GIS API; bounded daily reads only.", "terms_urls": [url]},
        "evidence": [{"url": url, "authority": "county", "finding": "Public parcel download."}, {"url": url + "/rest/services/Parcels/FeatureServer/0", "authority": "county", "finding": "County publishes parcel polygon layer."}],
        "review_log": {area: {"status": "reviewed", "note": "Reviewed official source.", "urls": [url]} for area in REVIEW_AREAS},
    }]}


class ParcelAccessSchemaTests(unittest.TestCase):
    def test_swift_yellow_medicine_fee_exemption_holds_and_products(self):
        records = load_parcel_access()
        names = ('Swift', 'Traverse', 'Wabasha', 'Waseca', 'Washington', 'Wilkin', 'Wright', 'Yellow Medicine')
        for name in names:
            record = records[name]
            self.assertEqual(record['review_date'], '2026-10-06')
            self.assertTrue(all(c['review_status'] != 'pending' for c in record['source_inventory'].values()))
        self.assertEqual(records['Swift']['county_direct_classification'], 'fee-based-parcel-data')
        self.assertIn('450', records['Swift']['parcel_dataset_fee'])
        self.assertEqual(records['Wilkin']['county_direct_classification'], 'free-parcel-data')
        self.assertIsNone(records['Wilkin']['parcel_dataset_fee'])
        self.assertIn('self-service', records['Wilkin']['comments'])
        for name in ('Swift', 'Wilkin'):
            self.assertEqual(records[name]['monitoring']['decision'], 'hold-for-terms')
        for name in names[1:]:
            self.assertEqual(records[name]['source_inventory']['county_download']['availability'], 'yes')
        for name in ('Wabasha', 'Waseca', 'Washington', 'Wright'):
            self.assertEqual(records[name]['source_inventory']['mngeo_public_repository']['availability'], 'yes')
        self.assertEqual(records['Washington']['source_inventory']['county_arcgis_rest']['sources'][0]['layer_id'], 6)

    def test_sherburne_stevens_batch_records_official_products_and_blockers(self):
        records = load_parcel_access()
        for name in ('Sherburne', 'St. Louis', 'Stearns', 'Steele', 'Stevens'):
            record = records[name]
            self.assertEqual(record['review_date'], '2026-10-06')
            self.assertEqual(record['source_inventory']['mngac_public_parcels']['availability'], 'yes')
            self.assertEqual(record['source_inventory']['county_download']['availability'], 'yes')
            self.assertEqual(record['monitoring']['decision'],
                             'hold-for-terms' if name == 'Stevens' else 'not-assessed')
            self.assertIsNone(record['parcel_dataset_fee'])
        self.assertEqual(records['Steele']['source_inventory']['mngeo_public_repository']['availability'], 'yes')
        self.assertEqual(records['Stearns']['source_inventory']['county_arcgis_rest']['availability'], 'unknown')
        stevens = records['Stevens']
        self.assertEqual(stevens['county_direct_classification'], 'free-parcel-data')
        self.assertTrue(stevens['research_complete'])
        self.assertIn('financial', stevens['monitoring']['reason'])
        for category in ('county_arcgis_rest', 'county_download'):
            self.assertEqual(stevens['source_inventory'][category]['sources'][0]['monitoring_decision'],
                             'hold-for-terms')
        for name in ('Sherburne', 'St. Louis', 'Steele', 'Stevens'):
            self.assertIn('esriGeometryPolygon', records[name]['source_inventory']['county_arcgis_rest']['finding'])

    def test_olmsted_scott_review_retains_static_evidence_and_existing_holds(self):
        records = load_parcel_access()
        olmsted = records['Olmsted']
        self.assertIn('gate', olmsted['source_inventory']['county_download']['finding'].lower())
        self.assertIn('cached', olmsted['source_inventory']['county_arcgis_rest']['finding'].lower())
        for name in ('Otter Tail', 'Pipestone', 'Polk', 'Pope', 'Renville', 'Rice', 'Scott'):
            self.assertIn('esriGeometryPolygon', records[name]['source_inventory']['county_arcgis_rest']['finding'])
        self.assertEqual(records['Otter Tail']['source_inventory']['county_arcgis_rest']['sources'][0]['layer_id'], 25)
        self.assertEqual(records['Polk']['source_inventory']['county_arcgis_rest']['sources'][0]['layer_id'], 0)
        held = {name for name, record in records.items()
                if record['monitoring']['decision'] == 'hold-for-terms'}
        self.assertEqual(held, {'Blue Earth', 'Brown', 'Faribault', 'Kandiyohi', 'Lincoln',
                               'Lake', 'Lyon', 'McLeod', 'Stevens', 'Swift', 'Wilkin'})

    def test_inventory_reviews_have_evidence_and_honest_blockers(self):
        from clearparcel.datawatch.parcel_access import INVENTORY_CATEGORIES
        records = load_parcel_access()
        reviewed = [r for r in records.values() if any(c['review_status'] != 'pending' for c in r['source_inventory'].values())]
        self.assertTrue(reviewed)
        for record in reviewed:
            urls = {e['url'] for e in record['evidence']}
            for key in INVENTORY_CATEGORIES:
                category = record['source_inventory'][key]
                with self.subTest(county=record['county'], category=key):
                    self.assertNotEqual(category['review_status'], 'pending')
                    self.assertEqual(category['review_date'], '2026-10-06')
                    self.assertTrue(category['evidence'])
                    self.assertTrue(set(category['evidence']) <= urls)
                    if category['review_status'] == 'blocked':
                        self.assertEqual(category['availability'], 'unknown')
                        self.assertEqual(category['sources'], [])
        for record in records.values():
            for category in record['source_inventory'].values():
                if category['review_status'] == 'pending':
                    self.assertIsNone(category['review_date'])
                    self.assertEqual(category['availability'], 'unknown')

    def migrated(self):
        from clearparcel.datawatch.parcel_access import migrate_parcel_access
        root = Path(__file__).parents[1] / "clearparcel/datawatch"
        index = json.loads((root / "minnesota_counties.json").read_text())["counties"]
        contacts = json.loads((root / "minnesota_county_contact_verification.json").read_text())["counties"]
        data = research_fixture()
        data["counties"][0]["county"] = "Aitkin"
        return migrate_parcel_access(data, index, {r["county"]: r["official_county_url"] for r in contacts})

    def test_v3_requires_exactly_87_canonical_counties(self):
        data = self.migrated()
        validate_parcel_access(data)
        self.assertEqual(len(data["counties"]), 87)
        for change in ("delete", "duplicate", "unknown"):
            bad = copy.deepcopy(data)
            if change == "delete":
                bad["counties"].pop()
            else:
                bad["counties"][-1]["county"] = "Aitkin" if change == "duplicate" else "Example"
            with self.assertRaises(ValueError):
                validate_parcel_access(bad)

    def test_inventory_categories_are_independent(self):
        data = self.migrated()
        record = data["counties"][0]
        self.assertEqual(record["source_inventory"]["county_arcgis_rest"]["availability"], "yes")
        for key in ("county_download", "mngeo_public_repository"):
            self.assertEqual(record["source_inventory"][key]["availability"], "unknown")
        category = record["source_inventory"]["county_download"]
        category.update(review_status="not-found", availability="no")
        with self.assertRaises(ValueError):
            validate_parcel_access(data)
        category.update(review_date="2026-10-06", evidence=[record["evidence"][0]["url"]], finding="Official parcel-specific download search found no download product.")
        validate_parcel_access(data)
        for key in ("count", "health", "last_checked"):
            bad = copy.deepcopy(data)
            bad["counties"][0]["source_inventory"]["county_download"][key] = 0
            with self.assertRaises(ValueError):
                validate_parcel_access(bad)

    def test_migration_preserves_evidence_without_inventing_reviews(self):
        data = self.migrated()
        original = research_fixture()["counties"][0]
        migrated = data["counties"][0]
        for key in ("evidence", "monitoring", "research_complete", "county_direct_classification"):
            self.assertEqual(migrated[key], original[key])
        self.assertTrue(all(not r["research_complete"] for r in data["counties"][1:]))
        self.assertTrue(all(r["statewide_open_coverage"]["available"] is None for r in data["counties"][1:]))
        self.assertTrue(all(c["review_status"] == "pending" for r in data["counties"][1:] for c in r["source_inventory"].values()))

    def test_migration_preserves_completed_legacy_records_and_holds(self):
        from clearparcel.datawatch.parcel_access import migrate_parcel_access, RECORD_FIELDS
        root = Path(__file__).parents[1] / "clearparcel/datawatch"
        legacy = {"schema_version": 2, "scope": "Preservation test", "counties": [
            {key: copy.deepcopy(record[key]) for key in RECORD_FIELDS}
            for record in load_parcel_access().values() if record["research_complete"]
        ]}
        index = json.loads((root / "minnesota_counties.json").read_text())["counties"]
        contacts = json.loads((root / "minnesota_county_contact_verification.json").read_text())["counties"]
        result = migrate_parcel_access(legacy, index, {r["county"]: r["official_county_url"] for r in contacts})
        migrated = {r["county"]: r for r in result["counties"]}
        self.assertEqual(len(legacy["counties"]), sum(r['research_complete'] for r in load_parcel_access().values()))
        for original in legacy["counties"]:
            self.assertEqual({k: migrated[original["county"]][k] for k in RECORD_FIELDS}, original)
        self.assertEqual(
            {name for name, r in migrated.items() if r["monitoring"]["decision"] == "hold-for-terms"},
            {r["county"] for r in legacy["counties"] if r["monitoring"]["decision"] == "hold-for-terms"},
        )
        for r in result["counties"]:
            for category in r["source_inventory"].values():
                self.assertEqual(category["review_status"], "pending")
                self.assertNotEqual(category["availability"], "no")

    def test_inventory_sources_reject_unknown_evidence_and_unsafe_links(self):
        data = self.migrated()
        source = data["counties"][0]["source_inventory"]["county_arcgis_rest"]["sources"][0]
        for key, value in (("evidence", ["https://unreviewed.example"]), ("approved_public_links", [{"label": "GIS", "href": "https://county.example?token=secret"}]), ("count", 123)):
            bad = copy.deepcopy(data)
            bad["counties"][0]["source_inventory"]["county_arcgis_rest"]["sources"][0][key] = value
            with self.assertRaises(ValueError):
                validate_parcel_access(bad)
        self.assertIsNone(source.get("monitored_source_id"))

    def test_public_classification_and_safe_links(self):
        from clearparcel.datawatch.public_values import public_access_classification, safe_public_url
        record = research_fixture()["counties"][0]
        self.assertEqual(public_access_classification(record), "OPEN")
        record["county_direct_classification"] = "fee-based-parcel-data"
        self.assertEqual(public_access_classification(record), "FEE BASED")
        record["county_direct_classification"] = "parcel-viewer-only"
        self.assertEqual(public_access_classification(record), "AMBIGUOUS")
        self.assertEqual(public_access_classification(None), "AMBIGUOUS")
        self.assertEqual(safe_public_url("https://county.example/gis"), "https://county.example/gis")
        for url in ("https://user:pass@example.com", "http://127.0.0.1", "http://10.0.0.1", "http://[::1]", "https://localhost", "https://server.internal", "https://server", "https://county.example?token=secret", "https://county.example?api_key=secret"):
            self.assertIsNone(safe_public_url(url), url)

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

    def test_minnesota_audit_completed_records_have_official_evidence(self):
        records = load_parcel_access()
        self.assertEqual(len(records), 87)
        records = {name: r for name, r in records.items() if r["research_complete"]}
        self.assertTrue(records)
        self.assertTrue(all(record["research_complete"] for record in records.values()))
        self.assertTrue(all(record["evidence"] for record in records.values()))
        self.assertTrue(all(
            all(area["status"] not in {"pending", "blocked"} for area in record["review_log"].values())
            for record in records.values()
        ))
        self.assertTrue(all(r['county_direct_classification'] in CLASSIFICATIONS for r in records.values()))
        self.assertTrue(records["Winona"]["statewide_open_coverage"]["available"])
        self.assertEqual(
            records["Winona"]["county_direct_classification"],
            "fee-based-parcel-data",
        )

    def test_policy_conflict_endpoints_are_held_for_terms(self):
        records = load_parcel_access()
        held = {"Blue Earth", "Brown", "Faribault", "Kandiyohi", "Lincoln"}

        self.assertTrue(held.issubset(
            {name for name, record in records.items() if record["monitoring"]["decision"] == "hold-for-terms"}
        ))
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
        self.assertTrue(direct)
        self.assertTrue(all(r["county_direct_classification"] == "free-parcel-data" for r in direct))
        self.assertTrue(all(r["monitoring"]["decision"] in {"candidate-low-frequency", "not-assessed", "hold-for-terms"} for r in direct))
        for record in direct:
            if record["monitoring"]["decision"] == "hold-for-terms":
                self.assertTrue(record["monitoring"]["terms_urls"])
        fee_records = [r for r in records.values() if r["county_direct_classification"] == "fee-based-parcel-data"]
        self.assertTrue(fee_records)
        self.assertTrue(all(r["fee_policy_url"] and r["parcel_dataset_fee"] and r["fee_product"] for r in fee_records))
        self.assertTrue(all(not r["usable_direct_machine_readable_source"] for r in fee_records))


if __name__ == "__main__":
    unittest.main()
