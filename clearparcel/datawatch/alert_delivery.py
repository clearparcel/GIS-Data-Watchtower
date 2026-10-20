"""Disabled-by-default alert delivery with a durable compare-and-swap ledger.

Builds on :func:`alert_routing.prepare_alert_preview`; it never polls a GIS
provider, changes schedules, or chooses a recipient. A caller must pass an
explicit transport *and* an enabled configuration before anything is sent.

Ledger record states::

    queued -> sending -> sent -> acknowledged
                      -> retry_wait -> sending ...   (definitive non-delivery)
                      -> exhausted                   (attempts used up / rejected)
                      -> ambiguous                   (outcome unknown; held)
    queued/retry_wait -> expired                     (stale and no longer current)
    queued/retry_wait/ambiguous -> superseded         (a recovery was accepted first)

``accepted`` in the operations vocabulary is the durable ``queued`` record; a
record is ``sent`` only after the transport returned a definitive hand-off; it
is ``acknowledged`` only by an explicit operator action. An ambiguous outcome
(timeout, crash after claim, partial write) is never resent automatically
unless the transport declares provider-side replay safety.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import random
import re
from pathlib import Path
import tempfile
import time
import uuid

from . import strict_json
from .alert_routing import prepare_alert_preview
from .storage import StorageBackend, StorageConflictError

LEDGER_SCHEMA_VERSION = 1
DEFAULT_LEDGER_NAME = "alerts/delivery-ledger.json"
STATES = ("queued", "sending", "sent", "retry_wait", "exhausted", "ambiguous",
          "expired", "superseded", "acknowledged")
_REASON = re.compile(r"[A-Za-z0-9 _.:-]{1,60}")
DEFAULTS = {
    "enabled": False,
    "transport": None,
    "max_attempts": 3,
    "retry_base_minutes": 15,
    "retry_cap_minutes": 360,
    "claim_lease_minutes": 15,
    "max_queue_age_hours": 72,
    "max_messages_per_digest": 25,
    "max_age_hours": 36,
}
_INTEGER_SETTINGS = ("max_attempts", "max_messages_per_digest")
_DURATION_SETTINGS = ("retry_base_minutes", "retry_cap_minutes", "claim_lease_minutes",
                      "max_queue_age_hours", "max_age_hours")


class LedgerError(ValueError):
    """The stored ledger is malformed; fail closed rather than resend."""


class DeliveryRejected(Exception):
    """Definitive non-delivery: the transport guarantees nothing was handed off."""

    def __init__(self, reason: str, *, retryable: bool, retry_after_seconds: float | None = None):
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class DeliveryAmbiguous(Exception):
    """The hand-off may or may not have happened (timeout, partial write)."""


def _utc(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamps must be ISO 8601") from exc
    else:
        raise ValueError("timestamps must be ISO 8601")
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _reason(text) -> str:
    """Keep only short machine-style reasons; free text may quote an address."""
    return text if isinstance(text, str) and _REASON.fullmatch(text) else "transport_rejected"


def normalize_config(config: dict | None) -> dict:
    """Merge a private delivery configuration over safe defaults."""
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("delivery configuration must be an object")
    unknown = set(config) - set(DEFAULTS)
    if unknown:
        raise ValueError("unknown delivery settings: " + ", ".join(sorted(unknown)))
    merged = {**DEFAULTS, **config}
    if type(merged["enabled"]) is not bool:
        raise ValueError("enabled must be true or false")
    if merged["transport"] is not None and not isinstance(merged["transport"], str):
        raise ValueError("transport must be a name")
    if merged["enabled"] and not merged["transport"]:
        raise ValueError("an enabled configuration must name its transport")
    for key in _INTEGER_SETTINGS:
        if type(merged[key]) is not int or not 1 <= merged[key] <= 100:
            raise ValueError(f"{key} must be an integer from 1 to 100")
    for key in _DURATION_SETTINGS:
        value = merged[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be finite and positive")
    if merged["retry_cap_minutes"] < merged["retry_base_minutes"]:
        raise ValueError("retry_cap_minutes must not be below retry_base_minutes")
    return merged


def _empty_ledger() -> dict:
    return {"schema_version": LEDGER_SCHEMA_VERSION, "private_evidence": True, "events": {}}


def validate_ledger(data) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise LedgerError("unsupported or malformed alert ledger")
    events = data.get("events")
    if not isinstance(events, dict):
        raise LedgerError("alert ledger events must be an object")
    for key, record in events.items():
        if (not isinstance(record, dict) or record.get("event_key") != key
                or record.get("state") not in STATES
                or type(record.get("attempts")) is not int or record["attempts"] < 0):
            raise LedgerError("malformed alert ledger record")
        for field in ("type", "worker", "source_id", "subject", "message"):
            if not isinstance(record.get(field), str):
                raise LedgerError(f"alert ledger record lacks {field}")
        required = ["accepted_at"]
        if record["state"] == "sending":
            required.append("claimed_at")
            if not isinstance(record.get("claim_id"), str):
                raise LedgerError("sending record lacks a claim")
        if record["state"] == "retry_wait":
            required.append("next_attempt_at")
        for field in required:
            try:
                _utc(record.get(field))
            except ValueError as exc:
                raise LedgerError(f"alert ledger record lacks a valid {field}") from exc
    if "transport_backoff_until" in data:
        try:
            _utc(data["transport_backoff_until"])
        except ValueError as exc:
            raise LedgerError("alert ledger transport backoff is invalid") from exc
    return data


class AlertLedger:
    """Delivery state persisted through a version-conditional storage backend."""

    def __init__(self, storage: StorageBackend, name: str = DEFAULT_LEDGER_NAME):
        self.storage = storage
        self.name = name

    def read(self) -> tuple[dict, str | int | None]:
        with tempfile.TemporaryDirectory(prefix="watchtower-alert-ledger-") as scratch:
            path = Path(scratch) / "ledger.json"
            exists, token = self.storage.download_versioned(self.name, path)
            if not exists:
                return _empty_ledger(), None
            try:
                data = strict_json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise LedgerError("alert ledger is not valid JSON") from exc
        return validate_ledger(data), token

    def update(self, change, *, attempts: int = 8):
        """Apply ``change(data) -> result`` under compare-and-swap.

        ``change`` mutates the supplied document in place. It may run more than
        once when another writer wins; it must derive everything from ``data``.
        """
        for attempt in range(attempts):
            data, token = self.read()
            before = json.dumps(data, sort_keys=True)
            result = change(data)
            if json.dumps(data, sort_keys=True) == before:
                return result
            validate_ledger(data)
            with tempfile.TemporaryDirectory(prefix="watchtower-alert-ledger-") as scratch:
                path = Path(scratch) / "ledger.json"
                path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n",
                                encoding="utf-8")
                try:
                    self.storage.upload_if_version(self.name, path, token)
                    return result
                except StorageConflictError:
                    if attempt + 1 >= attempts:
                        raise
            time.sleep(random.uniform(0.005, 0.05) * (attempt + 1))
        raise StorageConflictError(f"alert ledger changed repeatedly: {self.name}")


def _note(record: dict, at: datetime, state: str, **detail) -> None:
    history = record.setdefault("history", [])
    history.append({"at": _iso(at), "state": state, **detail})
    # Keep the newest transitions bounded; the first entry records acceptance.
    if len(history) > 20:
        del history[1:len(history) - 19]
    record["state"] = state


def _backoff(attempts: int, settings: dict, retry_after: float | None) -> timedelta:
    minutes = min(settings["retry_base_minutes"] * (2 ** max(attempts - 1, 0)),
                  settings["retry_cap_minutes"])
    seconds = minutes * 60
    # Never retry before an explicit Retry-After; queue expiry bounds the wait.
    if (type(retry_after) in (int, float) and math.isfinite(retry_after)
            and retry_after > seconds):
        seconds = retry_after
    return timedelta(seconds=seconds)


def _enqueue(data: dict, messages: list, at: datetime) -> tuple[list, list]:
    """Record new candidates once. Returns (new_keys, known_keys)."""
    events = data["events"]
    new, known = [], []
    for message in messages:
        key = message["event_key"]
        if key in events:
            known.append(key)
            continue
        record = {
            "event_key": key, "type": message["type"], "worker": message["worker"],
            "source_id": message["source_id"], "execution_id": message.get("execution_id"),
            "checked_at": message.get("checked_at"), "subject": message["subject"],
            "message": message["message"], "attempts": 0, "accepted_at": _iso(at),
        }
        _note(record, at, "queued")
        events[key] = record
        new.append(key)
        if message["type"] == "recovered":
            # A recovery closes the earlier incident for this worker/source. A
            # later failure has a new preview key and therefore reopens it.
            for other in events.values():
                if (other is not record and other["type"] != "recovered"
                        and other.get("worker") == message["worker"]
                        and other.get("source_id") == message["source_id"]
                        and not other.get("resolved_by")):
                    other["resolved_by"] = key
    return new, known


def _sweep(data: dict, at: datetime, settings: dict, current: set) -> None:
    """Settle stale, superseded and abandoned records before claiming.

    A queued item whose condition is still in the current preview is re-dated
    rather than expired: its key cannot be queued again, so expiring it would
    silence a continuing incident. Only conditions no longer current expire.
    """
    lease = timedelta(minutes=settings["claim_lease_minutes"])
    max_queue = timedelta(hours=settings["max_queue_age_hours"])
    for record in data["events"].values():
        if record["state"] == "sending" and at - _utc(record["claimed_at"]) >= lease:
            # The claimant may have handed the digest off before stopping.
            _note(record, at, "ambiguous", reason="claim_lease_expired",
                  claim_id=record.get("claim_id"))
        elif (record["state"] in ("queued", "retry_wait", "ambiguous")
              and record.get("resolved_by")):
            # Never deliver a failure after the recovery that closed it.
            _note(record, at, "superseded", resolved_by=record["resolved_by"])
        elif (record["state"] in ("queued", "retry_wait")
              and at - _utc(record["accepted_at"]) >= max_queue):
            if record["event_key"] in current:
                record["accepted_at"] = _iso(at)
                _note(record, at, record["state"], reason="still_current_redated")
            else:
                _note(record, at, "expired", reason="older_than_max_queue_age")


def _eligible(data: dict, at: datetime, replay_safe: bool, max_attempts: int) -> list:
    rows = []
    for record in data["events"].values():
        if record["state"] == "queued":
            rows.append(record)
        elif record["state"] == "retry_wait" and _utc(record["next_attempt_at"]) <= at:
            rows.append(record)
        elif (record["state"] == "ambiguous" and replay_safe
              and record["attempts"] < max_attempts):
            # Only a transport with provider-side duplicate suppression may
            # replay an unknown outcome; others wait for operator reconciliation.
            rows.append(record)
    rows.sort(key=lambda r: (r["accepted_at"], r["event_key"]))
    return rows


def build_digest(records: list, *, routing: dict, digest_id: str, created_at: datetime,
                 pending_after: int) -> dict:
    kinds = sorted({r["type"] for r in records})
    subject = f"Watchtower alerts: {len(records)} ({', '.join(kinds)})"
    lines = []
    for r in records:
        lines.append(f"- {r['type']} | worker {r['worker']} | source {r['source_id']} | "
                     f"execution {r['execution_id'] or 'none'} | checked {r['checked_at'] or 'unknown'}")
        lines.append(f"  {r['message']}")
        lines.append(f"  event {r['event_key'][:16]}")
    if pending_after:
        lines.append(f"{pending_after} further alert(s) remain queued for the next digest.")
    lines.append(f"Runbook: {routing.get('runbook_ref') or 'not set'}.")
    lines.append("Acknowledge each event after review; acknowledgement is recorded separately.")
    return {
        "schema_version": 1, "digest_id": digest_id, "created_at": _iso(created_at),
        "subject": subject, "body": "\n".join(lines), "channel": routing.get("channel"),
        "events": [{key: r[key] for key in ("event_key", "type", "worker", "source_id",
                                            "execution_id", "checked_at")} for r in records],
    }


def _summary(data: dict) -> dict:
    counts = {state: 0 for state in STATES}
    for record in data["events"].values():
        counts[record["state"]] += 1
    attention = sorted(k for k, r in data["events"].items()
                       if r["state"] in ("ambiguous", "exhausted")
                       or (r["state"] == "expired" and not r.get("abandoned_by")))
    unacknowledged = sorted(k for k, r in data["events"].items() if r["state"] == "sent")
    return {"state_counts": counts, "needs_operator_attention": attention,
            "sent_unacknowledged": unacknowledged,
            "transport_backoff_until": data.get("transport_backoff_until")}


def deliver_alerts(executions, *, expected_sources, routing, as_of, ledger: AlertLedger | None,
                   config=None, transport=None, now=None) -> dict:
    """Prepare current alerts and, only when enabled, deliver one digest.

    ``as_of`` is the evidence cutoff passed to the preview. ``now`` is the
    delivery clock (defaults to ``as_of``) used for leases, retries and expiry.
    Disabled configurations perform a read-only dry run and write nothing.
    """
    settings = normalize_config(config)
    preview = prepare_alert_preview(executions, expected_sources=expected_sources,
                                    routing=routing, as_of=as_of,
                                    max_age_hours=settings["max_age_hours"])
    clock = _utc(now if now is not None else as_of)
    receipt = {
        "schema_version": 1, "as_of": as_of, "delivery_time": _iso(clock),
        "private_evidence": True, "enabled": settings["enabled"],
        "transport": settings["transport"],
        "preview_messages": len(preview["messages"]),
        "routing_gaps": preview["routing_gaps"],
        "source_evidence_gaps": preview["source_evidence_gaps"],
        "input_evidence_complete": preview["input_evidence_complete"],
        "new_event_keys": [], "known_event_keys": [], "digest": None,
        "notification_delivery": "not_attempted",
        "activation_authorized": False, "delivery_acceptance_complete": False,
    }
    if not settings["enabled"]:
        receipt["mode"] = "disabled_dry_run"
        if ledger is not None:
            data, _ = ledger.read()
            receipt["new_event_keys"] = [m["event_key"] for m in preview["messages"]
                                         if m["event_key"] not in data["events"]]
            receipt["known_event_keys"] = [m["event_key"] for m in preview["messages"]
                                           if m["event_key"] in data["events"]]
            receipt["ledger"] = _summary(data)
        else:
            receipt["new_event_keys"] = [m["event_key"] for m in preview["messages"]]
        return receipt

    receipt["mode"] = "delivery"
    if ledger is None or transport is None:
        raise ValueError("enabled delivery requires a ledger and an explicit transport")
    if getattr(transport, "name", None) != settings["transport"]:
        raise ValueError("transport does not match the enabled configuration")
    evidence_age = clock - _utc(as_of)
    if (evidence_age < timedelta(0)
            or evidence_age > timedelta(hours=settings["max_age_hours"])):
        # Replaying old evidence would present historical conditions as current.
        raise ValueError("delivery requires as_of within max_age_hours before now")
    replay_safe = bool(getattr(transport, "replay_safe", False))
    claim_id = uuid.uuid4().hex
    current = {m["event_key"] for m in preview["messages"]}
    blocked = {"transport": False}

    def accept_and_claim(data):
        mine = [dict(r) for r in data["events"].values()
                if r["state"] == "sending" and r.get("claim_id") == claim_id]
        if mine:
            # Our claim write landed although its acknowledgement was lost.
            known = [m["event_key"] for m in preview["messages"]]
            return [], known, mine, 0
        new, known = _enqueue(data, preview["messages"], clock)
        _sweep(data, clock, settings, current)
        claimed = []
        backoff = data.get("transport_backoff_until")
        blocked["transport"] = bool(backoff) and clock < _utc(backoff)
        if not preview["routing_gaps"] and not blocked["transport"]:
            eligible = _eligible(data, clock, replay_safe, settings["max_attempts"])
            for record in eligible[:settings["max_messages_per_digest"]]:
                record["attempts"] += 1
                record["claim_id"] = claim_id
                record["claimed_at"] = _iso(clock)
                record.pop("next_attempt_at", None)
                _note(record, clock, "sending", claim_id=claim_id, attempt=record["attempts"])
                claimed.append(dict(record))
            pending_after = max(len(eligible) - len(claimed), 0)
        else:
            pending_after = 0
        return new, known, claimed, pending_after

    new, known, claimed, pending_after = ledger.update(accept_and_claim)
    receipt["new_event_keys"], receipt["known_event_keys"] = new, known
    if preview["routing_gaps"]:
        receipt["notification_delivery"] = "blocked_routing_incomplete"
    elif blocked["transport"]:
        receipt["notification_delivery"] = "blocked_transport_backoff"
    if not claimed:
        if receipt["notification_delivery"] == "not_attempted":
            receipt["notification_delivery"] = "nothing_to_send"
        receipt["ledger"] = _summary(ledger.read()[0])
        return receipt

    digest_id = hashlib.sha256((claim_id + "|" + "|".join(r["event_key"] for r in claimed))
                               .encode()).hexdigest()[:32]
    digest = build_digest(claimed, routing=preview["routing"], digest_id=digest_id,
                          created_at=clock, pending_after=pending_after)
    outcome, detail = "sent", {}
    provider_ref = None
    try:
        result = transport.send(digest)
        provider_ref = result.get("provider_ref") if isinstance(result, dict) else None
    except DeliveryRejected as exc:
        outcome = "rejected"
        retry_after = exc.retry_after_seconds
        if type(retry_after) not in (int, float) or not math.isfinite(retry_after) or retry_after < 0:
            retry_after = None
        detail = {"reason": _reason(exc.reason), "retryable": exc.retryable,
                  "retry_after_seconds": retry_after}
    except Exception as exc:  # noqa: BLE001 - any unknown failure is an unknown outcome
        outcome = "ambiguous"
        detail = {"reason": type(exc).__name__}

    def record_outcome(data):
        if outcome == "rejected" and detail["retry_after_seconds"]:
            # Transport backoff applies to every later event, not only these.
            until = clock + timedelta(seconds=detail["retry_after_seconds"])
            previous = data.get("transport_backoff_until")
            if not previous or _utc(previous) < until:
                data["transport_backoff_until"] = _iso(until)
        for key in (r["event_key"] for r in claimed):
            record = data["events"].get(key)
            if record is None or record.get("state") != "sending" or record.get("claim_id") != claim_id:
                continue  # A lease sweep or operator already reconciled this claim.
            record["digest_id"] = digest_id
            if outcome == "sent":
                record["sent_at"] = _iso(clock)
                record["provider_ref"] = provider_ref
                _note(record, clock, "sent", digest_id=digest_id)
            elif outcome == "ambiguous":
                _note(record, clock, "ambiguous", digest_id=digest_id, reason=detail["reason"])
            elif detail["retryable"] and record["attempts"] < settings["max_attempts"]:
                record["next_attempt_at"] = _iso(clock + _backoff(
                    record["attempts"], settings, detail["retry_after_seconds"]))
                _note(record, clock, "retry_wait", digest_id=digest_id, reason=detail["reason"])
            else:
                _note(record, clock, "exhausted", digest_id=digest_id, reason=detail["reason"])
            record.pop("claim_id", None)

    ledger.update(record_outcome)
    receipt["digest"] = {"digest_id": digest_id, "event_keys": [r["event_key"] for r in claimed],
                         "subject": digest["subject"], "outcome": outcome,
                         "pending_after": pending_after, **detail}
    receipt["notification_delivery"] = {"sent": "handed_off", "ambiguous": "ambiguous",
                                        "rejected": "rejected"}[outcome]
    receipt["ledger"] = _summary(ledger.read()[0])
    return receipt


def acknowledge(ledger: AlertLedger, event_keys: list, *, by: str, at) -> dict:
    """Record an operator acknowledgement for sent, ambiguous or expired events."""
    if not event_keys or not isinstance(by, str) or not by.strip() or len(by) > 120:
        raise ValueError("acknowledgement requires event keys and an operator label")
    moment = _utc(at)

    def change(data):
        done, refused = [], []
        for key in event_keys:
            record = data["events"].get(key)
            if record is None or record["state"] not in ("sent", "ambiguous", "expired"):
                refused.append(key)
                continue
            record["acknowledged_at"] = _iso(moment)
            record["acknowledged_by"] = by
            _note(record, moment, "acknowledged", prior=record["state"])
            done.append(key)
        return {"acknowledged": done, "refused": refused}

    return ledger.update(change)


def reconcile(ledger: AlertLedger, event_key: str, *, resolution: str, by: str, at) -> dict:
    """Resolve an ambiguous or exhausted record after checking the destination.

    ``sent``: the operator found the message at the destination.
    ``requeue``: the operator accepts possible duplicate delivery and retries.
    ``abandon``: keep the record, stop delivery attempts (``expired``).
    """
    if resolution not in ("sent", "requeue", "abandon"):
        raise ValueError("resolution must be sent, requeue or abandon")
    if not isinstance(by, str) or not by.strip() or len(by) > 120:
        raise ValueError("reconciliation requires an operator label")
    moment = _utc(at)

    def change(data):
        record = data["events"].get(event_key)
        if record is None or record["state"] not in ("ambiguous", "exhausted"):
            return {"reconciled": False}
        if resolution == "sent":
            record["sent_at"] = _iso(moment)
            _note(record, moment, "sent", reconciled_by=by)
        elif resolution == "requeue":
            record["attempts"] = 0
            record["accepted_at"] = _iso(moment)
            _note(record, moment, "queued", reconciled_by=by, duplicate_risk_accepted=True)
        else:
            record["abandoned_by"] = by
            _note(record, moment, "expired", reconciled_by=by, reason="operator_abandoned")
        return {"reconciled": True, "state": record["state"]}

    return ledger.update(change)


def ledger_status(ledger: AlertLedger) -> dict:
    data, _ = ledger.read()
    return {"schema_version": 1, "private_evidence": True, **_summary(data)}


class StructuredLogTransport:
    """Write one structured JSON digest line for a platform log collector.

    Intended only for a Cloud Run job, where stdout JSON becomes a Cloud
    Logging entry that a separately approved log-based alerting policy can
    route to the existing email channel. ``sent`` means handed to the platform
    collector, not delivered to a mailbox. Cloud Logging removes duplicate
    insert IDs only at query time, so replays are not safe.
    """

    name = "structured_log"
    replay_safe = False

    def __init__(self, stream=None, *, environ=None):
        import os
        import sys
        env = os.environ if environ is None else environ
        if not env.get("CLOUD_RUN_JOB"):
            raise RuntimeError("structured_log transport runs only inside a Cloud Run job")
        self.stream = sys.stdout if stream is None else stream
        self.job = env["CLOUD_RUN_JOB"]

    def send(self, digest: dict) -> dict:
        entry = {
            "severity": "ALERT",
            "message": digest["subject"],
            "watchtower_alert_digest": {
                "schema_version": digest["schema_version"], "digest_id": digest["digest_id"],
                "event_count": len(digest["events"]), "events": digest["events"],
                "body": digest["body"],
            },
            "logging.googleapis.com/labels": {"watchtower_alert": "digest"},
            "logging.googleapis.com/insertId": digest["digest_id"],
        }
        line = json.dumps(entry, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        try:
            self.stream.write(line + "\n")
            self.stream.flush()
        except Exception as exc:
            raise DeliveryAmbiguous("structured log write interrupted") from exc
        return {"provider_ref": f"{self.job}:{digest['digest_id']}"}
