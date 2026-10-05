from __future__ import annotations

import datetime as dt
import json
import os
import random
import time
from copy import deepcopy
from pathlib import Path

from .storage import StorageConflictError

_ALLOWED_STATUS = {"ok", "warn", "error"}

def _normalized_status(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in _ALLOWED_STATUS else "error"


def stamp_worker(result: dict, worker: str) -> dict:
    stamped = deepcopy(result)
    for record in (stamped.get("sources") or {}).values():
        record["worker"] = worker
    stamped["worker"] = worker
    return stamped


def merge_states(base: dict | None, partial: dict, worker: str) -> dict:
    """Merge one worker report without deleting observations from other workers."""
    base = deepcopy(base or {})
    merged_sources = deepcopy(base.get("sources") or {})
    partial_sources = deepcopy(partial.get("sources") or {})
    generated = partial.get("generated_at") or dt.datetime.now(dt.timezone.utc).isoformat()
    for source_id, record in partial_sources.items():
        previous = merged_sources.get(source_id) or {}
        record["status"] = _normalized_status(record.get("status"))
        record["worker"] = worker
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
    workers = deepcopy(base.get("workers") or {})
    workers[worker] = {
        "checked_at": generated,
        "last_report_at": generated,
        "last_success_at": generated,
        "source_count": len(partial_sources),
        "overall": _normalized_status(partial.get("overall")),
        "counts": partial.get("counts") or {},
        "telemetry": partial.get("telemetry") or {},
    }
    return {
        "schema_version": max(int(base.get("schema_version") or 2), int(partial.get("schema_version") or 2), 3),
        "generated_at": generated,
        "overall": "error" if counts["error"] else "warn" if counts["warn"] else "ok",
        "counts": counts,
        "sources": merged_sources,
        "workers": workers,
    }


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def with_freshness(state: dict, *, worker_stale_minutes: int = 1560, source_stale_minutes: int = 1560, now=None) -> dict:
    """Annotate reporting freshness without conflating it with source health."""
    result = deepcopy(state or {})
    now = now or dt.datetime.now(dt.timezone.utc)
    for worker in (result.get("workers") or {}).values():
        seen = _parse_time(worker.get("last_success_at") or worker.get("last_report_at") or worker.get("checked_at"))
        worker["stale"] = not seen or (now - seen.astimezone(dt.timezone.utc)).total_seconds() > worker_stale_minutes * 60
    workers = result.get("workers") or {}
    for source in (result.get("sources") or {}).values():
        seen = _parse_time(source.get("last_success_at") or source.get("last_report_at") or source.get("checked_at"))
        source["stale"] = not seen or (now - seen.astimezone(dt.timezone.utc)).total_seconds() > source_stale_minutes * 60
        source["worker_stale"] = bool((workers.get(source.get("worker")) or {}).get("stale"))
        source["health"] = "unhealthy" if source.get("status") in ("warn", "error") else "healthy"
        source["reporting"] = "stale" if source.get("stale") or source.get("worker_stale") else "current"
    result["stale_workers"] = sum(1 for row in workers.values() if row.get("stale"))
    result["stale_sources"] = sum(1 for row in (result.get("sources") or {}).values() if row.get("stale"))
    return result


def publish_partial(storage, name: str, partial: dict, worker: str, workdir: Path, *, retries: int = 8) -> dict:
    """Publish with compare-and-swap retry so competing workers cannot overwrite each other."""
    workdir.mkdir(parents=True, exist_ok=True)
    base_path = workdir / f".{worker}-aggregate-base.json"
    output_path = workdir / f".{worker}-aggregate-next.json"
    try:
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
    finally:
        for scratch in (base_path, output_path):
            try:
                scratch.unlink()
            except FileNotFoundError:
                pass


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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
