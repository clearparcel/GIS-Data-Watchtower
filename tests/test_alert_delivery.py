import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from clearparcel.datawatch.alert_delivery import (
    AlertLedger, DeliveryAmbiguous, DeliveryRejected, LedgerError, StructuredLogTransport,
    acknowledge, deliver_alerts, ledger_status, normalize_config, reconcile)
from clearparcel.datawatch.storage import LocalStorage, StorageConflictError


ROUTE = {"channel": "email", "recipient": "operator@example.invalid",
         "escalation_owner": "Synthetic operator", "runbook_ref": "docs/alert-routing.md"}
ENABLED = {"enabled": True, "transport": "fake"}


def run(day, sources=None, hour=10, worker="cloud"):
    """A synthetic full-fleet execution with an original worker report."""
    sources = sources or {"sample": ("ok", {})}
    start = f"2026-10-{day:02}T{hour:02}:00:00Z"
    report_sources, counts = {}, {"ok": 0, "warn": 0, "error": 0}
    for sid, (status, extra) in sources.items():
        counts[status] += 1
        report_sources[sid] = {"status": status,
                               "checked_at": f"2026-10-{day:02}T{hour:02}:00:01Z", **extra}
    overall = "error" if counts["error"] else "warn" if counts["warn"] else "ok"
    return {"execution_id": f"synthetic-{worker}-{day}-{hour}", "worker": worker,
            "started_at": start, "completed_at": f"2026-10-{day:02}T{hour:02}:05:00Z",
            "exit_code": {"ok": 0, "warn": 1, "error": 2}[overall],
            "report": {"generated_at": start, "scope": {"type": "fleet"}, "overall": overall,
                       "counts": counts, "sources": report_sources}}


def err(day, **extra):
    return run(day, {"sample": ("error", extra)})


def expected(*sources, worker="cloud"):
    return [{"worker": worker, "source_id": sid} for sid in (sources or ("sample",))]


class FakeTransport:
    """Injected transport: never touches a network or mailbox."""

    def __init__(self, *outcomes, name="fake", replay_safe=False):
        self.name = name
        self.replay_safe = replay_safe
        self.outcomes = list(outcomes)
        self.digests = []

    def send(self, digest):
        self.digests.append(digest)
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, BaseException):
            raise outcome
        return {"provider_ref": f"fake-{len(self.digests)}"}

    def sent_keys(self):
        return [event["event_key"] for digest in self.digests for event in digest["events"]]


class AlertDeliveryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ledger = AlertLedger(LocalStorage(self.root))

    def tearDown(self):
        self._tmp.cleanup()

    def deliver(self, rows, *, transport=None, config=ENABLED, as_of="2026-10-20T12:00:00Z",
                now=None, sources=None, routing=ROUTE, ledger="default"):
        return deliver_alerts(rows, expected_sources=sources or expected(), routing=routing,
                              as_of=as_of, now=now, config=config, transport=transport,
                              ledger=self.ledger if ledger == "default" else ledger)

    def states(self):
        data, _ = self.ledger.read()
        return {record["type"]: record["state"] for record in data["events"].values()}

    def ledger_path(self):
        return self.root / "alerts" / "delivery-ledger.json"

    # -- activation boundary -------------------------------------------------

    def test_disabled_by_default_is_a_read_only_dry_run(self):
        transport = FakeTransport()
        receipt = self.deliver([err(20)], transport=transport, config=None)
        self.assertEqual(receipt["mode"], "disabled_dry_run")
        self.assertEqual(receipt["notification_delivery"], "not_attempted")
        self.assertEqual(len(receipt["new_event_keys"]), 1)
        self.assertEqual(transport.digests, [])
        self.assertFalse(self.ledger_path().exists())
        self.assertFalse(receipt["activation_authorized"])
        self.assertFalse(receipt["delivery_acceptance_complete"])
        no_ledger = self.deliver([err(20)], config={"enabled": False}, ledger=None)
        self.assertEqual(no_ledger["mode"], "disabled_dry_run")

    def test_configuration_fails_closed(self):
        for bad in ({"enabled": "yes"}, {"enabled": True}, {"surprise": 1},
                    {"max_attempts": 0}, {"retry_base_minutes": float("nan")},
                    {"retry_base_minutes": 30, "retry_cap_minutes": 10},
                    {"retry_base_minutes": 1e12, "retry_cap_minutes": 1e12},
                    {"max_queue_age_hours": 721}, []):
            with self.subTest(config=bad), self.assertRaises(ValueError):
                normalize_config(bad)
        with self.assertRaises(ValueError):
            self.deliver([err(20)], transport=FakeTransport(name="other"))
        with self.assertRaises(ValueError):
            self.deliver([err(20)], transport=None)
        self.assertFalse(self.ledger_path().exists())

    def test_rollback_disable_then_reenable_expires_stale_queue(self):
        always = [DeliveryRejected("provider unavailable", retryable=True)] * 2
        first = FakeTransport(*always)
        self.deliver([err(20)], transport=first, now="2026-10-20T12:00:00Z")
        self.assertEqual(self.states(), {"source_error": "retry_wait"})
        before = self.ledger_path().read_bytes()
        # Rollback: the disabled configuration never writes or sends.
        dry = self.deliver([err(20), err(21)], config={"enabled": False},
                           transport=first, as_of="2026-10-21T12:00:00Z")
        self.assertEqual(dry["mode"], "disabled_dry_run")
        self.assertEqual(self.ledger_path().read_bytes(), before)
        self.assertEqual(len(first.digests), 1)
        # Re-enabled days later while the source still fails: the continuing
        # incident is re-dated and delivered rather than silently expired.
        later = FakeTransport()
        receipt = self.deliver([err(20), err(21), err(23)], transport=later,
                               as_of="2026-10-23T12:00:00Z")
        self.assertEqual(receipt["notification_delivery"], "handed_off")
        self.assertEqual(self.states(), {"source_error": "sent"})
        self.assertEqual(len(later.digests), 1)

    def test_stale_condition_no_longer_current_expires_for_operator_attention(self):
        gap = run(20)
        gap.pop("report")
        transport = FakeTransport(DeliveryRejected("unavailable", retryable=True))
        self.deliver([run(19), gap], transport=transport)
        self.assertEqual(self.states(), {"evidence_gap": "retry_wait"})
        receipt = self.deliver([run(19), gap, run(23)], transport=transport,
                               as_of="2026-10-23T12:00:00Z")
        self.assertEqual(receipt["notification_delivery"], "nothing_to_send")
        self.assertEqual(self.states(), {"evidence_gap": "expired"})
        key = next(iter(self.ledger.read()[0]["events"]))
        self.assertEqual(receipt["ledger"]["needs_operator_attention"], [key])
        self.assertEqual(acknowledge(self.ledger, [key], by="operator",
                                     at="2026-10-23T13:00:00Z")["acknowledged"], [key])
        self.assertEqual(ledger_status(self.ledger)["needs_operator_attention"], [])

    # -- classifications ------------------------------------------------------

    def test_failure_is_sent_once_and_repeated_incident_is_not_resent(self):
        transport = FakeTransport()
        first = self.deliver([err(19)], transport=transport, as_of="2026-10-19T12:00:00Z")
        self.assertEqual(first["notification_delivery"], "handed_off")
        repeat = self.deliver([err(19), err(20)], transport=transport)
        self.assertEqual(repeat["notification_delivery"], "nothing_to_send")
        self.assertEqual(repeat["known_event_keys"], first["new_event_keys"])
        replay = self.deliver([err(19), err(20)], transport=transport)
        self.assertEqual(replay["notification_delivery"], "nothing_to_send")
        self.assertEqual(len(transport.digests), 1)
        self.assertEqual(self.states(), {"source_error": "sent"})

    def test_recovery_resolves_incident_and_new_failure_reopens(self):
        transport = FakeTransport()
        self.deliver([err(18)], transport=transport, as_of="2026-10-18T12:00:00Z")
        self.deliver([err(18), run(19)], transport=transport, as_of="2026-10-19T12:00:00Z")
        reopened = self.deliver([err(18), run(19), err(20)], transport=transport)
        kinds = [d["events"][0]["type"] for d in transport.digests]
        self.assertEqual(kinds, ["source_error", "recovered", "source_error"])
        data, _ = self.ledger.read()
        errors = sorted((r for r in data["events"].values() if r["type"] == "source_error"),
                        key=lambda r: r["accepted_at"])
        recovered = next(r for r in data["events"].values() if r["type"] == "recovered")
        self.assertEqual(errors[0]["resolved_by"], recovered["event_key"])
        self.assertNotIn("resolved_by", errors[1])
        self.assertNotEqual(errors[0]["event_key"], errors[1]["event_key"])
        self.assertEqual(reopened["new_event_keys"], [errors[1]["event_key"]])

    def test_late_failure_after_its_recovery_is_superseded_not_sent(self):
        transport = FakeTransport()
        self.deliver([err(19), run(20)], transport=transport, now="2026-10-20T12:00:00Z")
        # A delayed caller (its own ledger handle on the same store) offers the
        # older failure after the recovery was accepted and sent.
        late = AlertLedger(LocalStorage(self.root))
        receipt = self.deliver([err(19)], transport=transport, now="2026-10-20T12:01:00Z",
                               ledger=late)
        self.assertEqual(receipt["notification_delivery"], "nothing_to_send")
        self.assertEqual([[e["type"] for e in d["events"]] for d in transport.digests],
                         [["recovered"]])
        data, _ = self.ledger.read()
        failure = next(r for r in data["events"].values() if r["type"] == "source_error")
        recovered = next(r for r in data["events"].values() if r["type"] == "recovered")
        self.assertEqual(failure["state"], "superseded")
        self.assertEqual(failure["resolved_by"], recovered["event_key"])
        self.assertEqual([h["state"] for h in failure["history"]], ["queued", "superseded"])
        self.assertEqual(ledger_status(self.ledger)["needs_operator_attention"], [])

    def test_delayed_older_recovery_does_not_close_a_newer_failure(self):
        transport = FakeTransport()
        self.deliver([run(18), err(19)], transport=transport,
                     as_of="2026-10-19T12:00:00Z")
        # A recovery checked before that failure arrives late from another caller.
        self.deliver([err(17), run(18)], transport=transport, as_of="2026-10-19T12:01:00Z",
                     now="2026-10-19T12:01:00Z")
        data, _ = self.ledger.read()
        failure = next(r for r in data["events"].values() if r["type"] == "source_error")
        recovered = next(r for r in data["events"].values() if r["type"] == "recovered")
        self.assertNotIn("resolved_by", failure)
        self.assertEqual(failure["state"], "sent")
        # The stale recovery is kept for audit but never sent after that failure.
        self.assertEqual(recovered["state"], "superseded")
        self.assertEqual(recovered["resolved_by"], failure["event_key"])
        self.assertEqual([[e["type"] for e in d["events"]] for d in transport.digests],
                         [["source_error"]])

    def test_failure_checked_after_recovery_opens_a_new_incident(self):
        transport = FakeTransport()
        self.deliver([err(19), run(20)], transport=transport, now="2026-10-20T12:00:00Z")
        receipt = self.deliver([err(19), run(20), run(20, {"sample": ("error", {})}, hour=11)], transport=transport,
                               now="2026-10-20T12:01:00Z")
        self.assertEqual(receipt["notification_delivery"], "handed_off")
        self.assertEqual([[e["type"] for e in d["events"]] for d in transport.digests],
                         [["recovered"], ["source_error"]])

    def test_warning_rate_limit_backoff_and_overdue_share_one_digest(self):
        rows = [run(18, {"limited": ("error", {"rate_limited": True})}),
                run(20, {"warned": ("warn", {}),
                         "limited": ("error", {"deferred": {"reason": "provider-rate-limit"},
                                               "checked_at": "2026-10-18T10:00:01Z"})})]
        transport = FakeTransport()
        receipt = self.deliver(rows, transport=transport, sources=expected("warned", "limited"))
        self.assertEqual(len(transport.digests), 1)
        kinds = sorted(e["type"] for e in transport.digests[0]["events"])
        self.assertEqual(kinds, ["check_overdue", "provider_backoff", "source_warning"])
        self.assertEqual(receipt["digest"]["pending_after"], 0)
        body = transport.digests[0]["body"]
        self.assertIn("Preserve the existing stop/backoff controls", body)
        limited = FakeTransport()
        self.deliver([run(20, {"limited": ("error", {"rate_limited": True})})],
                     transport=limited, sources=expected("limited"),
                     ledger=AlertLedger(LocalStorage(self.root / "limited")))
        self.assertEqual([e["type"] for e in limited.digests[0]["events"]],
                         ["provider_rate_limit"])
        self.assertIn("do not trigger an extra check", limited.digests[0]["body"])
        self.assertNotIn("operator@example.invalid", body)
        self.assertNotIn("operator@example.invalid", self.ledger_path().read_text())

    def test_overdue_alone_is_delivered_and_bound_to_check_time(self):
        transport = FakeTransport()
        self.deliver([run(17)], transport=transport, as_of="2026-10-19T12:00:00Z")
        self.deliver([run(17)], transport=transport)  # still overdue, same check
        self.assertEqual([d["events"][0]["type"] for d in transport.digests], ["check_overdue"])

    def test_missing_partial_or_malformed_reports_alert_as_evidence_gaps(self):
        for mutation in ("missing_report", "partial", "malformed_counts", "no_execution"):
            latest = run(20)
            if mutation == "missing_report":
                latest.pop("report")
            elif mutation == "partial":
                latest["report"]["scope"]["type"] = "source"
            elif mutation == "malformed_counts":
                latest["report"]["counts"]["ok"] = 99
            rows = [] if mutation == "no_execution" else [run(19), latest]
            with self.subTest(mutation=mutation):
                ledger = AlertLedger(LocalStorage(self.root / mutation))
                transport = FakeTransport()
                receipt = self.deliver(rows, transport=transport, ledger=ledger)
                self.assertEqual([e["type"] for e in transport.digests[0]["events"]],
                                 ["evidence_gap"])
                self.assertTrue(receipt["source_evidence_gaps"])

    def test_stale_recovery_is_not_sent_but_fresh_recovery_is(self):
        transport = FakeTransport()
        self.deliver([err(16), run(17)], transport=transport, as_of="2026-10-19T12:00:00Z")
        self.assertEqual([e["type"] for e in transport.digests[0]["events"]], ["check_overdue"])
        fresh_ledger = AlertLedger(LocalStorage(self.root / "fresh"))
        fresh = FakeTransport()
        self.deliver([err(19), run(20)], transport=fresh, ledger=fresh_ledger)
        self.assertEqual([e["type"] for e in fresh.digests[0]["events"]], ["recovered"])

    def test_missing_route_blocks_delivery_until_route_is_supplied(self):
        transport = FakeTransport()
        blocked = self.deliver([err(20)], transport=transport, routing={"channel": "email"})
        self.assertEqual(blocked["notification_delivery"], "blocked_routing_incomplete")
        self.assertEqual(transport.digests, [])
        self.assertEqual(self.states(), {"source_error": "queued"})
        later = self.deliver([err(20)], transport=transport, now="2026-10-20T13:00:00Z")
        self.assertEqual(later["notification_delivery"], "handed_off")

    # -- retries, ambiguity and interruption ---------------------------------

    def test_transport_429_honors_retry_after_and_attempts_are_bounded(self):
        limited = DeliveryRejected("transport 429", retryable=True, retry_after_seconds=7200)
        transport = FakeTransport(limited, limited, limited)
        first = self.deliver([err(20)], transport=transport, now="2026-10-20T12:00:00Z")
        self.assertEqual(first["notification_delivery"], "rejected")
        data, _ = self.ledger.read()
        record = next(iter(data["events"].values()))
        self.assertEqual(record["next_attempt_at"], "2026-10-20T14:00:00Z")
        early = self.deliver([err(20)], transport=transport, now="2026-10-20T13:59:00Z")
        self.assertEqual(early["notification_delivery"], "blocked_transport_backoff")
        self.deliver([err(20)], transport=transport, now="2026-10-20T14:00:00Z")
        self.deliver([err(20)], transport=transport, now="2026-10-20T22:00:00Z")
        self.assertEqual(len(transport.digests), 3)
        self.assertEqual(self.states(), {"source_error": "exhausted"})
        status = ledger_status(self.ledger)
        self.assertEqual(len(status["needs_operator_attention"]), 1)
        final = self.deliver([err(20)], transport=transport, now="2026-10-21T10:00:00Z")
        self.assertEqual(final["notification_delivery"], "nothing_to_send")
        self.assertEqual(len(transport.digests), 3)

    def test_backoff_without_retry_after_is_exponential_and_capped(self):
        rejected = DeliveryRejected("unavailable", retryable=True)
        transport = FakeTransport(rejected, rejected)
        config = {**ENABLED, "max_attempts": 5, "retry_base_minutes": 60, "retry_cap_minutes": 90}
        self.deliver([err(20)], transport=transport, config=config, now="2026-10-20T12:00:00Z")
        self.assertEqual(next(iter(self.ledger.read()[0]["events"].values()))["next_attempt_at"],
                         "2026-10-20T13:00:00Z")
        self.deliver([err(20)], transport=transport, config=config, now="2026-10-20T13:00:00Z")
        self.assertEqual(next(iter(self.ledger.read()[0]["events"].values()))["next_attempt_at"],
                         "2026-10-20T14:30:00Z")

    def test_retry_after_longer_than_cap_is_still_honored(self):
        transport = FakeTransport(DeliveryRejected("busy", retryable=True,
                                                   retry_after_seconds=10 * 3600))
        self.deliver([err(20)], transport=transport, now="2026-10-20T12:00:00Z")
        self.assertEqual(next(iter(self.ledger.read()[0]["events"].values()))["next_attempt_at"],
                         "2026-10-20T22:00:00Z")

    def test_definitive_rejection_is_terminal(self):
        transport = FakeTransport(DeliveryRejected("bad destination", retryable=False))
        receipt = self.deliver([err(20)], transport=transport)
        self.assertEqual(receipt["digest"]["outcome"], "rejected")
        self.assertEqual(self.states(), {"source_error": "exhausted"})

    def test_ambiguous_outcome_is_held_then_reconciled(self):
        for failure in (DeliveryAmbiguous("timeout"), TimeoutError("socket timeout")):
            with self.subTest(failure=type(failure).__name__):
                ledger = AlertLedger(LocalStorage(self.root / type(failure).__name__))
                transport = FakeTransport(failure)
                receipt = self.deliver([err(20)], transport=transport, ledger=ledger)
                self.assertEqual(receipt["notification_delivery"], "ambiguous")
                again = self.deliver([err(20)], transport=transport, ledger=ledger,
                                     now="2026-10-20T18:00:00Z")
                self.assertEqual(again["notification_delivery"], "nothing_to_send")
                self.assertEqual(len(transport.digests), 1)
                key = receipt["digest"]["event_keys"][0]
                self.assertEqual(ledger_status(ledger)["needs_operator_attention"], [key])
                result = reconcile(ledger, key, resolution="sent", by="operator",
                                   at="2026-10-20T19:00:00Z")
                self.assertEqual(result, {"reconciled": True, "state": "sent"})
                self.assertEqual(ledger_status(ledger)["sent_unacknowledged"], [key])

    def test_requeue_after_ambiguity_sends_once_more_with_recorded_risk(self):
        transport = FakeTransport(DeliveryAmbiguous("timeout"))
        receipt = self.deliver([err(20)], transport=transport)
        key = receipt["digest"]["event_keys"][0]
        reconcile(self.ledger, key, resolution="requeue", by="operator", at="2026-10-20T13:00:00Z")
        self.deliver([err(20)], transport=transport, now="2026-10-20T13:00:00Z")
        self.assertEqual(transport.sent_keys(), [key, key])
        record = self.ledger.read()[0]["events"][key]
        self.assertEqual(record["state"], "sent")
        self.assertTrue(any(h.get("duplicate_risk_accepted") for h in record["history"]))
        self.assertEqual(reconcile(self.ledger, key, resolution="abandon", by="operator",
                                   at="2026-10-20T14:00:00Z"), {"reconciled": False})

    def test_replay_safe_transport_retries_ambiguous_with_same_key(self):
        transport = FakeTransport(DeliveryAmbiguous("timeout"), replay_safe=True)
        receipt = self.deliver([err(20)], transport=transport)
        key = receipt["digest"]["event_keys"][0]
        self.deliver([err(20)], transport=transport, now="2026-10-20T12:30:00Z")
        self.assertEqual(transport.sent_keys(), [key, key])
        self.assertEqual(self.states(), {"source_error": "sent"})

    def test_interrupted_delivery_becomes_ambiguous_after_lease(self):
        transport = FakeTransport(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.deliver([err(20)], transport=transport)
        self.assertEqual(self.states(), {"source_error": "sending"})
        inside = self.deliver([err(20)], transport=transport, now="2026-10-20T12:10:00Z")
        self.assertEqual(inside["notification_delivery"], "nothing_to_send")
        after = self.deliver([err(20)], transport=transport, now="2026-10-20T12:15:00Z")
        self.assertEqual(after["notification_delivery"], "nothing_to_send")
        self.assertEqual(self.states(), {"source_error": "ambiguous"})
        self.assertEqual(len(transport.digests), 1)

    def test_late_outcome_after_lease_sweep_does_not_overwrite_ambiguity(self):
        test = self

        class SlowTransport(FakeTransport):
            def send(self, digest):
                # Another invocation sweeps the abandoned-looking claim meanwhile.
                test.deliver([err(20)], transport=FakeTransport(), now="2026-10-20T13:00:00Z")
                return super().send(digest)

        self.deliver([err(20)], transport=SlowTransport())
        self.assertEqual(self.states(), {"source_error": "ambiguous"})

    # -- durability and concurrency ------------------------------------------

    def test_concurrent_invocations_send_each_event_once(self):
        barrier = threading.Barrier(4)
        transports = [FakeTransport() for _ in range(4)]
        errors = []

        def worker(transport):
            try:
                ledger = AlertLedger(LocalStorage(self.root))
                barrier.wait()
                self.deliver([err(19), run(20, {"sample": ("error", {}),
                                                 "other": ("warn", {})})],
                             transport=transport, ledger=ledger,
                             sources=expected("sample", "other"))
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in transports]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(errors, [])
        keys = [k for t in transports for k in t.sent_keys()]
        self.assertEqual(len(keys), 2)
        self.assertEqual(len(set(keys)), 2)
        self.assertEqual(sorted(self.states().values()), ["sent", "sent"])

    def test_conflicting_writer_between_read_and_claim_is_retried(self):
        storage = LocalStorage(self.root)
        injected = {"done": False}

        class RacingStorage(LocalStorage):
            def upload_if_version(self, name, source, version):
                if not injected["done"]:
                    injected["done"] = True
                    # A competing invocation claims and sends first.
                    deliver_alerts([err(20)], expected_sources=expected(), routing=ROUTE,
                                   as_of="2026-10-20T12:00:00Z", config=ENABLED,
                                   transport=winner, ledger=AlertLedger(storage))
                return super().upload_if_version(name, source, version)

        winner, loser = FakeTransport(), FakeTransport()
        receipt = self.deliver([err(20)], transport=loser,
                               ledger=AlertLedger(RacingStorage(self.root)))
        self.assertEqual(len(winner.digests), 1)
        self.assertEqual(loser.digests, [])
        self.assertEqual(receipt["notification_delivery"], "nothing_to_send")

    def test_persistent_conflict_raises_without_sending(self):
        class AlwaysConflicting(LocalStorage):
            def upload_if_version(self, name, source, version):
                raise StorageConflictError("synthetic conflict")

        transport = FakeTransport()
        with self.assertRaises(StorageConflictError):
            self.deliver([err(20)], transport=transport,
                         ledger=AlertLedger(AlwaysConflicting(self.root)))
        self.assertEqual(transport.digests, [])

    def test_malformed_ledger_fails_closed(self):
        for content in ("not json", json.dumps({"schema_version": 99, "events": {}}),
                        json.dumps({"schema_version": 1, "events": {"k": {"event_key": "x"}}}),
                        json.dumps({"schema_version": 1, "events": {"k": {
                            "event_key": "k", "state": "sending", "attempts": 1}}}),
                        json.dumps({"schema_version": 1, "events": {"k": {
                            "event_key": "k", "state": "retry_wait", "attempts": 1,
                            "type": "source_error", "worker": "w", "source_id": "s",
                            "subject": "x", "message": "x",
                            "accepted_at": "2026-10-20T12:00:00Z"}}}),
                        json.dumps({"schema_version": 1, "events": {"k": {
                            "event_key": "k", "state": "queued", "attempts": 0,
                            "accepted_at": "2026-10-20T12:00:00Z"}}})):
            with self.subTest(content=content[:30]):
                self.ledger_path().parent.mkdir(parents=True, exist_ok=True)
                self.ledger_path().write_text(content, encoding="utf-8")
                transport = FakeTransport()
                with self.assertRaises(LedgerError):
                    self.deliver([err(20)], transport=transport)
                self.assertEqual(transport.digests, [])

    def test_digest_size_is_bounded_and_remainder_follows(self):
        rows = [run(20, {f"s{i}": ("error", {}) for i in range(3)})]
        config = {**ENABLED, "max_messages_per_digest": 2}
        transport = FakeTransport()
        first = self.deliver(rows, transport=transport, config=config,
                             sources=expected("s0", "s1", "s2"))
        self.assertEqual(first["digest"]["pending_after"], 1)
        self.assertIn("1 further alert", transport.digests[0]["body"])
        self.deliver(rows, transport=transport, config=config, now="2026-10-20T12:05:00Z",
                     sources=expected("s0", "s1", "s2"))
        self.assertEqual([len(d["events"]) for d in transport.digests], [2, 1])
        self.assertEqual(len(set(transport.sent_keys())), 3)

    def test_acknowledgement_requires_a_sent_or_ambiguous_record(self):
        transport = FakeTransport()
        receipt = self.deliver([err(20)], transport=transport)
        key = receipt["digest"]["event_keys"][0]
        result = acknowledge(self.ledger, [key, "unknown"], by="operator",
                             at="2026-10-20T13:00:00Z")
        self.assertEqual(result, {"acknowledged": [key], "refused": ["unknown"]})
        self.assertEqual(self.states(), {"source_error": "acknowledged"})
        again = acknowledge(self.ledger, [key], by="operator", at="2026-10-20T14:00:00Z")
        self.assertEqual(again["refused"], [key])
        with self.assertRaises(ValueError):
            acknowledge(self.ledger, [], by="operator", at="2026-10-20T14:00:00Z")
        # An acknowledged incident that is still failing is not repeated.
        self.deliver([err(20), err(21)], transport=transport, as_of="2026-10-21T12:00:00Z")
        self.assertEqual(len(transport.digests), 1)

    def test_transport_retry_after_blocks_new_events_too(self):
        transport = FakeTransport(DeliveryRejected("transport 429", retryable=True,
                                                   retry_after_seconds=7200))
        self.deliver([err(20)], transport=transport, now="2026-10-20T12:00:00Z")
        both = [run(20, {"sample": ("error", {}), "other": ("warn", {})})]
        sources = expected("sample", "other")
        blocked = self.deliver(both, transport=transport, sources=sources,
                               now="2026-10-20T12:30:00Z")
        self.assertEqual(blocked["notification_delivery"], "blocked_transport_backoff")
        self.assertEqual(blocked["ledger"]["transport_backoff_until"], "2026-10-20T14:00:00Z")
        self.assertEqual(len(transport.digests), 1)
        self.deliver(both, transport=transport, sources=sources, now="2026-10-20T14:00:00Z")
        self.assertEqual(len(transport.digests), 2)
        self.assertEqual(sorted(e["type"] for e in transport.digests[1]["events"]),
                         ["source_error", "source_warning"])

    def test_failure_waiting_to_retry_is_superseded_by_its_recovery(self):
        transport = FakeTransport(DeliveryRejected("transport 429", retryable=True,
                                                   retry_after_seconds=6 * 3600))
        self.deliver([err(20)], transport=transport, now="2026-10-20T12:00:00Z")
        rows = [err(20), run(20, hour=13)]
        held = self.deliver(rows, transport=transport, as_of="2026-10-20T14:00:00Z")
        self.assertEqual(held["notification_delivery"], "blocked_transport_backoff")
        self.assertEqual(self.states(), {"source_error": "superseded", "recovered": "queued"})
        self.deliver(rows, transport=transport, as_of="2026-10-20T18:00:00Z")
        self.assertEqual([e["type"] for d in transport.digests for e in d["events"]],
                         ["source_error", "recovered"])
        self.assertEqual(self.states(), {"source_error": "superseded", "recovered": "sent"})
        self.assertEqual(ledger_status(self.ledger)["needs_operator_attention"], [])

    def test_enabled_delivery_refuses_replayed_or_future_evidence(self):
        transport = FakeTransport()
        for as_of, now in (("2026-10-11T12:00:00Z", "2026-10-20T12:00:00Z"),
                           ("2026-10-20T12:00:00Z", "2026-10-20T11:55:00Z")):
            with self.subTest(as_of=as_of, now=now), self.assertRaises(ValueError):
                self.deliver([err(10), run(11)], transport=transport, as_of=as_of, now=now)
        self.assertEqual(transport.digests, [])
        self.assertFalse(self.ledger_path().exists())

    def test_small_clock_skew_is_tolerated(self):
        transport = FakeTransport()
        receipt = self.deliver([err(20)], transport=transport, as_of="2026-10-20T12:00:00Z",
                               now="2026-10-20T11:59:00Z")
        self.assertEqual(receipt["notification_delivery"], "handed_off")
        self.assertEqual(receipt["evaluated_at"], "2026-10-20T12:00:00Z")

    def test_lagging_as_of_is_judged_at_the_delivery_clock(self):
        transport = FakeTransport()
        receipt = self.deliver([err(18), run(19)], transport=transport,
                               as_of="2026-10-19T12:00:00Z", now="2026-10-20T23:00:00Z")
        self.assertEqual(receipt["evaluated_at"], "2026-10-20T23:00:00Z")
        self.assertEqual([e["type"] for e in transport.digests[0]["events"]], ["check_overdue"])

    def test_oversized_retry_after_is_terminal_without_overflow(self):
        for seconds in (1e13, 30 * 86400):
            with self.subTest(seconds=seconds):
                ledger = AlertLedger(LocalStorage(self.root / str(int(seconds))))
                transport = FakeTransport(DeliveryRejected("transport 429", retryable=True,
                                                           retry_after_seconds=seconds))
                receipt = self.deliver([err(20)], transport=transport, ledger=ledger)
                self.assertEqual(receipt["digest"]["retryable"], False)
                self.assertIsNone(receipt["ledger"]["transport_backoff_until"])
                self.assertEqual(len(receipt["ledger"]["needs_operator_attention"]), 1)
                later = self.deliver([err(20), run(20, {"other": ("warn", {}),
                                                        "sample": ("error", {})}, hour=11)],
                                     transport=transport, ledger=ledger,
                                     sources=expected("sample", "other"),
                                     now="2026-10-20T12:05:00Z")
                self.assertEqual(later["notification_delivery"], "handed_off")

    def test_recovery_closed_record_cannot_be_requeued_and_ambiguity_stays(self):
        transport = FakeTransport(DeliveryRejected("bad destination", retryable=False))
        failed = self.deliver([err(19)], transport=transport, as_of="2026-10-19T12:00:00Z")
        key = failed["digest"]["event_keys"][0]
        self.deliver([err(19), run(20)], transport=transport)
        self.assertEqual(self.states(), {"source_error": "exhausted", "recovered": "sent"})
        refused = reconcile(self.ledger, key, resolution="requeue", by="operator",
                            at="2026-10-20T13:00:00Z")
        self.assertEqual(refused, {"reconciled": False, "reason": "resolved_by_recovery"})
        ambiguous_ledger = AlertLedger(LocalStorage(self.root / "ambiguous"))
        unsure = FakeTransport(DeliveryAmbiguous("timeout"))
        self.deliver([err(19)], transport=unsure, ledger=ambiguous_ledger,
                     as_of="2026-10-19T12:00:00Z")
        self.deliver([err(19), run(20)], transport=unsure, ledger=ambiguous_ledger)
        states = {r["type"]: r["state"] for r in ambiguous_ledger.read()[0]["events"].values()}
        self.assertEqual(states, {"source_error": "ambiguous", "recovered": "sent"})

    def test_replay_safe_transport_does_not_replay_a_recovered_failure(self):
        transport = FakeTransport(DeliveryAmbiguous("timeout"), replay_safe=True)
        self.deliver([err(19)], transport=transport, as_of="2026-10-19T12:00:00Z")
        self.deliver([err(19), run(20)], transport=transport)
        self.assertEqual([[e["type"] for e in d["events"]] for d in transport.digests],
                         [["source_error"], ["recovered"]])
        self.assertEqual(self.states(), {"source_error": "ambiguous", "recovered": "sent"})

    def test_claim_write_that_landed_but_reported_conflict_is_recognized(self):
        state = {"calls": 0}

        class LostAck(LocalStorage):
            def upload_if_version(self, name, source, version):
                super().upload_if_version(name, source, version)
                state["calls"] += 1
                if state["calls"] == 1:
                    raise StorageConflictError("acknowledgement lost after write")

        transport = FakeTransport()
        receipt = self.deliver([err(20)], transport=transport,
                               ledger=AlertLedger(LostAck(self.root)))
        self.assertEqual(receipt["notification_delivery"], "handed_off")
        self.assertEqual(len(transport.digests), 1)
        self.assertEqual(self.states(), {"source_error": "sent"})

    def test_outcome_write_failure_after_send_is_held_not_resent(self):
        state = {"calls": 0}

        class FailsSecondWrite(LocalStorage):
            def upload_if_version(self, name, source, version):
                state["calls"] += 1
                if state["calls"] == 2:
                    raise OSError("synthetic storage outage")
                return super().upload_if_version(name, source, version)

        transport = FakeTransport()
        with self.assertRaises(OSError):
            self.deliver([err(20)], transport=transport,
                         ledger=AlertLedger(FailsSecondWrite(self.root)))
        self.assertEqual(self.states(), {"source_error": "sending"})
        self.deliver([err(20)], transport=transport, now="2026-10-20T12:20:00Z")
        self.assertEqual(self.states(), {"source_error": "ambiguous"})
        self.assertEqual(len(transport.digests), 1)

    def test_replay_safe_ambiguity_stops_at_max_attempts(self):
        transport = FakeTransport(*[DeliveryAmbiguous("timeout")] * 3, replay_safe=True)
        config = {**ENABLED, "max_attempts": 2}
        self.deliver([err(20)], transport=transport, config=config)
        self.deliver([err(20)], transport=transport, config=config, now="2026-10-20T12:30:00Z")
        self.deliver([err(20)], transport=transport, config=config, now="2026-10-20T13:00:00Z")
        self.assertEqual(len(transport.digests), 2)
        self.assertEqual(self.states(), {"source_error": "ambiguous"})

    def test_generation_token_storage_behaves_like_gcs(self):
        class GenerationStorage:
            """In-memory stand-in for GCS generation preconditions."""
            def __init__(self):
                self.objects = {}

            def download_versioned(self, name, destination):
                if name not in self.objects:
                    return False, None
                raw, generation = self.objects[name]
                destination.write_bytes(raw)
                return True, generation

            def upload_if_version(self, name, source, version):
                current = self.objects.get(name, (None, 0))[1]
                if current != (0 if version is None else int(version)):
                    raise StorageConflictError("generation mismatch")
                self.objects[name] = (source.read_bytes(), current + 1)

        storage = GenerationStorage()
        ledger = AlertLedger(storage)
        transport = FakeTransport()
        self.deliver([err(20)], transport=transport, ledger=ledger)
        self.deliver([err(20)], transport=transport, ledger=ledger, now="2026-10-20T13:00:00Z")
        self.assertEqual(len(transport.digests), 1)
        self.assertEqual(storage.objects[ledger.name][1], 2)
        with self.assertRaises(StorageConflictError):
            storage.upload_if_version(ledger.name, self.root / "missing", None)

    def test_free_text_rejections_and_owner_labels_stay_out(self):
        transport = FakeTransport(DeliveryRejected("bounced for someone@example.invalid",
                                                   retryable=False))
        receipt = self.deliver([err(20)], transport=transport)
        self.assertEqual(receipt["digest"]["reason"], "transport_rejected")
        stored = self.ledger_path().read_text() + json.dumps(transport.digests)
        self.assertNotIn("someone@example.invalid", stored)
        self.assertNotIn("Synthetic operator", stored)

    def test_provider_diagnostics_never_reach_ledger_or_digest(self):
        transport = FakeTransport()
        self.deliver([err(20, error="private-token-secret",
                          url="https://private.example.invalid/?secret=secret",
                          feature_count=123456)], transport=transport)
        stored = self.ledger_path().read_text() + json.dumps(transport.digests)
        for forbidden in ("private-token-secret", "https://private", "feature_count", "123456"):
            self.assertNotIn(forbidden, stored)


