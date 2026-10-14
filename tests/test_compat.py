"""Names that v0.2.3 exposed must keep resolving (private wrappers import them)."""
import importlib
import unittest

from clearparcel.datawatch import _compat

# Every module attribute present in v0.2.3 and absent from the current modules,
# found by comparing vars() of each clearparcel.datawatch module.
V023_REMOVED = {
    "county_profile_exports": ["re"],
    "county_profile_panel": ["_json"],
    "county_profiles": ["provider_edit_timestamp"],
    "dashboard": ["MNGAC_FIELDS_FILE", "NO_DATA_COLOR", "PERCENT_COLORS", "_county_mngac_summary", "_csv_safe",
                  "_gac_xlsx_sheets", "_mngac_xlsx_sheets", "_refresh_script", "_xlsx_col_name",
                  "_xlsx_sheet_xml", "percentage_color_js", "percentage_legend", "profile_time", "re",
                  "render_county_profile_panel"],
    "dashboard_exports": ["re"],
    "dashboard_gac": ["_county_mngac_summary"],
    "parcel_access": ["public_access_classification"],
    "public_dashboard": ["_approval", "_catalog_date", "_county_monitoring_counts", "_project", "_public_count",
                         "_public_date", "_public_number", "_public_status", "_records",
                         "_sanitize_catalog_records", "_sanitize_completeness", "_sanitize_gac",
                         "_sanitize_mngac", "_snapshot_csv"],
    "watch": ["MNGAC_FIELDS_FILE", "_destination_publicity", "_load_mngac_schema", "sys"],
}


class CompatTests(unittest.TestCase):
    def test_every_v023_attribute_still_resolves(self):
        for module_name, names in V023_REMOVED.items():
            module = importlib.import_module("clearparcel.datawatch." + module_name)
            for name in names:
                with self.subTest(module=module_name, name=name):
                    self.assertIsNotNone(getattr(module, name))
                    exec(f"from clearparcel.datawatch.{module_name} import {name}", {})

    def test_map_covers_exactly_the_removed_names(self):
        self.assertEqual({m: sorted(n) for m, n in _compat.LEGACY.items()},
                         {m: sorted(n) for m, n in V023_REMOVED.items()})

    def test_moved_names_are_the_current_objects(self):
        from clearparcel.datawatch import dashboard, dashboard_exports, public_dashboard, public_projection
        from clearparcel.datawatch.county_profile_panel import percentage_legend
        self.assertIs(dashboard._csv_safe, dashboard_exports._csv_safe)
        self.assertIs(dashboard.percentage_legend, percentage_legend)
        self.assertIs(public_dashboard._sanitize_mngac, public_projection._sanitize_mngac)

    def test_restored_helpers_behave_as_before(self):
        from clearparcel.datawatch import county_profile_panel, dashboard, watch
        self.assertEqual(county_profile_panel._json({"a": "<b>&"}), '{"a": "\\u003cb\\u003e\\u0026"}')
        self.assertEqual(watch._load_mngac_schema()["standard"]["short_name"],
                         importlib.import_module("clearparcel.datawatch.gac_standards").load_gac_standard("parcel")["standard"]["short_name"])
        self.assertTrue(watch.MNGAC_FIELDS_FILE.is_file())
        self.assertFalse(watch._destination_publicity("http://localhost/x"))
        self.assertTrue(watch._destination_publicity("https://93.184.216.34/x"))
        summary = dashboard._county_mngac_summary({}, {"name": "Douglas"})
        self.assertEqual(set(summary), {"data", "county", "source_id", "source", "checked_at"})

    def test_unknown_names_still_raise_attribute_error(self):
        from clearparcel.datawatch import dashboard, watch
        for module in (dashboard, watch):
            with self.assertRaises(AttributeError):
                getattr(module, "definitely_not_a_name")
            self.assertIsNone(getattr(module, "definitely_not_a_name", None))


if __name__ == "__main__":
    unittest.main()
