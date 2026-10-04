from __future__ import annotations

import os
from pathlib import Path

from .aggregate import publish_partial
from .storage import backend_from_env
from .watch import check_sources, load_config


ARTIFACTS = {
    "state_file": "state.json",
    "history_file": "history.jsonl",
    "alerts_file": "alerts.json",
    "alerts_text_file": "alerts.txt",
}


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

    for key, object_name in ARTIFACTS.items():
        if key not in config:
            continue
        local = workdir / object_name
        storage.download(object_name, local)
        config[key] = str(local)

    profile = os.environ.get("WATCHTOWER_EXECUTION_PROFILE", "cloud")
    result = check_sources(config, save=True, execution_profile=profile)
    publish_worker_result(config, result, profile, workdir=workdir)

    for key, object_name in ARTIFACTS.items():
        path = config.get(key)
        if path and Path(path).is_file():
            storage.upload(object_name, Path(path))
    return result
