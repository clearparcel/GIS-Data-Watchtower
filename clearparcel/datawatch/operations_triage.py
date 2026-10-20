"""Offline evidence triage; never polls providers, changes state, or sends alerts."""
from __future__ import annotations

from datetime import datetime, timezone
import math


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def triage_executions(executions: list, *, as_of: str, max_age_hours: float = 36) -> dict:
    """Join operator-correlated execution receipts to original worker reports.

    Input is private evidence, not an aggregate or a public dashboard snapshot.
    Exit codes describe the process outcome; they cannot identify failing sources.
    """
    now = _time(as_of)
    if now is None or not isinstance(executions, list):
        raise ValueError("require an aware as_of timestamp and an executions list")
    if (type(max_age_hours) not in (int, float) or not math.isfinite(max_age_hours)
            or max_age_hours <= 0):
        raise ValueError("max_age_hours must be finite and positive")
    prepared, seen = [], set()
    for item in executions:
        if not isinstance(item, dict):
            raise ValueError("each execution must be an object")
        run, worker = item.get("execution_id"), item.get("worker")
        start, end = _time(item.get("started_at")), _time(item.get("completed_at"))
        if not all(isinstance(x, str) and x.strip() for x in (run, worker)):
            raise ValueError("execution_id and worker are required")
        if (worker, run) in seen:
            raise ValueError("duplicate execution identity")
        seen.add((worker, run))
        if start is None or end is None or not start <= end <= now:
            raise ValueError("execution requires ordered aware timestamps no later than as_of")
        prepared.append((start, end, worker, run, item))
    prepared.sort(key=lambda row: (row[0], row[2], row[3]))
    # Overlapping executions cannot establish an unambiguous recovery sequence.
    ends = {}
    for start, end, worker, _, _ in prepared:
        if worker in ends and start <= ends[worker]:
            raise ValueError("overlapping executions for a worker require manual reconciliation")
        ends[worker] = end

    rows, events, unresolved = [], [], {}
    for start, end, worker, run, item in prepared:
        code = item.get("exit_code")
        outcome = {0: "ok_exit", 1: "source_warning_exit", 2: "source_or_scope_error_exit",
                   3: "tool_failure_exit"}.get(code) if type(code) is int else None
        row = {"execution_id": run, "worker": worker, "exit_code": code if type(code) is int else None,
               "outcome": outcome or "unclassified_exit", "evidence_gaps": [], "sources": []}
        rows.append(row)
        gaps = row["evidence_gaps"]
        report = item.get("report")
        if outcome is None:
            gaps.append("unrecognized_exit_code")
        if not isinstance(report, dict):
            gaps.append("missing_worker_report")
            continue
        generated = _time(report.get("generated_at"))
        sources = report.get("sources")
        if generated is None or not start <= generated <= end:
            gaps.append("report_outside_execution_window")
        if report.get("worker") not in (None, worker) or "workers" in report:
            gaps.append("not_this_workers_original_report")
        if not isinstance(sources, dict) or not all(isinstance(s, dict) for s in sources.values()):
            gaps.append("invalid_sources")
            continue
        counts = {status: sum(s.get("status") == status for s in sources.values())
                  for status in ("ok", "warn", "error")}
        if sum(counts.values()) != len(sources):
            gaps.append("unknown_source_status")
        reported_counts = report.get("counts")
        if (not isinstance(reported_counts, dict) or reported_counts != counts
                or any(type(v) is not int for v in reported_counts.values())):
            gaps.append("counts_disagree_with_sources")
        scope = report.get("scope")
        scope_type = scope.get("type") if isinstance(scope, dict) else None
        if not sources:
            # Empty scope is an intentional exit 2, but has no provider cause.
            if scope_type != "empty":
                gaps.append("no_source_evidence")
            expected = "error"
        else:
            expected = "error" if counts["error"] else "warn" if counts["warn"] else "ok"
        if report.get("overall") != expected:
            gaps.append("overall_disagrees_with_sources")
        if type(code) is not int or code != {"ok": 0, "warn": 1, "error": 2}[expected]:
            gaps.append("exit_disagrees_with_report")
        valid_report = not gaps
        row["scope"] = scope_type
        row["report_freshness"] = (
            "unknown" if generated is None or generated > now else
            "overdue" if (now - generated).total_seconds() > max_age_hours * 3600 else "fresh"
        )
        for sid, source in sorted(sources.items()):
            checked = _time(source.get("checked_at"))
            deferred = bool(source.get("deferred"))
            rate_limited = source.get("rate_limited") is True
            valid_check = (checked is not None and generated is not None
                           and generated <= checked <= end and not deferred)
            if not valid_check and not deferred:
                gaps.append(f"unverified_check_time:{sid}")
            if source.get("worker") not in (None, worker):
                gaps.append(f"source_worker_mismatch:{sid}")
                valid_check = False
            status = source.get("status")
            if status not in ("ok", "warn", "error"):
                status = "unknown"
            if status == "ok" and (deferred or rate_limited):
                gaps.append(f"success_with_backoff:{sid}")
            if checked is not None and checked > end:
                gaps.append(f"future_check_time:{sid}")
            detail = {"source_id": sid, "status": status,
                      "checked_at": checked.isoformat() if checked else None,
                      "freshness": "unknown" if checked is None or checked > end else
                      "overdue" if (now - checked).total_seconds() > max_age_hours * 3600 else "fresh",
                      "reason": "provider_backoff" if deferred else
                      "provider_rate_limit" if rate_limited else
                      "source_error" if status == "error" else
                      "source_warning" if status == "warn" else status}
            row["sources"].append(detail)
            key = (worker, sid)
            if not valid_report:
                continue
            if status in ("warn", "error"):
                unresolved[key] = {"worker": worker, "source_id": sid, "execution_id": run,
                                   "status": status, "reason": detail["reason"]}
                events.append({"type": detail["reason"], **unresolved[key]})
            elif status == "ok" and valid_check and not rate_limited and key in unresolved:
                previous = unresolved.pop(key)
                events.append({"type": "recovered", "worker": worker, "source_id": sid,
                               "execution_id": run, "previous_execution_id": previous["execution_id"],
                               "checked_at": source["checked_at"]})
    return {"schema_version": 1, "as_of": as_of, "private_evidence": True,
            "evidence_complete": bool(rows) and all(not r["evidence_gaps"] for r in rows),
            "executions": rows, "events": events,
            "unresolved_sources": list(unresolved.values()),
            "notification_delivery": "not_attempted",
            "provider_change_verification": "UNVERIFIED"}
