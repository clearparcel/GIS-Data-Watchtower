import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from clearparcel.datawatch.storage import LocalStorage
from clearparcel.datawatch.weekly_digest import LOG_KEY, MAX_BODY, MAX_LISTED, build_digest, emit_digest, run_weekly_digest

REPO = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 11, 9, 14, 0, tzinfo=dt.timezone.utc)  # Monday 8:00 AM Central


def _ms(days_ago: float) -> int:
    return int((NOW - dt.timedelta(days=days_ago)).timestamp() * 1000)


def _state(sources: dict, *, checked: dt.datetime = NOW, worker_report: dt.datetime = NOW) -> dict:
    stamp = checked.isoformat()
    return {"schema_version": 2, "generated_at": stamp, "overall": "ok",
            "workers": {"cloud": {"overall": "ok", "last_report_at": worker_report.isoformat()}},
            "sources": {sid: {"id": sid, "status": "ok", "worker": "cloud", "checked_at": stamp, **rec}
                        for sid, rec in sources.items()}}


class BuildDigestTests(unittest.TestCase):
    def test_counts_and_lists_stale_sources_oldest_first(self):
        state = _state({
            "fresh": {"name": "Fresh County", "editing_info": {"lastEditDate": _ms(3)}},
            "old": {"name": "Old County", "editing_info": {"lastEditDate": _ms(120)}},
            "older": {"name": "Older County", "editing_info": {"lastEditDate": _ms(400)}},
            "blank": {"name": "Blank County"},
        })
        digest = build_digest(state, {}, {}, now=NOW)
        self.assertEqual(digest["counts"], {"current": 1, "stale": 2, "unknown": 1})
        self.assertEqual(digest["digest_id"], "2026-W46")
        self.assertEqual(digest["subject"], "Watchtower weekly digest 2026-W46: 2 stale, 1 unknown")
        body = digest["body"]
        self.assertLess(body.index("Older County: 400 days"), body.index("Old County: 120 days"))
        self.assertIn("No publisher update time:\n  Blank County", body)
        self.assertNotIn("Fresh County", body)
        self.assertIn("0 source(s) and 0 worker(s) past the check window", body)

    def test_configured_interval_is_honored(self):
        state = _state({"weekly": {"name": "Weekly", "editing_info": {"lastEditDate": _ms(10)}}})
        digest = build_digest(state, {"sources": [{"id": "weekly", "expected_update_days": 7}]}, {}, now=NOW)
        self.assertIn("Weekly: 10 days since update (expected within 7)", digest["body"])

    def test_overdue_checks_are_reported_separately_from_stale_data(self):
        late = NOW - dt.timedelta(days=3)
        state = _state({"a": {"editing_info": {"lastEditDate": _ms(1)}}}, checked=late, worker_report=late)
        digest = build_digest(state, {}, {}, now=NOW)
        self.assertEqual(digest["counts"]["stale"], 0)
        self.assertEqual((digest["overdue_checks"], digest["overdue_workers"]), (1, 1))
        self.assertIn("1 source(s) and 1 worker(s) past the check window", digest["body"])
        self.assertIn("Checks overdue:\n  cloud worker\n  a", digest["body"])
        self.assertTrue(digest["subject"].endswith(", 2 overdue"))

    def test_long_lists_are_cut_and_the_body_stays_bounded(self):
        sources = {f"s{i:03d}": {"name": f"County number {i:03d} with a long parcel layer name",
                                 "editing_info": {"lastEditDate": _ms(200 + i)}} for i in range(60)}
        sources.update({f"u{i:03d}": {"name": f"Unknown {i:03d}"} for i in range(30)})
        digest = build_digest(_state(sources), {}, {}, now=NOW)
        body = digest["body"]
        self.assertLessEqual(len(body), MAX_BODY)
        self.assertLessEqual(body.count("days since update"), MAX_LISTED)
        self.assertRegex(body, r"and 5\d more")
        self.assertIn("No publisher update time:", body)
        self.assertIn("0 source(s) and 0 worker(s) past the check window", body)

    def test_summary_lines_and_every_section_survive_a_crowded_week(self):
        late = NOW - dt.timedelta(days=3)
        sources = {f"s{i:02d}": {"name": f"Stale county {i:02d} parcels", "editing_info": {"lastEditDate": _ms(300)}}
                   for i in range(20)}
        sources.update({f"u{i:02d}": {"name": f"Unknown county {i:02d} parcels"} for i in range(20)})
        digest = build_digest(_state(sources, checked=late, worker_report=late), {}, {}, now=NOW)
        body = digest["body"]
        self.assertLessEqual(len(body), MAX_BODY)
        self.assertIn("Watchtower checks: 40 source(s) and 1 worker(s) past the check window.", body)
        for title in ("Stale publisher data", "No publisher update time:", "Checks overdue:"):
            self.assertIn(title, body)
        self.assertIn("  cloud worker", body)
        self.assertTrue(digest["subject"].endswith(", 41 overdue"), digest["subject"])

    def test_week_number_uses_central_time(self):
        sunday_night_central = dt.datetime(2026, 11, 9, 4, 30, tzinfo=dt.timezone.utc)  # Sun 10:30 PM CT
        self.assertEqual(build_digest(_state({}), {}, {}, now=sunday_night_central)["digest_id"], "2026-W45")

    def test_empty_state_is_a_valid_digest(self):
        digest = build_digest({}, {}, {}, now=NOW)
        self.assertEqual(digest["counts"], {"current": 0, "stale": 0, "unknown": 0})
        self.assertIn("of 0 sources", digest["body"])


