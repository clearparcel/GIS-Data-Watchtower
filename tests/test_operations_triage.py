import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from clearparcel.datawatch.operations_triage import triage_executions


AS_OF = "2026-10-20T12:00:00Z"


def execution(day, status="ok", worker="cloud", **source_values):
    start = f"2026-10-{day:02}T10:00:00Z"
    checked = f"2026-10-{day:02}T10:00:01Z"
    return {"execution_id": f"synthetic-{day}", "worker": worker,
            "started_at": start, "completed_at": f"2026-10-{day:02}T10:05:00Z",
            "exit_code": {"ok": 0, "warn": 1, "error": 2}[status],
            "report": {"worker": worker, "generated_at": start, "overall": status,
                       "scope": {"type": "fleet"},
                       "counts": {s: int(s == status) for s in ("ok", "warn", "error")},
                       "sources": {"sample": {"status": status, "checked_at": checked,
                                               **source_values}}}}


class OperationsTriageTests(unittest.TestCase):
    def triage(self, rows, **kwargs):
        return triage_executions(rows, as_of=AS_OF, **kwargs)

    def test_status_exits_do_not_prove_provider_cause_without_reports(self):
        rows = []
        for day, code in zip(range(15, 20), (0, 2, 2, 1, 3)):
            row = execution(day)
            row["exit_code"] = code
            del row["report"]
            rows.append(row)
        result = self.triage(rows)
        self.assertFalse(result["evidence_complete"])
        self.assertEqual([r["outcome"] for r in result["executions"]],
                         ["ok_exit", "source_or_scope_error_exit", "source_or_scope_error_exit",
                          "source_warning_exit", "tool_failure_exit"])
        self.assertEqual(result["events"], [])

    def test_synthetic_failure_backoff_and_later_recovery_preserve_input(self):
        rows = [execution(16, "error", rate_limited=True),
                execution(17, "error", deferred={"reason": "provider-rate-limit"},
                          checked_at="2026-10-16T10:00:01Z"),
                execution(19)]
        original = copy.deepcopy(rows)
        result = self.triage(list(reversed(rows)))
        self.assertTrue(result["evidence_complete"])
        self.assertEqual([e["type"] for e in result["events"]],
                         ["provider_rate_limit", "provider_backoff", "recovered"])
        self.assertEqual(result["unresolved_sources"], [])
        self.assertEqual(result["notification_delivery"], "not_attempted")
        self.assertEqual(rows, original)

    def test_missing_source_and_different_worker_do_not_clear_failure(self):
        missing = execution(17)
        missing["report"]["sources"] = {"other": missing["report"]["sources"]["sample"]}
        result = self.triage([execution(16, "error"), missing, execution(19, worker="local")])
        self.assertEqual(len(result["unresolved_sources"]), 1)
        self.assertNotIn("recovered", [e["type"] for e in result["events"]])

    def test_stale_or_deferred_success_cannot_claim_recovery(self):
        for values in ({"checked_at": "2026-10-15T10:00:01Z"},
                       {"deferred": {"reason": "provider-rate-limit"}},
                       {"rate_limited": True},
                       {"worker": "local"}):
            with self.subTest(values=values):
                result = self.triage([execution(16, "error"), execution(19, **values)])
                self.assertEqual(len(result["unresolved_sources"]), 1)
                if "worker" not in values:
                    self.assertFalse(result["evidence_complete"])

    def test_future_deferred_observation_is_not_fresh_evidence(self):
        row = execution(19, "warn", deferred={"reason": "provider-rate-limit"},
                        checked_at="2026-10-20T10:00:00Z")
        result = self.triage([row])
        self.assertFalse(result["evidence_complete"])
        self.assertEqual(result["executions"][0]["sources"][0]["freshness"], "unknown")

    def test_mismatched_report_cannot_claim_recovery(self):
        for field, value in (("counts", {"ok": 99, "warn": 0, "error": 0}),
                             ("overall", "warn"), ("worker", "local"),
                             ("generated_at", "2026-10-16T10:00:00Z"),
                             ("workers", {"cloud": {}})):
            with self.subTest(field=field):
                good = execution(19)
                good["report"][field] = value
                result = self.triage([execution(16, "error"), good])
                self.assertFalse(result["evidence_complete"])
                self.assertEqual(len(result["unresolved_sources"]), 1)

    def test_fresh_report_does_not_refresh_deferred_source(self):
        result = self.triage([execution(20, "warn", checked_at="2026-10-15T10:00:00Z",
                                       deferred={"reason": "provider-rate-limit"})])
        row = result["executions"][0]
        self.assertEqual(row["report_freshness"], "fresh")
        self.assertEqual(row["sources"][0]["freshness"], "overdue")

    def test_conflicting_exit_and_unknown_status_are_evidence_gaps(self):
        row = execution(19)
        row["exit_code"] = 3
        self.assertIn("exit_disagrees_with_report",
                      self.triage([row])["executions"][0]["evidence_gaps"])
        row["report"]["sources"]["sample"]["status"] = "unexpected"
        self.assertIn("unknown_source_status",
                      self.triage([row])["executions"][0]["evidence_gaps"])

    def test_empty_scope_is_not_a_provider_failure(self):
        row = execution(19, "error")
        row["report"].update(scope={"type": "empty"}, sources={},
                             counts={"ok": 0, "warn": 0, "error": 0})
        result = self.triage([row])
        self.assertTrue(result["evidence_complete"])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["executions"][0]["scope"], "empty")

    def test_reject_ambiguous_identity_time_and_age(self):
        with self.assertRaises(ValueError):
            self.triage([execution(19), execution(19)])
        overlap = execution(19)
        overlap["execution_id"] = "different"
        with self.assertRaises(ValueError):
            self.triage([execution(19), overlap])
        for stamp in ("not-a-date", "2026-10-19T10:00:00", "2026-10-21T10:00:00Z"):
            row = execution(19)
            row["started_at"] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                self.triage([row])
        for age in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(age=age), self.assertRaises(ValueError):
                self.triage([], max_age_hours=age)
        self.assertFalse(self.triage([])["evidence_complete"])

    def test_raw_diagnostics_credentials_and_measurements_are_not_copied(self):
        row = execution(19, "error", url="https://private.invalid/?token=secret",
                        error="sensitive diagnostic", mngac_completeness={"owner": "PRIVATE"})
        result = json.dumps(self.triage([row]))
        for secret in ("private.invalid", "secret", "sensitive diagnostic", "PRIVATE"):
            self.assertNotIn(secret, result)

    def test_cli_creates_receipt_without_overwriting_evidence(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "triage_provider_runs.py"
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.json", Path(directory) / "receipt.json"
            source.write_text(json.dumps([execution(19)]), encoding="utf-8-sig")
            original = source.read_bytes()
            command = [sys.executable, str(script), "--input", str(source),
                       "--output", str(output), "--as-of", AS_OF]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            receipt = output.read_bytes()
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertEqual(output.read_bytes(), receipt)
            command[command.index("--output") + 1] = str(source)
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
