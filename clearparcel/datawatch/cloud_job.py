from __future__ import annotations

import os
from pathlib import Path

from .aggregate import publish_partial
from .storage import StorageConflictError, backend_from_env
from .watch import check_sources, load_config


ARTIFACTS = {
    "state_file": "state.json",
    "history_file": "history.jsonl",
    "alerts_file": "alerts.json",
    "alerts_text_file": "alerts.txt",
}
HISTORY_ARCHIVE = "history.jsonl.1"


def publish_worker_result(config: dict, result: dict, profile: str, *, workdir: Path | None = None) -> dict | None:
    """Publish a worker report when a shared aggregate object is configured."""
    aggregate_name = os.environ.get("WATCHTOWER_AGGREGATE_OBJECT") or config.get("aggregate_object")
    if not aggregate_name:
        return None
    root = config.get("_root_dir") or Path(config.get("state_file", ".")).parent
    storage = backend_from_env(root)
    workdir = workdir or Path(os.environ.get("WATCHTOWER_WORKDIR") or root)
    return publish_partial(storage, str(aggregate_name), result, profile, Path(workdir))


def run_cloud_job(config_path: str | Path) -> dict:
    config = load_config(config_path)
    workdir = Path(os.environ.get("WATCHTOWER_WORKDIR", "/tmp/watchtower")).expanduser()
    workdir.mkdir(parents=True, exist_ok=True)
    storage = backend_from_env(config.get("_root_dir") or Path(config_path).parent.parent)

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

    profile = os.environ.get("WATCHTOWER_EXECUTION_PROFILE", "cloud")
    result = check_sources(config, save=True, execution_profile=profile)

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
