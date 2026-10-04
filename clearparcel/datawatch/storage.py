from __future__ import annotations

import abc
import os
from pathlib import Path


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def download(self, name: str, destination: Path) -> bool:
        """Copy an object to destination. Return False when it does not exist."""

    @abc.abstractmethod
    def upload(self, name: str, source: Path) -> None:
        """Upload source to the named object."""


class LocalStorage(StorageBackend):
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def download(self, name: str, destination: Path) -> bool:
        source = self.root / name
        if not source.is_file():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        return True

    def upload(self, name: str, source: Path) -> None:
        destination = self.root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        tmp.write_bytes(source.read_bytes())
        tmp.replace(destination)


class GCSStorage(StorageBackend):
    def __init__(self, bucket: str, prefix: str = ""):
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise RuntimeError("GCS storage requires the optional 'gcs' dependency: pip install 'clearparcel-gis-data-watchtower[gcs]'") from exc
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket)
        self.prefix = prefix.strip("/")

    def _name(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    def download(self, name: str, destination: Path) -> bool:
        blob = self.bucket.blob(self._name(name))
        if not blob.exists(self.client):
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(destination))
        return True

    def upload(self, name: str, source: Path) -> None:
        blob = self.bucket.blob(self._name(name))
        blob.upload_from_filename(str(source), if_generation_match=None)


def backend_from_env(default_root: str | Path) -> StorageBackend:
    kind = os.environ.get("WATCHTOWER_STORAGE", "local").strip().lower()
    if kind == "local":
        return LocalStorage(os.environ.get("WATCHTOWER_STORAGE_ROOT") or default_root)
    if kind == "gcs":
        bucket = os.environ.get("WATCHTOWER_GCS_BUCKET")
        if not bucket:
            raise RuntimeError("WATCHTOWER_GCS_BUCKET is required when WATCHTOWER_STORAGE=gcs")
        return GCSStorage(bucket, os.environ.get("WATCHTOWER_GCS_PREFIX", ""))
    raise RuntimeError(f"unsupported WATCHTOWER_STORAGE backend: {kind}")
