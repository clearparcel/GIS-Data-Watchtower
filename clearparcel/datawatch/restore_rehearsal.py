"""Synthetic local aggregate restore/CAS rehearsal; no deployment configuration."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import threading

from . import aggregate, file_lock, storage, strict_json
from .storage import LocalStorage, StorageConflictError


OBJECT = "aggregate.json"
STAMP = "2026-01-01T00:00:00+00:00"


class RehearsalFailure(RuntimeError):
    """An observed restore or publishing invariant did not hold."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RehearsalFailure(message)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _report(worker: str, minute: int, status: str = "ok") -> dict:
    stamp = f"2026-01-01T00:{minute:02d}:00+00:00"
    return {
        "generated_at": stamp, "overall": status, "scope": {"type": "fleet"},
        "counts": {key: int(key == status) for key in ("ok", "warn", "error")},
        "sources": {f"synthetic-{worker}": {
            "id": f"synthetic-{worker}", "status": status, "checked_at": stamp,
            "feature_count": 0 if worker == "cloud" else 7,
        }},
    }


def _restore_empty(backend: LocalStorage, raw: bytes, expected_hash: str, scratch: Path) -> None:
    """Internal fixture restore: validate before a create-only conditional upload."""
    if _digest(raw) != expected_hash:
        raise ValueError("backup digest mismatch")
    document = strict_json.loads(raw.decode("utf-8"))
    if not isinstance(document, dict) or not document.get("sources") or not document.get("workers"):
        raise ValueError("backup is not a populated aggregate fixture")
    scratch.write_bytes(raw)
    backend.upload_if_version(OBJECT, scratch, None)


class _RacingLocalStorage(LocalStorage):
    """Only synchronize first reads; production storage implements all writes."""

    def __init__(self, root: Path, barrier: threading.Barrier):
        super().__init__(root)
        self.barrier = barrier
        self.first_read = True
        self.conflicts = 0

    def download_versioned(self, name: str, destination: Path):
        result = super().download_versioned(name, destination)
        if self.first_read:
            self.first_read = False
            self.barrier.wait(timeout=10)
        return result

    def upload_if_version(self, name: str, source: Path, version) -> None:
        try:
            super().upload_if_version(name, source, version)
        except StorageConflictError:
            self.conflicts += 1
            raise


