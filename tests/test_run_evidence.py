import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from clearparcel.datawatch import cli
from clearparcel.datawatch.alert_delivery import AlertLedger
from clearparcel.datawatch.run_evidence import (
    RECEIPTS_OBJECT, ReceiptError, ReceiptLog, build_receipt, expected_sources,
    minimize_report, record_run_evidence)
from clearparcel.datawatch.storage import LocalStorage, StorageConflictError
from clearparcel.datawatch.watch import _held_county_slugs

ROUTE = {"channel": "email", "recipient": "operator@example.invalid",
         "escalation_owner": "Synthetic operator", "runbook_ref": "docs/alert-routing.md"}


def report(day, status="ok", **extra):
    stamp = f"2026-10-{day:02}T10:00:00Z"
    return {"generated_at": stamp, "scope": {"type": "fleet"}, "overall": status,
            "counts": {s: int(s == status) for s in ("ok", "warn", "error")},
            "telemetry": {"wall_ms": 5}, "runtime_identity": {"image": "synthetic"},
            "sources": {"sample": {"status": status, "checked_at": f"2026-10-{day:02}T10:00:01Z",
                                   "url": "https://private.example.invalid/?token=secret",
                                   "error": "private-diagnostic", "feature_count": 98765,
                                   **extra}}}


CONFIG = {"sources": [{"id": "sample", "name": "Sample", "execution_profiles": ["cloud"]}]}


class FakeTransport:
    name = "fake"
    replay_safe = False
    sent = []

    def send(self, digest):
        FakeTransport.sent.append(digest)
        return {"provider_ref": "fake"}


class RunEvidenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.storage = LocalStorage(self.root)
        FakeTransport.sent = []

    def tearDown(self):
        self._tmp.cleanup()

    def record(self, day, status="ok", *, env=None, exit_code=None, rpt="default",
               start="09:59", end="10:05", now=None, **kwargs):
        environ = {"WATCHTOWER_RUN_RECEIPTS": "1", "CLOUD_RUN_EXECUTION": f"exec-{day}"}
        environ.update(env or {})
        stream = io.StringIO()
        summary = record_run_evidence(
            kwargs.pop("config", CONFIG), storage=kwargs.pop("storage", self.storage),
            profile="cloud", started_at=f"2026-10-{day:02}T{start}:00Z",
            completed_at=f"2026-10-{day:02}T{end}:00Z",
            exit_code={"ok": 0, "warn": 1, "error": 2}[status] if exit_code is None else exit_code,
            report=report(day, status) if rpt == "default" else rpt,
            environ=environ, stream=stream, transports={"fake": FakeTransport},
            now=now or f"2026-10-{day:02}T{end}:00Z", **kwargs)
        return summary, [json.loads(line) for line in stream.getvalue().splitlines()]

    def receipts_path(self):
        return self.root / RECEIPTS_OBJECT

    def test_minimized_report_keeps_triage_fields_only(self):
        slim = minimize_report(report(20, "error", deferred={"reason": "provider-rate-limit"},
                                      rate_limited=True))
        text = json.dumps(slim)
        for forbidden in ("private.example", "secret", "private-diagnostic", "98765",
                          "telemetry", "runtime_identity"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(slim["sources"]["sample"],
                         {"status": "error", "checked_at": "2026-10-20T10:00:01Z",
                          "rate_limited": True, "deferred": True})
        self.assertIsNone(minimize_report(None))

    def test_disabled_by_default_writes_nothing(self):
        summary = record_run_evidence(CONFIG, storage=self.storage, profile="cloud",
                                      started_at="2026-10-20T09:59:00Z",
                                      completed_at="2026-10-20T10:05:00Z", exit_code=0,
                                      report=report(20), environ={}, stream=io.StringIO())
        self.assertEqual(summary, {"receipts": "disabled", "delivery": "not_configured"})
        self.assertFalse(self.receipts_path().exists())

    def test_receipt_log_is_idempotent_bounded_and_per_worker(self):
        log = ReceiptLog(self.storage, keep=3)
        for day in range(10, 16):
            for worker in ("cloud", "local"):
                self.assertTrue(log.append(build_receipt(
                    worker=worker, execution_id=f"{worker}-{day}", started_at="x",
                    completed_at="y", exit_code=0, report=None)))
        self.assertFalse(log.append(build_receipt(worker="cloud", execution_id="cloud-15",
                                                  started_at="x", completed_at="y",
                                                  exit_code=0, report=None)))
        self.assertEqual([r["execution_id"] for r in log.executions("cloud")],
                         ["cloud-13", "cloud-14", "cloud-15"])
        self.assertEqual(len(log.executions("local")), 3)
        with self.assertRaises(ValueError):
            ReceiptLog(self.storage, keep=0)

    def test_receipt_log_retries_conflicts_and_rejects_malformed_data(self):
        injected = {"done": False}
        storage = self.storage

        class Racing(LocalStorage):
            def upload_if_version(self, name, source, version):
                if not injected["done"]:
                    injected["done"] = True
                    ReceiptLog(storage).append(build_receipt(
                        worker="cloud", execution_id="other", started_at="x",
                        completed_at="y", exit_code=0, report=None))
                return super().upload_if_version(name, source, version)

        self.assertTrue(ReceiptLog(Racing(self.root)).append(build_receipt(
            worker="cloud", execution_id="mine", started_at="x", completed_at="y",
            exit_code=0, report=None)))
        self.assertEqual({r["execution_id"] for r in ReceiptLog(self.storage).executions("cloud")},
                         {"other", "mine"})
        for content in ("not json", json.dumps({"schema_version": 9, "executions": []}),
                        json.dumps({"schema_version": 1, "executions": [{"worker": 1}]})):
            with self.subTest(content=content[:20]):
                self.receipts_path().write_text(content, encoding="utf-8")
                with self.assertRaises(ReceiptError):
                    ReceiptLog(self.storage).read()

    def test_expected_scope_follows_profiles_enablement_and_holds(self):
        held = sorted(_held_county_slugs())
        self.assertTrue(held, "the research data file should hold at least one county")
        config = {"sources": [
            {"id": "cloud-only", "execution_profiles": ["cloud"]},
            {"id": "any", "execution_profiles": ["any"]},
            {"id": "local-only", "execution_profiles": ["local"]},
            {"id": "disabled", "enabled": False, "execution_profiles": ["cloud"]},
            {"id": "held-parcel", "execution_profiles": ["cloud"], "county_slug": held[0],
             "category": "Parcels"},
            {"id": "held-roads", "execution_profiles": ["cloud"], "county_slug": held[0],
             "category": "Roads"},
        ]}
        self.assertEqual([r["source_id"] for r in expected_sources(config, "cloud")],
                         ["cloud-only", "any", "held-roads"])
        self.assertEqual([r["source_id"] for r in expected_sources(config, "local")],
                         ["any", "local-only"])

    def test_receipts_without_delivery_configuration(self):
        summary, lines = self.record(20)
        self.assertEqual(summary, {"receipts": "recorded", "delivery": "not_configured",
                                   "execution_id": "exec-20:0:0"})
        self.assertEqual(lines, [])
        again, _ = self.record(20)
        self.assertEqual(again["receipts"], "already_recorded")
        stored = self.receipts_path().read_text()
        self.assertNotIn("private.example", stored)
        self.assertNotIn("98765", stored)

    def test_disabled_delivery_configuration_is_a_logged_dry_run(self):
        private = json.dumps({"delivery": {"enabled": False}, "routing": ROUTE})
        summary, lines = self.record(20, "error", env={"WATCHTOWER_ALERT_DELIVERY_CONFIG": private})
        self.assertEqual(summary["mode"], "disabled_dry_run")
        self.assertEqual(lines[0]["severity"], "INFO")
        self.assertEqual(lines[0]["watchtower_alert_delivery"]["preview_messages"], 1)
        self.assertNotIn("operator@example.invalid", json.dumps(lines))
        self.assertFalse((self.root / "alerts" / "delivery-ledger.json").exists())
        self.assertEqual(FakeTransport.sent, [])

    def test_enabled_delivery_uses_recorded_history_for_failure_and_recovery(self):
        private = json.dumps({"delivery": {"enabled": True, "transport": "fake"}, "routing": ROUTE})
        env = {"WATCHTOWER_ALERT_DELIVERY_CONFIG": private}
        first, _ = self.record(19, "error", env=env)
        self.assertEqual(first["delivery"], "handed_off")
        repeat, _ = self.record(20, "error", env=env)
        self.assertEqual(repeat["delivery"], "nothing_to_send")
        recovered, _ = self.record(21, "ok", env=env)
        self.assertEqual(recovered["delivery"], "handed_off")
        kinds = [e["type"] for d in FakeTransport.sent for e in d["events"]]
        self.assertEqual(kinds, ["source_error", "recovered"])
        ledger = AlertLedger(self.storage).read()[0]
        self.assertEqual(sorted(r["state"] for r in ledger["events"].values()), ["sent", "sent"])

    def test_tool_failure_receipt_without_report_alerts_as_evidence_gap(self):
        private = json.dumps({"delivery": {"enabled": True, "transport": "fake"}, "routing": ROUTE})
        summary, _ = self.record(20, exit_code=3, rpt=None,
                                 env={"WATCHTOWER_ALERT_DELIVERY_CONFIG": private})
        self.assertEqual(summary["delivery"], "handed_off")
        self.assertEqual([e["type"] for e in FakeTransport.sent[0]["events"]], ["evidence_gap"])

    def enabled(self, **extra):
        private = json.dumps({"delivery": {"enabled": True, "transport": "fake"}, "routing": ROUTE})
        return {"WATCHTOWER_ALERT_DELIVERY_CONFIG": private, **extra}

    def test_overlapping_or_late_receipts_do_not_block_later_delivery(self):
        self.record(19, "ok", env=self.enabled())
        # A manual run overlapping the scheduled one on the 20th.
        self.record(20, "ok", env=self.enabled())
        overlap, lines = self.record(20, "ok", start="10:01", end="10:07",
                                     env=self.enabled(CLOUD_RUN_EXECUTION="manual-overlap"))
        self.assertEqual(overlap["delivery"], "held_out_of_order_run")
        self.assertEqual(lines[-1]["severity"], "WARNING")
        nxt, lines = self.record(21, "error", env=self.enabled())
        self.assertEqual(nxt["delivery"], "handed_off")
        self.assertEqual(lines[-1]["watchtower_alert_delivery"]["receipts_excluded"], 1)
        self.assertEqual([e["type"] for e in FakeTransport.sent[-1]["events"]], ["source_error"])

    def test_overlapping_failure_is_not_sent_twice(self):
        first, _ = self.record(20, "error", start="09:58", end="10:05", env=self.enabled())
        self.assertEqual(first["delivery"], "handed_off")
        held, _ = self.record(20, "error", start="10:00", end="10:12",
                              env=self.enabled(CLOUD_RUN_EXECUTION="manual-overlap"))
        self.assertEqual(held["delivery"], "held_out_of_order_run")
        nxt, _ = self.record(21, "error", env=self.enabled())
        self.assertEqual(nxt["delivery"], "nothing_to_send")
        self.assertEqual(len(FakeTransport.sent), 1)

    def test_earlier_run_recorded_late_is_held_not_sent_twice(self):
        later, _ = self.record(20, "error", start="09:59", end="10:15",
                               env=self.enabled(CLOUD_RUN_EXECUTION="run-b"))
        self.assertEqual(later["delivery"], "handed_off")
        late = self.record(19, "error", env=self.enabled(CLOUD_RUN_EXECUTION="run-a"),
                           now="2026-10-20T10:20:00Z")[0]
        self.assertEqual(late["delivery"], "held_out_of_order_run")
        nxt, lines = self.record(21, "error", env=self.enabled())
        self.assertEqual(nxt["delivery"], "nothing_to_send")
        self.assertEqual(lines[-1]["watchtower_alert_delivery"]["receipts_excluded"], 1)
        self.assertEqual(len(FakeTransport.sent), 1)

    def test_later_recorded_longer_overlap_does_not_rekey_the_incident(self):
        first, _ = self.record(20, "error", start="10:00", end="10:05", env=self.enabled())
        self.assertEqual(first["delivery"], "handed_off")
        # A manual run that started earlier but finished (and was recorded) later.
        held, _ = self.record(20, "error", start="09:58", end="10:20",
                              env=self.enabled(CLOUD_RUN_EXECUTION="manual-long"))
        self.assertEqual(held["delivery"], "held_out_of_order_run")
        nxt, lines = self.record(21, "error", env=self.enabled())
        self.assertEqual(nxt["delivery"], "nothing_to_send")
        self.assertEqual(lines[-1]["watchtower_alert_delivery"]["receipts_excluded"], 1)
        self.assertEqual(len(FakeTransport.sent), 1)

    def test_pinned_receipts_do_not_lose_another_sources_reopened_recovery(self):
        config = {"sources": [{"id": s, "execution_profiles": ["cloud"]} for s in ("s1", "s2")]}
        pattern = {1: "error", 2: "ok", 3: "error", 4: "error", 5: "error", 6: "error",
                   7: "error", 8: "ok"}
        for day, s2 in pattern.items():
            stamp = f"2026-10-{day:02}T10:00:00Z"
            statuses = {"s1": "error", "s2": s2}
            rpt = {"generated_at": stamp, "scope": {"type": "fleet"}, "overall": "error",
                   "counts": {s: sum(v == s for v in statuses.values())
                              for s in ("ok", "warn", "error")},
                   "sources": {sid: {"status": st, "checked_at": f"2026-10-{day:02}T10:00:01Z"}
                               for sid, st in statuses.items()}}
            summary, _ = self.record(day, exit_code=2, rpt=rpt, config=config, keep=3,
                                     env=self.enabled())
            self.assertNotEqual(summary["delivery"], "failed", day)
        sent = [(e["type"], e["source_id"]) for d in FakeTransport.sent for e in d["events"]]
        self.assertEqual(sent.count(("source_error", "s1")), 1)
        self.assertEqual([x for x in sent if x[1] == "s2"],
                         [("source_error", "s2"), ("recovered", "s2"), ("source_error", "s2"),
                          ("recovered", "s2")])
        pinned = [r for r in ReceiptLog(self.storage).executions("cloud") if r.get("pinned_sources")]
        self.assertEqual([(r["execution_id"], r["pinned_sources"]) for r in pinned],
                         [("exec-1:0:0", ["s1"])])

    def test_malformed_stored_timestamps_are_excluded_not_fatal(self):
        log = ReceiptLog(self.storage)
        log.append(build_receipt(worker="cloud", execution_id="bad", started_at="not-a-time",
                                 completed_at="2026-10-19T10:05:00Z", exit_code=0, report=None))
        summary, lines = self.record(20, "error", env=self.enabled())
        self.assertEqual(summary["delivery"], "handed_off")
        self.assertEqual(lines[-1]["watchtower_alert_delivery"]["receipts_excluded"], 1)

    def test_long_incident_keeps_its_key_after_trimming(self):
        for day in range(1, 13):
            self.record(day, "error", env=self.enabled(), keep=3)
        kinds = [e["type"] for d in FakeTransport.sent for e in d["events"]]
        self.assertEqual(kinds.count("source_error"), 1)
        rows = ReceiptLog(self.storage).executions("cloud")
        self.assertEqual(rows[0]["execution_id"], "exec-1:0:0")
        self.assertEqual(len(rows), 4)
        self.record(13, "ok", env=self.enabled(), keep=3)
        self.record(14, "ok", env=self.enabled(), keep=3)
        self.assertEqual(len(ReceiptLog(self.storage).executions("cloud")), 3)
        self.assertEqual([e["type"] for d in FakeTransport.sent for e in d["events"]],
                         ["source_error", "recovered"])

    def test_late_append_does_not_release_an_open_incidents_receipt(self):
        for day in range(1, 6):
            self.record(day, "error", env=self.enabled(), keep=3)
        self.record(2, "error", start="10:01", end="10:04", keep=3,
                    env=self.enabled(CLOUD_RUN_EXECUTION="late-manual"),
                    now="2026-10-05T10:30:00Z")
        ids = [r["execution_id"] for r in ReceiptLog(self.storage).executions("cloud")]
        self.assertIn("exec-1:0:0", ids)
        self.record(6, "error", env=self.enabled(), keep=3)
        self.assertEqual([e["type"] for d in FakeTransport.sent for e in d["events"]],
                         ["source_error"])

    def test_implausible_times_are_refused_and_cannot_block_the_chain(self):
        future, lines = self.record(20, "error", now="2026-10-20T10:01:00Z", env=self.enabled())
        self.assertEqual(future["receipts"], "rejected_invalid_times")
        self.assertEqual(lines[-1]["watchtower_alert_pipeline_error"]["error"], "invalid_times")
        long_run, _ = self.record(20, "error", start="00:00", end="13:00", env=self.enabled())
        self.assertEqual(long_run["receipts"], "rejected_invalid_times")
        self.assertFalse(self.receipts_path().exists())
        # A far-future row already stored (for example by an older version) is ignored.
        ReceiptLog(self.storage).append(build_receipt(
            worker="cloud", execution_id="skewed", started_at="2027-10-20T09:59:00Z",
            completed_at="2027-10-20T10:05:00Z", exit_code=2, report=None),
            now="2027-10-20T10:05:00Z")
        for day in (21, 22):
            summary, _ = self.record(day, "error" if day == 21 else "ok", env=self.enabled())
            self.assertEqual(summary["delivery"], "handed_off")
        self.assertEqual([e["type"] for d in FakeTransport.sent for e in d["events"]],
                         ["source_error", "recovered"])

    def test_retried_task_attempt_is_a_distinct_receipt(self):
        # The first attempt crashed without a report; the retry succeeded.
        first, _ = self.record(20, exit_code=3, rpt=None, start="09:00", end="09:05",
                               env=self.enabled(CLOUD_RUN_TASK_ATTEMPT="0"))
        retry, _ = self.record(20, "ok", env=self.enabled(CLOUD_RUN_TASK_ATTEMPT="1"))
        self.assertEqual((first["execution_id"], retry["execution_id"]),
                         ("exec-20:0:0", "exec-20:0:1"))
        self.assertEqual(retry["receipts"], "recorded")
        self.assertEqual(retry["delivery"], "nothing_to_send")
        self.assertEqual([e["type"] for d in FakeTransport.sent for e in d["events"]],
                         ["evidence_gap"])
        self.assertEqual(len(ReceiptLog(self.storage).executions("cloud")), 2)

    def test_no_expected_sources_skips_delivery_quietly(self):
        summary, lines = self.record(20, env=self.enabled(), config={"sources": []})
        self.assertEqual(summary["delivery"], "no_expected_sources")
        self.assertEqual(lines, [])

    def test_failures_are_logged_and_never_raised(self):
        class Broken(LocalStorage):
            def upload_if_version(self, name, source, version):
                raise StorageConflictError("synthetic")

        summary, lines = self.record(20, storage=Broken(self.root))
        self.assertEqual(summary["receipts"], "failed")
        self.assertEqual(lines[0]["severity"], "ERROR")
        self.assertEqual(lines[0]["watchtower_alert_pipeline_error"]["stage"], "receipt")
        bad_configs = ("{not json", json.dumps({"delivery": {"enabled": True, "transport": "nope"},
                                                "routing": ROUTE}),
                       json.dumps({"delivery": {"enabled": True, "transport": "structured_log"},
                                   "routing": ROUTE}))
        for day, bad in enumerate(bad_configs, start=21):
            with self.subTest(config=bad[:30]):
                summary, lines = self.record(day, env={"WATCHTOWER_ALERT_DELIVERY_CONFIG": bad})
                self.assertEqual(summary["delivery"], "failed")
                self.assertEqual(lines[-1]["watchtower_alert_pipeline_error"]["stage"], "delivery")
        self.assertEqual(FakeTransport.sent, [])


class CloudJobEvidenceTests(unittest.TestCase):
    CONFIG = Path(__file__).resolve().parents[1] / "config" / "example_sources.json"

    def run_cli(self, root, env_extra, *, result=None, error=None):
        env = {"WATCHTOWER_STORAGE": "local", "WATCHTOWER_STORAGE_ROOT": str(root),
               "CLOUD_RUN_EXECUTION": "synthetic-exec", **env_extra}
        side = {"side_effect": error} if error else {"return_value": result}
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, env), \
                patch("sys.argv", ["watchtower", "--config", str(self.CONFIG), "cloud-job", "--json"]), \
                patch("clearparcel.datawatch.cloud_job.run_cloud_job", **side), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main()
        return code, stderr.getvalue()

    def test_cloud_job_records_receipts_only_when_enabled_and_keeps_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            code, _ = self.run_cli(root, {"WATCHTOWER_RUN_RECEIPTS": "0"}, result=report(20, "error"))
            self.assertEqual(code, cli.EXIT_SOURCE_ERROR)
            self.assertFalse((root / RECEIPTS_OBJECT).exists())
            code, _ = self.run_cli(root, {"WATCHTOWER_RUN_RECEIPTS": "1"}, result=report(20, "error"))
            self.assertEqual(code, cli.EXIT_SOURCE_ERROR)
            rows = ReceiptLog(LocalStorage(root)).executions("cloud")
            self.assertEqual([(r["execution_id"], r["exit_code"]) for r in rows],
                             [("synthetic-exec:0:0", 2)])

    def test_cloud_job_failure_records_a_reportless_receipt_and_still_exits_3(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            code, stderr = self.run_cli(root, {"WATCHTOWER_RUN_RECEIPTS": "1"},
                                        error=RuntimeError("synthetic failure"))
            self.assertEqual(code, cli.EXIT_TOOL_FAILURE)
            self.assertIn("synthetic failure", stderr)
            rows = ReceiptLog(LocalStorage(root)).executions("cloud")
            self.assertEqual([(r["exit_code"], r["report"]) for r in rows], [(3, None)])


if __name__ == "__main__":
    unittest.main()
