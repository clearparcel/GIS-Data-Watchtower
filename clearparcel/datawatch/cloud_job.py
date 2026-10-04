from __future__ import annotations

import os
from pathlib import Path

from .storage import backend_from_env
from .watch import check_sources, load_config


ARTIFACTS = {
    "state_file": "state.json",
    "history_file": "history.jsonl",
    "alerts_file": "alerts.json",
    "alerts_text_file": "alerts.txt",
}


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

    result = check_sources(config, save=True)

    for key, object_name in ARTIFACTS.items():
        path = config.get(key)
        if path and Path(path).is_file():
            storage.upload(object_name, Path(path))
    return result
