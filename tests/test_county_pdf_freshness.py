"""County PDFs carry the stale-cache note, monitoring status and each standard's observation date."""
import datetime as dt
import importlib.util
import io
import unittest

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.county_profile_pdf import county_profile_pdf

NOTE = "Showing the last available monitoring snapshot."


def snapshot(**extra):
    return {"county": "Synthetic", "status": "overdue", "snapshot_created_central": "2026-11-12T09:00:00-06:00",
            "parcel_source_profile": {"county": {"slug": "synthetic"}, "monitoring": {}},
            "gac": {"road": {"observed_at": "2026-09-01T12:00:00+00:00", "retained": True,
                             "county": {"record_count": 10, "mandatory_population_percent": 99.0}},
                    "address": {"observed_at": "2026-11-11T12:00:00+00:00", "retained": False,
                                "county": {"record_count": 5}}}, **extra}


@unittest.skipUnless(importlib.util.find_spec("reportlab") and importlib.util.find_spec("pypdf"), "PDF extras required")
class CountyPdfFreshnessTests(unittest.TestCase):
    def text(self, pdf):
        from pypdf import PdfReader
        return [page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages]

    def test_stale_cache_note_changes_the_pdf_and_appears_on_every_page(self):
        normal = county_profile_pdf(snapshot())
        stale = county_profile_pdf(snapshot(snapshot_note=NOTE))
        self.assertNotEqual(normal, stale)
        for page in self.text(stale):
            self.assertIn(NOTE, page)
        for page in self.text(normal):
            self.assertNotIn(NOTE, page)

    def test_each_standard_shows_its_own_observation_date_and_retained_state(self):
        pages = self.text(county_profile_pdf(snapshot()))
        self.assertEqual(len(pages), 3)
        gac = pages[2]
        self.assertIn("Observed 2026-09-01", gac)
        self.assertIn("Observed 2026-11-11", gac)
        self.assertIn("Earlier result kept", gac)
        self.assertIn("Observed date unavailable", gac)  # parcel: no observation supplied
        self.assertIn("PDF created from public snapshot", pages[0])

    def test_monitoring_status_is_rendered(self):
        self.assertIn("Check overdue", self.text(county_profile_pdf(snapshot()))[1])


class CountySnapshotObservationTests(unittest.TestCase):
    def test_county_snapshot_gac_payload_carries_observation_context(self):
        stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).replace(microsecond=0).isoformat()
        state = {"generated_at": stamp, "sources": {"mn-state-parcels": {
            "id": "mn-state-parcels", "category": "Parcels", "status": "error", "checked_at": stamp,
            "last_success_at": "2026-09-01T12:00:00+00:00", "gac_check_status": "error",
            "mngac_completeness": {"fields": {"PIN": {}}, "counties": {"Aitkin": {"record_count": 3}}}}}}
        config = {"_render_state": state, "state_file": "unused.json"}
        value = dashboard._county_snapshot(config, "aitkin", state=dashboard._dashboard_state(config))
        parcel = value["gac"]["parcel"]
        self.assertEqual(parcel["observed_at"], "2026-09-01T12:00:00+00:00")
        self.assertEqual(parcel["latest_attempt_at"], stamp)
        self.assertTrue(parcel["retained"])


if __name__ == "__main__":
    unittest.main()
