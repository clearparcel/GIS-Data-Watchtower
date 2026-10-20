"""Minimum spacing between provider-polling runs. Disabled unless configured.

When ``WATCHTOWER_MIN_DISPATCH_HOURS`` is set, every command that polls
providers (``cloud-job`` and ``check``) first claims a slot in the private
``runs/dispatch-guard.json`` object through the existing version-conditional
storage. A run that starts sooner than the minimum after the previous claimed
run is refused before any provider request. The claim itself is a
compare-and-swap write, so two runs started at the same moment cannot both
proceed.

Spacing is compared at whole-minute resolution (a 30-second tolerance), so a
few seconds of scheduler jitter cannot skip the daily run on the spring
daylight-saving change, when a 05:00 America/Chicago schedule is exactly 23
elapsed hours after the previous run.

An operator can still run a check early by passing an explicit override
reason. The override is recorded in the guard history with the run, so it is
visible in later cadence reviews; it is never implied.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import uuid

from . import strict_json
from .storage import StorageBackend, StorageConflictError

GUARD_OBJECT = "runs/dispatch-guard.json"
SCHEMA_VERSION = 1
ENV_MIN_HOURS = "WATCHTOWER_MIN_DISPATCH_HOURS"
TOLERANCE = timedelta(seconds=30)
CLOCK_SKEW = timedelta(minutes=2)
KEEP = 60
MAX_HOURS = 168.0
MAX_REASON = 200


class DispatchRefused(RuntimeError):
    """A provider-polling run was refused before any provider request."""


class DispatchGuardError(ValueError):
    """The guard configuration or stored record is invalid; fail closed."""


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def configured_min_hours(environ=None) -> float | None:
    """The configured minimum spacing in hours, or None when the guard is off."""
    raw = (os.environ if environ is None else environ).get(ENV_MIN_HOURS)
    if raw is None or not str(raw).strip():
        return None
    try:
        hours = float(str(raw).strip())
    except ValueError as exc:
        raise DispatchGuardError(f"{ENV_MIN_HOURS} must be a number of hours") from exc
    if not math.isfinite(hours) or not 1.0 <= hours <= MAX_HOURS:
        raise DispatchGuardError(f"{ENV_MIN_HOURS} must be between 1 and {MAX_HOURS:g} hours")
    return hours


def _validate(data) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise DispatchGuardError("dispatch guard record has an unsupported shape")
    runs = data.get("runs")
    if not isinstance(runs, list):
        raise DispatchGuardError("dispatch guard record has no run list")
    for row in runs:
        if not isinstance(row, dict) or _time(row.get("started_at")) is None:
            raise DispatchGuardError("dispatch guard record has an invalid run entry")
    return data


def _read(storage: StorageBackend, name: str):
    with tempfile.TemporaryDirectory(prefix="watchtower-dispatch-") as scratch:
        path = Path(scratch) / "guard.json"
        exists, token = storage.download_versioned(name, path)
        if not exists:
            return {"schema_version": SCHEMA_VERSION, "private_evidence": True, "runs": []}, None
        try:
            data = strict_json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise DispatchGuardError("dispatch guard record is not valid JSON") from exc
    return _validate(data), token


def _write(storage: StorageBackend, name: str, data: dict, token) -> None:
    with tempfile.TemporaryDirectory(prefix="watchtower-dispatch-") as scratch:
        path = Path(scratch) / "guard.json"
        path.write_text(json.dumps(data, indent=1, allow_nan=False) + "\n", encoding="utf-8")
        storage.upload_if_version(name, path, token)


def claim_dispatch(storage: StorageBackend, *, min_hours: float, command: str, override: str | None = None,
                   execution_id: str | None = None, now: datetime | None = None,
                   name: str = GUARD_OBJECT, attempts: int = 5) -> dict:
    """Record this run as the latest provider dispatch, or raise DispatchRefused.

    Nothing is written when the run is refused.
    """
    if type(min_hours) not in (int, float) or not 1.0 <= float(min_hours) <= MAX_HOURS:
        raise DispatchGuardError("min_hours must be between 1 and 168")
    reason = (override or "").strip()
    if override is not None and not reason:
        raise DispatchGuardError("an override needs a reason")
    if len(reason) > MAX_REASON:
        raise DispatchGuardError(f"override reason is limited to {MAX_REASON} characters")
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    minimum = timedelta(hours=float(min_hours))
    run_id = execution_id or os.environ.get("CLOUD_RUN_EXECUTION") or f"local-{uuid.uuid4().hex[:12]}"
    for _ in range(attempts):
        data, token = _read(storage, name)
        previous = max((_time(r["started_at"]) for r in data["runs"]), default=None)
        if previous is not None and not reason:
            if previous > clock + CLOCK_SKEW:
                raise DispatchRefused("the previous provider run is recorded in the future; "
                                      "refusing until an operator reviews the dispatch guard")
            elapsed = clock - previous
            if elapsed + TOLERANCE < minimum:
                wait = minimum - elapsed - TOLERANCE
                raise DispatchRefused(
                    f"provider checks last started {elapsed.total_seconds() / 3600:.2f} h ago; the minimum "
                    f"spacing is {float(min_hours):g} h (next allowed in about "
                    f"{math.ceil(wait.total_seconds() / 60)} min). Pass an override reason to run anyway.")
        entry = {"started_at": _iso(clock), "execution_id": str(run_id)[:120], "command": command,
                 "min_hours": float(min_hours)}
        if previous is not None:
            entry["hours_since_previous"] = round((clock - previous).total_seconds() / 3600, 3)
        if reason:
            entry["override_reason"] = reason
        runs = sorted(data["runs"] + [entry], key=lambda r: r["started_at"])[-KEEP:]
        try:
            _write(storage, name, {"schema_version": SCHEMA_VERSION, "private_evidence": True, "runs": runs},
                   token)
            return entry
        except StorageConflictError:
            continue  # Another run claimed first: re-read and re-evaluate against its claim.
    raise DispatchRefused("the dispatch guard changed during every claim attempt; another run is starting")


def guard_dispatch(storage_factory, *, command: str, override: str | None, environ=None) -> dict | None:
    """Claim a dispatch slot when the guard is configured; None when it is off."""
    min_hours = configured_min_hours(environ)
    if min_hours is None:
        if override is not None:
            raise DispatchGuardError("--override-min-interval was given but the dispatch guard is not configured")
        return None
    entry = claim_dispatch(storage_factory(), min_hours=min_hours, command=command, override=override)
    logged = {k: v for k, v in entry.items() if k != "override_reason"}
    if "override_reason" in entry:
        logged["override"] = True
    print(json.dumps({"severity": "WARNING" if "override_reason" in entry else "NOTICE",
                      "message": "Watchtower provider dispatch claimed", "watchtower_dispatch": logged}),
          file=sys.stderr)
    return entry
