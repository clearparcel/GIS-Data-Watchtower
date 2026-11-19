from __future__ import annotations

import datetime as dt
import json
import math
import random
import tempfile
import time
from copy import deepcopy
from pathlib import Path

from . import strict_json
from .watch import _EXECUTION_PROFILES
from .file_lock import atomic_write
from .parcel_access import CountyPermission
from .storage import StorageBackend, StorageConflictError

_ALLOWED_STATUS = {"ok", "warn", "error"}
# Tolerated clock difference between a worker and the aggregate writer.
CLOCK_SKEW_TOLERANCE_SECONDS = 300
# A full ("fleet") report may retire a worker's other sources only when it
# still covers at least this share of the sources the worker owned.
FLEET_RETIREMENT_MIN_SHARE = 0.5
_PARTIAL_SCOPES = {"source", "source_filter"}

def _normalized_status(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in _ALLOWED_STATUS else "error"


def merge_states(base: dict | None, partial: dict, worker: str, *, now: dt.datetime | None = None) -> dict:
    """Merge one worker report without deleting observations from other workers.

    Raises:
        ValueError: The report has no valid generated_at, is dated in the
            future beyond the clock-skew tolerance, checked no sources, or
            comes from a retired worker.
    """
    if not isinstance(worker, str) or worker not in _EXECUTION_PROFILES:
        raise ValueError("worker name must be a supported execution profile")
    base = deepcopy(base or {})
    merged_sources = deepcopy(base.get("sources") or {})
    partial_sources = deepcopy(partial.get("sources") or {})
    generated = partial.get("generated_at")
    incoming_time = _parse_time(generated)
    if incoming_time is None:
        raise ValueError("worker report requires a valid generated_at")
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    # Effective only when the merging clock is independent of the worker's
    # (e.g. the offline `aggregate` command or another worker's publish).
    if incoming_time > now + dt.timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS):
        # A future-dated report would block every later report from this worker.
        raise ValueError("worker report generated_at is in the future; check the worker clock")
    scope_type = (partial.get("scope") or {}).get("type")
    if scope_type == "empty":
        raise ValueError("refusing to merge a worker report that checked no sources")
    if not partial_sources and not (scope_type == "fleet" and partial.get("allow_inventory_shrink") is True):
        # Judge by contents, not the label: only an explicit fleet drain may be empty.
        raise ValueError("refusing to merge a worker report with no source observations")
    limit = now + dt.timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS)
    for source_id, record in partial_sources.items():
        if not isinstance(record, dict):
            raise ValueError(f"worker report source {str(source_id)[:80]!r} is not an object")
        # A future check time would win every later ordering comparison and
        # block publication; refuse it here, at the private write (fourth review Q02).
        checked = _parse_time(record.get("checked_at"))
        if record.get("checked_at") is not None and checked is None:
            # An unreadable check time is not an absent legacy one: it would fall
            # back to report-time ordering and look current (fifth review V04).
            raise ValueError(f"worker report source {str(source_id)[:80]!r} checked_at is not a valid time")
        if checked is not None and checked > limit:
            raise ValueError(f"worker report source {str(source_id)[:80]!r} checked_at is in the future; "
                             "check the worker clock")
    retired_workers = deepcopy(base.get('retired_workers') or {})
    if worker in retired_workers:
        retired_at = _parse_time(retired_workers[worker].get('retired_at'))
        if retired_at is not None and incoming_time <= retired_at:
            return base
        raise ValueError('retired worker cannot publish a new report')
    workers = deepcopy(base.get("workers") or {})
    retired_sources = deepcopy(base.get("retired_sources") or {})
    previous_worker = workers.get(worker) or {}
    # A stored time beyond the skew tolerance in the future came from a skewed
    # clock; it is not evidence and must not block later valid reports (T02).
    previous_worker_time = _plausible_time(previous_worker.get("last_report_at")
                                           or previous_worker.get("checked_at"), now)
    if previous_worker_time and incoming_time <= previous_worker_time:
        return base
    shrink_refused = 0
    if scope_type == "fleet":
        # A complete report is authoritative only for this worker's inventory.
        # Legacy and filtered reports remain additive, including shared IDs.
        owned = [sid for sid, record in merged_sources.items() if record.get("worker") == worker]
        retirable = []
        for source_id in owned:
            # The newest retained time, report or provider check: a source
            # measured after this report started is not retired by it (Q01).
            seen = _latest_time(merged_sources[source_id], now)
            if source_id not in partial_sources and (seen is None or seen <= incoming_time):
                retirable.append(source_id)
        # Refuse to retire most of a worker's inventory from one report (for
        # example a profile typo or a truncated registry) unless explicitly allowed.
        # Coverage counts only this worker's own sources that the report either
        # observed or deliberately skipped (disabled or reassigned in the
        # registry); unrelated or renamed IDs do not count.
        intended = {sid for sid, reason in (partial.get("skipped_sources") or {}).items()
                    if reason in {"disabled", "execution-profile"} | CountyPermission.COVERAGE_SKIPS}
        covered = sum(1 for sid in owned if sid in partial_sources or sid in intended)
        allowed = (partial.get("allow_inventory_shrink") is True
                   or covered >= math.ceil(len(owned) * FLEET_RETIREMENT_MIN_SHARE))
        if allowed:
            for source_id in retirable:
                del merged_sources[source_id]
                retired_sources[source_id] = {"worker": worker, "retired_at": generated}
        else:
            shrink_refused = len(retirable)
    for source_id, record in partial_sources.items():
        previous = merged_sources.get(source_id) or {}
        tombstone = retired_sources.get(source_id) or {}
        retired_at = _parse_time(tombstone.get("retired_at"))
        # Reinstatement needs evidence after the retirement: the provider check
        # when the record carries one (a deferred record carries an older
        # measurement), otherwise the report time (fourth review Q01). A
        # deferral without a check made no request: it is no evidence (V03).
        if retired_at is not None and (unmeasured_deferral(record) or (
                _parse_time(record.get("checked_at")) or incoming_time) <= retired_at):
            continue
        if _source_update_is_stale(record, previous, incoming_time, worker, now):
            # An older observation is not the current state, but its success
            # or availability is still history: arrival order must not erase
            # it (fifth review V05).
            _merge_history(previous, record, generated, now)
            continue
        if (record.get("deferred") and _parse_time(record.get("checked_at")) is None
                and _plausible_time(previous.get("checked_at"), now) is not None):
            # A deferred first check (a worker rebuilding its local state) made
            # no request: keep the last measurement and its check time, with
            # the new backoff warning (fourth review Q04).
            record = _carry_measurement(previous, record)
        if shrink_refused and previous.get("worker") not in (None, worker):
            # A report that failed the inventory guard (for example a wrong
            # registry) must not take sources over from another worker.
            continue
        record["status"] = _normalized_status(record.get("status"))
        record["worker"] = worker
        retired_sources.pop(source_id, None)
        record["last_report_at"] = generated
        # Inherit only trustworthy history. A fast clock can otherwise mask the
        # first failed check made after the clock was corrected.
        _inherit_history(record, previous, ("last_success_at", "last_available_at"), now)
        _merge_history(record, record, generated, now)
        merged_sources[source_id] = record

    counts = {
        status: sum(1 for row in merged_sources.values() if row.get("status") == status)
        for status in ("ok", "warn", "error")
    }
    # Report publication is the worker heartbeat even when one or more sources fail.
    # Keep that clock separate from the most recent all-clear worker run.
    worker_status = _normalized_status(partial.get("overall"))
    if _plausible_time(previous_worker.get("last_success_at"), now) is None:
        previous_worker.pop("last_success_at", None)
    if scope_type in _PARTIAL_SCOPES or shrink_refused:
        # A filtered run, or a fleet report whose inventory shrink was refused,
        # proves the worker is alive but cannot vouch for its whole inventory:
        # keep the fleet-level health from the last full run. A worker whose
        # first report is filtered has no fleet-level health yet (T10).
        if (previous_worker.get("checked_at") is not None
                and _plausible_time(previous_worker["checked_at"], now) is None):
            previous_worker = {}  # Its last fleet check cannot establish health.
        workers[worker] = {**previous_worker, "last_report_at": generated, "last_partial_report_at": generated}
    else:
        workers[worker] = {
            "checked_at": generated,
            "last_report_at": generated,
            "last_success_at": generated if worker_status == "ok" else previous_worker.get("last_success_at"),
            "source_count": len(partial_sources),
            "overall": worker_status,
            "counts": partial.get("counts") or {},
            "telemetry": partial.get("telemetry") or {},
        }
    if scope_type == "fleet":
        # Only a complete report can establish or clear a refused shrink.
        if shrink_refused:
            workers[worker]["inventory_shrink_refused"] = shrink_refused
        else:
            workers[worker].pop("inventory_shrink_refused", None)
    previous_generated = _plausible_time(base.get("generated_at"), now)
    fleet_generated = base["generated_at"] if previous_generated and previous_generated > incoming_time else generated
    return {
        "schema_version": max(int(base.get("schema_version") or 2), int(partial.get("schema_version") or 2), 3),
        "generated_at": fleet_generated,
        "overall": "error" if counts["error"] else "warn" if counts["warn"] else "ok",
        "counts": counts,
        "sources": merged_sources,
        "workers": workers,
        "retired_sources": retired_sources,
        "retired_workers": retired_workers,
    }


