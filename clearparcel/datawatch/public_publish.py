from __future__ import annotations

import datetime as dt
import json
from copy import deepcopy
import os
import sys
import tempfile
from pathlib import Path

from clearparcel.datawatch.public_dashboard import sanitize_public_render_state, sanitize_source_metadata
from clearparcel.datawatch import strict_json
from clearparcel.datawatch.public_projection import (InvalidSnapshotError, _overall, _status_counts,
                                                     validate_snapshot_structure, validate_snapshot_totals)
from clearparcel.datawatch.storage import GCSStorage, StorageBackend, StorageConflictError, gcs_object_identity
from clearparcel.datawatch.aggregate import (CLOCK_SKEW_TOLERANCE_SECONDS, _carry_measurement, _latest_time,
                                             _parse_time, _plausible_time, observation_rolls_back,
                                             unmeasured_deferral)
from clearparcel.datawatch.provider_watchdog import _emit, run_provider_watchdog

QUARANTINE_LOG_KEY = "watchtower_publisher_clock_quarantine"


_FORBIDDEN_PUBLIC_KEYS = {
    "url",
    "schema_hash",
    "observation_fingerprint",
    "tracked_values",
    "changes",
    "provenance",
    "telemetry",
    "statistics_queries",
    "gac_check_error",
}


class PublisherAliasError(RuntimeError):
    """Source and destination address the same object; publishing would overwrite private input."""


def _refuse_alias(source_identity: str | None, destination_identity: str | None) -> None:
    if source_identity is not None and source_identity == destination_identity:
        raise PublisherAliasError(
            "public publisher source and destination are the same object; refusing to overwrite private input")


def _identity(backend, name: str) -> str | None:
    identify = getattr(backend, "object_identity", None)
    return identify(name) if callable(identify) else None


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


def validate_private_aggregate(raw: object) -> None:
    """Reject a private aggregate whose containers are missing or malformed.

    Projection keeps only known leaves and creates empty containers, so it
    cannot tell a malformed fleet from an empty one. A structurally valid empty
    fleet still declares its containers (as ``aggregate.merge_states`` does).
    """
    if not isinstance(raw, dict):
        raise InvalidSnapshotError("private aggregate is not an object")
    for key in ("counts", "sources", "workers"):
        if not isinstance(raw.get(key), dict):
            raise InvalidSnapshotError(f"private aggregate {key} is missing or not an object")
    for key in ("sources", "workers", "retired_sources", "retired_workers"):
        container = raw.get(key, {})
        if not isinstance(container, dict) or not all(isinstance(record, dict) for record in container.values()):
            raise InvalidSnapshotError(f"private aggregate {key} contains a malformed record")
    # Projection drops an invalid tally, which would leave an empty, healthy
    # looking publication; check the supplied totals before anything is
    # discarded (follow-up review F01). The fleet tally is derived from the
    # sources (aggregate.merge_states), so it must also agree with them.
    for key in ("ok", "warn", "error"):
        if key in raw["counts"]:
            value = raw["counts"][key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidSnapshotError(f"private aggregate count {key} is invalid")
    # A mistyped status is tallied nowhere, so it could sit beside an all-clear
    # fleet. Aggregation writes only ok/warn/error; an absent or legacy
    # "unknown" status stays visible as unknown (third review T03).
    for source_id, record in raw["sources"].items():
        if "status" in record and record["status"] not in _PRIVATE_SOURCE_STATUSES:
            raise InvalidSnapshotError(f"private aggregate source {str(source_id)[:80]!r} has an invalid status")
        # Aggregation writes a worker name; any other assignment is unreadable
        # input, never a silent watchdog or digest failure (fourth review Q10).
        # A padded name is a separate worker to the watchdog but no known
        # worker publicly, so one source would be stale privately and current
        # publicly (fifth review V06).
        if record.get("worker") is not None and (not isinstance(record["worker"], str)
                                                 or not record["worker"].strip()
                                                 or record["worker"] != record["worker"].strip()):
            raise InvalidSnapshotError(f"private aggregate source {str(source_id)[:80]!r} has an invalid worker")
    validate_snapshot_totals(raw)


_PRIVATE_SOURCE_STATUSES = {"ok", "warn", "error", "unknown", None}


def _ordering_times(state: dict):
    """Every time the rollback guard orders publications by."""
    yield "generated_at", state.get("generated_at")
    for name, worker in (state.get("workers") or {}).items():
        for key in ("last_report_at", "checked_at"):
            yield f"workers.{name}.{key}", worker.get(key)
    for name, worker in (state.get("retired_workers") or {}).items():
        yield f"retired_workers.{name}.retired_at", worker.get("retired_at")
    for name, source in (state.get("sources") or {}).items():
        for key in ("last_report_at", "checked_at"):
            yield f"sources.{name}.{key}", source.get(key)
    for name, tombstone in (state.get("retired_sources") or {}).items():
        if isinstance(tombstone, dict):
            yield f"retired_sources.{name}.retired_at", tombstone.get("retired_at")


def validate_ordering_clocks(state: dict, now: dt.datetime) -> None:
    """Refuse a publication dated ahead of this publisher's clock.

    A future time would win every later rollback comparison and block valid
    publications until real time caught up (third review T02).
    """
    limit = now + dt.timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS)
    for label, value in _ordering_times(state):
        stamp = _parse_time(value)
        if stamp is not None and stamp > limit:
            raise InvalidSnapshotError(f"aggregate time {label[:120]} is in the future; check the worker clock")


