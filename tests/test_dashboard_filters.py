"""Table filters must hide rows on every screen size and filter on the right attribute.

Review of ff9f9a7, findings 01 and 12: the mobile table CSS forced every row to
``display:table-row!important``, which beat the inline ``display:none`` the
filters set, and the county "Actively checked" filter matched source health
instead of check age.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import dashboard_gac, public_dashboard
from clearparcel.datawatch.dashboard_counties import render_counties
from clearparcel.datawatch.dashboard_templates import _TABLE_CSS

NODE_AVAILABLE = bool(shutil.which("node")) or os.environ.get("WATCHTOWER_REQUIRE_NODE") == "1"


def _source(slug: str, status: str, when: str) -> dict:
    return {"id": f"mn-{slug}-parcels", "county_slug": slug, "category": "Parcels", "status": status,
            "checked_at": when, "last_report_at": when}


def _counties_page() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    current, old = now.isoformat(), (now - dt.timedelta(days=10)).isoformat()
    sources = [_source("wabasha", "warn", current), _source("rice", "ok", current),
               _source("aitkin", "warn", old)]
    state = {"generated_at": current, "sources": {x["id"]: x for x in sources}}
    return render_counties({"_render_state": state, "state_file": "unused.json"})


def _row(page: str, slug: str) -> str:
    return re.search(rf'<tr data-name="{slug}"[^>]*>', page).group(0)


class HiddenRowCssTests(unittest.TestCase):
    def test_hidden_rows_beat_the_mobile_table_row_rule(self):
        mobile = _TABLE_CSS.index(".table-scroll tr{display:table-row!important}")
        hidden = _TABLE_CSS.index(".table-scroll tr[hidden]{display:none!important}")
        # Higher specificity and later in the sheet: hidden rows stay hidden at every width.
        self.assertGreater(hidden, mobile)

    def test_no_table_filter_uses_inline_display(self):
        state = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "sources": {}}
        with patch.object(public_dashboard, "_dashboard_state", return_value=state):
            pages = {"counties": _counties_page(),
                     "overview": public_dashboard.render_public_dashboard({"_public_mode": True})}
        sources = {"public_dashboard": public_dashboard, "dashboard_gac": dashboard_gac}
        for name, module in sources.items():
            pages[name] = Path(module.__file__).read_text(encoding="utf-8")
        for name, text in pages.items():
            with self.subTest(page=name):
                self.assertNotRegex(text, r"\.style\.display\s*=")


class CountyFilterTests(unittest.TestCase):
    def test_rows_carry_check_age_separately_from_health(self):
        page = _counties_page()
        self.assertIn('data-status="warn" data-reporting="current"', _row(page, "wabasha"))
        self.assertIn('data-status="ok" data-reporting="current"', _row(page, "rice"))
        self.assertIn('data-status="warn" data-reporting="overdue"', _row(page, "aitkin"))
        self.assertIn('data-reporting="none"', _row(page, "hennepin"))
        self.assertIn('<option value="reporting:current">Actively checked</option>', page)
        self.assertIn('<option value="reporting:overdue">Check overdue</option>', page)

    @unittest.skipUnless(NODE_AVAILABLE, "JavaScript execution requires Node.js")
    def test_filters_select_by_check_age_and_by_health(self):
        page = _counties_page()
        script = re.search(r"(function filterCounties\(\)\{.*?\})document\.getElementById\('cq'\)", page).group(1)
        rows = [{"name": slug, "status": status, "reporting": reporting}
                for slug, status, reporting in re.findall(
                    r'<tr data-name="([^"]+)" data-status="([^"]+)" data-reporting="([^"]+)">', page)]
        self.assertEqual(len(rows), 87)
        harness = f"""
const rows={json.dumps(rows)}.map(d=>({{dataset:d,hidden:false}}));
const controls={{cq:{{value:''}},cs:{{value:''}},'counties-no-results':{{hidden:true}}}};
const document={{getElementById:id=>controls[id],querySelectorAll:()=>rows}};
{script}
const out={{}};
for(const [q,s] of [['','reporting:current'],['','reporting:overdue'],['','warn'],['','ok'],['zzz','']]){{
  controls.cq.value=q;controls.cs.value=s;filterCounties();
  out[q+'|'+s]={{shown:rows.filter(r=>!r.hidden).map(r=>r.dataset.name),empty:!controls['counties-no-results'].hidden}};
}}
console.log(JSON.stringify(out));
"""
        result = json.loads(subprocess.run(["node", "-e", harness], capture_output=True, encoding="utf-8",
                                           check=True).stdout)
        # Actively checked includes a current county that needs attention.
        self.assertEqual(sorted(result["|reporting:current"]["shown"]), ["rice", "wabasha"])
        # Check overdue includes an overdue county that keeps its warning.
        self.assertEqual(result["|reporting:overdue"]["shown"], ["aitkin"])
        self.assertEqual(sorted(result["|warn"]["shown"]), ["aitkin", "wabasha"])
        self.assertEqual(result["|ok"]["shown"], ["rice"])
        self.assertEqual(result["zzz|"], {"shown": [], "empty": True})

    def test_card_count_matches_actively_checked_filter(self):
        page = _counties_page()
        card = int(re.search(r'Counties being checked</div><div class="metric">(\d+)', page).group(1))
        self.assertEqual(card, page.count('data-reporting="current"'))


class UnknownReportClockTests(unittest.TestCase):
    """Follow-up review of f8f0997, F08: an unknown worker clock is check overdue."""

    def _page(self) -> str:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        sources = [{**_source("wabasha", "ok", now), "worker": "cloud"}, _source("rice", "ok", now)]
        state = {"generated_at": now, "workers": {}, "sources": {x["id"]: x for x in sources}}
        return render_counties({"_render_state": state, "state_file": "unused.json"})

    def test_missing_worker_report_is_counted_and_filtered_as_overdue(self):
        page = self._page()
        row = _row(page, "wabasha")
        self.assertIn('data-reporting="overdue"', row)
        self.assertIn('data-status="overdue"', row)
        self.assertIn('data-reporting="current"', _row(page, "rice"))
        self.assertIn("report time unavailable", page)
        card = re.search(r'Counties being checked</div><div class="metric">(\d+)</div>'
                         r'<span class="subtext">Counties with a source for checks: (\d+)\. Checks overdue: (\d+)\.', page)
        checked, paths, overdue = (int(card.group(i)) for i in (1, 2, 3))
        self.assertEqual((checked, overdue), (1, 1))
        self.assertEqual(checked + overdue, paths)


if __name__ == "__main__":
    unittest.main()