def run_rehearsal() -> dict:
    """Exercise real local storage and aggregate publishing in owned temp storage."""
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    checks: list[str] = []
    # Never consult backend_from_env, source registries, credentials or cloud APIs.
    with tempfile.TemporaryDirectory(prefix="watchtower-restore-rehearsal-") as temporary:
        root = Path(temporary)
        original = LocalStorage(root / "original")
        restored = LocalStorage(root / "restored")
        workdir = root / "work"
        aggregate.publish_partial(original, OBJECT, _report("cloud", 0), "cloud", workdir)
        aggregate.publish_partial(original, OBJECT, _report("local", 0), "local", workdir)
        # Keep a source retirement tombstone in the captured fixture.
        downloaded = root / "captured.json"
        exists, version = original.download_versioned(OBJECT, downloaded)
        _require(exists, "original aggregate missing")
        fixture = json.loads(downloaded.read_text(encoding="utf-8"))
        fixture["retired_sources"] = {"synthetic-retired": {"worker": "cloud", "retired_at": STAMP}}
        aggregate.save_json(downloaded, fixture)
        original.upload_if_version(OBJECT, downloaded, version)
        exists, captured_version = original.download_versioned(OBJECT, downloaded)
        _require(exists, "capture failed")
        backup = downloaded.read_bytes()
        backup_hash = _digest(backup)
        _require(captured_version == backup_hash, "snapshot bytes do not match local version token")
        checks.append("capture_version_matches_bytes")

        try:
            _restore_empty(restored, backup + b" ", backup_hash, root / "corrupt.json")
        except ValueError:
            pass
        else:
            raise RehearsalFailure("corrupt backup accepted")
        _require(not (restored.root / OBJECT).exists(), "corrupt backup wrote destination")
        checks.append("corrupt_backup_rejected_without_write")

        _restore_empty(restored, backup, backup_hash, root / "restore.json")
        readback = root / "readback.json"
        exists, restored_version = restored.download_versioned(OBJECT, readback)
        _require(exists and readback.read_bytes() == backup and restored_version == backup_hash,
                 "restored bytes differ from backup")
        _require(json.loads(readback.read_bytes()) == fixture, "restored aggregate differs")
        checks.append("empty_destination_restore_exact")

        try:
            _restore_empty(restored, backup, backup_hash, root / "second-restore.json")
        except StorageConflictError:
            pass
        else:
            raise RehearsalFailure("restore overwrote occupied destination")
        _require((restored.root / OBJECT).read_bytes() == backup, "occupied destination changed")
        checks.append("occupied_destination_restore_refused")

        # Establish a newer writer, then try the captured restore token.
        aggregate.publish_partial(restored, OBJECT, _report("cloud", 1, "error"), "cloud", workdir)
        newer = (restored.root / OBJECT).read_bytes()
        try:
            restored.upload_if_version(OBJECT, downloaded, restored_version)
        except StorageConflictError:
            pass
        else:
            raise RehearsalFailure("stale restore token overwrote a newer writer")
        _require((restored.root / OBJECT).read_bytes() == newer, "newer writer lost")
        checks.append("stale_restore_refused_newer_writer_preserved")

        # Both publishers read the same base before either may upload. Each uses
        # an independent backend instance, as real writers do. One must conflict
        # and the production publish_partial retry must reload/merge both reports.
        barrier = threading.Barrier(2)
        racers = [_RacingLocalStorage(restored.root, barrier) for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(aggregate.publish_partial, racers[0], OBJECT,
                            _report("cloud", 2, "error"), "cloud", workdir),
                pool.submit(aggregate.publish_partial, racers[1], OBJECT,
                            _report("local", 3, "warn"), "local", workdir),
            ]
            for future in futures:
                future.result(timeout=30)
        conflict_count = sum(racer.conflicts for racer in racers)
        _require(conflict_count == 1, "expected one real CAS conflict")
        final_raw = (restored.root / OBJECT).read_bytes()
        final = json.loads(final_raw)
        expected = aggregate.merge_states(
            aggregate.merge_states(json.loads(newer), _report("cloud", 2, "error"), "cloud"),
            _report("local", 3, "warn"), "local")
        _require(final == expected, "concurrent publish lost data or metadata")
        checks.append("concurrent_publish_retry_preserves_both_workers")
        _require(final["sources"]["synthetic-cloud"]["last_success_at"] == STAMP,
                 "failed check erased previous success")
        _require(final["sources"]["synthetic-cloud"]["checked_at"] == _report("cloud", 2)["generated_at"],
                 "source check time changed")
        _require(final["sources"]["synthetic-local"]["last_available_at"] == _report("local", 3)["generated_at"],
                 "availability time changed")
        _require(final["retired_sources"] == fixture["retired_sources"], "tombstones lost")
        checks.append("provenance_observation_clocks_and_tombstones_preserved")

        aggregate.publish_partial(restored, OBJECT, _report("cloud", 0), "cloud", workdir)
        _require((restored.root / OBJECT).read_bytes() == final_raw, "old worker report changed aggregate")
        checks.append("delayed_report_cannot_regress_restored_state")
        _require((original.root / OBJECT).read_bytes() == backup, "backup origin changed")
        _require(downloaded.read_bytes() == backup, "captured backup changed")
        _require(not list(workdir.iterdir()), "aggregate scratch leaked")
        checks.append("origin_backup_and_scratch_preserved")
        final_hash = _digest(final_raw)
    # Completion is recorded only after the temporary directory exits cleanly.
    return {
        "schema_version": 1, "result": "passed", "synthetic": True,
        "backend": "local", "started_at": started,
        "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "checks_passed": checks, "observed_cas_conflicts": conflict_count,
        "backup_sha256": backup_hash, "final_aggregate_sha256": final_hash,
        "implementation_sha256": {
            Path(module.__file__).name: _digest(Path(module.__file__).read_bytes())
            for module in (aggregate, storage, file_lock)
        } | {Path(__file__).name: _digest(Path(__file__).read_bytes())},
        "temporary_storage_removed": True,
        "production_restore_verified": False, "gcs_verified": False,
        "activation_authorized": False,
    }