class EmitTests(unittest.TestCase):
    def test_one_structured_line_the_policy_can_match(self):
        digest = build_digest(_state({"a": {}}), {}, {}, now=NOW)
        out = io.StringIO()
        emit_digest(digest, out)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["severity"], "NOTICE")
        self.assertEqual(payload["message"], digest["subject"])
        self.assertEqual(payload[LOG_KEY]["schema_version"], 1)
        self.assertEqual(payload[LOG_KEY]["body"], digest["body"])
        self.assertEqual(payload[LOG_KEY]["digest_id"], "2026-W46")


class RunFromStorageTests(unittest.TestCase):
    def test_reads_aggregate_and_history_from_storage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "aggregate.json").write_text(json.dumps(_state(
                {"a": {"name": "A", "editing_info": {"lastEditDate": _ms(20)}}})), encoding="utf-8")
            history = [{"checked_at": (NOW - dt.timedelta(days=d)).isoformat(),
                        "sources": {"a": {"status": "ok",
                                          "data_updated_at": (NOW - dt.timedelta(days=d)).isoformat()}}}
                       for d in (40, 32, 28, 20)]
            (root / "history.jsonl").write_text("\n".join(json.dumps(row) for row in history) + "\n",
                                                encoding="utf-8")
            out = io.StringIO()
            digest = run_weekly_digest({}, LocalStorage(root), out, aggregate_object="aggregate.json", now=NOW)
        # Learned interval: gaps 8, 4, 8 days -> median 8 * 1.5 = 12, so 20 days old is stale.
        self.assertEqual(digest["counts"]["stale"], 1)
        self.assertIn("(expected within 12)", digest["body"])
        self.assertEqual(json.loads(out.getvalue())[LOG_KEY]["digest_id"], "2026-W46")

    def test_missing_aggregate_fails_loudly(self):
        with tempfile.TemporaryDirectory() as td, self.assertRaises(FileNotFoundError):
            run_weekly_digest({}, LocalStorage(td), io.StringIO(), aggregate_object="aggregate.json", now=NOW)


class CliTests(unittest.TestCase):
    def test_cli_logs_the_digest_from_storage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = root / "store"
            store.mkdir()
            (store / "aggregate-state.json").write_text(json.dumps(_state({"a": {}})), encoding="utf-8")
            config = root / "config" / "data_sources.json"
            config.parent.mkdir()
            config.write_text(json.dumps({"sources": [{"id": "a", "name": "A", "adapter": "arcgis_layer",
                                                       "url": "https://a.example/0"}]}), encoding="utf-8")
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("WATCHTOWER_", "CLEARPARCEL_WATCHTOWER_"))}
            env.update({"WATCHTOWER_STORAGE": "local", "WATCHTOWER_STORAGE_ROOT": str(store),
                        "WATCHTOWER_AGGREGATE_OBJECT": "aggregate-state.json"})
            result = subprocess.run([sys.executable, "-m", "clearparcel.datawatch.cli", "--config", str(config),
                                     "weekly-digest"], capture_output=True, text=True, env=env, cwd=REPO)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload[LOG_KEY]["counts"], {"current": 0, "stale": 0, "unknown": 1})


if __name__ == "__main__":
    unittest.main()
