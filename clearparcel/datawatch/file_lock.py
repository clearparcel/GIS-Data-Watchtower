"""Process-owned file locks and atomic local replacements, without extra dependencies."""
from __future__ import annotations

import errno
import os
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


def atomic_write(path: Path, raw: bytes) -> None:
    """Use unique scratch in the destination directory, including on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            scratch = Path(stream.name)
            stream.write(raw)
        scratch.replace(path)
    finally:
        if scratch is not None:
            scratch.unlink(missing_ok=True)
