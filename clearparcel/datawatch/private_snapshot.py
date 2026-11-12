"""Validate the stored shapes used by private dashboard readers before caching."""
from __future__ import annotations

import math

from .public_projection import validate_snapshot_structure


def _object(record, key):
    value = record.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"invalid private snapshot {key}")
    return value


def _metrics(record):
    counts = _object(record, "counts")
    for key in ("ok", "warn", "error"):
        if key in counts and (type(counts[key]) is not int or counts[key] < 0):
            raise ValueError("invalid private snapshot count")
    telemetry = _object(record, "telemetry")
    for key in ("wall_ms", "cpu_ms", "peak_python_memory_kb", "sources_checked", "total_source_elapsed_ms"):
        value = telemetry.get(key)
        if value is not None and (type(value) not in (int, float) or value < 0
                                  or (type(value) is float and not math.isfinite(value))
                                  or value > 1e100):
            raise ValueError("invalid private snapshot telemetry")


def _record(record):
    if not isinstance(record, dict):
        raise ValueError("invalid private snapshot record")
    _metrics(record)
    for key in ("id", "name", "worker", "status", "category", "provider", "overall",
                "adapter", "kind", "url", "county_slug"):
        if record.get(key) is not None and not isinstance(record[key], str):
            raise ValueError(f"invalid private snapshot {key}")
    for key in ("provenance", "tracked_values", "public_metadata", "gac_completeness", "mngac_completeness", "county_records"):
        _object(record, key)
    if record.get("changes") is not None:
        if not isinstance(record["changes"], list) or not all(isinstance(item, dict) for item in record["changes"]):
            raise ValueError("invalid private snapshot changes")


def validate_private_snapshot(value, *, history=False):
    """Allow absent legacy optional fields, but reject malformed present fields."""
    if not isinstance(value, dict):
        raise ValueError("private snapshot must be an object")
    _record(value)
    for key in ("sources", "workers", "retired_sources", "retired_workers"):
        for record in _object(value, key).values():
            _record(record)
    _object(value, "rate_limits")
    if not history:
        validate_snapshot_structure(value)
