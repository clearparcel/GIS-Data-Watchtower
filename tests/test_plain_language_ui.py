"""Public simplification preserves access and check freshness boundaries."""
import copy
import datetime as dt
import re
import unittest

from clearparcel.datawatch.county_directory import project_public_county
from clearparcel.datawatch.county_directory_view import county_access_summary, published_access_summary
from clearparcel.datawatch.county_profiles import county_identities
from clearparcel.datawatch.dashboard_counties import render_counties
from tests.html_text import metric


class PlainLanguageUITests(unittest.TestCase):
    def test_recent_source_with_overdue_worker_is_not_counted_as_being_checked(self):
        now = dt.datetime.now(dt.UTC)
        state = {"generated_at": now.isoformat(), "sources": {"synthetic": {
            "id": "synthetic", "name": "Synthetic county parcels", "county_slug": "wabasha",
            "category": "Parcels", "status": "ok", "worker": "cloud",
            "checked_at": now.isoformat(), "last_success_at": now.isoformat()}},
            "workers": {"cloud": {"last_report_at": now.isoformat(), "overall": "ok", "source_count": 1}}}
        config = {"_render_state": state, "_public_mode": True, "state_file": "unused.json"}
        self.assertEqual(metric(render_counties(config), "Counties being checked"), "1")
        state["workers"]["cloud"]["last_report_at"] = (now - dt.timedelta(days=3)).isoformat()
        before = copy.deepcopy(state)
        page = render_counties(config)
        self.assertEqual(metric(page, "Counties being checked"), "0")
        self.assertIn("Counties with a source for checks: 1. Checks overdue: 1.", page)
        row = re.search(r'<tr data-name="wabasha".*?</tr>', page, re.S).group()
        self.assertIn("Check overdue", row)
        self.assertEqual(state, before)

    def test_county_column_does_not_treat_a_statewide_link_as_a_county_download(self):
        county = county_identities()["aitkin"]
        directory = project_public_county(county, {"fips": county["fips"], "access": {
            "parcel_polygons": {"classification": "open", "methods": [{
                "kind": "mngeo_open", "url": "https://example.org/statewide",
                "scope": "Synthetic statewide data", "evidence_date": "2026-11-07"}]}}})
        before = copy.deepcopy(directory)
        self.assertEqual(county_access_summary(directory), "Only a statewide link is listed")
        # The existing machine-readable/export summary retains its vocabulary.
        self.assertEqual(published_access_summary(directory), "Open GIS Data · MnGeo open")
        self.assertEqual(directory, before)

    def test_check_status_filter_includes_paused_and_permission_states(self):
        page = render_counties({"_render_state": {"sources": {}}, "_public_mode": True})
        select = re.search(r'<select id="cs".*?</select>', page, re.S).group()
        self.assertIn('value="paused"', select)
        self.assertIn('value="awaiting-permission"', select)
        self.assertIn('id="counties-no-results" hidden role="status"', page)
