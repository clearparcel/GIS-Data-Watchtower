"""Structural accessibility and phone-layout regressions (review package 5).

Rendered-page checks were also run with axe-core at 320/375/768/1280 px during
development; these tests pin the markup those results depend on.
"""
import re
import unittest
from unittest.mock import patch

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.county_profile_panel import percentage_legend, render_county_profile_panel
from clearparcel.datawatch.dashboard_refresh import _SCRIPT
from clearparcel.datawatch.dashboard_templates import _accessible_tables, _layout


def public_page(body="<h2>Example</h2><table><thead><tr><th>A</th></tr></thead><tbody><tr><th>Row</th></tr></tbody></table>"):
    return _layout("Minnesota Counties — GIS Data Watchtower", body, static=True)


def private_page(body="<p>x</p>"):
    return _layout("Overview", body, static=False, csrf_token="t")


class SkipLinkAndFocusTests(unittest.TestCase):
    def test_skip_link_is_the_first_focusable_element_in_both_layouts(self):
        for page in (public_page(), private_page()):
            after_body = page.split("<body>", 1)[1].lstrip()
            self.assertTrue(after_body.startswith('<a class="skip-link" href="#main-content">'), after_body[:80])
            self.assertIn('id="main-content" tabindex="-1"', page)

    def test_active_tab_is_kept_visible_without_moving_keyboard_start(self):
        # scrollIntoView moves Chromium's sequential-focus starting point past the skip link.
        page = public_page()
        tab_script = re.search(r"<script[^>]*>\(function\(\)\{const row=document\.querySelector\('\.public-tabs'\).*?</script>", page, re.S)
        self.assertIsNotNone(tab_script)
        self.assertNotIn("scrollIntoView", tab_script.group(0))
        self.assertIn("row.scrollLeft", tab_script.group(0))

    def test_county_dialog_focus_trap_covers_all_focusable_controls(self):
        panel = render_county_profile_panel({})
        self.assertIn("button,a[href],summary,input,select,textarea", panel)


class PhoneHeaderAndNavTests(unittest.TestCase):
    def test_status_text_and_short_tab_labels_exist_for_phones(self):
        page = public_page()
        self.assertIn('<span class="live-dot" aria-hidden="true">', page)
        self.assertIn('<span class="live-short">READ ONLY</span>', page)
        self.assertIn('<span class="tab-long">Minnesota Counties</span><span class="tab-short">Counties</span>', page)
        # The short label must stay in the accessibility tree; CSS hides whichever label is unused.
        self.assertNotIn('class="tab-short" aria-hidden', page)
        # A descendant rule here once hid the short label (the last <span> in the block).
        self.assertNotIn(".live-state span:last-child{display:none}", page)

    def test_pause_button_state_is_carried_by_its_label_only(self):
        for page in (public_page(), private_page()):
            self.assertIn('<button type="button" id="refresh-pause">Pause refresh</button>', page)
            self.assertNotIn('id="refresh-pause" aria-pressed', page)
        self.assertIn("'Resume refresh':'Pause refresh'", _SCRIPT)
        self.assertNotIn("aria-pressed", _SCRIPT)


