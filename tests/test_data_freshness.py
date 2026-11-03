import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.data_freshness import (
    DEFAULT_EXPECTED_DAYS, data_freshness, expected_interval, publisher_updated_at, summarize)

NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)


def _ms(stamp: dt.datetime) -> int:
    return int(stamp.timestamp() * 1000)


def _days_ago(days: float) -> dt.datetime:
    return NOW - dt.timedelta(days=days)


class PublisherTimeTests(unittest.TestCase):
    def test_arcgis_edit_date_wins(self):
        rec = {"editing_info": {"lastEditDate": _ms(_days_ago(3))},
               "tracked_values": {"last_modified": "Wed, 01 Jan 2025 00:00:00 GMT"}}
        self.assertEqual(publisher_updated_at(rec), _days_ago(3).isoformat())

    def test_http_last_modified_is_used_next(self):
        rec = {"tracked_values": {"last_modified": "Mon, 02 Nov 2026 15:00:00 GMT"}}
        self.assertEqual(publisher_updated_at(rec), "2026-11-02T15:00:00+00:00")

    def test_invalid_values_are_not_times(self):
        for rec in ({"editing_info": {"lastEditDate": "1700000000000"}}, {"editing_info": {"lastEditDate": True}},
                    {"tracked_values": {"last_modified": "yesterday"}}, {}, None, "x"):
            self.assertIsNone(publisher_updated_at(rec), rec)


class ExpectedIntervalTests(unittest.TestCase):
    def test_configured_override_wins(self):
        self.assertEqual(expected_interval({"expected_update_days": 7}, []), (7, "configured"))

    def test_invalid_override_is_ignored(self):
        for value in (0, -5, 3651, 7.5, "7", True):
            self.assertEqual(expected_interval({"expected_update_days": value}, []), (DEFAULT_EXPECTED_DAYS, "default"))

    def test_learned_from_three_distinct_updates(self):
        history = [{"data_updated_at": _days_ago(d).isoformat()} for d in (30, 30, 20, 10, 10)]
        self.assertEqual(expected_interval({}, history), (15, "observed"))  # median 10 days * 1.5

    def test_two_updates_are_not_enough_to_learn(self):
        history = [{"data_updated_at": _days_ago(d).isoformat()} for d in (20, 10)]
        self.assertEqual(expected_interval({}, history), (DEFAULT_EXPECTED_DAYS, "default"))


class DataFreshnessTests(unittest.TestCase):
    def test_states(self):
        current = data_freshness({"editing_info": {"lastEditDate": _ms(_days_ago(10))}}, now=NOW)
        self.assertEqual((current["state"], current["age_days"], current["basis"]), ("current", 10, "default"))
        stale = data_freshness({"editing_info": {"lastEditDate": _ms(_days_ago(120))}}, now=NOW)
        self.assertEqual(stale["state"], "stale")
        self.assertEqual(data_freshness({}, now=NOW)["state"], "unknown")

    def test_future_time_is_unknown_not_current(self):
        future = data_freshness({"editing_info": {"lastEditDate": _ms(NOW + dt.timedelta(days=5))}}, now=NOW)
        self.assertEqual(future["state"], "unknown")
        near = data_freshness({"editing_info": {"lastEditDate": _ms(NOW + dt.timedelta(hours=2))}}, now=NOW)
        self.assertEqual(near["state"], "current")

    def test_configured_interval_drives_staleness(self):
        rec = {"editing_info": {"lastEditDate": _ms(_days_ago(10))}}
        self.assertEqual(data_freshness(rec, source_config={"expected_update_days": 7}, now=NOW)["state"], "stale")

    def test_summary_counts_every_state(self):
        rows = [{"state": "current"}, {"state": "stale"}, {"state": "unknown"}, {"state": "bogus"}, None]
        self.assertEqual(summarize(rows), {"current": 1, "stale": 1, "unknown": 3})


