"""Regression tests for public-accuracy fixes (review package 3)."""
import datetime as dt
import re
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

from clearparcel.datawatch import dashboard, dashboard_views, public_dashboard
from clearparcel.datawatch.county_profile_panel import profile_time
from clearparcel.datawatch.dashboard import render_mngac
from clearparcel.datawatch.dashboard_exports import _gac_xlsx_sheets, _xlsx_sheet_xml
from clearparcel.datawatch.dashboard_refresh import _SCRIPT
from clearparcel.datawatch.gac_standards import load_gac_standard
from clearparcel.datawatch.public_values import provider_edit_date, spreadsheet_cell, spreadsheet_text


class TableShape(HTMLParser):
    """Collect, per table, the header width and each body row's cell count.

    State is kept per table so nested tables cannot disturb an outer table.
    The header width is the widest header row (multi-row headers are not
    summed); body rows are any rows outside <thead>.
    """

    def __init__(self):
        super().__init__()
        self.tables, self._stack = [], []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append({"id": dict(attrs).get("id"), "headers": 0, "rows": [],
                                "section": None, "row": None, "row_is_header": False})
            return
        if not self._stack:
            return
        table = self._stack[-1]
        if tag in ("thead", "tbody", "tfoot"):
            table["section"] = tag
        elif tag == "tr":
            table["row"], table["row_is_header"] = 0, table["section"] == "thead"
        elif tag in ("td", "th") and table["row"] is not None:
            table["row"] += int(dict(attrs).get("colspan") or 1)

    def handle_endtag(self, tag):
        if not self._stack:
            return
        table = self._stack[-1]
        if tag == "tr" and table["row"] is not None:
            if table["row_is_header"]:
                table["headers"] = max(table["headers"], table["row"])
            else:
                table["rows"].append(table["row"])
            table["row"] = None
        elif tag in ("thead", "tbody", "tfoot"):
            table["section"] = None
        elif tag == "table":
            self.tables.append(self._stack.pop())


def assert_table_shapes(test, page):
    parser = TableShape()
    parser.feed(page)
    checked = 0
    for table in parser.tables:
        if not table["headers"]:
            continue
        for cells in table["rows"]:
            test.assertEqual(cells, table["headers"], f"table {table['id']!r}: row has {cells} cells for {table['headers']} headers")
        checked += 1
    return checked


def parcel_state():
    schema = load_gac_standard("parcel")
    fields = {}
    for spec in schema["fields"][:3]:
        fields[spec["field"]] = {**spec, "present_in_source_schema": True, "population_scanned": True,
                                 "populated": 90, "record_count": 100, "percent": 90.0, "county_median_percent": 88.0,
                                 "counties_with_values": 2}
    missing = schema["fields"][3]
    fields[missing["field"]] = {**missing, "present_in_source_schema": False, "population_scanned": False}
    data = {"standard_key": "parcel", "standard": schema["standard"], "population_scope": "all",
            "record_count": 100, "field_count": len(schema["fields"]), "covered_counties": 2,
            "field_population_percent": 40.0, "mandatory_population_percent": 80.0,
            "observed_at": "2026-10-09T14:00:00+00:00", "fields": fields,
            "counties": {"Douglas": {"record_count": 60, "field_population_percent": 40.0},
                         "Wabasha": {"record_count": 40, "field_population_percent": 42.0}}}
    return {"sources": {"mn-state-parcels": {"status": "ok", "mngac_completeness": data}}}, missing


