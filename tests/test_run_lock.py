"""A restart after the run-lock owner exits must not be refused as a live overlap.

Review of ff9f9a7, finding 07. Windows releases a killed process's byte-range
lock asynchronously, so the run lock waits a bounded time before reporting
contention. A live owner is still excluded. Offline: temporary files only.
"""
from __future__ import annotations

import errno
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch


def _hold_lock_in_child(state: Path) -> subprocess.Popen:
    script = ("import sys; from pathlib import Path; "
              "from clearparcel.datawatch.watch import _acquire_run_lock; "
              "lock=_acquire_run_lock(Path(sys.argv[1])); "
              "print('ready',flush=True); sys.stdin.read()")
    child = subprocess.Popen([sys.executable, "-c", script, str(state)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    if child.stdout.readline().strip() != "ready":
        child.kill(); child.wait(timeout=5)
        raise AssertionError("child did not acquire the run lock")
    return child


def _stop(child: subprocess.Popen) -> None:
    if child.poll() is None:
        child.kill()
    child.wait(timeout=5)
    for stream in (child.stdin, child.stdout):
        if stream is not None:
            stream.close()


class TransientReleaseTests(unittest.TestCase):
    def test_lock_released_shortly_after_a_refusal_is_acquired(self):
        """Emulate Windows: the OS reports the dead owner's lock for a moment."""
        if sys.platform == "win32":
            self.skipTest("emulates Windows through the POSIX lock call")
        import fcntl
        real, refusals = fcntl.flock, []

        def flaky(fd, op):
            if len(refusals) < 3:
                refusals.append(op)
                raise BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")
            return real(fd, op)

        with tempfile.TemporaryDirectory() as td, patch.object(fcntl, "flock", flaky):
            lock = watch._acquire_run_lock(Path(td) / "state.json", wait_seconds=2)
            watch._release_run_lock(lock)
        self.assertEqual(len(refusals), 3)

    def test_restart_after_kill_succeeds_repeatedly(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            for attempt in range(5):
                with self.subTest(attempt=attempt):
                    child = _hold_lock_in_child(state)
                    try:
                        child.kill(); child.wait(timeout=5)
                        watch._release_run_lock(watch._acquire_run_lock(state))
                    finally:
                        _stop(child)


class LiveOwnerTests(unittest.TestCase):
    def test_live_owner_in_another_process_is_still_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            child = _hold_lock_in_child(state)
            try:
                for _attempt in range(3):
                    started = time.monotonic()
                    with self.assertRaisesRegex(watch.WatchtowerRunLockedError, "already running"):
                        watch._acquire_run_lock(state, wait_seconds=0.3)
                    self.assertGreaterEqual(time.monotonic() - started, 0.25)
            finally:
                _stop(child)

    def test_check_reports_genuine_contention_before_any_request(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            config = {"state_file": str(state), "history_file": str(Path(td) / "h.jsonl"), "sources": []}
            owner = watch._acquire_run_lock(state)
            try:
                with patch.object(watch, "_RUN_LOCK_WAIT_SECONDS", 0.1), \
                        patch.object(watch, "_check_sources_unlocked") as check, \
                        self.assertRaisesRegex(watch.WatchtowerRunLockedError, "another Watchtower check is already running"):
                    watch.check_sources(config, save=True)
                check.assert_not_called()
            finally:
                watch._release_run_lock(owner)


if __name__ == "__main__":
    unittest.main()