class DeliveryCommandTests(unittest.TestCase):
    SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deliver_alerts.py"

    def command(self, root, *args):
        env = {k: v for k, v in os.environ.items()
               if k not in ("WATCHTOWER_STORAGE", "CLOUD_RUN_JOB")}
        env["WATCHTOWER_STORAGE_ROOT"] = str(Path(root) / "must-not-be-used")
        return subprocess.run([sys.executable, str(self.SCRIPT), "--ledger-root", str(root), *args],
                              capture_output=True, text=True, env=env)

    def test_cli_defaults_to_disabled_and_enabled_local_run_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = {"executions": [err(20)], "expected_sources": expected(), "routing": ROUTE}
            source = root / "input.json"
            source.write_text(json.dumps(data), encoding="utf-8")
            ledger_root = root / "ledger"
            first = self.command(ledger_root, "deliver", "--input", str(source),
                                 "--output", str(root / "dry.json"),
                                 "--as-of", "2026-10-20T12:00:00Z")
            self.assertEqual(first.returncode, 0, first.stderr)
            receipt = json.loads((root / "dry.json").read_text())
            self.assertEqual(receipt["mode"], "disabled_dry_run")
            self.assertFalse(ledger_root.exists())
            self.assertFalse((ledger_root / "must-not-be-used").exists())
            config = root / "config.json"
            config.write_text(json.dumps({"enabled": True, "transport": "structured_log"}),
                              encoding="utf-8")
            refused = self.command(ledger_root, "deliver", "--input", str(source),
                                   "--config", str(config), "--output", str(root / "on.json"),
                                   "--as-of", "2026-10-20T12:00:00Z")
            self.assertEqual(refused.returncode, 2)
            self.assertFalse((root / "on.json").exists())
            self.assertFalse(ledger_root.exists())
            again = self.command(ledger_root, "deliver", "--input", str(source),
                                 "--output", str(root / "dry.json"),
                                 "--as-of", "2026-10-20T12:00:00Z")
            self.assertEqual(again.returncode, 2)
            status = self.command(ledger_root, "status")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["sent_unacknowledged"], [])
            ack = self.command(ledger_root, "acknowledge", "--event-key", "missing", "--by", "op")
            self.assertEqual(json.loads(ack.stdout)["refused"], ["missing"])
            missing_root = subprocess.run([sys.executable, str(self.SCRIPT), "status"],
                                          capture_output=True, text=True,
                                          env={k: v for k, v in os.environ.items()
                                               if k != "WATCHTOWER_STORAGE"})
            self.assertEqual(missing_root.returncode, 2)


