import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from clearparcel.datawatch.alert_routing import prepare_alert_preview


ROUTE = {"channel": "email", "recipient": "operator@example.invalid",
         "escalation_owner": "Synthetic operator", "runbook_ref": "docs/alert-routing.md"}
EXPECTED = [{"worker": "cloud", "source_id": "sample"}]


def run(day, status="ok", **source_values):
    start = f"2026-10-{day:02}T10:00:00Z"
    return {"execution_id": f"synthetic-{day}", "worker": "cloud",
            "started_at": start, "completed_at": f"2026-10-{day:02}T10:05:00Z",
            "exit_code": {"ok": 0, "warn": 1, "error": 2}[status],
            "report": {"generated_at": start, "scope": {"type": "fleet"},
                       "overall": status,
                       "counts": {s: int(s == status) for s in ("ok", "warn", "error")},
                       "sources": {"sample": {"status": status,
                                   "checked_at": f"2026-10-{day:02}T10:00:01Z",
                                   **source_values}}}}


class AlertRoutingTests(unittest.TestCase):
    def preview(self, rows, **kwargs):
        return prepare_alert_preview(rows, expected_sources=kwargs.pop("expected_sources", EXPECTED),
                                     routing=kwargs.pop("routing", ROUTE),
                                     as_of=kwargs.pop("as_of", "2026-10-20T12:00:00Z"),
                                     **kwargs)

    def kinds(self, result):
        return [message["type"] for message in result["messages"]]

    def test_failure_and_recovery_are_bounded_to_latest_worker_run(self):
        rows = [run(19, "error"), run(20)]
        original = copy.deepcopy(rows)
        preview = self.preview(rows)
        self.assertEqual(self.kinds(preview), ["recovered"])
        self.assertEqual(rows, original)
        self.assertEqual(preview["notification_delivery"], "not_attempted")
        self.assertFalse(preview["activation_authorized"])
        self.assertFalse(preview["delivery_acceptance_complete"])
        self.assertEqual(self.kinds(self.preview([run(20)])), [])
        self.assertEqual(self.kinds(self.preview([run(20, "error")])), ["source_error"])
        self.assertEqual(self.kinds(self.preview([run(20, "warn")])), ["source_warning"])

    def test_overdue_is_separate_and_old_recovery_is_not_current(self):
        result = self.preview([run(17, "error"), run(18)])
        self.assertEqual(self.kinds(result), ["check_overdue"])
        result = self.preview([run(18, "error")])
        self.assertEqual(self.kinds(result), ["source_error", "check_overdue"])
        exact = "2026-10-19T22:00:01Z"
        self.assertEqual(self.kinds(self.preview([run(18)], as_of=exact)), [])
        self.assertEqual(self.kinds(self.preview([run(18)], as_of="2026-10-19T22:00:02Z")),
                         ["check_overdue"])

    def test_rate_limit_and_retained_check_do_not_become_recovery(self):
        result = self.preview([run(19, "error", rate_limited=True)])
        self.assertEqual(self.kinds(result), ["provider_rate_limit"])
        result = self.preview([run(18, "error", rate_limited=True),
                               run(20, "error", deferred={"reason": "provider-rate-limit"},
                                   checked_at="2026-10-18T10:00:01Z")])
        self.assertEqual(self.kinds(result), ["provider_backoff", "check_overdue"])
        self.assertEqual(result["messages"][0]["checked_at"], "2026-10-18T10:00:01+00:00")

    def test_missing_invalid_or_partial_latest_report_cannot_reuse_old_success(self):
        for mutation in ("missing_report", "missing_source", "partial", "counts", "future"):
            latest = run(20)
            if mutation == "missing_report":
                latest.pop("report")
            elif mutation == "missing_source":
                latest["report"]["sources"]["other"] = latest["report"]["sources"].pop("sample")
            elif mutation == "partial":
                latest["report"]["scope"]["type"] = "source"
            elif mutation == "counts":
                latest["report"]["counts"]["ok"] = 99
            else:
                latest["report"]["sources"]["sample"]["checked_at"] = "2026-10-21T10:00:00Z"
            with self.subTest(mutation=mutation):
                result = self.preview([run(19), latest])
                self.assertEqual(self.kinds(result), ["evidence_gap"])
                self.assertTrue(result["source_evidence_gaps"])
        self.assertEqual(self.kinds(self.preview([])), ["evidence_gap"])

    def test_expected_scope_does_not_hide_missing_worker(self):
        scope = EXPECTED + [{"worker": "local", "source_id": "sample"}]
        result = self.preview([run(19, "error"), run(20)], expected_sources=scope)
        self.assertEqual(self.kinds(result), ["recovered", "evidence_gap"])
        self.assertEqual(result["messages"][1]["worker"], "local")

    def test_incident_keys_are_stable_until_recovery_then_change(self):
        first = self.preview([run(18, "error")])["messages"][0]["event_key"]
        again = self.preview([run(18, "error"), run(19, "error")])["messages"][0]["event_key"]
        self.assertEqual(first, again)
        reopened = self.preview([run(18, "error"), run(19), run(20, "error")])
        self.assertNotEqual(first, reopened["messages"][0]["event_key"])
        late = self.preview([run(18)], as_of="2026-10-21T12:00:00Z")
        self.assertEqual(self.preview([run(18)])["messages"][0]["event_key"],
                         late["messages"][0]["event_key"])

    def test_provider_diagnostics_are_not_copied(self):
        result = self.preview([run(20, "error", error="private-token-secret",
                                   url="https://private.example.invalid/?secret=secret",
                                   feature_count=123456)])
        serialized = json.dumps(result)
        for forbidden in ("private-token-secret", "https://private", "feature_count", "123456"):
            self.assertNotIn(forbidden, serialized)

    def test_missing_route_stays_explicit_and_input_is_not_mutated(self):
        route = {}
        result = self.preview([run(20, "error")], routing=route)
        self.assertEqual(len(result["routing_gaps"]), 4)
        self.assertEqual(route, {})
        self.assertFalse(result["activation_authorized"])

    def test_invalid_route_scope_and_age_fail_closed(self):
        for route in ({**ROUTE, "recipient": "a\nBcc: b"}, {**ROUTE, "channel": "sms"},
                      {**ROUTE, "recipient": []}):
            with self.assertRaises(ValueError):
                self.preview([run(20)], routing=route)
        for scope in ([], EXPECTED * 2, [{"worker": "cloud", "source_id": ""}]):
            with self.assertRaises(ValueError):
                self.preview([run(20)], expected_sources=scope)
        for age in (0, True, float("nan")):
            with self.assertRaises(ValueError):
                self.preview([run(20)], max_age_hours=age)

    def test_cli_preserves_inputs_outputs_and_reports_evidence_gaps(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "preview_alert_routing.py"
        with tempfile.TemporaryDirectory() as td:
            source, target = Path(td) / "input.json", Path(td) / "preview.json"
            data = {"executions": [run(20, "error")], "expected_sources": EXPECTED, "routing": ROUTE}
            source.write_text(json.dumps(data), encoding="utf-8")
            command = [sys.executable, str(script), "--input", str(source),
                       "--output", str(target), "--as-of", "2026-10-20T12:00:00Z"]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            saved = target.read_bytes()
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertEqual(target.read_bytes(), saved)
            self.assertEqual(json.loads(source.read_text()), data)
            data["executions"] = []
            source.write_text(json.dumps(data), encoding="utf-8")
            command[command.index("--output") + 1] = str(Path(td) / "gap.json")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
