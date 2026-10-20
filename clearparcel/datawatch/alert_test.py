"""Owner-approved synthetic delivery test. Never polls providers or touches real alerts.

``watchtower alert-test --kind failure|recovery --confirm-test-send`` runs the
normal delivery path (preview, ledger, digest, transport) over synthetic
executions for the reserved source ``alert-delivery-test``. It uses its own
ledger object, so the production ledger, receipts and incident keys are never
touched, and its digest subject is prefixed so the message is unmistakably a
test. Routing comes from ``WATCHTOWER_ALERT_DELIVERY_CONFIG``; the transport is
named explicitly because the production ``delivery.enabled`` flag may still be
false while delivery is being accepted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import uuid

from . import strict_json
from .alert_delivery import TRANSPORTS, AlertLedger, deliver_alerts

TEST_SOURCE = "alert-delivery-test"
TEST_WORKER = "test"
TEST_LEDGER = "alerts/test-delivery-ledger.json"
TEST_PREFIX = "TEST - "


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def synthetic_executions(kind: str, *, now: datetime, nonce: str) -> list:
    """A failing run, optionally followed by a recovering run, ending before ``now``."""
    if kind not in ("failure", "recovery"):
        raise ValueError("kind must be failure or recovery")

    def run(index: int, status: str, start: datetime) -> dict:
        end = start + timedelta(minutes=1)
        return {"execution_id": f"alert-test-{nonce}-{index}", "worker": TEST_WORKER,
                "started_at": _iso(start), "completed_at": _iso(end),
                "exit_code": 0 if status == "ok" else 2,
                "report": {"generated_at": _iso(start), "scope": {"type": "fleet"},
                           "overall": status,
                           "counts": {s: int(s == status) for s in ("ok", "warn", "error")},
                           "sources": {TEST_SOURCE: {"status": status,
                                                     "checked_at": _iso(start + timedelta(seconds=1))}}}}

    rows = [run(1, "error", now - timedelta(minutes=10))]
    if kind == "recovery":
        rows.append(run(2, "ok", now - timedelta(minutes=5)))
    return rows


class _Prefixed:
    """Wrap a transport so every test digest is labeled as a test."""

    def __init__(self, inner):
        self.inner, self.name, self.replay_safe = inner, inner.name, False

    def send(self, digest: dict) -> dict:
        labeled = dict(digest, subject=TEST_PREFIX + digest["subject"],
                       body="SYNTHETIC DELIVERY TEST - no real source is affected.\n" + digest["body"])
        return self.inner.send(labeled)


def run_alert_test(kind: str, *, storage, environ=None, transports=None, now=None) -> dict:
    env = os.environ if environ is None else environ
    raw = env.get("WATCHTOWER_ALERT_DELIVERY_CONFIG")
    if not raw:
        raise ValueError("WATCHTOWER_ALERT_DELIVERY_CONFIG is required for routing")
    private = strict_json.loads(raw)
    if not isinstance(private, dict):
        raise ValueError("delivery configuration must be an object")
    name = (private.get("delivery") or {}).get("transport") or "structured_log"
    factory = (transports or TRANSPORTS).get(name)
    if factory is None:
        raise ValueError("unsupported transport")
    clock = now or datetime.now(timezone.utc)
    nonce = env.get("CLOUD_RUN_EXECUTION") or uuid.uuid4().hex[:12]
    return deliver_alerts(synthetic_executions(kind, now=clock, nonce=nonce),
                          expected_sources=[{"worker": TEST_WORKER, "source_id": TEST_SOURCE}],
                          routing=private.get("routing"), as_of=_iso(clock), now=_iso(clock),
                          ledger=AlertLedger(storage, TEST_LEDGER),
                          config={"enabled": True, "transport": name},
                          transport=_Prefixed(factory()))