class RegistryAndHistoryTests(unittest.TestCase):
    def test_registry_rejects_an_invalid_override(self):
        good = [{"id": "a", "expected_update_days": 30}]
        watch.validate_source_registry(good)
        for value in (0, "30", 30.0, 4000):
            with self.subTest(value=value), self.assertRaises(watch.InvalidSourceRegistryError):
                watch.validate_source_registry([{"id": "a", "expected_update_days": value}])

    def test_history_records_the_publisher_time(self):
        stamp = _days_ago(4)
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=False):
            for name in list(os.environ):
                if name.startswith("CLEARPARCEL_WATCHTOWER_") or name.startswith("WATCHTOWER_"):
                    os.environ.pop(name, None)
            root = Path(td)
            config = {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
                      "retries": 1, "retry_delay_seconds": 0,
                      "sources": [{"id": "a", "name": "A", "adapter": "arcgis_layer", "url": "https://a.example/0"}]}
            with patch.object(watch, "_source_check",
                              return_value={"feature_count": 1, "problems": [],
                                            "editing_info": {"lastEditDate": _ms(stamp)}}):
                watch.check_sources(config, save=True)
            row = json.loads((root / "history.jsonl").read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(row["sources"]["a"]["data_updated_at"], stamp.isoformat())
            entry = watch.load_history(config, source_filter="a", exact=True, limit=1)["entries"][0]
            self.assertEqual(entry["data_updated_at"], stamp.isoformat())


class OverviewDisplayTests(unittest.TestCase):
    def test_overview_shows_data_freshness_separately(self):
        from clearparcel.datawatch.dashboard_views import render_dashboard
        now = dt.datetime.now(dt.timezone.utc)
        stamp = (now - dt.timedelta(minutes=5)).isoformat()
        state = {"schema_version": 2, "generated_at": stamp, "overall": "ok", "counts": {"ok": 3},
                 "workers": {"cloud": {"overall": "ok", "last_report_at": stamp}},
                 "sources": {
                     "fresh": {"id": "fresh", "status": "ok", "worker": "cloud", "checked_at": stamp,
                               "editing_info": {"lastEditDate": _ms(now - dt.timedelta(days=2))}},
                     "old": {"id": "old", "status": "ok", "worker": "cloud", "checked_at": stamp,
                             "editing_info": {"lastEditDate": _ms(now - dt.timedelta(days=200))}},
                     "none": {"id": "none", "status": "ok", "worker": "cloud", "checked_at": stamp}}}
        with tempfile.TemporaryDirectory() as td:
            page = render_dashboard({"_render_state": state, "state_file": str(Path(td) / "s.json"),
                                     "history_file": str(Path(td) / "h.jsonl")})
        card = page[page.index('id="data-freshness"'):]
        card = card[:card.index("</div></div>") if "</div></div>" in card else 400]
        self.assertIn("1 stale", card)
        self.assertIn("1 current", card)
        self.assertIn("1 with no publisher update time", card)
        # Stale data is not an outage: the alert panel still shows all clear.
        self.assertIn("No active alerts.", page)

    def test_source_page_shows_age_interval_and_basis(self):
        from clearparcel.datawatch.dashboard_views import render_source
        now = dt.datetime.now(dt.timezone.utc)
        stamp = now.isoformat()
        state = {"schema_version": 2, "generated_at": stamp, "overall": "ok", "counts": {"ok": 1},
                 "workers": {"cloud": {"overall": "ok", "last_report_at": stamp}},
                 "sources": {"old": {"id": "old", "name": "Old Parcels", "status": "ok", "worker": "cloud",
                                     "checked_at": stamp,
                                     "editing_info": {"lastEditDate": _ms(now - dt.timedelta(days=40))}}}}
        with tempfile.TemporaryDirectory() as td:
            page = render_source({"_render_state": state, "state_file": str(Path(td) / "s.json"),
                                  "history_file": str(Path(td) / "h.jsonl"),
                                  "sources": [{"id": "old", "expected_update_days": 30}]}, "old")
        self.assertIn("Data stale · 40 days old · expected within 30 days (set in the source registry)", page)


if __name__ == "__main__":
    unittest.main()
