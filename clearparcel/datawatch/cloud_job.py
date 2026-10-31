from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import urllib.parse
from pathlib import Path

from .aggregate import publish_partial
from .storage import StorageConflictError, backend_from_env
from . import strict_json
from .watch import (
    _EXECUTION_PROFILES,
    _active_rate_limits,
    _resolve_execution_profile,
    _validated_state,
    check_sources,
    load_config,
    load_state,
    validate_source_registry,
)


ARTIFACTS = {
    "state_file": "state.json",
    "history_file": "history.jsonl",
    "alerts_file": "alerts.json",
    "alerts_text_file": "alerts.txt",
}
HISTORY_ARCHIVE = "history.jsonl.1"
# Per-host provider 429 backoffs, written (version-conditional) the moment a
# 429 arrives, so a container killed before its state upload still leaves the
# embargo behind (audit WT31-02). Private: it lives beside state.json.
RATE_LIMIT_EMBARGO = "rate-limit-embargo.json"
_EMBARGO_ATTEMPTS = 8
# RFC 2606 / 6761 names used only by placeholder configurations.
_PLACEHOLDER_DOMAINS = ("example.com", "example.org", "example.net", "example", "invalid", "test", "localhost")


def is_placeholder_config(config: dict) -> bool:
    """True when every configured source points at a reserved example host."""
    sources = config.get("sources") or []
    if not sources:
        return False
    for source in sources:
        try:
            host = (urllib.parse.urlparse(str(source.get("url") or "")).hostname or "").rstrip(".").lower()
        except ValueError:
            return False
        if not any(host == d or host.endswith("." + d) for d in _PLACEHOLDER_DOMAINS):
            return False
    return True


def _aggregate_object(config: dict) -> str | None:
    return os.environ.get("WATCHTOWER_AGGREGATE_OBJECT") or config.get("aggregate_object")


def require_publishable_profile(config: dict, profile: str | None) -> None:
    """Refuse, before any provider request, a worker name the shared aggregate cannot carry."""
    if _aggregate_object(config) and profile not in _EXECUTION_PROFILES:
        raise ValueError(f"only {' or '.join(sorted(_EXECUTION_PROFILES))} workers publish to the shared "
                         f"aggregate; got execution profile {profile!r}")


def publish_worker_result(config: dict, result: dict, profile: str, *, workdir: Path | None = None) -> dict | None:
    """Publish a worker report when a shared aggregate object is configured."""
    aggregate_name = _aggregate_object(config)
    if not aggregate_name:
        return None
    require_publishable_profile(config, profile)
    scope_type = (result.get("scope") or {}).get("type")
    explicit_drain = scope_type == "fleet" and result.get("allow_inventory_shrink") is True
    if scope_type == "empty" or (not result.get("sources") and not explicit_drain):
        return None  # Never publish a report that checked nothing (an explicit drain excepted).
    root = config.get("_root_dir") or Path(config.get("state_file", ".")).parent
    storage = backend_from_env(root)
    workdir = workdir or Path(os.environ.get("WATCHTOWER_WORKDIR") or root)
    return publish_partial(storage, str(aggregate_name), result, profile, Path(workdir))


def _file_digest(path: Path | None) -> str | None:
    import hashlib
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path is not None and path.is_file() else None
    except OSError:
        return None


def _upload_backoff_checkpoint(storage, state_path: Path | None, downloaded: str | None, versions: dict) -> bool:
    """Upload a changed local state after a failed run; never mask the original failure."""
    if state_path is None or _file_digest(state_path) in (None, downloaded):
        return False
    try:
        storage.upload_if_version(ARTIFACTS["state_file"], state_path, versions.get(ARTIFACTS["state_file"]))
    except Exception:  # noqa: BLE001 - a conflict means another writer advanced state
        return False
    return True


def _merge_backoffs(*sources: dict) -> dict:
    """Combine per-host backoffs; the longer (or operator-held) embargo wins."""
    merged: dict = {}
    for backoffs in sources:
        for host, entry in (backoffs or {}).items():
            current = merged.get(host)
            if current is None:
                merged[host] = dict(entry)
                continue
            if current.get("hold_until_cleared") is True:
                continue
            if entry.get("hold_until_cleared") is True or str(entry.get("not_before")) > str(current.get("not_before")):
                merged[host] = dict(entry)
    return merged


def _read_embargo(storage, local: Path) -> tuple[dict, str | int | None]:
    """The active shared embargo and its version. An unreadable embargo fails closed."""
    exists, version = storage.download_versioned(RATE_LIMIT_EMBARGO, local)
    if not exists:
        return {}, version
    try:
        value = strict_json.loads(local.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("rate_limits"), dict):
            raise ValueError("rate_limits must be an object")
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"{RATE_LIMIT_EMBARGO} is unreadable; refusing to poll providers "
                           "until an operator repairs it") from exc
    return _active_rate_limits(value["rate_limits"], dt.datetime.now(dt.timezone.utc)), version


def _embargo_sink(storage, workdir: Path):
    """Persist each 429 backoff to the shared embargo object immediately."""
    local = workdir / RATE_LIMIT_EMBARGO

    def sink(rate_limits: dict) -> None:
        for _attempt in range(_EMBARGO_ATTEMPTS):
            current, version = _read_embargo(storage, local)
            merged = _merge_backoffs(current, rate_limits)
            local.write_text(json.dumps({"schema_version": 1, "rate_limits": merged}, indent=2,
                                        allow_nan=False) + "\n", encoding="utf-8")
            try:
                storage.upload_if_version(RATE_LIMIT_EMBARGO, local, version)
                return
            except StorageConflictError:
                continue
        raise StorageConflictError(f"{RATE_LIMIT_EMBARGO} kept changing; backoff not persisted")

    return sink


