from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path

from clearparcel.datawatch.public_dashboard import sanitize_public_render_state, sanitize_source_metadata
from clearparcel.datawatch.storage import GCSStorage, StorageBackend, StorageConflictError
from clearparcel.datawatch.aggregate import _parse_time


_FORBIDDEN_PUBLIC_KEYS = {
    "url",
    "schema_hash",
    "observation_fingerprint",
    "tracked_values",
    "changes",
    "provenance",
    "telemetry",
    "statistics_queries",
}


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _unsafe_paths(value, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}".strip(".")
            if key in _FORBIDDEN_PUBLIC_KEYS:
                found.append(next_path)
            found.extend(_unsafe_paths(item, next_path))
    elif isinstance(value, list):
        for item in value:
            found.extend(_unsafe_paths(item, f"{path}[]"))
    return found


def validate_public_state(state: dict) -> None:
    """Fail closed if a public snapshot contains an operational/private key."""
    unsafe = _unsafe_paths(state)
    if unsafe:
        raise RuntimeError("public snapshot contains forbidden fields: " + ", ".join(sorted(unsafe)))
    for source in (state.get('sources') or {}).values():
        if isinstance(source, dict) and 'public_metadata' in source:
            metadata = source['public_metadata']
            if not isinstance(metadata, dict) or sanitize_source_metadata({'public_metadata': metadata}) != metadata:
                raise RuntimeError('public snapshot contains invalid public_metadata')


def _snapshot_is_superseded(candidate: dict, current: dict) -> bool:
    """Refuse rollback of known fleet, worker, or retained source observations."""
    def older(new, old):
        old_time, new_time = _parse_time(old), _parse_time(new)
        return old_time is not None and (new_time is None or new_time < old_time)
    if older(candidate.get("generated_at"), current.get("generated_at")):
        return True
    for name, worker in (current.get("workers") or {}).items():
        incoming = (candidate.get("workers") or {}).get(name) or {}
        if older(incoming.get("last_report_at") or incoming.get("checked_at"),
                 worker.get("last_report_at") or worker.get("checked_at")):
            return True
    for name, source in (current.get("sources") or {}).items():
        incoming = (candidate.get("sources") or {}).get(name)
        source_seen = source.get("last_report_at") or source.get("checked_at")
        if incoming is None:
            tombstone = (candidate.get("retired_sources") or {}).get(name)
            if not isinstance(tombstone, dict) or older(tombstone.get("retired_at"), source_seen):
                return True
        elif older(incoming.get("last_report_at") or incoming.get("checked_at"), source_seen):
            return True
    for name, tombstone in (current.get("retired_sources") or {}).items():
        retired_at = tombstone.get("retired_at") if isinstance(tombstone, dict) else None
        incoming = (candidate.get("sources") or {}).get(name)
        incoming_tombstone = (candidate.get("retired_sources") or {}).get(name)
        if incoming is not None:
            incoming_at = incoming.get("last_report_at") or incoming.get("checked_at")
            if _parse_time(retired_at) is not None and (
                _parse_time(incoming_at) is None or _parse_time(incoming_at) <= _parse_time(retired_at)
            ):
                return True
        elif not isinstance(incoming_tombstone, dict) or older(
            incoming_tombstone.get("retired_at"), retired_at
        ):
            return True
    return False


def publish_public_snapshot(
    source: StorageBackend,
    destination: StorageBackend,
    *,
    source_object: str = "aggregate-state.json",
    destination_object: str = "aggregate-state.json",
    workdir: str | Path,
) -> dict:
    """Read the unified aggregate, sanitize it, and publish only the public representation."""
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="watchtower-public-", dir=root) as scratch:
        scratch_root = Path(scratch)
        raw_path = scratch_root / "aggregate-source.json"
        public_path = scratch_root / "aggregate-public.json"

        if not source.download(source_object, raw_path):
            raise FileNotFoundError(f"source aggregate not found: {source_object}")

        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        public = sanitize_public_render_state(raw)
        validate_public_state(public)
        current_path = scratch_root / "destination.json"
        published = False
        for attempt in range(8):
            try:
                exists, version = destination.download_versioned(destination_object, current_path)
                current = json.loads(current_path.read_text(encoding="utf-8")) if exists else {}
                if _snapshot_is_superseded(public, current):
                    public = current
                    break
                public["public_published_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                # Keep the publication clock monotonic when hosts have clock skew.
                previous_time = _parse_time(current.get("public_published_at"))
                if previous_time and previous_time > _parse_time(public["public_published_at"]):
                    public["public_published_at"] = current["public_published_at"]
                public_path.write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                destination.upload_if_version(destination_object, public_path, version)
                published = True
                break
            except StorageConflictError:
                if attempt == 7:
                    raise

        return {
            "published": published,
            "reason": "published" if published else "superseded",
            "public_published_at": public.get("public_published_at"),
            "generated_at": public.get("generated_at"),
            "overall": public.get("overall"),
            "source_count": len(public.get("sources") or {}),
            "worker_count": len(public.get("workers") or {}),
            "destination_object": destination_object,
        }


def publish_public_snapshot_from_env() -> dict:
    """Publish with two GCS clients sharing this process's application default credentials.

    Distinct service identities are a deployment configuration responsibility.
    """
    source = GCSStorage(
        _required_env("WATCHTOWER_PUBLIC_SOURCE_BUCKET"),
        os.environ.get("WATCHTOWER_PUBLIC_SOURCE_PREFIX", "").strip("/"),
    )
    destination = GCSStorage(
        _required_env("WATCHTOWER_PUBLIC_DEST_BUCKET"),
        os.environ.get("WATCHTOWER_PUBLIC_DEST_PREFIX", "").strip("/"),
    )
    return publish_public_snapshot(
        source,
        destination,
        source_object=os.environ.get("WATCHTOWER_PUBLIC_SOURCE_OBJECT", "aggregate-state.json"),
        destination_object=os.environ.get("WATCHTOWER_PUBLIC_DEST_OBJECT", "aggregate-state.json"),
        workdir=os.environ.get("WATCHTOWER_PUBLIC_PUBLISH_WORKDIR", "/tmp/watchtower-public-publish"),
    )
