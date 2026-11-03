import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from clearparcel.datawatch import public_publish
from clearparcel.datawatch.provider_watchdog import ERROR_KEY, LOG_KEY, overdue_workers, run_provider_watchdog
from clearparcel.datawatch.public_publish import publish_public_snapshot
from clearparcel.datawatch.storage import LocalStorage

NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)


def _agg(**workers):
    return {"schema_version": 2, "generated_at": "2026-11-03T11:00:00+00:00", "overall": "ok",
            "counts": {"ok": 0, "warn": 0, "error": 0}, "workers": workers, "sources": {}}


def _lines(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


class OverdueWorkersTests(unittest.TestCase):
    def test_recent_report_is_not_overdue(self):
        findings, checked = overdue_workers(
            _agg(cloud={"last_report_at": "2026-11-02T11:05:00+00:00"}), now=NOW)
        self.assertEqual((findings, checked), ([], 1))

    def test_report_older_than_threshold_is_overdue(self):
        findings, _ = overdue_workers(
            _agg(cloud={"last_report_at": "2026-11-02T09:59:00+00:00"}), now=NOW)
        self.assertEqual(findings[0]["reason"], "overdue")
        self.assertEqual(findings[0]["worker"], "cloud")
        self.assertEqual(findings[0]["age_minutes"], 26 * 60 + 1)
        self.assertEqual(findings[0]["threshold_minutes"], 1560)

    def test_age_exactly_at_threshold_is_not_overdue(self):
        findings, _ = overdue_workers(_agg(cloud={"last_report_at": "2026-11-02T10:00:00+00:00"}), now=NOW)
        self.assertEqual(findings, [])

    def test_checked_at_is_used_when_last_report_at_is_absent(self):
        findings, _ = overdue_workers(_agg(cloud={"checked_at": "2026-11-03T05:00:00+00:00"}), now=NOW)
        self.assertEqual(findings, [])

    def test_missing_time_and_future_time_are_findings(self):
        findings, _ = overdue_workers(
            _agg(a={}, b={"last_report_at": "not-a-time"}, c={"last_report_at": "2026-11-03T13:00:00+00:00"}),
            now=NOW)
        self.assertEqual({f["worker"]: f["reason"] for f in findings},
                         {"a": "no_report_time", "b": "no_report_time", "c": "clock_skew"})

    def test_small_future_skew_is_tolerated(self):
        findings, _ = overdue_workers(_agg(cloud={"last_report_at": "2026-11-03T12:04:00+00:00"}), now=NOW)
        self.assertEqual(findings, [])

    def test_expected_worker_missing_from_aggregate_is_overdue(self):
        findings, checked = overdue_workers(
            _agg(local={"last_report_at": "2026-10-01T00:00:00+00:00"}), now=NOW, expected={"cloud"})
        self.assertEqual(checked, 1)
        self.assertEqual(findings, [{"worker": "cloud", "threshold_minutes": 1560,
                                     "reason": "missing", "last_report_at": None}])

    def test_retired_workers_are_not_expected_by_default(self):
        aggregate = _agg(cloud={"last_report_at": "2026-11-03T05:00:00+00:00"})
        aggregate["retired_workers"] = {"local": {"retired_at": "2026-10-10T00:00:00+00:00"}}
        self.assertEqual(overdue_workers(aggregate, now=NOW), ([], 1))


class RunProviderWatchdogTests(unittest.TestCase):
    def test_logs_one_error_line_per_overdue_worker(self):
        stream = io.StringIO()
        summary = run_provider_watchdog(
            _agg(cloud={"last_report_at": "2026-11-01T00:00:00+00:00"},
                 other={"last_report_at": "2026-11-03T05:00:00+00:00"}),
            stream, now=NOW, environ={})
        lines = _lines(stream)
        self.assertEqual(summary, {"checked": 2, "overdue": ["cloud"]})
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["severity"], "ERROR")
        self.assertEqual(lines[0][LOG_KEY]["worker"], "cloud")

    def test_environment_sets_expected_workers_and_threshold(self):
        stream = io.StringIO()
        summary = run_provider_watchdog(
            _agg(cloud={"last_report_at": "2026-11-03T11:00:00+00:00"},
                 local={"last_report_at": "2026-10-01T00:00:00+00:00"}),
            stream, now=NOW, environ={"WATCHTOWER_WATCHDOG_WORKERS": "cloud",
                                      "WATCHTOWER_WORKER_STALE_MINUTES": "30"})
        self.assertEqual(summary, {"checked": 1, "overdue": ["cloud"]})
        self.assertEqual(_lines(stream)[0][LOG_KEY]["threshold_minutes"], 30)

    def test_empty_worker_list_falls_back_to_all_current_workers(self):
        summary = run_provider_watchdog(_agg(cloud={"last_report_at": "2026-11-01T00:00:00+00:00"}), io.StringIO(),
                                        now=NOW, environ={"WATCHTOWER_WATCHDOG_WORKERS": " , "})
        self.assertEqual(summary, {"checked": 1, "overdue": ["cloud"]})

    def test_internal_failure_is_logged_with_a_fixed_key(self):
        stream = io.StringIO()
        summary = run_provider_watchdog(_agg(cloud={}), stream, now="not-a-datetime", environ={})
        self.assertEqual(summary["error"], "watchdog_failed")
        self.assertEqual(_lines(stream), [{"severity": "ERROR", ERROR_KEY: "watchdog_failed"}])

    def test_invalid_threshold_falls_back_to_default(self):
        stream = io.StringIO()
        run_provider_watchdog(_agg(cloud={"last_report_at": "2026-11-01T00:00:00+00:00"}), stream, now=NOW,
                              environ={"WATCHTOWER_WORKER_STALE_MINUTES": "soon"})
        self.assertEqual(_lines(stream)[0][LOG_KEY]["threshold_minutes"], 1560)

    def test_never_raises_on_bad_input_or_broken_stream(self):
        class Broken:
            def write(self, _):
                raise OSError("closed")

            def flush(self):
                raise OSError("closed")

        self.assertEqual(run_provider_watchdog(None, io.StringIO(), now=NOW, environ={}),
                         {"checked": 0, "overdue": []})
        summary = run_provider_watchdog(_agg(cloud={}), Broken(), now=NOW, environ={})
        self.assertEqual(summary["overdue"], ["cloud"])

    def test_log_line_carries_no_private_fields(self):
        stream = io.StringIO()
        run_provider_watchdog(
            _agg(cloud={"last_report_at": "2026-11-01T00:00:00+00:00", "telemetry": {"secret": 1},
                        "url": "https://private.invalid"}), stream, now=NOW, environ={})
        self.assertEqual(set(_lines(stream)[0][LOG_KEY]),
                         {"worker", "threshold_minutes", "reason", "last_report_at", "age_minutes"})


