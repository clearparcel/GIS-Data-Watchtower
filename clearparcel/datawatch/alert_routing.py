"""Private, offline alert previews. No transport, delivery, or scheduler integration."""
from __future__ import annotations

import hashlib
import json

from .operations_triage import triage_executions


_MESSAGES = {
    "source_error": "Source check failed. Inspect the correlated report and preserve provider backoff.",
    "source_warning": "Source check reported a warning. Inspect the correlated report before changing operations.",
    "provider_rate_limit": "Provider rate limit observed. Preserve Retry-After; do not trigger an extra check.",
    "provider_backoff": "Provider backoff remains active. Preserve the existing stop/backoff controls.",
    "recovered": "A later valid check recovered from the recorded issue for this worker and source.",
    "check_overdue": "Latest source check exceeds the configured age threshold. This alone does not prove an outage.",
    "evidence_gap": "Current source evidence is missing or inconsistent. Investigate before claiming health or recovery.",
}


def _label(value, field):
    if (not isinstance(value, str) or not value.strip() or len(value) > 320
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError(f"{field} must be a nonempty single-line label")
    return value


def prepare_alert_preview(executions, *, expected_sources, routing, as_of,
                          max_age_hours=36):
    """Build current message candidates from original, operator-correlated runs.

    expected_sources is an explicit private list of worker/source pairs. It is
    not an approval ledger. routing selects a draft recipient, not permission to
    send. Every invocation is stateless and requires the relevant issue history.
    """
    if not isinstance(expected_sources, list) or not expected_sources:
        raise ValueError("expected_sources must be a nonempty list")
    expected = set()
    for row in expected_sources:
        if not isinstance(row, dict):
            raise ValueError("expected source must be an object")
        pair = (_label(row.get("worker"), "worker"),
                _label(row.get("source_id"), "source_id"))
        if pair in expected:
            raise ValueError("duplicate expected worker/source")
        expected.add(pair)
    if not isinstance(routing, dict):
        raise ValueError("routing must be an object")
    route = {}
    gaps = []
    for key in ("channel", "recipient", "escalation_owner", "runbook_ref"):
        value = routing.get(key)
        if value is None or value == "":
            route[key] = None
            gaps.append(f"missing_{key}")
        else:
            route[key] = _label(value, key)
    if route["channel"] not in (None, "email"):
        raise ValueError("only draft email routing is supported")

    triage = triage_executions(executions, as_of=as_of,
                               max_age_hours=max_age_hours)
    latest = {row["worker"]: row for row in triage["executions"]}
    # Retain the start of an unresolved incident, not the latest failed run.
    incident, event_ids = {}, {}
    for event in triage["events"]:
        pair = (event["worker"], event["source_id"])
        initial = incident.setdefault(pair, event["execution_id"])
        event_ids[(pair, event["execution_id"], event["type"])] = initial
        if event["type"] == "recovered":
            incident.pop(pair)

    messages = []

    def add(kind, pair, row, source, identity):
        key = json.dumps([kind, *pair, identity], ensure_ascii=True,
                         separators=(",", ":"))
        messages.append({
            "event_key": hashlib.sha256(key.encode()).hexdigest(),
            "type": kind, "worker": pair[0], "source_id": pair[1],
            "execution_id": row["execution_id"] if row else None,
            "checked_at": source.get("checked_at") if source else None,
            "subject": f"Watchtower: {kind}",
            "message": _MESSAGES[kind],
        })

    source_gaps = []
    for pair in sorted(expected):
        row = latest.get(pair[0])
        source = next((s for s in row["sources"] if s["source_id"] == pair[1]), None) if row else None
        # A partial run cannot prove fleet coverage. Never fall back to an older
        # successful row when the latest worker run is missing or inconsistent.
        if (row is None or row["evidence_gaps"] or row.get("scope") != "fleet"
                or source is None or source["freshness"] == "unknown"):
            source_gaps.append({"worker": pair[0], "source_id": pair[1]})
            add("evidence_gap", pair, row, source,
                row["execution_id"] if row else "no_execution")
            continue
        for event in triage["events"]:
            if ((event["worker"], event["source_id"]) != pair
                    or event["execution_id"] != row["execution_id"]):
                continue
            # Historical recovery is not a fresh health notification.
            if event["type"] == "recovered" and source["freshness"] != "fresh":
                continue
            add(event["type"], pair, row, source,
                event_ids[(pair, event["execution_id"], event["type"])])
        if source["freshness"] == "overdue":
            add("check_overdue", pair, row, source, source["checked_at"])

    return {
        "schema_version": 1, "as_of": as_of, "private_evidence": True,
        "mode": "offline_preview", "routing": route, "routing_gaps": gaps,
        "source_evidence_gaps": source_gaps,
        "input_evidence_complete": triage["evidence_complete"],
        "max_age_hours": max_age_hours, "messages": messages,
        "notification_delivery": "not_attempted", "activation_authorized": False,
        "delivery_acceptance_complete": False,
        "deduplication": "candidate_keys_only_no_delivery_ledger",
    }
