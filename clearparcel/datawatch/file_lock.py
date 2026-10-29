"""Process-owned file locks and atomic local replacements, without extra dependencies."""
from __future__ import annotations

import errno
import os
import stat
import tempfile
import time
from pathlib import Path


def _sharing_violation(exc: BaseException) -> bool:
    """Windows denies access while another handle still has the file open.

    ``os.replace`` and ``open`` then raise ``PermissionError`` with errno 13
    (WinError 5 access denied, or 32/33 sharing or lock violation). That is
    transient contention, not a missing directory permission: the caller has
    already created a file in the same directory.
    """
    if not isinstance(exc, OSError):
        return False
    winerror = getattr(exc, "winerror", None)
    if winerror in (5, 32, 33):
        return True
    return os.name == "nt" and exc.errno in (errno.EACCES, errno.EAGAIN, errno.EPERM)


def _retry_sharing(operation, *, timeout: float):
    """Retry ``operation`` while Windows reports a sharing violation."""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            return operation()
        except OSError as exc:
            if not _sharing_violation(exc):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.02, remaining))


class FileLock:
    """A persistent lock file whose OS lock is released on process termination.

    Never unlink the lock file: a successor must lock the same inode/byte as
    existing holders. A legacy lock directory requires operator reconciliation.
    """
    def __init__(self, path: Path, *, timeout: float = 0) -> None:
        self.path = path
        self.timeout = timeout
        self._file = None

    def acquire(self) -> FileLock:
        if self._file is not None:
            raise RuntimeError("file lock is already acquired")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_dir():
            raise RuntimeError("legacy lock directory requires stopped-worker reconciliation: " + str(self.path))
        deadline = time.monotonic() + self.timeout
        while True:
            stream = None
            try:
                try:
                    stream = self.path.open("a+b")
                except OSError as exc:
                    # Opening the lock file can itself be denied on Windows
                    # while another handle is replacing or locking it.
                    if not _sharing_violation(exc):
                        raise
                    raise _LockContended(exc) from exc
                try:
                    if os.fstat(stream.fileno()).st_size == 0:
                        stream.write(b"\0")
                        stream.flush()
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    stream.close()
                    stream = None
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) and not _sharing_violation(exc):
                        raise
                    raise _LockContended(exc) from exc
                self._file = stream
                return self
            except _LockContended as contended:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"timed out waiting for file lock: {self.path}") from contended.__cause__
                time.sleep(min(0.025, remaining))
            except BaseException:
                if stream is not None and self._file is None:
                    stream.close()
                raise

    def close(self) -> None:
        stream, self._file = self._file, None
        if stream is not None:
            # Closing the owning descriptor releases only this owner's lock.
            stream.close()

    def exists(self) -> bool:
        return self.path.exists()

    def __enter__(self) -> FileLock:
        return self.acquire()

    def __exit__(self, *args) -> None:
        self.close()


class _LockContended(Exception):
    """The lock file is momentarily unavailable; acquire() waits and retries."""


def _fsync_directory(directory: Path) -> None:
    """Make a completed rename durable across power loss where the OS supports it."""
    if os.name != "posix":
        return  # Windows has no directory handles to flush; NTFS journals the rename.
    try:
        handle = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def atomic_write(path: Path, raw: bytes, *, mode: int | None = None) -> None:
    """Replace a file atomically via unique scratch in the destination directory.

    File data is flushed to disk before the rename. Permission bits come from
    ``mode`` when given, else from the file being replaced, so readers keep
    access; a brand-new file keeps the private 0600 of its scratch file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            mode = None
        except OSError as exc:
            if not _sharing_violation(exc):
                raise
            mode = None
    scratch = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            scratch = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            try:
                os.chmod(scratch, mode)
            except OSError:
                pass  # Best effort; Windows honors only the read-only bit.
        # A concurrent reader on Windows keeps the destination open, and
        # os.replace then raises PermissionError 13 (Access is denied).
        # The scratch file is already in this directory, so retry the rename.
        _retry_sharing(lambda: scratch.replace(path), timeout=5.0)
        _fsync_directory(path.parent)
    finally:
        if scratch is not None:
            try:
                scratch.unlink(missing_ok=True)
            except OSError:
                # Windows cannot delete a read-only file; clear the bit and retry.
                try:
                    os.chmod(scratch, stat.S_IWRITE | stat.S_IREAD)
                    scratch.unlink(missing_ok=True)
                except OSError:
                    pass
