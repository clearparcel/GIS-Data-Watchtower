from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from clearparcel.datawatch.public_dashboard import sanitize_public_render_state
from clearparcel.datawatch.storage import GCSStorage, StorageBackend


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
    raw_path = root / "aggregate-source.json"
    public_path = root / "aggregate-public.json"

    if not source.download(source_object, raw_path):
        raise FileNotFoundError(f"source aggregate not found: {source_object}")

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    public = sanitize_public_render_state(raw)
    public["public_published_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    validate_public_state(public)

    temp = public_path.with_suffix(".tmp")
    temp.write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(public_path)
    destination.upload(destination_object, public_path)

    return {
        "published": True,
        "public_published_at": public.get("public_published_at"),
        "generated_at": public.get("generated_at"),
        "overall": public.get("overall"),
        "source_count": len(public.get("sources") or {}),
        "worker_count": len(public.get("workers") or {}),
        "destination_object": destination_object,
    }


def publish_public_snapshot_from_env() -> dict:
    """Publish the public snapshot using separate source/destination GCS identities."""
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