def retire_worker(state: dict, worker: str, retired_at: str, *, now: dt.datetime | None = None) -> dict:
    """Archive an inactive worker after its sources have migrated, without deleting observations.

    Raises:
        ValueError: The worker owns sources, is unknown, retirement would roll
            back time, or the retirement is dated in the future.
    """
    stamp = _parse_time(retired_at)
    if stamp is None:
        raise ValueError('worker retirement requires a valid timestamp')
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    if stamp > now + dt.timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS):
        # A future retirement would block publication (fourth review Q02).
        raise ValueError('worker retirement is dated in the future; check the clock')
    if any(source.get('worker') == worker for source in (state.get('sources') or {}).values()):
        raise ValueError('worker still owns source observations')
    prior = (state.get('workers') or {}).get(worker)
    if not isinstance(prior, dict):
        raise ValueError('worker is not active')
    for value in (state.get('generated_at'), prior.get('last_report_at'), prior.get('checked_at'),
                  prior.get('last_success_at')):
        # A stored time beyond the skew tolerance is not evidence; with the
        # future-retirement guard it would leave no acceptable time (V02).
        seen = _plausible_time(value, now)
        if seen is not None and stamp <= seen:
            raise ValueError('worker retirement must follow retained observations')
    result = deepcopy(state)
    archived = result['workers'].pop(worker)
    archived['retired_at'] = retired_at
    result.setdefault('retired_workers', {})[worker] = archived
    result['generated_at'] = retired_at
    return result


