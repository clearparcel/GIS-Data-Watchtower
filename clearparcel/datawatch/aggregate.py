from __future__ import annotations

import datetime as dt
import json
from copy import deepcopy
from pathlib import Path


def stamp_worker(result: dict, worker: str) -> dict:
    stamped = deepcopy(result)
    for record in (stamped.get("sources") or {}).values():
        record["worker"] = worker
    stamped["worker"] = worker
    return stamped


def merge_states(base: dict | None, partial: dict, worker: str) -> dict:
    """Merge a worker's partial result into authoritative state without deleting other workers."""
    base = deepcopy(base or {})
    merged_sources = deepcopy(base.get("sources") or {})
    partial_sources = deepcopy(partial.get("sources") or {})
    for source_id, record in partial_sources.items():
        record["worker"] = worker
        merged_sources[source_id] = record

    counts = {
        status: sum(1 for row in merged_sources.values() if row.get("status") == status)
        for status in ("ok", "warn", "error")
    }
    generated = partial.get("generated_at") or dt.datetime.now(dt.timezone.utc).isoformat()
    workers = deepcopy(base.get("workers") or {})
    workers[worker] = {
        "checked_at": generated,
        "source_count": len(partial_sources),
        "overall": partial.get("overall"),
        "counts": partial.get("counts") or {},
        "telemetry": partial.get("telemetry") or {},
    }
    return {
        "schema_version": max(int(base.get("schema_version") or 2), int(partial.get("schema_version") or 2)),
        "generated_at": generated,
        "overall": "error" if counts["error"] else "warn" if counts["warn"] else "ok",
        "counts": counts,
        "sources": merged_sources,
        "workers": workers,
    }


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
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
