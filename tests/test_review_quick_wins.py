"""Regressions for the Oct 23, 2026 review quick wins (P2-01, P2-08, P2-09, P3-02)."""
import os
import re
import shutil
import subprocess
import unittest
from unittest.mock import patch

from clearparcel.datawatch import analytics, gac_standards, public_dashboard
from clearparcel.datawatch.public_projection import sanitize_public_render_state
from clearparcel.datawatch.public_values import sanitize_item_metadata
from clearparcel.datawatch.watch import _arcgis_gac_metadata, _gac_bool

NODE_AVAILABLE = bool(shutil.which('node')) or os.environ.get('WATCHTOWER_REQUIRE_NODE') == '1'


class GacBoolTests(unittest.TestCase):
    def test_numeric_and_textual_flags(self):
        cases = [(0, False), (1, True), ("0", False), ("1", True), (False, False), (True, True),
                 ("no", False), ("Yes", True), (None, None), ("", None), (2, None), (-1, None),
                 ("maybe", None), (0.0, None), ([], None), ({}, None)]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertIs(_gac_bool(value), expected)

    def test_numeric_zero_survives_metadata_and_county_explanation(self):
        from clearparcel.datawatch import dashboard, dashboard_gac
        rows = {"features": [{"attributes": {"county_name": "Douglas", "ng911_upload": 1, "gac_open": 0}}]}
        with patch("clearparcel.datawatch.watch._json_request", return_value=(rows, {"status": 200})):
            records = _arcgis_gac_metadata("https://example.invalid/FeatureServer/0", 5, standard_key="address")
        self.assertIs(records["Douglas"]["gac_open"], False)
        self.assertIs(records["Douglas"]["ng911_upload"], True)
        data = {"counties": {}, "county_metadata": records}
        with patch.object(dashboard, "_gac_data", return_value=data):
            html = dashboard_gac._render_county_gac_summaries({}, {"name": "Douglas"})
        self.assertIn("NG911 participant · not opted into public GAC data", html)


class ItemMetadataStatusTests(unittest.TestCase):
    def test_non_string_statuses_are_unavailable_not_errors(self):
        for status in ([], {}, None, 3, "unknown-status"):
            with self.subTest(status=status):
                self.assertIsNone(sanitize_item_metadata({"status": status, "publication_date": "2026-01-02"}))
        self.assertEqual(sanitize_item_metadata({"status": "ok", "publication_date": "2026-01-02"}),
                         {"status": "ok", "publication_date": "2026-01-02"})

    def test_full_catalog_projection_survives_malformed_status(self):
        state = {"sources": {"mn-parcel-county-catalog": {
            "status": "ok", "county_records": {
                "Douglas": {"item_metadata": {"status": ["held"]}, "gac_open_approval": "yes"},
                "Rice": {"item_metadata": {"status": "ok", "revision_date": "2026-02-03"}}}}}}
        records = sanitize_public_render_state(state)["sources"]["mn-parcel-county-catalog"]["county_records"]
        self.assertNotIn("item_metadata", records["Douglas"])
        self.assertEqual(records["Douglas"]["gac_open_approval"], "yes")
        self.assertEqual(records["Rice"]["item_metadata"], {"status": "ok", "revision_date": "2026-02-03"})