def publish_worker_retirement(storage: StorageBackend, name: str, worker: str, retired_at: str,
                              workdir: Path, *, retries: int = 8) -> dict:
    """Retire an inactive worker with CAS, revalidating ownership after each conflict.

    Raises:
        ValueError: The latest aggregate is absent or retirement is unsafe.
        StorageConflictError: Concurrent writers exhaust the bounded retry budget.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='watchtower-retirement-', dir=workdir) as scratch:
        base_path, output_path = Path(scratch) / 'base.json', Path(scratch) / 'next.json'
        for attempt in range(retries):
            exists, version = storage.download_versioned(name, base_path)
            if not exists:
                raise ValueError('cannot retire worker from absent aggregate')
            result = retire_worker(load_json(base_path), worker, retired_at)
            save_json(output_path, result)
            try:
                storage.upload_if_version(name, output_path, version)
                return result
            except StorageConflictError:
                if attempt + 1 >= retries:
                    raise
    raise ValueError('retirement requires a positive retry budget')


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _plausible_time(value, now: dt.datetime):
    """A parsed time, or None when missing, invalid or beyond the skew tolerance after ``now``."""
    parsed = _parse_time(value)
    if parsed is None or parsed > now + dt.timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS):
        return None
    return parsed


def unmeasured_deferral(record: dict) -> bool:
    """A rate-limit deferral that carries no provider check: zero attempts, no evidence."""
    return bool(record.get("deferred")) and _parse_time(record.get("checked_at")) is None


def _history_times(record: dict, generated: str) -> tuple[str | None, str | None]:
    """When ``record`` proves a successful and an available provider check, as merge records them."""
    observed = record.get("checked_at")
    stamp = observed if _parse_time(observed) else generated
    status = record.get("status")
    success = stamp if status == "ok" and not record.get("deferred") else None
    available = (stamp if status in ("ok", "warn") and not record.get("deferred")
                 and not record.get("rate_limited") else None)
    return success, available


def _inherit_history(record: dict, previous: dict, keys: tuple[str, ...], now: dt.datetime) -> None:
    """Keep the latest trustworthy historical evidence from either copy."""
    for key in keys:
        prior = _plausible_time(previous.get(key), now)
        current = _plausible_time(record.get(key), now)
        if prior is not None and (current is None or prior > current):
            record[key] = previous[key]
        elif current is None:
            record.pop(key, None)


def _merge_history(stored: dict, record: dict, generated: str, now: dt.datetime) -> None:
    """Advance ``stored`` last-success/availability times with an older report's evidence."""
    for key, value in zip(("last_success_at", "last_available_at"), _history_times(record, generated)):
        candidate = _plausible_time(value, now)
        if candidate is None:
            continue
        known = _plausible_time(stored.get(key), now)
        if known is None or candidate > known:
            stored[key] = value


