"""Process-owned file locks and atomic local replacements, without extra dependencies."""
from __future__ import annotations

import errno
import os
import stat
import tempfile
import time
from pathlib import Path


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
        stream = self.path.open("a+b")
        try:
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"\0")
                stream.flush()
            end = time.monotonic() + self.timeout
            while True:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._file = stream
                    return self
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    remaining = end - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"timed out waiting for file lock: {self.path}") from exc
                    time.sleep(min(0.025, remaining))
        except BaseException:
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
        scratch.replace(path)
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