class AnalyticsUrlTests(unittest.TestCase):
    BASE = {"WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED": "true",
            "WATCHTOWER_POSTHOG_PROJECT_TOKEN": "phc_synthetic_token"}

    def config(self, **extra):
        with patch.dict(os.environ, {**self.BASE, **extra}, clear=False):
            for key in ("WATCHTOWER_POSTHOG_HOST", "WATCHTOWER_POSTHOG_SCRIPT_URL"):
                if key not in extra:
                    os.environ.pop(key, None)
            return analytics.posthog_config(), analytics.posthog_csp_sources()

    def test_malformed_hosts_and_script_urls_disable_analytics(self):
        for host in ("https://example.com:notaport", "https://example.com:99999", "https://[::1",
                     "https://[not-ipv6]/", "http://us.i.posthog.com"):
            with self.subTest(host=host):
                self.assertEqual(self.config(WATCHTOWER_POSTHOG_HOST=host), (None, None))
        for script in ("https://cdn.example.com:bad/static/array.js", "https://[::1/array.js",
                       "https://cdn.example.com/static/other.js"):
            with self.subTest(script=script):
                self.assertEqual(self.config(WATCHTOWER_POSTHOG_SCRIPT_URL=script), (None, None))

    def test_valid_configuration_still_enables(self):
        config, _ = self.config(WATCHTOWER_POSTHOG_HOST="https://us.i.posthog.com")
        self.assertEqual(config["api_host"], "https://us.i.posthog.com")
        config, _ = self.config(WATCHTOWER_POSTHOG_HOST="https://ph.example.com:8443",
                                WATCHTOWER_POSTHOG_SCRIPT_URL="https://cdn.example.com/static/array.js")
        self.assertEqual(config["api_host"], "https://ph.example.com:8443")
        self.assertEqual(config["script_origin"], "https://cdn.example.com")

    def test_page_and_csp_generation_survive_a_bad_port(self):
        from clearparcel.datawatch.dashboard_templates import _public_layout_v2
        with patch.dict(os.environ, {**self.BASE, "WATCHTOWER_POSTHOG_HOST": "https://example.com:notaport"}):
            page = _public_layout_v2("Synthetic", "<p>body</p>")
        self.assertIn("<p>body</p>", page)
        self.assertNotIn("posthog", page.lower())


class FieldCountLabelTests(unittest.TestCase):
    def test_counts_come_from_the_bundled_standard(self):
        self.assertEqual(gac_standards.standard_field_counts("parcel"),
                         {"fields": 91, "mandatory": 7, "mandatory_words": "seven"})
        changed = {"fields": [{"inclusion": "Mandatory"}] * 3 + [{"inclusion": "Optional"}] * 9}
        self.assertEqual(gac_standards.standard_field_counts(schema=changed),
                         {"fields": 12, "mandatory": 3, "mandatory_words": "three"})
        many = {"fields": [{"inclusion": "Mandatory"}] * 14}
        self.assertEqual(gac_standards.standard_field_counts(schema=many)["mandatory_words"], "14")

    def test_gac_page_labels_follow_a_changed_schema(self):
        from clearparcel.datawatch import dashboard, dashboard_gac
        changed = {"standard": {"name": "Synthetic"}, "fields": [
            {"field": f"F{i}", "label": f"F{i}", "inclusion": "Mandatory" if i < 3 else "Optional"} for i in range(12)]}
        data = {"standard_key": "parcel", "standard": changed["standard"], "field_count": 12,
                "covered_counties": 0, "fields": {}, "counties": {}}
        with patch.object(dashboard, "_load_mngac_schema", return_value=changed), \
                patch.object(dashboard, "_mngac_data", return_value=data), \
                patch.object(dashboard, "_dashboard_state", return_value={"sources": {}}):
            page = dashboard_gac.render_mngac({"_public_mode": True}, "parcel", view="statewide")
        self.assertIn("All 12 fields", page)
        self.assertIn("the three mandatory fields", page)
        self.assertNotIn("All 91 fields", page)

    @unittest.skipUnless(NODE_AVAILABLE, "JavaScript execution requires Node.js")
    def test_missing_or_zero_denominator_is_unavailable(self):
        import inspect
        text = inspect.getsource(public_dashboard)
        expression = re.search(r"fields\.textContent=(\(d\.fields.*?);\n", text).group(1)
        self.assertNotIn("||91", expression.replace(" ", ""))
        script = ("const out=[];for(const d of [{fields:37,field_count:91},{fields:37},{fields:null,field_count:0},"
                  "{fields:5,field_count:'91'}]){out.push(" + expression + ")}console.log(JSON.stringify(out))")
        result = subprocess.run(["node", "-e", script], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(result.stdout.strip(), '["37 / 91","37 / —","— / —","5 / —"]')


if __name__ == "__main__":
    unittest.main()