def _latest_time(record: dict, now: dt.datetime):
    """The newest plausible report or provider-check time of a stored record."""
    times = [t for t in (_plausible_time(record.get(key), now) for key in ("last_report_at", "checked_at"))
             if t is not None]
    return max(times) if times else None


# Fields a deferred record never takes from the stored record it replaces.
_DEFERRED_CARRY_EXCLUDE = {"error", "changes", "deferred", "problems", "status", "rate_limited",
                           "last_report_at", "last_success_at", "last_available_at", "worker"}


def _carry_measurement(previous: dict, record: dict) -> dict:
    """A deferred record over the last stored measurement, as ``watch._deferred_record`` builds it."""
    carried = {key: value for key, value in previous.items() if key not in _DEFERRED_CARRY_EXCLUDE}
    carried.update({key: value for key, value in record.items() if value is not None})
    for key in ("checked_at", "last_success_at", "last_available_at", "worker"):
        if key in previous:
            carried[key] = previous[key]
        else:
            carried.pop(key, None)
    if previous.get("status") == "error":
        # Never report healthier than the last real observation.
        carried["status"] = "error"
        carried["error"] = previous.get("error") or record.get("error")
    return carried


def observation_rolls_back(incoming: dict, existing: dict) -> bool:
    """True when ``incoming`` carries an older provider observation than ``existing``.

    Ordering follows when the provider was checked (``checked_at``), not when a
    worker's run started or reported: overlapping workers can report an older
    observation after a newer one (third review T01). Records without a check
    time fall back to report time.
    """
    existing_checked, incoming_checked = _parse_time(existing.get("checked_at")), _parse_time(incoming.get("checked_at"))
    if existing_checked is not None and incoming_checked is not None:
        return incoming_checked < existing_checked
    existing_seen = _parse_time(existing.get("last_report_at") or existing.get("checked_at"))
    incoming_seen = _parse_time(incoming.get("last_report_at") or incoming.get("checked_at"))
    return existing_seen is not None and (incoming_seen is None or incoming_seen < existing_seen)


def _source_update_is_stale(record: dict, previous: dict, incoming_time: dt.datetime, worker: str,
                            now: dt.datetime) -> bool:
    """Whether a reported source record must not replace the stored one."""
    if not previous:
        return False
    previous_checked = _plausible_time(previous.get("checked_at"), now)
    incoming_checked = _parse_time(record.get("checked_at"))
    if previous_checked is not None and incoming_checked is not None:
        # Both carry a provider observation: the older one never wins.
        return incoming_checked < previous_checked
    if previous_checked is not None and previous.get("worker") not in (None, worker):
        # A record without an observation (a deferred first check) never
        # replaces another worker's measured observation.
        return True
    seen = _plausible_time(previous.get("last_report_at") or previous.get("checked_at"), now)
    return seen is not None and seen >= incoming_time


