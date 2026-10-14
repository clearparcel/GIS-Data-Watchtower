from __future__ import annotations

import datetime as dt
import json
import math
import random
import tempfile
import time
from copy import deepcopy
from pathlib import Path

from .storage import StorageBackend, StorageConflictError
from .file_lock import atomic_write

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


def stamp_worker(result: dict, worker: str) -> dict:
    stamped = deepcopy(result)
    for record in (stamped.get("sources") or {}).values():
        record["worker"] = worker
    stamped["worker"] = worker
    return stamped


def merge_states(base: dict | None, partial: dict, worker: str, *, now: dt.datetime | None = None) -> dict:
    """Merge one worker report without deleting observations from other workers.

    Raises:
        ValueError: The report has no valid generated_at, is dated in the
            future beyond the clock-skew tolerance, checked no sources, or
            comes from a retired worker.
    """
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
    retired_workers = deepcopy(base.get('retired_workers') or {})
    if worker in retired_workers:
        retired_at = _parse_time(retired_workers[worker].get('retired_at'))
        if retired_at is not None and incoming_time <= retired_at:
            return base
        raise ValueError('retired worker cannot publish a new report')
    workers = deepcopy(base.get("workers") or {})
    retired_sources = deepcopy(base.get("retired_sources") or {})
    previous_worker = workers.get(worker) or {}
    previous_worker_time = _parse_time(previous_worker.get("last_report_at")
                                       or (workers.get(worker) or {}).get("checked_at"))
    if previous_worker_time and incoming_time <= previous_worker_time:
        return base
    shrink_refused = 0
    if scope_type == "fleet":
        # A complete report is authoritative only for this worker's inventory.
        # Legacy and filtered reports remain additive, including shared IDs.
        owned = [sid for sid, record in merged_sources.items() if record.get("worker") == worker]
        retirable = []
        for source_id in owned:
            record = merged_sources[source_id]
            seen = _parse_time(record.get("last_report_at") or record.get("checked_at"))
            if source_id not in partial_sources and (seen is None or seen <= incoming_time):
                retirable.append(source_id)
        # Refuse to retire most of a worker's inventory from one report (for
        # example a profile typo or a truncated registry) unless explicitly allowed.
        # Coverage counts only this worker's own sources that the report either
        # observed or deliberately skipped (disabled or reassigned in the
        # registry); unrelated or renamed IDs do not count.
        intended = {sid for sid, reason in (partial.get("skipped_sources") or {}).items()
                    if reason in {"disabled", "execution-profile"}}
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
        if retired_at is not None and incoming_time <= retired_at:
            continue
        seen = _parse_time(previous.get("last_report_at") or previous.get("checked_at"))
        if seen and seen >= incoming_time:
            continue
        record["status"] = _normalized_status(record.get("status"))
        record["worker"] = worker
        retired_sources.pop(source_id, None)
        record["last_report_at"] = generated
        if record.get("status") == "ok":
            record["last_success_at"] = generated
        elif previous.get("last_success_at"):
            record["last_success_at"] = previous["last_success_at"]
        merged_sources[source_id] = record

    counts = {
        status: sum(1 for row in merged_sources.values() if row.get("status") == status)
        for status in ("ok", "warn", "error")
    }
    # Report publication is the worker heartbeat even when one or more sources fail.
    # Keep that clock separate from the most recent all-clear worker run.
    worker_status = _normalized_status(partial.get("overall"))
    if scope_type in _PARTIAL_SCOPES and previous_worker:
        # A filtered run proves the worker is alive but says nothing about its
        # whole inventory: keep the fleet-level health from the last full run.
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
    previous_generated = _parse_time(base.get("generated_at"))
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


def retire_worker(state: dict, worker: str, retired_at: str) -> dict:
    """Archive an inactive worker after its sources have migrated, without deleting observations.

    Raises:
        ValueError: The worker owns sources, is unknown, or retirement would roll back time.
    """
    stamp = _parse_time(retired_at)
    if stamp is None:
        raise ValueError('worker retirement requires a valid timestamp')
    if any(source.get('worker') == worker for source in (state.get('sources') or {}).values()):
        raise ValueError('worker still owns source observations')
    prior = (state.get('workers') or {}).get(worker)
    if not isinstance(prior, dict):
        raise ValueError('worker is not active')
    for value in (state.get('generated_at'), prior.get('last_report_at'), prior.get('checked_at'),
                  prior.get('last_success_at')):
        seen = _parse_time(value)
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


def _age_seconds(now: dt.datetime, seen: dt.datetime) -> float:
    return (now - seen.astimezone(dt.timezone.utc)).total_seconds()


def with_freshness(state: dict, *, worker_stale_minutes: int = 1560, source_stale_minutes: int = 1560, now=None) -> dict:
    """Annotate reporting freshness without conflating it with source health."""
    result = deepcopy(state or {})
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    for worker in (result.get("workers") or {}).values():
        seen = _parse_time(worker.get("last_report_at") or worker.get("checked_at") or worker.get("last_success_at"))
        worker["stale"] = not seen or _age_seconds(now, seen) > worker_stale_minutes * 60
        worker["clock_skew"] = bool(seen and _age_seconds(now, seen) < -CLOCK_SKEW_TOLERANCE_SECONDS)
    workers = result.get("workers") or {}
    for source in (result.get("sources") or {}).values():
        seen = _parse_time(source.get("last_report_at") or source.get("checked_at") or source.get("last_success_at"))
        source["stale"] = not seen or _age_seconds(now, seen) > source_stale_minutes * 60
        source["worker_stale"] = bool((workers.get(source.get("worker")) or {}).get("stale"))
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
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"unable to decode JSON state file: {path}")


def save_json(path: Path, document: dict) -> None:
    atomic_write(path, (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
