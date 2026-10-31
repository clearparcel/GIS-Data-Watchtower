"""Times implausibly far in the future are unknown, never current (audit WT31-07)."""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch.aggregate import CLOCK_SKEW_TOLERANCE_SECONDS
from clearparcel.datawatch.dashboard_refresh import _SCRIPT
from clearparcel.datawatch.public_dashboard import _public_age, _publication_health, render_public_dashboard
from clearparcel.datawatch.public_projection import sanitize_public_render_state
from clearparcel.datawatch.public_publish import publish_public_snapshot
from clearparcel.datawatch.storage import LocalStorage

NOW = dt.datetime(2026, 10, 31, 12, tzinfo=dt.timezone.utc)


def iso(delta_seconds, base=None):
    return ((base or NOW) + dt.timedelta(seconds=delta_seconds)).isoformat()


class PublicationHealthTests(unittest.TestCase):
    def health(self, delta):
        return _publication_health({"public_published_at": iso(delta)}, max_age_seconds=1800, now=NOW)

    def test_forty_days_ahead_is_not_current(self):
        healthy, payload = self.health(40 * 86400)
        self.assertFalse(healthy)
        self.assertEqual(payload["status"], "stale")
        self.assertEqual(payload["reason"], "publication_clock_skew")
        self.assertNotIn("age_seconds", payload)

    def test_both_sides_of_the_tolerance(self):
        self.assertTrue(self.health(CLOCK_SKEW_TOLERANCE_SECONDS)[0])
        self.assertFalse(self.health(CLOCK_SKEW_TOLERANCE_SECONDS + 1)[0])
        self.assertTrue(self.health(-60)[0])
        self.assertEqual(self.health(60)[1]["age_seconds"], 0)

    def test_naive_legacy_time_is_still_read_as_utc(self):
        naive = (NOW - dt.timedelta(minutes=5)).replace(tzinfo=None).isoformat()
        healthy, payload = _publication_health({"public_published_at": naive}, max_age_seconds=1800, now=NOW)
        self.assertTrue(healthy)
        self.assertEqual(payload["age_seconds"], 300)

    def test_relative_age_label(self):
        now = dt.datetime.now(dt.timezone.utc)
        self.assertEqual(_public_age(iso(40 * 86400, now)), "Unavailable")
        self.assertEqual(_public_age(iso(60, now)), "Just now")


class OverviewTests(unittest.TestCase):
    def state(self, offset_seconds):
        now = dt.datetime.now(dt.timezone.utc)
        stamp = iso(offset_seconds, now)
        return sanitize_public_render_state({
            "schema_version": 2, "generated_at": stamp, "public_published_at": stamp, "overall": "ok",
            "counts": {"ok": 1, "warn": 0, "error": 0},
            "workers": {"cloud": {"overall": "ok", "source_count": 1, "last_report_at": stamp}},
            "sources": {"a": {"id": "a", "name": "A", "status": "ok", "worker": "cloud", "checked_at": stamp}},
        })

    @staticmethod
    def worker_label(page):
        return re.search(r'data-worker-report="cloud">([^<]*)<', page).group(1)

    def render(self, state):
        with patch("clearparcel.datawatch.public_dashboard._dashboard_state", return_value=state):
            return render_public_dashboard({"_public_mode": True})

    def test_future_source_worker_and_publication_times_are_unknown(self):
        page = self.render(self.state(40 * 86400))
        self.assertIn("Public publication reporting: Unknown", page)
        self.assertIn("Source reporting: 0 overdue · 1 without a check time", page)
        self.assertEqual(self.worker_label(page), "Healthy · Reporting unknown")

    def test_current_times_stay_current(self):
        page = self.render(self.state(-60))
        self.assertIn("Public publication reporting: Current", page)
        self.assertIn("Source reporting: 0 overdue · 0 without a check time", page)
        self.assertEqual(self.worker_label(page), "Healthy · Reporting on time")


class PublisherClockTests(unittest.TestCase):
    def publish_after(self, previous_published_at):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, destination = LocalStorage(root / "s"), LocalStorage(root / "d")
            source.root.mkdir()
            destination.root.mkdir()
            stamp = dt.datetime.now(dt.timezone.utc).isoformat()
            doc = {"schema_version": 2, "generated_at": stamp, "overall": "ok",
                   "counts": {"ok": 0, "warn": 0, "error": 0}, "workers": {}, "sources": {}}
            (source.root / "aggregate-state.json").write_text(json.dumps(doc), encoding="utf-8")
            (destination.root / "aggregate-state.json").write_text(
                json.dumps({**doc, "public_published_at": previous_published_at}), encoding="utf-8")
            return publish_public_snapshot(source, destination, workdir=root / "w")["public_published_at"]

    def test_implausible_previous_publication_time_is_not_carried_forward(self):
        future = iso(40 * 86400, dt.datetime.now(dt.timezone.utc))
        published = dt.datetime.fromisoformat(self.publish_after(future))
        self.assertLess(abs((published - dt.datetime.now(dt.timezone.utc)).total_seconds()), 60)

    def test_small_skew_keeps_the_publication_clock_monotonic(self):
        slightly_ahead = iso(60, dt.datetime.now(dt.timezone.utc))
        self.assertEqual(self.publish_after(slightly_ahead), slightly_ahead)


@unittest.skipUnless(shutil.which("node") or os.environ.get("WATCHTOWER_REQUIRE_NODE") == "1",
                     "Node required for refresh-controller clock regression")
class RefreshControllerClockTests(unittest.TestCase):
    def test_client_labels_treat_future_times_as_unavailable(self):
        helpers = re.search(r"const SKEW_MS=.*?\nfunction ahead\(stamp\)\{.*?\}\nfunction relative\(value\)\{.*?\n", _SCRIPT, re.S)
        self.assertIsNotNone(helpers)
        scenario = helpers.group(0) + r"""
const assert=require('assert');
const future=new Date(Date.now()+40*86400000).toISOString();
const near=new Date(Date.now()+60000).toISOString();
assert.equal(relative(future),'Unavailable');
assert.equal(relative(near),'Just now');
assert.equal(ahead(Date.parse(future)),true);
assert.equal(ahead(Date.parse(near)),false);
console.log('OK');
"""
        result = subprocess.run(["node", "-e", scenario], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "OK")
        for fragment in ("!Number.isFinite(stamp)||ahead(stamp)?'Report time unavailable'",
                         "Number.isFinite(parsed)&&!ahead(parsed)?",
                         "if(!Number.isFinite(t)||ahead(t))missing++"):
            self.assertIn(fragment, _SCRIPT)


if __name__ == "__main__":
    unittest.main()