_SOURCE_CLOCKS = ("checked_at", "last_report_at", "last_success_at", "last_available_at")
_WORKER_CLOCKS = ("checked_at", "last_report_at", "last_success_at")


def _untrusted_clock(value, now: dt.datetime) -> bool:
    """A present clock that is unreadable or beyond the skew tolerance after ``now``."""
    if value is None or value == "":
        return False
    parsed = _parse_time(value) if isinstance(value, str) else None
    return parsed is None or parsed > now + dt.timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS)


def untrusted_clocks(raw: dict, now: dt.datetime) -> dict[str, list[str]]:
    """Private records whose stored clocks cannot order a publication (fifth review V01/V04).

    One such record, for example one written before the private future-time
    guard or by a worker merging against its own fast clock, must not hold the
    whole fleet's publication: the publisher keeps that record's last
    published version instead and reports it.
    """
    def bad(container, keys):
        return sorted(str(name) for name, record in (raw.get(container) or {}).items()
                      if isinstance(record, dict) and any(_untrusted_clock(record.get(key), now) for key in keys))
    return {"sources": sorted(set(bad("sources", _SOURCE_CLOCKS)) | set(bad("retired_sources", ("retired_at",)))),
            "workers": sorted(set(bad("workers", _WORKER_CLOCKS)) | set(bad("retired_workers", ("retired_at",))))}


def _quarantine(candidate: dict, current: dict, untrusted: dict[str, list[str]], now: dt.datetime) -> None:
    """Replace each untrusted record with its last published version, or drop it."""
    sections = {"sources": ("sources", "retired_sources"), "workers": ("workers", "retired_workers")}
    for kind, names in untrusted.items():
        clocks = _SOURCE_CLOCKS if kind == "sources" else _WORKER_CLOCKS
        for name in names:
            for section in sections[kind]:
                previous = (current.get(section) or {}).get(name)
                keys = clocks if section in ("sources", "workers") else ("retired_at",)
                if isinstance(previous, dict) and not any(_untrusted_clock(previous.get(key), now) for key in keys):
                    candidate.setdefault(section, {})[name] = deepcopy(previous)
                else:
                    (candidate.get(section) or {}).pop(name, None)


def _carry_published_measurements(candidate: dict, current: dict, now: dt.datetime) -> bool:
    """Keep a published measurement under a rebuilt candidate's zero-attempt deferral (V04)."""
    carried = False
    for name, record in (candidate.get("sources") or {}).items():
        previous = (current.get("sources") or {}).get(name)
        if (isinstance(previous, dict) and unmeasured_deferral(record)
                and _plausible_time(previous.get("checked_at"), now) is not None):
            candidate["sources"][name] = _carry_measurement(previous, record)
            carried = True
    return carried


def _retally(candidate: dict) -> None:
    """Totals and overall follow the sources after quarantine or carry, as aggregation derives them."""
    derived = _status_counts(candidate.get("sources") or {})
    for key in ("ok", "warn", "error"):
        if key in candidate.get("counts", {}):
            candidate["counts"][key] = derived[key]
    if candidate.get("overall") is not None:
        candidate["overall"] = _overall(derived)


