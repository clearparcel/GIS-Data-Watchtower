import importlib.util
import io
import unittest

from clearparcel.datawatch.county_profile_pdf import county_profile_pdf


@unittest.skipUnless(importlib.util.find_spec("reportlab") and importlib.util.find_spec("pypdf"), "PDF extras required")
class CountyProfilePdfTests(unittest.TestCase):
    def test_pdf_is_paginated_searchable_and_contains_links_and_all_field_rows(self):
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
        self.assertGreater(len(reader.pages), 2)
        extracted = "\n".join(page.extract_text() for page in reader.pages)
        for expected in ("Échantillon", "POLICY_END", "ROAD_FIELD_089", "SCHEMA_LAST_FIELD",
                         "Example contact", "Public source", "Public revision",
                         "Packaged parcel access research", "Packaged access research", "Historical finding"):
            self.assertIn(expected, extracted)
        self.assertNotIn("PRIVATE_SENTINEL", extracted)
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