class PublisherIntegrationTests(unittest.TestCase):
    def _publish(self, aggregate, with_files=False, **kwargs):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "source").mkdir()
            (root / "dest").mkdir()
            source_text = json.dumps(aggregate)
            (root / "source" / "aggregate-state.json").write_text(source_text, encoding="utf-8")
            result = publish_public_snapshot(LocalStorage(root / "source"), LocalStorage(root / "dest"),
                                             workdir=root / "work", **kwargs)
            if not with_files:
                return result
            published = json.loads((root / "dest" / "aggregate-state.json").read_text(encoding="utf-8"))
            unchanged = (root / "source" / "aggregate-state.json").read_text(encoding="utf-8") == source_text
            return result, published, unchanged

    def test_watchdog_changes_neither_the_snapshot_nor_the_private_aggregate(self):
        aggregate = _agg(cloud={"overall": "ok", "last_report_at": "2026-10-01T00:00:00+00:00"})
        _, without, unchanged_a = self._publish(aggregate, with_files=True)
        _, with_dog, unchanged_b = self._publish(aggregate, with_files=True, watchdog_stream=io.StringIO())
        without.pop("public_published_at")
        with_dog.pop("public_published_at")
        self.assertEqual(without, with_dog)
        self.assertTrue(unchanged_a and unchanged_b)

    def test_environment_switch_turns_the_watchdog_off(self):
        env = {"WATCHTOWER_PUBLIC_SOURCE_BUCKET": "src", "WATCHTOWER_PUBLIC_DEST_BUCKET": "dst"}
        for value, expected in (("0", None), ("1", "stream"), (None, "stream")):
            environ = dict(env, **({"WATCHTOWER_PROVIDER_WATCHDOG": value} if value is not None else {}))
            with patch.dict(public_publish.os.environ, environ, clear=True), \
                    patch.object(public_publish, "GCSStorage"), \
                    patch.object(public_publish, "publish_public_snapshot", return_value={}) as publish:
                public_publish.publish_public_snapshot_from_env()
            stream = publish.call_args.kwargs["watchdog_stream"]
            self.assertEqual(stream is None, expected is None, value)

    def test_overdue_worker_is_logged_and_publication_still_succeeds(self):
        stream = io.StringIO()
        result = self._publish(_agg(cloud={"overall": "ok", "last_report_at": "2026-10-01T00:00:00+00:00"}),
                               watchdog_stream=stream)
        self.assertTrue(result["published"])
        self.assertEqual(result["provider_watchdog"]["overdue"], ["cloud"])
        self.assertEqual(_lines(stream)[0][LOG_KEY]["reason"], "overdue")

    def test_without_stream_the_watchdog_does_not_run(self):
        result = self._publish(_agg(cloud={"overall": "ok", "last_report_at": "2026-10-01T00:00:00+00:00"}))
        self.assertNotIn("provider_watchdog", result)


if __name__ == "__main__":
    unittest.main()
