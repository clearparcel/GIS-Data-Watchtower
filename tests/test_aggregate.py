"""Hybrid aggregate merge semantics (see docs/hybrid-aggregation.md)."""
import datetime as dt
import unittest

from clearparcel.datawatch import aggregate

NOW = dt.datetime(2026, 10, 13, 12, 0, tzinfo=dt.timezone.utc)


def report(minutes, statuses, scope="fleet"):
    stamp = (NOW + dt.timedelta(minutes=minutes)).isoformat()
    return {"generated_at": stamp, "overall": "ok", "scope": {"type": scope},
            "sources": {sid: {"id": sid, "status": status, "checked_at": stamp} for sid, status in statuses.items()}}


def merge(base, partial, worker, minutes=60):
    return aggregate.merge_states(base, partial, worker, now=NOW + dt.timedelta(minutes=minutes))


class MergeTests(unittest.TestCase):
    def test_workers_keep_each_others_sources_and_counts_are_derived(self):
        state = merge({}, report(0, {"a": "ok", "b": "warn"}), "cloud")
        state = merge(state, report(5, {"c": "error"}), "local")
        self.assertEqual({sid: src["worker"] for sid, src in state["sources"].items()},
                         {"a": "cloud", "b": "cloud", "c": "local"})
        self.assertEqual(state["counts"], {"ok": 1, "warn": 1, "error": 1})
        self.assertEqual(set(state["workers"]), {"cloud", "local"})

    def test_older_or_repeated_reports_never_replace_newer_ones(self):
        newer = merge({}, report(10, {"a": "error"}), "cloud")
        self.assertEqual(merge(newer, report(0, {"a": "ok"}), "cloud"), newer)
        self.assertEqual(merge(newer, report(10, {"a": "ok"}), "cloud"), newer)

    def test_success_time_survives_failures(self):
        state = merge({}, report(0, {"a": "ok"}), "cloud")
        first = state["sources"]["a"]["last_success_at"]
        state = merge(state, report(10, {"a": "error"}), "cloud")
        self.assertEqual(state["sources"]["a"]["last_success_at"], first)
        self.assertEqual(state["sources"]["a"]["last_report_at"], report(10, {})["generated_at"])

    def test_invalid_reports_are_refused(self):
        for partial in ({"sources": {}}, {**report(0, {}), "generated_at": "not-a-time"},
                        report(0, {"a": "ok"}, scope="empty"), report(24 * 60, {"a": "ok"})):
            with self.subTest(partial=partial.get("generated_at")), self.assertRaises(ValueError):
                merge({}, partial, "cloud")

    def test_retired_workers_cannot_publish_again(self):
        state = merge({}, report(0, {"a": "ok"}), "local")
        state = merge(state, report(2, {"a": "ok"}), "cloud")  # cloud takes the source over first
        state = aggregate.retire_worker(state, "local", (NOW + dt.timedelta(minutes=5)).isoformat())
        self.assertIn("local", state["retired_workers"])
        with self.assertRaises(ValueError):
            merge(state, report(10, {"a": "ok"}), "local")


class AggregateOverviewAlertTests(unittest.TestCase):
    """The private overview derives aggregate alerts and never claims an unearned all-clear."""

    def render(self, state):
        import tempfile
        from pathlib import Path
        from clearparcel.datawatch.dashboard_views import render_dashboard
        with tempfile.TemporaryDirectory() as tmp:
            return render_dashboard({"_render_state": state, "state_file": str(Path(tmp) / "state.json"),
                                     "history_file": str(Path(tmp) / "history.jsonl")})

    def alerts_card(self, state):
        page = self.render(state)
        start = page.index('id="alerts"')
        return page[start:page.index("</div>", start)]

    @staticmethod
    def current(statuses):
        now = dt.datetime.now(dt.timezone.utc)
        stamp = (now - dt.timedelta(minutes=5)).isoformat()
        partial = {"generated_at": stamp, "overall": "ok", "scope": {"type": "fleet"},
                   "sources": {sid: {"id": sid, "status": st, "checked_at": stamp} for sid, st in statuses.items()}}
        return aggregate.merge_states({}, partial, "cloud", now=now)

    def test_aggregate_alerts_are_derived_from_source_status(self):
        state = self.current({"a": "ok", "b": "warn", "c": "error"})
        self.assertNotIn("active_alerts", state)
        card = self.alerts_card(state)
        self.assertNotIn("Alert status unavailable.", card)
        self.assertNotIn("No active alerts.", card)
        self.assertIn("<strong>b</strong>", card)
        self.assertIn("<strong>c</strong>", card)
        self.assertNotIn("<strong>a</strong>", card)

    def test_healthy_current_aggregate_is_all_clear(self):
        page = self.render(self.current({"a": "ok", "b": "ok"}))
        self.assertIn("No active alerts.", page)

    def test_overdue_worker_blocks_the_all_clear(self):
        state = merge({}, report(0, {"a": "ok"}), "cloud")  # reported in October: long past the window
        page = self.render(state)
        self.assertNotIn("No active alerts.", page)
        self.assertIn("Cloud worker", page)
        self.assertIn("has not reported within the freshness window", page)

    def test_overdue_source_under_a_current_worker_is_an_alert(self):
        state = self.current({"a": "ok", "b": "ok"})
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat()
        state["sources"]["b"]["checked_at"] = old
        card = self.alerts_card(state)
        self.assertNotIn("No active alerts.", card)
        self.assertIn("<strong>b</strong>", card)
        self.assertIn("older than the freshness window", card)

    def test_unannotated_state_is_annotated_before_deriving(self):
        from clearparcel.datawatch.dashboard_views import derive_aggregate_alerts
        state = merge({}, report(0, {"a": "ok"}), "cloud")  # October report, no freshness flags
        alerts = derive_aggregate_alerts(state)
        self.assertTrue(any(a["type"] == "worker_overdue" for a in alerts))

    def test_state_without_worker_data_is_unavailable_not_all_clear(self):
        page = self.render({"schema_version": 2, "overall": "ok", "counts": {}, "sources": {}})
        self.assertIn("Alert status unavailable.", page)
        self.assertNotIn("No active alerts.", page)

    def test_explicit_empty_alert_list_is_still_all_clear(self):
        state = merge({}, report(0, {"a": "ok"}), "cloud")
        page = self.render({**state, "active_alerts": []})
        self.assertIn("No active alerts.", page)
        self.assertNotIn("Alert status unavailable.", page)

    def test_reported_alerts_are_listed(self):
        state = merge({}, report(0, {"c": "error"}), "cloud")
        page = self.render({**state, "active_alerts": [{"source": "c", "severity": "error", "message": "Check failed"}]})
        self.assertIn("Check failed", page)
        self.assertNotIn("Alert status unavailable.", page)


if __name__ == "__main__":
    unittest.main()
