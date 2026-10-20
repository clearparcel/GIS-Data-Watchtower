import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from clearparcel.datawatch import cli
from clearparcel.datawatch.dispatch_guard import (
    DispatchGuardError, DispatchRefused, claim_dispatch, configured_min_hours, configured_tolerance,
    guard_dispatch, guard_object)
GUARD_OBJECT = guard_object("cloud")
from clearparcel.datawatch.storage import LocalStorage, StorageConflictError

T0 = datetime(2026, 10, 21, 10, 0, 4, tzinfo=timezone.utc)
CENTRAL = ZoneInfo("America/Chicago")


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.storage = LocalStorage(self.root)

    def tearDown(self):
        self.td.cleanup()

    def claim(self, when, **kw):
        return claim_dispatch(self.storage, min_hours=kw.pop("min_hours", 23), command="cloud-job",
                              execution_id=kw.pop("execution_id", "exec"), now=when,
                              profile=kw.pop("profile", "cloud"), **kw)

    def runs(self):
        return json.loads((self.root / GUARD_OBJECT).read_text(encoding="utf-8"))["runs"]

    def test_first_run_is_recorded_and_an_early_second_run_is_refused_without_writing(self):
        self.claim(T0)
        before = (self.root / GUARD_OBJECT).read_bytes()
        with self.assertRaisesRegex(DispatchRefused, "8.70 h ago; the minimum spacing is 23 h"):
            self.claim(T0 + timedelta(hours=8.7))
        self.assertEqual((self.root / GUARD_OBJECT).read_bytes(), before)

    def test_run_at_the_minimum_is_allowed_and_records_spacing(self):
        self.claim(T0)
        entry = self.claim(T0 + timedelta(hours=23), execution_id="next")
        self.assertEqual(entry["hours_since_previous"], 23.0)
        self.assertEqual([r["execution_id"] for r in self.runs()], ["exec", "next"])

    def test_spacing_has_a_bounded_start_delay_tolerance(self):
        self.claim(T0)
        second = T0 + timedelta(hours=23) - timedelta(minutes=10)
        self.claim(second)
        with self.assertRaises(DispatchRefused):
            self.claim(second + timedelta(hours=23) - timedelta(minutes=10, seconds=1))
        third = second + timedelta(hours=23) - timedelta(minutes=1)
        with self.assertRaises(DispatchRefused):
            self.claim(third, tolerance=timedelta(0))

    def test_spring_daylight_saving_day_run_is_not_skipped_by_scheduler_jitter(self):
        # A slow cold start the day before and a fast one on the change day.
        before = datetime(2027, 3, 13, 5, 4, 15, tzinfo=CENTRAL).astimezone(timezone.utc)
        after = datetime(2027, 3, 14, 5, 0, 5, tzinfo=CENTRAL).astimezone(timezone.utc)
        self.assertLess(after - before, timedelta(hours=23))
        self.claim(before)
        self.claim(after)
        self.assertEqual(len(self.runs()), 2)

    def test_override_runs_early_and_records_the_reason(self):
        self.claim(T0)
        entry = self.claim(T0 + timedelta(hours=2), override="  verify Todd recovery after fix  ")
        self.assertEqual(entry["override_reason"], "verify Todd recovery after fix")
        self.assertEqual(self.runs()[-1]["override_reason"], "verify Todd recovery after fix")

    def test_override_needs_a_bounded_reason(self):
        with self.assertRaises(DispatchGuardError):
            self.claim(T0, override="   ")
        with self.assertRaises(DispatchGuardError):
            self.claim(T0, override="x" * 201)

    def test_future_previous_run_fails_closed(self):
        self.claim(T0 + timedelta(hours=5))
        with self.assertRaisesRegex(DispatchRefused, "future"):
            self.claim(T0)

    def test_invalid_stored_record_fails_closed(self):
        (self.root / "runs").mkdir()
        (self.root / GUARD_OBJECT).write_text("{not json", encoding="utf-8")
        with self.assertRaises(DispatchGuardError):
            self.claim(T0)
        (self.root / GUARD_OBJECT).write_text(json.dumps({"schema_version": 1, "runs": [{"x": 1}]}), encoding="utf-8")
        with self.assertRaises(DispatchGuardError):
            self.claim(T0)

    def test_concurrent_claim_is_re_evaluated_against_the_winner(self):
        real = self.storage.upload_if_version
        calls = []

        def racing(name, source, version):
            if not calls:
                calls.append(1)
                claim_dispatch(LocalStorage(self.root), min_hours=23, command="cloud-job",
                               execution_id="winner", now=T0, profile="cloud")
                raise StorageConflictError("raced")
            return real(name, source, version)

        with patch.object(self.storage, "upload_if_version", side_effect=racing):
            with self.assertRaises(DispatchRefused):
                self.claim(T0 + timedelta(seconds=5), execution_id="loser")
        self.assertEqual([r["execution_id"] for r in self.runs()], ["winner"])

    def test_profiles_keep_separate_slots(self):
        self.claim(T0, profile="cloud")
        self.claim(T0 + timedelta(minutes=5), profile="local")
        with self.assertRaises(DispatchRefused):
            self.claim(T0 + timedelta(minutes=10), profile="local")
        self.assertEqual(guard_object(None), "runs/dispatch-guard-unassigned.json")
        self.assertEqual(guard_object("../x"), "runs/dispatch-guard-unassigned.json")
        self.assertEqual(self.runs()[0]["profile"], "cloud")

    def test_dashboard_refresh_claims_the_slot_before_polling(self):
        from clearparcel.datawatch import dashboard
        config = {"_root_dir": str(self.root), "state_file": str(self.root / "state.json")}
        env = {"WATCHTOWER_STORAGE": "local", "WATCHTOWER_STORAGE_ROOT": str(self.root),
               "WATCHTOWER_MIN_DISPATCH_HOURS": "23"}
        stderr = io.StringIO()
        with patch.dict(os.environ, env), patch.object(dashboard, "check_sources", return_value={}) as check, \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(dashboard.refresh_providers(config, "cloud"), {})
            self.assertIsNone(dashboard.refresh_providers(config, "cloud"))
        self.assertEqual(check.call_count, 1)
        self.assertIn("watchtower_dispatch_refused", stderr.getvalue())
        self.assertEqual(self.runs()[0]["command"], "dashboard-refresh")

    def test_history_is_bounded(self):
        for day in range(70):
            self.claim(T0 + timedelta(days=day), execution_id=f"d{day}")
        runs = self.runs()
        self.assertEqual(len(runs), 60)
        self.assertEqual(runs[-1]["execution_id"], "d69")

    def test_configuration_is_off_by_default_and_validated(self):
        self.assertIsNone(configured_min_hours({}))
        self.assertIsNone(configured_min_hours({"WATCHTOWER_MIN_DISPATCH_HOURS": " "}))
        self.assertEqual(configured_min_hours({"WATCHTOWER_MIN_DISPATCH_HOURS": "23"}), 23.0)
        for bad in ("abc", "0.5", "200", "nan", "inf"):
            with self.assertRaises(DispatchGuardError):
                configured_min_hours({"WATCHTOWER_MIN_DISPATCH_HOURS": bad})
        self.assertIsNone(guard_dispatch(lambda: self.storage, command="check", override=None, profile="cloud", environ={}))
        with self.assertRaises(DispatchGuardError):
            guard_dispatch(lambda: self.storage, command="check", override="early", profile="cloud", environ={})
        with self.assertRaises(DispatchRefused):
            guard_dispatch(lambda: self.storage, command="check", override=None, profile="any",
                           environ={"WATCHTOWER_MIN_DISPATCH_HOURS": "23"})
        with self.assertRaises(DispatchRefused):
            guard_dispatch(lambda: self.storage, command="check", override="early", profile=None,
                           environ={"WATCHTOWER_MIN_DISPATCH_HOURS": "23"})
        self.assertEqual(configured_tolerance({}), timedelta(minutes=10))
        self.assertEqual(configured_tolerance({"WATCHTOWER_DISPATCH_TOLERANCE_MINUTES": "0"}), timedelta(0))
        for bad in ("-1", "31", "nan", "x"):
            with self.assertRaises(DispatchGuardError):
                configured_tolerance({"WATCHTOWER_DISPATCH_TOLERANCE_MINUTES": bad})
        self.assertFalse((self.root / GUARD_OBJECT).exists())


