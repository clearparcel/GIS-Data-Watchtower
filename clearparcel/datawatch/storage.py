from __future__ import annotations

import abc
import hashlib
import os
import random
import time
from pathlib import Path

from .file_lock import FileLock, _retry_sharing, atomic_write


class StorageConflictError(RuntimeError):
    """The stored object changed after a worker read it."""


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def download(self, name: str, destination: Path) -> bool:
        """Copy an object to destination. Return False when it does not exist."""

    # There is deliberately no unconditional upload: every shared write goes
    # through upload_if_version so concurrent workers cannot overwrite each other.

    def download_versioned(self, name: str, destination: Path) -> tuple[bool, str | int | None]:
        exists = self.download(name, destination)
        token = hashlib.sha256(destination.read_bytes()).hexdigest() if exists else None
        return exists, token

    def upload_if_version(self, name: str, source: Path, version: str | int | None) -> None:
        raise NotImplementedError("storage backend must implement atomic version-conditional uploads")


class LocalStorage(StorageBackend):
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def _path(self, name: str) -> Path:
        """Map a GCS-style object key to a file that stays under ``root``.

        Keys are relative, ``/``-separated names. Absolute, drive-qualified,
        UNC, backslash, empty-segment and ``.``/``..`` keys are rejected before
        any filesystem access. The resolved path must still lie under the root,
        so a symlink or junction inside the store that points elsewhere is
        refused too. Only the parent directory is resolved: on Windows,
        resolving a file that another writer is atomically replacing can
        briefly yield a path outside the root.
        """
        if (not isinstance(name, str) or not name or "\x00" in name or "\\" in name
                or ":" in name or name.startswith("/")
                or any(part in ("", ".", "..") for part in name.split("/"))):
            raise ValueError(f"invalid local storage object name: {name!r}")
        candidate = self.root / name
        parent = candidate.parent.resolve()
        if not parent.is_relative_to(self.root) or candidate.is_symlink() or candidate.is_junction():
            raise ValueError(f"local storage object name escapes the storage root: {name!r}")
        return parent / candidate.name

    @staticmethod
    def _read_shared(path: Path) -> bytes:
        """Read bytes, retrying a Windows sharing violation during atomic replace."""
        return _retry_sharing(path.read_bytes, timeout=5.0)

    @staticmethod
    def _token(path: Path) -> str | None:
        return hashlib.sha256(LocalStorage._read_shared(path)).hexdigest() if path.is_file() else None

    def download(self, name: str, destination: Path) -> bool:
        source = self._path(name)
        if not source.is_file():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._read_shared(source))
        return True

    def download_versioned(self, name: str, destination: Path) -> tuple[bool, str | None]:
        source = self._path(name)
        if not source.is_file():
            return False, None
        # Read one immutable byte snapshot and derive the token from exactly the
        # bytes copied to the worker. Writers use atomic replacement, so this
        # binds the compare-and-swap token to the snapshot the caller consumed.
        raw = self._read_shared(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        return True, hashlib.sha256(raw).hexdigest()

    def upload_if_version(self, name: str, source: Path, version: str | int | None) -> None:
        destination = self._path(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(destination.with_suffix(destination.suffix + ".lock"), timeout=10):
            if self._token(destination) != version:
                raise StorageConflictError(f"object changed while updating: {name}")
            atomic_write(destination, source.read_bytes())


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
        destination.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
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
            generation = int(blob.generation)
            try:
                # Bind downloaded bytes to the generation token. If the object
                # changes after reload(), GCS rejects this read instead of
                # returning bytes from a different generation with a stale token.
                blob.download_to_filename(str(destination), if_generation_match=generation)
                return True, generation
            except Exception as exc:
                try:
                    from google.api_core.exceptions import NotFound, PreconditionFailed
                    if isinstance(exc, NotFound):
                        raise StorageConflictError(f"object changed while reading: {name}") from exc
                    if isinstance(exc, PreconditionFailed):
                        if attempt < 2:
                            # Another writer is mid-update: back off briefly before re-reading.
                            time.sleep(0.25 * (2 ** attempt) + random.uniform(0, 0.25))
                            continue
                        raise StorageConflictError(f"object changed while reading: {name}") from exc
                except ImportError:
                    pass
                raise
        raise StorageConflictError(f"object changed repeatedly while reading: {name}")

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