def _apply_embargo(storage, state_path: Path | None, workdir: Path) -> None:
    """Fold the shared embargo into the downloaded local state before any request."""
    embargo, _version = _read_embargo(storage, workdir / RATE_LIMIT_EMBARGO)
    if not embargo or state_path is None:
        return
    state = load_state(state_path) if state_path.is_file() else {"schema_version": 1, "sources": {}}
    state = _validated_state(state)
    state["rate_limits"] = _merge_backoffs(state.get("rate_limits") or {}, embargo)
    state.pop("_state_recovered_from_backup", None)
    state_path.write_text(json.dumps(state, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def job_storage(config: dict, config_path: str | Path):
    """The storage backend a cloud job reads and writes (shared with run evidence)."""
    return backend_from_env(config.get("_root_dir") or Path(config_path).parent.parent)


def job_profile() -> str | None:
    """The worker profile a cloud job runs as."""
    return _resolve_execution_profile(os.environ.get("WATCHTOWER_EXECUTION_PROFILE") or "cloud")


def preflight_cloud_job(config: dict) -> None:
    """The cloud job's own refusals, checked before any provider-run slot is claimed."""
    if is_placeholder_config(config) and os.environ.get("WATCHTOWER_ALLOW_EXAMPLE_CONFIG") != "1":
        # Fail closed: the container default points at the repository example.
        raise RuntimeError("cloud-job refuses the placeholder example configuration; pass --config with the "
                           "deployment registry (or set WATCHTOWER_ALLOW_EXAMPLE_CONFIG=1 for a synthetic test)")
    require_publishable_profile(config, job_profile())
    validate_source_registry(config.get("sources", []))


def run_cloud_job(config_path: str | Path) -> dict:
    configured = os.environ.get("WATCHTOWER_WORKDIR")
    if configured:
        return _run_cloud_job(config_path, Path(configured).expanduser())
    # A private per-run directory: concurrent or leftover runs never share downloaded state.
    with tempfile.TemporaryDirectory(prefix="watchtower-job-") as scratch:
        return _run_cloud_job(config_path, Path(scratch))


def _run_cloud_job(config_path: str | Path, workdir: Path) -> dict:
    config = load_config(config_path)
    preflight_cloud_job(config)
    workdir.mkdir(parents=True, exist_ok=True)
    storage = job_storage(config, config_path)

    versions = {}
    for key, object_name in ARTIFACTS.items():
        if key not in config:
            continue
        local = workdir / object_name
        exists, version = storage.download_versioned(object_name, local)
        versions[object_name] = version
        if not exists:
            try:
                local.unlink()
            except FileNotFoundError:
                pass
        config[key] = str(local)

    # Rotation is performed against the sibling history.jsonl.1 file. Preserve
    # that object across ephemeral cloud workers with its own version precondition.
    history_path = Path(config.get("history_file", workdir / ARTIFACTS["history_file"]))
    archive_path = history_path.with_suffix(history_path.suffix + ".1")
    archive_exists, archive_version = storage.download_versioned(HISTORY_ARCHIVE, archive_path)
    versions[HISTORY_ARCHIVE] = archive_version
    if not archive_exists:
        try:
            archive_path.unlink()
        except FileNotFoundError:
            pass

    profile = job_profile()
    require_publishable_profile(config, profile)
    state_path = Path(config["state_file"]) if config.get("state_file") else None
    # A backoff another (possibly killed) job recorded applies to this run too.
    _apply_embargo(storage, state_path, workdir)
    downloaded_state = _file_digest(state_path)
    try:
        result = check_sources(config, save=True, execution_profile=profile,
                               rate_limit_sink=_embargo_sink(storage, workdir))
    except BaseException:
        # A provider 429 is checkpointed into local state as soon as it is
        # signaled. If the run then fails, upload that checkpoint (version-
        # conditional) so the next job still honors the backoff.
        _upload_backoff_checkpoint(storage, state_path, downloaded_state, versions)
        raise
    if (result.get("scope") or {}).get("type") == "empty":
        # Nothing was checked: upload nothing and publish nothing (exit 2).
        return result

    # All read/modify/write artifacts use the version captured with the exact
    # downloaded snapshot. Publish state last so a conflict cannot make a stale
    # state object look authoritative after another writer has advanced it.
    upload_order = ("history_file", "alerts_file", "alerts_text_file", "state_file")
    if archive_path.is_file():
        try:
            storage.upload_if_version(HISTORY_ARCHIVE, archive_path, versions.get(HISTORY_ARCHIVE))
        except StorageConflictError as exc:
            raise StorageConflictError(
                f"concurrent update detected for {HISTORY_ARCHIVE}; stale cloud-job output was not uploaded"
            ) from exc
    for key in upload_order:
        object_name = ARTIFACTS[key]
        path = config.get(key)
        if not path or not Path(path).is_file():
            continue
        try:
            storage.upload_if_version(object_name, Path(path), versions.get(object_name))
        except StorageConflictError as exc:
            raise StorageConflictError(
                f"concurrent update detected for {object_name}; stale cloud-job output was not uploaded"
            ) from exc

    # Publish the shared worker aggregate only after the worker's own state/history
    # artifacts have committed successfully. A stale artifact conflict therefore
    # cannot advertise a worker result that failed its persistence gate.
    publish_worker_result(config, result, profile, workdir=workdir)
    return result