def _snapshot_is_superseded(candidate: dict, current: dict, now: dt.datetime | None = None) -> bool:
    """Refuse rollback of known fleet, worker, or retained source observations.

    A destination time beyond the skew tolerance in the future is not evidence
    of a newer publication: it never blocks recovery (third review T02).
    """
    now = now or dt.datetime.now(dt.timezone.utc)

    def older(new, old):
        old_time, new_time = _plausible_time(old, now), _parse_time(new)
        return old_time is not None and (new_time is None or new_time < old_time)
    if older(candidate.get("generated_at"), current.get("generated_at")):
        return True
    for name, worker in (current.get("workers") or {}).items():
        incoming = (candidate.get("workers") or {}).get(name) or {}
        if not incoming:
            tombstone = (candidate.get('retired_workers') or {}).get(name) or {}
            # An implausibly future stored heartbeat is not evidence (fourth review Q03).
            seen = _plausible_time(worker.get('last_report_at') or worker.get('checked_at'), now)
            retired = _parse_time(tombstone.get('retired_at'))
            if retired is None or (seen is not None and retired <= seen):
                return True
            if any(source.get('worker') == name for source in (candidate.get('sources') or {}).values()):
                return True
            continue
        if older(incoming.get("last_report_at") or incoming.get("checked_at"),
                 worker.get("last_report_at") or worker.get("checked_at")):
            return True
    for name, retired in (current.get('retired_workers') or {}).items():
        incoming = (candidate.get('retired_workers') or {}).get(name) or {}
        if not incoming or name in (candidate.get('workers') or {}) or older(incoming.get('retired_at'), retired.get('retired_at')):
            return True
    for name, source in (current.get("sources") or {}).items():
        incoming = (candidate.get("sources") or {}).get(name)
        source_seen = source.get("last_report_at") or source.get("checked_at")
        if incoming is None:
            tombstone = (candidate.get("retired_sources") or {}).get(name)
            # A retirement must follow the newest retained time, including a
            # provider check made after the retiring report started (Q01).
            latest = _latest_time(source, now)
            if not isinstance(tombstone, dict) or older(tombstone.get("retired_at"),
                                                        latest.isoformat() if latest else None):
                return True
        elif _plausible_time(source.get("checked_at"), now) is not None and observation_rolls_back(incoming, source):
            # Ordered by provider observation, not worker report time (T01).
            return True
        elif _plausible_time(source.get("checked_at"), now) is None and older(
                incoming.get("last_report_at") or incoming.get("checked_at"), source_seen):
            return True
    for name, tombstone in (current.get("retired_sources") or {}).items():
        retired_at = tombstone.get("retired_at") if isinstance(tombstone, dict) else None
        incoming = (candidate.get("sources") or {}).get(name)
        incoming_tombstone = (candidate.get("retired_sources") or {}).get(name)
        if incoming is not None:
            # Reinstatement needs evidence after the retirement: the provider
            # check when the record carries one, as in aggregation (Q01).
            # A deferral without a check made no request: no evidence (V03).
            incoming_at = (incoming.get("checked_at") if _parse_time(incoming.get("checked_at"))
                           else None if incoming.get("deferred") else incoming.get("last_report_at"))
            if _plausible_time(retired_at, now) is not None and (
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
    watchdog_stream=None,
    log_stream=None,
) -> dict:
    """Read the unified aggregate, sanitize it, and publish only the public representation.

    With ``watchdog_stream`` set, the provider-run watchdog checks the private
    aggregate's worker report times first and logs overdue workers to it.
    Records whose stored clocks are unreadable or in the future keep their last
    published version; they are logged to ``log_stream`` (default: the
    watchdog stream, else standard error) and listed in the summary.
    """
    # Before any read or write: the destination must never be the private input.
    _refuse_alias(_identity(source, source_object), _identity(destination, destination_object))
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="watchtower-public-", dir=root) as scratch:
        scratch_root = Path(scratch)
        raw_path = scratch_root / "aggregate-source.json"
        public_path = scratch_root / "aggregate-public.json"

        if not source.download(source_object, raw_path):
            raise FileNotFoundError(f"source aggregate not found: {source_object}")

        raw = strict_json.loads(raw_path.read_text(encoding="utf-8"))
        # The watchdog never raises and runs first, so overdue workers still
        # alert when the aggregate itself is refused below (fourth review Q10).
        watchdog = run_provider_watchdog(raw, watchdog_stream) if watchdog_stream is not None else None
        # Before projection: projecting creates empty containers, so a malformed
        # private aggregate would otherwise publish as a healthy empty fleet.
        validate_private_aggregate(raw)
        sanitized = sanitize_public_render_state(raw)
        validate_public_state(sanitized)
        # The same contract the public reader applies: a snapshot it would
        # reject must never replace the last accepted publication.
        validate_snapshot_structure(sanitized)
        now = dt.datetime.now(dt.timezone.utc)
        # A future fleet time is a whole-fleet clock error: refuse it. Per-record
        # clock errors are quarantined below instead (fifth review V01).
        validate_ordering_clocks({"generated_at": sanitized.get("generated_at")}, now)
        untrusted = untrusted_clocks(raw, now)
        quarantined = {kind: names for kind, names in untrusted.items() if names}
        if quarantined:
            stream = log_stream if log_stream is not None else (
                watchdog_stream if watchdog_stream is not None else sys.stderr)
            _emit(stream, {"severity": "ERROR", QUARANTINE_LOG_KEY: quarantined})
        public = sanitized
        current_path = scratch_root / "destination.json"
        published = False
        for attempt in range(8):
            try:
                exists, version = destination.download_versioned(destination_object, current_path)
                current = strict_json.loads(current_path.read_text(encoding="utf-8")) if exists else {}
                public = deepcopy(sanitized)
                _quarantine(public, current, untrusted, now)
                if _carry_published_measurements(public, current, now) or quarantined:
                    _retally(public)
                validate_snapshot_structure(public)
                validate_ordering_clocks(public, now)
                if _snapshot_is_superseded(public, current):
                    public = current
                    break
                public["public_published_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                # Keep the publication clock monotonic when hosts have clock skew,
                # but never carry forward a previous time implausibly far in the
                # future: it would mask missed publications (audit WT31-07).
                previous_time = _parse_time(current.get("public_published_at"))
                now_time = _parse_time(public["public_published_at"])
                if (previous_time and previous_time > now_time
                        and (previous_time - now_time).total_seconds() <= CLOCK_SKEW_TOLERANCE_SECONDS):
                    public["public_published_at"] = current["public_published_at"]
                public_path.write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                destination.upload_if_version(destination_object, public_path, version)
                published = True
                break
            except StorageConflictError:
                if attempt == 7:
                    raise

        summary = {
            "published": published,
            "reason": "published" if published else "superseded",
            "public_published_at": public.get("public_published_at"),
            "generated_at": public.get("generated_at"),
            "overall": public.get("overall"),
            "source_count": len(public.get("sources") or {}),
            "worker_count": len(public.get("workers") or {}),
            "destination_object": destination_object,
        }
        if watchdog is not None:
            summary["provider_watchdog"] = watchdog
        if quarantined:
            summary["clock_quarantine"] = quarantined
        return summary


def publish_public_snapshot_from_env() -> dict:
    """Publish with two GCS clients sharing this process's application default credentials.

    Distinct service identities are a deployment configuration responsibility.
    """
    source_bucket = _required_env("WATCHTOWER_PUBLIC_SOURCE_BUCKET")
    source_prefix = os.environ.get("WATCHTOWER_PUBLIC_SOURCE_PREFIX", "").strip("/")
    destination_bucket = _required_env("WATCHTOWER_PUBLIC_DEST_BUCKET")
    destination_prefix = os.environ.get("WATCHTOWER_PUBLIC_DEST_PREFIX", "").strip("/")
    source_object = os.environ.get("WATCHTOWER_PUBLIC_SOURCE_OBJECT", "aggregate-state.json")
    destination_object = os.environ.get("WATCHTOWER_PUBLIC_DEST_OBJECT", "aggregate-state.json")
    # Refuse an ambiguous configuration before constructing either client.
    _refuse_alias(gcs_object_identity(source_bucket, source_prefix, source_object),
                  gcs_object_identity(destination_bucket, destination_prefix, destination_object))
    source = GCSStorage(source_bucket, source_prefix)
    destination = GCSStorage(destination_bucket, destination_prefix)
    return publish_public_snapshot(
        source,
        destination,
        source_object=source_object,
        destination_object=destination_object,
        workdir=os.environ.get("WATCHTOWER_PUBLIC_PUBLISH_WORKDIR", "/tmp/watchtower-public-publish"),
        watchdog_stream=None if os.environ.get("WATCHTOWER_PROVIDER_WATCHDOG", "1").strip() == "0" else sys.stderr,
    )