def _age_seconds(now: dt.datetime, seen: dt.datetime) -> float:
    return (now - seen.astimezone(dt.timezone.utc)).total_seconds()


def _source_check_time(source: dict) -> dt.datetime | None:
    """When a provider was last actually checked for this source.

    A deferred (rate-limit) record carries the previous check time and gets a
    new report time without any request, so report time never stands in for
    it. Legacy records without a check time fall back to report time.
    """
    checked = _parse_time(source.get("checked_at"))
    if source.get("check_withheld"):
        return None
    if source.get("checked_at") is not None or source.get("deferred"):
        return checked
    return _parse_time(source.get("last_report_at") or source.get("last_success_at"))


def with_freshness(state: dict, *, worker_stale_minutes: int = 1560, source_stale_minutes: int = 1560, now=None) -> dict:
    """Annotate reporting freshness without conflating it with source health."""
    result = deepcopy(state or {})
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    # A time beyond the clock-skew tolerance in the future is not evidence of a
    # current check: it is flagged and reported stale until a plausible one arrives.
    for worker in (result.get("workers") or {}).values():
        seen = _parse_time(worker.get("last_report_at") or worker.get("checked_at") or worker.get("last_success_at"))
        worker["clock_skew"] = bool(seen and _age_seconds(now, seen) < -CLOCK_SKEW_TOLERANCE_SECONDS)
        worker["stale"] = not seen or worker["clock_skew"] or _age_seconds(now, seen) > worker_stale_minutes * 60
    workers = result.get("workers") or {}
    for source in (result.get("sources") or {}).values():
        seen = _source_check_time(source)
        source["clock_skew"] = bool(seen and _age_seconds(now, seen) < -CLOCK_SKEW_TOLERANCE_SECONDS)
        source["stale"] = not seen or source["clock_skew"] or _age_seconds(now, seen) > source_stale_minutes * 60
        assigned = source.get("worker")
        # An assigned source whose worker record is missing has no worker report: stale, not current.
        source["worker_stale"] = bool(source.get("worker_unverified")) or (assigned is not None and (
            not isinstance(assigned, str) or assigned not in _EXECUTION_PROFILES
            or not isinstance(workers.get(assigned), dict) or bool(workers[assigned].get("stale"))))
        status = source.get("status")
        source["health"] = "healthy" if status == "ok" else "unhealthy" if status in ("warn", "error") else "unknown"
        source["reporting"] = "stale" if source.get("stale") or source.get("worker_stale") else "current"
    result["stale_workers"] = sum(1 for row in workers.values() if row.get("stale"))
    result["stale_sources"] = sum(1 for row in (result.get("sources") or {}).values() if row.get("stale"))
    return result


def publish_partial(storage, name: str, partial: dict, worker: str, workdir: Path, *, retries: int = 8) -> dict:
    """Publish with compare-and-swap retry so competing workers cannot overwrite each other."""
    workdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="watchtower-aggregate-", dir=workdir) as scratch:
        base_path = Path(scratch) / "base.json"
        output_path = Path(scratch) / "next.json"
        for attempt in range(retries):
            exists, version = storage.download_versioned(name, base_path)
            base = load_json(base_path) if exists else {}
            merged = merge_states(base, partial, worker)
            save_json(output_path, merged)
            try:
                storage.upload_if_version(name, output_path, version)
                return merged
            except StorageConflictError:
                if attempt + 1 >= retries:
                    raise
                time.sleep(min(0.5, 0.02 * (2 ** attempt)) + random.random() * 0.02)
        raise StorageConflictError(f"unable to publish aggregate after {retries} attempts")


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return strict_json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"unable to decode JSON state file: {path}")


def save_json(path: Path, document: dict) -> None:
    atomic_write(path, (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
