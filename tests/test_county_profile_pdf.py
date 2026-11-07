import importlib.util
import io
import unittest

from clearparcel.datawatch.county_profile_pdf import county_profile_pdf


@unittest.skipUnless(importlib.util.find_spec("reportlab") and importlib.util.find_spec("pypdf"), "PDF extras required")
class CountyProfilePdfTests(unittest.TestCase):
    def test_pdf_is_three_page_summary_with_links_and_private_content_excluded(self):
        from pypdf import PdfReader

        snapshot = {
            "county": "Synthetic Échantillon",
            "status": "current",
            "parcel_source_profile": {
                "county": {"name": "Synthetic Échantillon", "slug": "synthetic", "fips": "27001"},
                "monitoring": {"reporting": "current"},
                "access": {"public_classification": "Historical finding"},
                "county_directory": {"correspondence": "PRIVATE_SENTINEL"},
                "direct_gac_schema": [{"field": "SCHEMA_LAST_FIELD"}],
            },
            "county_directory": {
                "public_revision": 4, "published_at": "2026-11-06T16:00:00+00:00",
                "contacts": [{"name": "Example contact"}], "access": {},
                "policy": {"text": ("Public long policy text. " * 260) + " POLICY_END",
                           "url": "https://example.org/official"},
                "correspondence": [{"note": "PRIVATE_SENTINEL"}],
            },
            "gac": {"road": {"county": {"fields": [{"field": f"ROAD_FIELD_{i:03}"} for i in range(90)]}}},
            "direct_sources": [{"name": "Public source", "worker": "PRIVATE_SENTINEL"}],
            "parcel_access": {"monitoring_assessment": {"reason": "PRIVATE_SENTINEL"}},
        }
        pdf = county_profile_pdf(snapshot)
        self.assertIs(pdf, county_profile_pdf(snapshot))
        reader = PdfReader(io.BytesIO(pdf))
        self.assertEqual(len(reader.pages), 3)
        extracted = "\n".join(page.extract_text() for page in reader.pages)
        for expected in ("Échantillon", "County GIS", "MN GAC field summaries",
                         "Example contact", "full text online"):
            self.assertIn(expected, extracted)
        for omitted in ("PRIVATE_SENTINEL", "POLICY_END", "ROAD_FIELD_089", "SCHEMA_LAST_FIELD", "Historical finding"):
            self.assertNotIn(omitted, extracted)
        links = [annotation.get_object().get("/A", {}).get("/URI")
                 for page in reader.pages for annotation in page.get("/Annots", [])]
        self.assertIn("https://example.org/official", links)
        snapshot["county_directory"]["policy"]["text"] = "New confirmed policy"
        snapshot["county_directory"]["public_revision"] = 5
        updated = county_profile_pdf(snapshot)
        self.assertNotEqual(pdf, updated)
        updated_text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(updated)).pages)
        self.assertIn("New confirmed policy", updated_text)
        self.assertNotIn("POLICY_END", updated_text)

    def test_long_contacts_and_missing_metrics_stay_bounded(self):
        from pypdf import PdfReader
        snapshot = {"county": "Long County Name " * 5,
                    "county_directory": {"contacts": [{"name": "Name " * 1000, "email": "x" * 1000} for _ in range(20)],
                                         "policy": {"text": "Policy " * 10000}},
                    "parcel_source_profile": {"county": {"slug": "synthetic"}}}
        pdf = county_profile_pdf(snapshot)
        r = PdfReader(io.BytesIO(pdf))
        self.assertEqual(len(r.pages), 3)
        text = "\n".join(p.extract_text() for p in r.pages)
        self.assertIn("17 additional contacts online", text)
        self.assertIn("No data", text)
        self.assertNotIn("0.00%", text)
        for page in r.pages:
            self.assertIn("GIS Data Watchtower", page.extract_text())
            self.assertEqual(len(page.images), 1)

    def test_statewide_metrics_show_population_and_selected_mandatory_gaps(self):
        from pypdf import PdfReader
        snapshot = {"county": "Synthetic", "gac": {"parcel": {"county": {
            "record_count": 100, "field_count": 91, "scanned_field_count": 91,
            "mandatory_field_count": 7, "mandatory_fields_full": 4,
            "mandatory_population_percent": 57.14,
            "fields": {"CTU_NAME": {"present_in_source_schema": True, "population_scanned": True, "percent": 0},
                       "PRIVATE_FIELD": {"note": "PRIVATE_SENTINEL"}}}}}}
        text = PdfReader(io.BytesIO(county_profile_pdf(snapshot))).pages[2].extract_text()
        self.assertIn("57.14%", text)
        self.assertIn("CTU Name: 0.00%", text)
        self.assertIn("100 records", text)
        self.assertIn("91 of 91 standard fields", text)
        self.assertNotIn("PRIVATE_SENTINEL", text)
