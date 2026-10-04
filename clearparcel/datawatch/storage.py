from __future__ import annotations

import abc
import hashlib
import os
import random
import time
from pathlib import Path


class StorageConflictError(RuntimeError):
    """The stored object changed after a worker read it."""


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def download(self, name: str, destination: Path) -> bool:
        """Copy an object to destination. Return False when it does not exist."""

    @abc.abstractmethod
    def upload(self, name: str, source: Path) -> None:
        """Upload source to the named object."""

    def download_versioned(self, name: str, destination: Path) -> tuple[bool, str | int | None]:
        exists = self.download(name, destination)
        token = hashlib.sha256(destination.read_bytes()).hexdigest() if exists else None
        return exists, token

    def upload_if_version(self, name: str, source: Path, version: str | int | None) -> None:
        self.upload(name, source)


class LocalStorage(StorageBackend):
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def _path(self, name: str) -> Path:
        return self.root / name

    @staticmethod
    def _token(path: Path) -> str | None:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

    def download(self, name: str, destination: Path) -> bool:
        source = self._path(name)
        if not source.is_file():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        return True

    def download_versioned(self, name: str, destination: Path) -> tuple[bool, str | None]:
        exists = self.download(name, destination)
        return exists, self._token(self._path(name))

    def upload(self, name: str, source: Path) -> None:
        destination = self._path(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        tmp.write_bytes(source.read_bytes())
        tmp.replace(destination)

    def upload_if_version(self, name: str, source: Path, version: str | int | None) -> None:
        destination = self._path(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        lock = destination.with_suffix(destination.suffix + ".lock")
        deadline = time.monotonic() + 10
        while True:
            try:
                lock.mkdir()
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for aggregate lock: {lock}")
                time.sleep(0.02 + random.random() * 0.03)
        try:
            if self._token(destination) != version:
                raise StorageConflictError(f"object changed while updating: {name}")
            tmp = destination.with_suffix(destination.suffix + f".{os.getpid()}.tmp")
            tmp.write_bytes(source.read_bytes())
            tmp.replace(destination)
        finally:
            lock.rmdir()


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
        exists, _ = self.download_versioned(name, destination)
        return exists

    def download_versioned(self, name: str, destination: Path) -> tuple[bool, int | None]:
        blob = self.bucket.blob(self._name(name))
        try:
            blob.reload(client=self.client)
        except Exception as exc:
            try:
                from google.api_core.exceptions import NotFound
                if isinstance(exc, NotFound):
                    return False, None
            except ImportError:
                pass
            raise
        destination.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(destination))
        return True, int(blob.generation)

    def upload(self, name: str, source: Path) -> None:
        self.bucket.blob(self._name(name)).upload_from_filename(str(source))

    def upload_if_version(self, name: str, source: Path, version: str | int | None) -> None:
        blob = self.bucket.blob(self._name(name))
        generation = 0 if version is None else int(version)
        try:
            blob.upload_from_filename(str(source), if_generation_match=generation)
        except Exception as exc:
            try:
                from google.api_core.exceptions import PreconditionFailed
                if isinstance(exc, PreconditionFailed):
                    raise StorageConflictError(f"object changed while updating: {name}") from exc
            except ImportError:
                pass
            raise


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