class TableShapeTests(unittest.TestCase):
    def test_statewide_parcel_field_table_has_one_cell_per_header(self):
        state, missing = parcel_state()
        with patch("clearparcel.datawatch.dashboard._dashboard_state", return_value=state):
            page = render_mngac({"_public_mode": True}, "parcel", view="statewide")
        self.assertIn('id="mngac-fields"', page)
        self.assertGreaterEqual(assert_table_shapes(self, page), 1)
        row = re.search(r'<tr data-name="[^"]*' + re.escape(missing["field"].lower()) + r'".*?</tr>', page, re.S).group(0)
        self.assertIn("<td>Missing</td><td>Not scanned</td>", row)
        self.assertIn("<td>—</td>", row)  # no counties statistic: not "0/87"

    def test_tables_on_gac_and_counties_pages_have_consistent_columns(self):
        state, _ = parcel_state()
        config = {"_public_mode": True, "_render_state": state, "state_file": "unused.json"}
        checked = 0
        for key in ("parcel", "address", "road"):
            for view in ("statewide", "county"):
                with self.subTest(standard=key, view=view), \
                        patch("clearparcel.datawatch.dashboard._dashboard_state", return_value=state):
                    checked += assert_table_shapes(self, render_mngac(config, key, view=view))
        with self.subTest(page="counties"):
            from clearparcel.datawatch.dashboard_counties import render_counties
            checked += assert_table_shapes(self, render_counties(config))
        self.assertGreaterEqual(checked, 2)

    def test_parser_isolates_nested_tables(self):
        page = ("<table id='outer'><thead><tr><th>a</th><th>b</th></tr></thead><tbody>"
                "<tr><td><table><thead><tr><th>x</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table></td><td>2</td></tr>"
                "<tr><td>3</td></tr></tbody></table>")
        parser = TableShape()
        parser.feed(page)
        outer = next(t for t in parser.tables if t["id"] == "outer")
        self.assertEqual((outer["headers"], outer["rows"]), (2, [2, 1]))


class CalendarDateTests(unittest.TestCase):
    def test_date_only_catalog_values_keep_their_calendar_day(self):
        self.assertEqual(provider_edit_date(1735689600000), "2025-01-01")  # 2025-01-01T00:00Z
        self.assertIsNone(provider_edit_date("1735689600000"))
        self.assertEqual(profile_time(provider_edit_date(1735689600000)), "2025-01-01")
        self.assertEqual(dashboard._format_arcgis_date(1735689600000)[:10], "2025-01-01")


class OverdueStatusTests(unittest.TestCase):
    def status_for(self, checked_at):
        state = {"generated_at": checked_at, "sources": {"mn-todd-parcels": {
            "id": "mn-todd-parcels", "county_slug": "todd", "category": "Parcels", "status": "ok",
            "checked_at": checked_at, "last_report_at": checked_at, "last_success_at": checked_at}}}
        config = {"_render_state": state, "state_file": "unused.json"}
        state = dashboard._dashboard_state(config)
        research = dashboard.load_parcel_access()
        profiles = dashboard._county_profiles(config, state, research)
        county = next(c for c in dashboard._load_counties() if c["slug"] == "todd")
        return dashboard._county_status(config, county, state, profiles=profiles, research=research)

    def test_healthy_but_overdue_county_is_not_actively_checked(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).isoformat()
        info = self.status_for(old)
        self.assertEqual(info["status"], "overdue")
        self.assertEqual(dashboard._friendly_status("overdue"), "Check overdue")
        self.assertTrue(info["actively_monitored"])  # the path exists; only its age changed

    def test_counties_card_counts_paths_and_states_overdue(self):
        from clearparcel.datawatch.dashboard_counties import render_counties
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).isoformat()
        state = {"generated_at": old, "sources": {"mn-todd-parcels": {
            "id": "mn-todd-parcels", "county_slug": "todd", "category": "Parcels", "status": "ok",
            "checked_at": old, "last_report_at": old, "last_success_at": old}}}
        page = render_counties({"_render_state": state, "state_file": "unused.json"})
        self.assertIn("Counties with a monitoring path", page)
        self.assertIn("1 of these is overdue for a new check.", page)
        self.assertNotIn("Counties actively checked", page)

    def test_recent_check_is_actively_checked(self):
        info = self.status_for(dt.datetime.now(dt.timezone.utc).isoformat())
        self.assertEqual(info["status"], "ok")


class FreshnessCacheTests(unittest.TestCase):
    def test_cache_key_changes_with_time_even_when_state_bytes_do_not(self):
        with patch.object(public_dashboard.time, "time", return_value=1_000_000.0):
            first = public_dashboard._freshness_bucket()
        with patch.object(public_dashboard.time, "time", return_value=1_000_000.0 + public_dashboard.FRESHNESS_RECOMPUTE_SECONDS):
            later = public_dashboard._freshness_bucket()
        self.assertNotEqual(first, later)

    def test_publication_status_uses_central_time(self):
        self.assertNotIn("toLocaleString()", _SCRIPT)
        self.assertIn("timeZone:'America/Chicago'", _SCRIPT)


