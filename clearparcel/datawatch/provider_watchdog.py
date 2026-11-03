"""Provider-run watchdog: notice when no provider run has reported recently.

Cloud Monitoring's metric-absence condition is capped at 23.5 hours, which is
shorter than one daily provider cycle, so it cannot express "no provider run
in 26 hours". The public publisher already runs every few minutes and already
reads the unified aggregate, including each worker's last report time. This
module turns that into one structured ``ERROR`` log line per overdue worker,
which a log-based alerting policy routes to email.

The watchdog never polls a provider, never changes the publisher's result, and
never raises: observability must not stop publication.
"""
from __future__ import annotations

import datetime as dt
import json
import os

from clearparcel.datawatch.aggregate import CLOCK_SKEW_TOLERANCE_SECONDS, _parse_time

LOG_KEY = "watchtower_provider_run_overdue"
DEFAULT_STALE_MINUTES = 1560  # 26 hours: one daily run, the 23-hour spacing guard, DST shifts.


def _expected_from_env(environ) -> set[str] | None:
    raw = str(environ.get("WATCHTOWER_WATCHDOG_WORKERS", "")).strip()
    if not raw:
        return None
    return {name.strip() for name in raw.split(",") if name.strip()}


def _stale_minutes_from_env(environ) -> int:
    raw = str(environ.get("WATCHTOWER_WORKER_STALE_MINUTES", "")).strip()
    try:
        value = int(raw) if raw else DEFAULT_STALE_MINUTES
    except ValueError:
        return DEFAULT_STALE_MINUTES
    return value if value > 0 else DEFAULT_STALE_MINUTES


def overdue_workers(aggregate: dict, *, now: dt.datetime, stale_minutes: int = DEFAULT_STALE_MINUTES,
                    expected: set[str] | None = None) -> tuple[list[dict], int]:
    """Return (overdue findings, number of workers checked).

    ``expected`` names the workers that must report. When it is ``None``, every
    current (non-retired) worker in the aggregate is expected. An expected
    worker missing from the aggregate is overdue with reason ``missing``.
    """
    workers = aggregate.get("workers") if isinstance(aggregate, dict) else None
    workers = workers if isinstance(workers, dict) else {}
    names = sorted(expected) if expected is not None else sorted(workers)
    now = now.astimezone(dt.timezone.utc)
    findings = []
    for name in names:
        worker = workers.get(name)
        base = {"worker": name, "threshold_minutes": stale_minutes}
        if not isinstance(worker, dict):
            findings.append({**base, "reason": "missing", "last_report_at": None})
            continue
        stamp = worker.get("last_report_at") or worker.get("checked_at")
        seen = _parse_time(stamp)
        if seen is None:
            findings.append({**base, "reason": "no_report_time", "last_report_at": None})
            continue
        age = (now - seen.astimezone(dt.timezone.utc)).total_seconds()
        if age < -CLOCK_SKEW_TOLERANCE_SECONDS:
            findings.append({**base, "reason": "clock_skew", "last_report_at": str(stamp)})
        elif age > stale_minutes * 60:
            findings.append({**base, "reason": "overdue", "last_report_at": str(stamp),
                             "age_minutes": int(age // 60)})
    return findings, len(names)


def run_provider_watchdog(aggregate: dict, stream, *, now: dt.datetime | None = None,
                          environ=None) -> dict:
    """Log one ERROR line per overdue worker; return a small summary. Never raises."""
    try:
        environ = os.environ if environ is None else environ
        stale_minutes = _stale_minutes_from_env(environ)
        findings, checked = overdue_workers(
            aggregate, now=now or dt.datetime.now(dt.timezone.utc), stale_minutes=stale_minutes,
            expected=_expected_from_env(environ))
        for finding in findings:
            _emit(stream, {"severity": "ERROR", LOG_KEY: finding})
        return {"checked": checked, "overdue": [f["worker"] for f in findings]}
    except Exception:  # noqa: BLE001 - observability must not fail publication
        return {"checked": 0, "overdue": [], "error": "watchdog_failed"}


def _emit(stream, payload: dict) -> None:
    try:
        stream.write(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n")
        stream.flush()
    except Exception:  # noqa: BLE001
        pass