class MapTests(unittest.TestCase):
    def test_map_offers_a_skip_link_and_shares_the_no_data_pattern(self):
        svg = dashboard._mngac_map_svg()
        self.assertTrue(svg.startswith('<a class="skip-link map-skip" href="#mngac-map-end">Skip county map</a>'))
        self.assertIn('<pattern id="pct-no-data"', svg)
        self.assertTrue(svg.endswith('<span id="mngac-map-end" class="map-end" tabindex="-1"></span>'))
        self.assertEqual(svg.count('role="button"'), 87)
        self.assertNotIn("aria-pressed", svg)  # set by the overview script, which manages selection

    def test_map_skip_link_is_shown_beside_the_map_when_focused(self):
        for page in (public_page(), private_page()):
            self.assertRegex(page, r"\.map-skip:focus\{+position:static")

    def test_gac_county_page_puts_the_skip_target_after_the_disclosure(self):
        from tests.test_gac_county_view import county_state
        state, _, _ = county_state("parcel")
        with patch("clearparcel.datawatch.dashboard._dashboard_state", return_value=state):
            page = dashboard.render_mngac({"_public_mode": True}, "parcel", county="douglas")
        self.assertEqual(page.count('id="mngac-map-end"'), 1)
        self.assertIn('</details><span id="mngac-map-end" class="map-end" tabindex="-1"></span>', page)

    def test_focus_and_selection_outlines_contrast_with_every_map_fill(self):
        from clearparcel.datawatch.county_map_status import MAP_STATUSES
        from clearparcel.datawatch.county_profile_panel import NO_DATA_COLOR, PERCENT_COLORS

        def luminance(color):
            channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        def ratio(a, b):
            high, low = sorted((luminance(a), luminance(b)), reverse=True)
            return (high + 0.05) / (low + 0.05)

        page = public_page()
        focus = re.search(r"\.mngac-county:focus-visible[^{]*\{stroke:(#[0-9a-f]{6});[^}]*drop-shadow\(0 0 1\.5px (#[0-9a-f]{6})\)", page)
        selected = re.search(r"\.mngac-county\.selected[^{]*\{stroke:(#[0-9a-f]{3,6});[^}]*drop-shadow\(0 0 1\.5px (#[0-9a-f]{6})\)", page)
        self.assertIsNotNone(focus)
        self.assertIsNotNone(selected)
        fills = [NO_DATA_COLOR, *PERCENT_COLORS, *(color for _, color, _ in MAP_STATUSES.values())]
        for core, halo in (focus.groups(), selected.groups()):
            core = "#ffffff" if core == "#fff" else core
            for fill in fills:
                self.assertGreaterEqual(max(ratio(core, fill), ratio(halo, fill)), 3.0, (core, halo, fill))

    def test_gac_map_links_get_the_same_outlines_in_both_layouts(self):
        # On GAC maps keyboard focus sits on the <a> around each county shape.
        for page in (public_page(), private_page()):
            self.assertRegex(page, r'\.gac-map-link:focus-visible \.mngac-county\{+stroke:#')
            self.assertRegex(page, r'\.gac-map-link\[aria-current="page"\] \.mngac-county\{+stroke:#fff')

    def test_legend_is_a_named_group_with_a_patterned_no_data_swatch(self):
        legend = percentage_legend()
        self.assertIn('role="group" aria-label="Map legend"', legend)
        self.assertIn("pct-no-data-swatch", legend)
        self.assertIn(">No data</span>", legend)

    def test_scripted_scrolling_respects_reduced_motion(self):
        from pathlib import Path
        source = Path(dashboard.__file__).with_name("dashboard_gac.py").read_text(encoding="utf-8")
        for call in re.findall(r"scrollIntoView\(\{\{[^)]*\}\}\)", source):
            self.assertIn("prefers-reduced-motion", call)


class TableTests(unittest.TestCase):
    def test_tables_get_a_caption_and_region_label_from_the_nearest_heading(self):
        out = _accessible_tables("<h3>Parcel monitoring paths</h3><p>x</p><table><thead><tr><th>Path</th></tr></thead>"
                                 "<tbody><tr><th>Both</th><td>1</td></tr></tbody></table>")
        self.assertIn('aria-label="Parcel monitoring paths"', out)
        self.assertIn('<caption class="sr-only">Parcel monitoring paths</caption>', out)
        self.assertIn('<th scope="col">Path</th>', out)
        self.assertIn('<th scope="row">Both</th>', out)
        self.assertNotIn("Scrollable data table", out)

    def test_existing_captions_and_wrapper_labels_are_kept(self):
        out = _accessible_tables('<div class="table-scroll" aria-label="Gaps"><table><caption>Field gaps</caption>'
                                 '<tr><td>1</td></tr></table></div>')
        self.assertIn('aria-label="Gaps"', out)
        self.assertEqual(out.count("<caption"), 1)

    def test_table_processing_stays_fast_on_adversarial_markup(self):
        import time
        # Unclosed tags made html.parser (before CPython 3.12.11) and .*? table
        # matching quadratic; every case here must stay linear.
        for hostile in ("<" * 60000, "<h1" * 20000, "<tbody" * 20000, "<caption" * 20000,
                        "<h2>" + "<" * 60000 + "<table><tr><td>1</td></tr></table>",
                        "<h3>" * 20000, "<table>" * 20000, "<th" * 20000,
                        '<div class="table-scroll">' * 20000 + "<table></table>"):
            started = time.perf_counter()
            _accessible_tables(hostile)
            self.assertLess(time.perf_counter() - started, 2.0, hostile[:12])

    def test_table_without_any_heading_still_gets_a_label(self):
        out = _accessible_tables("<table><tr><td>1</td></tr></table>")
        self.assertIn('aria-label="Data table"', out)


if __name__ == "__main__":
    unittest.main()