class CountyDirectParcelTests(unittest.TestCase):
    def test_sources_are_identified_by_category_and_county_not_id_suffix(self):
        self.assertTrue(dashboard_views._county_direct_parcels("mn-wabasha-parcels", {"category": "Parcels", "county_slug": "wabasha"}))
        self.assertTrue(dashboard_views._county_direct_parcels("mn-rice-parcels-direct", {}))
        self.assertFalse(dashboard_views._county_direct_parcels("mngeo-parcels-open", {"category": "Parcels"}))
        self.assertFalse(dashboard_views._county_direct_parcels("mn-x-address", {"category": "Address Points", "county_slug": "x"}))


class ContactTests(unittest.TestCase):
    def test_no_placeholder_contacts_and_county_authority_requires_a_way_to_reach_someone(self):
        records = dashboard._load_county_contact_records()
        for county, record in records.items():
            for contact in record["contacts"]:
                self.assertNotIn(str(contact.get("name") or "").strip().upper(), {"TBD", "TBA"}, county)
            if record["authority"] == "county":
                self.assertTrue(any(dashboard._reachable(c) for c in record["contacts"]), county)
        self.assertTrue(any(dashboard._reachable(c) for c in records["Mahnomen"]["contacts"]))

    def test_listed_contacts_keeps_named_people_without_contact_details(self):
        listed = dashboard._listed_contacts([{"name": "TBD"}, {"name": "Jane Doe"}, {"name": "", "phone": "507"}])
        self.assertEqual([c.get("name") for c in listed], ["Jane Doe", ""])


class ExportTests(unittest.TestCase):
    def test_xlsx_text_has_no_formula_guard_apostrophe_but_csv_does(self):
        self.assertEqual(spreadsheet_text("+1 507-555-0100"), "+1 507-555-0100")
        self.assertEqual(spreadsheet_text("-"), "-")
        self.assertTrue(spreadsheet_cell("=SUM(A1)").startswith("'"))
        xml = _xlsx_sheet_xml([["+1 507", "=1+1"]])
        self.assertIn(">+1 507<", xml)
        self.assertIn('t="inlineStr"', xml)

    def test_gac_detail_population_scanned_column_reports_the_scan(self):
        # Real shape (watch.py): statewide field summaries carry the flag;
        # per-county entries exist only for scanned fields and carry no flag.
        schema = load_gac_standard("address")
        scanned, unscanned = schema["fields"][0]["field"], schema["fields"][1]["field"]
        snapshot = {"gac": {"address": {"standard": schema["standard"],
            "fields": {scanned: {"population_scanned": True}, unscanned: {"population_scanned": False}},
            "counties": {"Douglas": {"fields": {scanned: {"populated": 4, "record_count": 5, "percent": 80.0}}}}}}}
        header, *rows = dict(_gac_xlsx_sheets(snapshot))["GAC Detail"]
        column = header.index("Population scanned")
        by_field = {r[2]: r[column] for r in rows if r[1] == "Douglas"}
        self.assertIs(by_field[scanned], True)
        self.assertIs(by_field[unscanned], False)
        # Without flags, county measurements prove a scan; absence is unknown.
        snapshot["gac"]["address"]["fields"] = {}
        header, *rows = dict(_gac_xlsx_sheets(snapshot))["GAC Detail"]
        by_field = {r[2]: r[column] for r in rows if r[1] == "Douglas"}
        self.assertEqual((by_field[scanned], by_field[unscanned]), (True, None))
        # A county listed only in metadata has no scan result at all.
        snapshot["gac"]["address"]["fields"] = {scanned: {"population_scanned": True}}
        snapshot["gac"]["address"]["county_metadata"] = {"Wabasha": {"gac_open": False}}
        header, *rows = dict(_gac_xlsx_sheets(snapshot))["GAC Detail"]
        self.assertIsNone(next(r[column] for r in rows if r[1] == "Wabasha" and r[2] == scanned))


class MissingIsNotZeroTests(unittest.TestCase):
    def test_county_gac_panel_shows_dashes_for_missing_statistics(self):
        from clearparcel.datawatch.dashboard_gac import _render_county_mngac
        with patch.object(dashboard, "_mngac_county_record", return_value=({"covered_counties": None}, {"field_population_percent": None})):
            panel = _render_county_mngac({}, {"name": "Douglas"})
        self.assertIn('<div class="metric">—</div>', panel)
        self.assertIn('<div class="metric">—/—</div>', panel)
        self.assertNotIn(">0<", panel)


if __name__ == "__main__":
    unittest.main()
