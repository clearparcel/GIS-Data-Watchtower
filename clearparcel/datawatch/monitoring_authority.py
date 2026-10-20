"""Offline matching of parcel-monitoring evidence; never grants runtime authority."""
from __future__ import annotations

from collections import Counter
from datetime import date
import hashlib
import json
import math
from urllib.parse import urlsplit


def evidence_hash(value) -> str:
    """Bind a receipt to exact JSON input, including endpoint and source options."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _date(value):
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _hours(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _profiles(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(p, str) and p in ("cloud", "local") for p in value)
            and len(value) == len(set(value)))


def _index(records):
    if not isinstance(records, list):
        raise ValueError("evidence records must be lists")
    index = {}
    for record in records:
        if not isinstance(record, dict) or not _text(record.get("source_id")):
            raise ValueError("evidence requires a source_id")
        index.setdefault(record["source_id"], []).append(record)
    return index


def _dated(record, today):
    reviewed, due = _date(record.get("reviewed_on")), _date(record.get("review_due"))
    return reviewed is not None and due is not None and reviewed <= today < due


def reconciliation_receipt(sources, research, approvals, cadences, *, as_of):
    """Check supplied private records, without authenticating their assertions.

    ``research`` maps canonical county slugs to current parcel-access records.
    Cadence records assert the minimum interval across ALL workers/manual checks,
    not merely an average frequency or the interval of one scheduler.
    """
    today = _date(as_of)
    if today is None or not isinstance(sources, list) or not isinstance(research, dict):
        raise ValueError("require sources list, research mapping and YYYY-MM-DD as_of")
    if not all(isinstance(s, dict) and _text(s.get("id")) for s in sources):
        raise ValueError("sources require unique nonempty IDs")
    ids = [s["id"] for s in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate registry source ID")
    approval_index, cadence_index = _index(approvals), _index(cadences)
    rows = []
    for source in sources:
        sid = source["id"]
        slug = str(source.get("county_slug") or "").strip().lower()
        category = str(source.get("category") or "").strip().lower()
        record = research.get(slug)
        monitoring = record.get("monitoring") if isinstance(record, dict) else None
        decision = monitoring.get("decision") if isinstance(monitoring, dict) else None
        row = {"source_id": sid, "county_slug": slug or None,
               "source_sha256": evidence_hash(source),
               "research_sha256": evidence_hash(record) if record is not None else None,
               "research_decision": decision, "status": "needs_review", "gaps": []}
        rows.append(row)
        gaps = row["gaps"]
        if source.get("enabled") is False:
            row["status"] = "disabled"
            continue
        if category and not category.startswith("parcel"):
            row["status"] = "outside_parcel_scope"
            continue
        if not slug or not category:
            gaps.append("county_direct_scope_unresolved")
            continue
        if decision == "hold-for-terms":
            row["status"] = "held_by_research"
            continue
        if decision not in ("candidate-low-frequency", "not-assessed", "not-appropriate"):
            gaps.append("missing_or_unknown_research_decision")
        if decision == "not-appropriate":
            gaps.append("research_requires_hold_review")
        endpoint = source.get("url")
        try:
            parsed = urlsplit(endpoint) if isinstance(endpoint, str) else None
            endpoint_valid = parsed is not None and parsed.scheme in ("http", "https") and bool(parsed.hostname)
        except ValueError:
            endpoint_valid = False
        if not endpoint_valid:
            gaps.append("source_endpoint_missing_or_invalid")
        profiles = source.get("execution_profiles")
        if not _profiles(profiles):
            gaps.append("explicit_cloud_local_profiles_required")
        candidates = approval_index.get(sid, [])
        if len(candidates) != 1:
            gaps.append("missing_approval" if not candidates else "ambiguous_approvals")
            continue
        approval = candidates[0]
        if approval.get("decision") != "approved":
            gaps.append("approval_not_granted")
        if not _dated(approval, today):
            gaps.append("approval_stale_or_invalid_dates")
        for field in ("reviewer_ref", "approval_ref", "terms_ref"):
            if not _text(approval.get(field)):
                gaps.append("missing_" + field)
        for field in ("source_sha256", "research_sha256"):
            if approval.get(field) != row[field] or not _text(row[field]):
                gaps.append(field + "_mismatch")
        if approval.get("county_slug") != slug:
            gaps.append("approval_county_mismatch")
        approved_profiles = approval.get("execution_profiles")
        if (not _profiles(approved_profiles) or not _profiles(profiles)
                or set(approved_profiles) != set(profiles)):
            gaps.append("approval_profile_mismatch")
        minimum = approval.get("minimum_interval_hours")
        if not _hours(minimum):
            gaps.append("invalid_approved_interval")
        elif minimum < 24 and not _text(approval.get("cadence_exception_ref")):
            gaps.append("subdaily_exception_evidence_required")
        observed = cadence_index.get(sid, [])
        if len(observed) != 1:
            gaps.append("missing_cadence_evidence" if not observed else "ambiguous_cadence_evidence")
            continue
        cadence = observed[0]
        if not _dated(cadence, today) or not _text(cadence.get("evidence_ref")):
            gaps.append("cadence_evidence_stale_or_incomplete")
        if cadence.get("source_sha256") != row["source_sha256"]:
            gaps.append("cadence_source_mismatch")
        if (not _profiles(cadence.get("execution_profiles")) or not _profiles(profiles)
                or set(cadence["execution_profiles"]) != set(profiles)):
            gaps.append("cadence_profile_mismatch")
        actual = cadence.get("minimum_interval_hours")
        if not _hours(actual):
            gaps.append("invalid_observed_interval")
        elif _hours(minimum) and actual < minimum:
            gaps.append("cadence_exceeds_approved_frequency")
        if cadence.get("covers_all_dispatch_paths") is not True:
            gaps.append("combined_dispatch_cadence_unverified")
        if not gaps:
            row["status"] = "documented"
    unused = sorted((set(approval_index) | set(cadence_index)) - set(ids))
    counts = dict(Counter(row["status"] for row in rows))
    return {"schema_version": 1, "as_of": as_of, "private_evidence": True,
            "input_sha256": evidence_hash({"sources": sources, "research": research,
                                          "approvals": approvals, "cadences": cadences}),
            "counts": counts, "sources": rows, "unmatched_evidence_ids": unused,
            "reconciliation_complete": bool(rows) and not unused and not counts.get("needs_review"),
            "activation_authorized": False, "live_configuration_verified": False}