class CliGuardTests(unittest.TestCase):
    CONFIG = Path(__file__).resolve().parents[1] / "config" / "example_sources.json"

    def run_cli(self, root, argv, env_extra=None):
        env = {"WATCHTOWER_STORAGE": "local", "WATCHTOWER_STORAGE_ROOT": str(root),
               "WATCHTOWER_RUN_RECEIPTS": "0", "WATCHTOWER_ALLOW_EXAMPLE_CONFIG": "1",
               "WATCHTOWER_EXECUTION_PROFILE": "cloud", **(env_extra or {})}
        stdout, stderr = io.StringIO(), io.StringIO()
        result = {"overall": "ok", "counts": {}, "sources": {}}
        with patch.dict(os.environ, env), \
                patch("sys.argv", ["watchtower", "--config", str(self.CONFIG), *argv]), \
                patch("clearparcel.datawatch.cloud_job.run_cloud_job", return_value=result) as job, \
                patch("clearparcel.datawatch.cli.check_sources", return_value=result) as check, \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main()
        return code, job.call_count + check.call_count, stderr.getvalue()

    def test_guard_off_by_default_runs_without_a_record(self):
        with tempfile.TemporaryDirectory() as td:
            code, polled, _ = self.run_cli(Path(td), ["cloud-job"])
            self.assertEqual((code, polled), (cli.EXIT_OK, 1))
            self.assertFalse((Path(td) / GUARD_OBJECT).exists())

    def test_second_run_within_the_minimum_is_refused_before_polling(self):
        env = {"WATCHTOWER_MIN_DISPATCH_HOURS": "23"}
        with tempfile.TemporaryDirectory() as td:
            code, polled, _ = self.run_cli(Path(td), ["cloud-job"], env)
            self.assertEqual((code, polled), (cli.EXIT_OK, 1))
            code, polled, stderr = self.run_cli(
                Path(td), ["check", "--source", "x", "--no-save", "--execution-profile", "cloud"], env)
            self.assertEqual((code, polled), (cli.EXIT_DISPATCH_REFUSED, 0))
            self.assertIn("watchtower_dispatch_refused", stderr)
            code, polled, stderr = self.run_cli(
                Path(td), ["cloud-job", "--override-min-interval", "owner-approved recheck"], env)
            self.assertEqual((code, polled), (cli.EXIT_OK, 1))
            self.assertIn('"override": true', stderr)
            self.assertNotIn("owner-approved recheck", stderr)

    def test_placeholder_refusal_does_not_use_the_slot(self):
        env = {"WATCHTOWER_MIN_DISPATCH_HOURS": "23", "WATCHTOWER_ALLOW_EXAMPLE_CONFIG": "0"}
        with tempfile.TemporaryDirectory() as td:
            code, polled, _ = self.run_cli(Path(td), ["cloud-job"], env)
            self.assertEqual((code, polled), (cli.EXIT_TOOL_FAILURE, 0))
            self.assertFalse((Path(td) / GUARD_OBJECT).exists())

    def test_unreadable_guard_record_exits_3(self):
        env = {"WATCHTOWER_MIN_DISPATCH_HOURS": "23"}
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "runs").mkdir()
            (Path(td) / GUARD_OBJECT).write_text("{", encoding="utf-8")
            code, polled, stderr = self.run_cli(Path(td), ["cloud-job"], env)
            self.assertEqual((code, polled), (cli.EXIT_TOOL_FAILURE, 0))
            self.assertIn("dispatch guard", stderr)


if __name__ == "__main__":
    unittest.main()