class StructuredLogTransportTests(unittest.TestCase):
    DIGEST = {"schema_version": 1, "digest_id": "abc123", "subject": "Watchtower alerts: 1",
              "body": "- source_error", "channel": "email",
              "events": [{"event_key": "k", "type": "source_error", "worker": "cloud",
                          "source_id": "sample", "execution_id": "x", "checked_at": None}]}

    def test_refuses_outside_cloud_run_job(self):
        with self.assertRaises(RuntimeError):
            StructuredLogTransport(io.StringIO(), environ={})

    def test_writes_one_structured_line_and_is_not_replay_safe(self):
        stream = io.StringIO()
        transport = StructuredLogTransport(stream, environ={"CLOUD_RUN_JOB": "synthetic-job"})
        self.assertFalse(transport.replay_safe)
        result = transport.send(self.DIGEST)
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["severity"], "ALERT")
        self.assertEqual(entry["logging.googleapis.com/insertId"], "abc123")
        self.assertEqual(entry["watchtower_alert_digest"]["event_count"], 1)
        self.assertEqual(result["provider_ref"], "synthetic-job:abc123")

    def test_interrupted_write_is_ambiguous(self):
        class Broken(io.StringIO):
            def flush(self):
                raise OSError("pipe closed")

        transport = StructuredLogTransport(Broken(), environ={"CLOUD_RUN_JOB": "synthetic-job"})
        with self.assertRaises(DeliveryAmbiguous):
            transport.send(self.DIGEST)


if __name__ == "__main__":
    unittest.main()
