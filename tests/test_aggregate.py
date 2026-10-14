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


if __name__ == "__main__":
    unittest.main()
