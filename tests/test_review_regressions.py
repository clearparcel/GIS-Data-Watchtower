"""Offline regressions for the October 6 manual review findings."""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from clearparcel.datawatch import dashboard, watch
from clearparcel.datawatch.aggregate import merge_states, publish_partial
from clearparcel.datawatch.file_lock import FileLock, atomic_write
from clearparcel.datawatch import storage as storage_module
from clearparcel.datawatch.public_publish import publish_public_snapshot, _snapshot_is_superseded
from clearparcel.datawatch.storage import LocalStorage, StorageConflictError


def report(hour, sources, scope="fleet"):
    return {"generated_at": f"2026-10-06T{hour:02}:00:00+00:00", "overall": "ok",
            "scope": {"type": scope}, "sources": sources}


class ReviewRegressions(unittest.TestCase):
    def test_missing_or_invalid_report_time_cannot_bypass_ordering(self):
        state = merge_states({}, report(12, {"a": {"status": "error"}}), "cloud")
        for value in (None, "", "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                merge_states(state, {"generated_at": value, "sources": {}}, "cloud")

    def test_duplicate_report_is_idempotent_and_late_report_cannot_resurrect(self):
        state = merge_states({}, report(10, {"old": {"status": "ok"}}), "cloud")
        state = merge_states(state, report(12, {}), "cloud")
        self.assertEqual(merge_states(state, report(12, {"old": {"status": "error"}}), "cloud"), state)
        self.assertEqual(merge_states(state, report(11, {"old": {"status": "ok"}}), "cloud"), state)

    def test_public_guard_compares_workers_and_retained_sources(self):
        for key, timestamp in (("workers", "last_report_at"), ("sources", "checked_at")):
            with self.subTest(key=key):
                current = report(12, {})
                candidate = report(12, {})
                current[key] = {"a": {timestamp: report(11, {})["generated_at"]}}
                candidate[key] = {"a": {timestamp: report(10, {})["generated_at"]}}
                self.assertTrue(_snapshot_is_superseded(candidate, current))
        state = merge_states({}, report(10, {"old": {"status": "ok"}}), "cloud")
        self.assertFalse(_snapshot_is_superseded(merge_states(state, report(12, {}), "cloud"), state))

    def test_dashboard_profile_is_required_and_validated(self):
        config = {"sources": [{"execution_profiles": ["local"]}]}
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                dashboard._dashboard_execution_profile(config)
            self.assertIsNone(dashboard._dashboard_execution_profile({"sources": []}))
            self.assertEqual(dashboard._dashboard_execution_profile(dict(config, dashboard_execution_profile="local")), "local")
        with patch.dict(os.environ, {"WATCHTOWER_EXECUTION_PROFILE": "typo"}):
            with self.assertRaises(ValueError):
                dashboard._dashboard_execution_profile(config)

    def test_old_owner_release_cannot_release_successors_lock(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "lock"
            first = FileLock(path).acquire()
            first.close()
            with FileLock(path):
                first.close()
                with self.assertRaises(TimeoutError):
                    FileLock(path).acquire()

    def test_legacy_cas_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "object.json.lock"
            path.mkdir()
            with self.assertRaisesRegex(RuntimeError, "stopped-worker reconciliation"):
                FileLock(path).acquire()
            self.assertTrue(path.is_dir())

    def test_unconditional_upload_cannot_interrupt_conditional_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            backend = LocalStorage(root / "objects")
            first, second = root / "first", root / "second"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            ready, release, second_started, second_done = (threading.Event() for _ in range(4))
            errors = []
            original = storage_module.atomic_write
            def paused(*args):
                if threading.current_thread().name == "conditional":
                    ready.set()
                    if not release.wait(5):
                        raise TimeoutError("conditional writer was not released")
                return original(*args)
            def write_conditional():
                try:
                    backend.upload_if_version("object", first, None)
                except Exception as exc:
                    errors.append(exc)
            def write_unconditional():
                second_started.set()
                try:
                    backend.upload("object", second)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    second_done.set()
            with patch.object(storage_module, "atomic_write", side_effect=paused):
                conditional = threading.Thread(target=write_conditional, name="conditional")
                unconditional = threading.Thread(target=write_unconditional)
                conditional.start()
                try:
                    self.assertTrue(ready.wait(5))
                    unconditional.start()
                    self.assertTrue(second_started.wait(5))
                    self.assertFalse(second_done.wait(0.2), "unconditional writer bypassed the CAS lock")
                finally:
                    release.set()
                    conditional.join(timeout=5)
                    if unconditional.ident is not None:
                        unconditional.join(timeout=5)
            self.assertFalse(conditional.is_alive() or unconditional.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual((backend.root / "object").read_bytes(), b"second")

    def test_same_worker_concurrent_merges_have_independent_scratch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = LocalStorage(root / "objects")
            ready, release = threading.Event(), threading.Event()
            errors = []
            original = storage.upload_if_version
            def paused(*args):
                if threading.current_thread().name == "old-report":
                    ready.set()
                    if not release.wait(5):
                        raise TimeoutError("new report did not finish")
                return original(*args)
            def run_old():
                try:
                    publish_partial(storage, "state.json", report(11, {"a": {"status": "ok"}}), "cloud", root / "work")
                except Exception as exc:
                    errors.append(exc)
            with patch.object(storage, "upload_if_version", side_effect=paused):
                thread = threading.Thread(target=run_old, name="old-report")
                thread.start()
                try:
                    self.assertTrue(ready.wait(5))
                    publish_partial(storage, "state.json", report(12, {"a": {"status": "error"}}), "cloud", root / "work")
                finally:
                    release.set()
                    thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            final = json.loads((root / "objects" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(final["sources"]["a"]["status"], "error")
            self.assertEqual(list((root / "work").iterdir()), [])

    def test_public_cas_retry_limit_and_identical_snapshot_republication(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, destination = LocalStorage(root / "source"), LocalStorage(root / "destination")
            source.root.mkdir()
            (source.root / "aggregate-state.json").write_text(json.dumps(report(12, {})), encoding="utf-8")
            self.assertTrue(publish_public_snapshot(source, destination, workdir=root / "work")["published"])
            self.assertTrue(publish_public_snapshot(source, destination, workdir=root / "work")["published"])
            with patch.object(destination, "upload_if_version", side_effect=StorageConflictError("competing writer")) as upload:
                with self.assertRaises(StorageConflictError):
                    publish_public_snapshot(source, destination, workdir=root / "work")
                self.assertEqual(upload.call_count, 8)
            self.assertEqual(list((root / "work").iterdir()), [])

    def test_late_report_cannot_revert_newer_error_or_worker_time(self):
        newer = merge_states({}, report(12, {"a": {"status": "error"}}), "cloud")
        merged = merge_states(newer, report(11, {"a": {"status": "ok"}}), "cloud")
        self.assertEqual(merged, newer)

    def test_full_report_retires_only_that_workers_omitted_sources(self):
        state = merge_states({}, report(10, {"old": {"status": "ok"}}), "cloud")
        state = merge_states(state, report(11, {"local": {"status": "ok"}}), "local")
        state = merge_states(state, report(12, {}), "cloud")
        self.assertEqual(set(state["sources"]), {"local"})
        self.assertEqual(state["workers"]["cloud"]["source_count"], 0)

    def test_filtered_and_legacy_reports_do_not_retire_other_sources(self):
        for scope in ("source", None):
            with self.subTest(scope=scope):
                state = merge_states({}, report(10, {"a": {"status": "ok"}}), "cloud")
                partial = report(11, {"b": {"status": "error"}})
                if scope is None:
                    partial.pop("scope")
                else:
                    partial["scope"] = {"type": scope}
                state = merge_states(state, partial, "cloud")
                self.assertEqual(set(state["sources"]), {"a", "b"})

    def test_older_cross_worker_report_preserves_newer_source_and_fleet_time(self):
        state = merge_states({}, report(12, {"shared": {"status": "error"}}), "local")
        state = merge_states(state, report(11, {"shared": {"status": "ok"}}), "cloud")
        self.assertEqual(state["sources"]["shared"]["status"], "error")
        self.assertEqual(state["generated_at"], report(12, {})["generated_at"])

    def test_live_run_lock_is_not_stolen_even_after_configured_age(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            owner = watch._acquire_run_lock(state, 60)
            try:
                os.utime(state.with_suffix(".json.lock"), (time.time()-61, time.time()-61))
                with self.assertRaises(watch.WatchtowerRunLockedError):
                    successor = watch._acquire_run_lock(state, 60)
                    watch._release_run_lock(successor)
            finally:
                watch._release_run_lock(owner)

    def test_no_save_check_does_not_acquire_state_lock(self):
        config = {"state_file": "/datawatch/state.json", "sources": []}
        with patch.object(watch, "_acquire_run_lock") as acquire, patch.object(
            watch, "_check_sources_unlocked", return_value={"overall": "ok", "sources": {}}
        ) as check:
            result = watch.check_sources(
                config, source_filter="mn-state-roads", save=False, execution_profile="cloud"
            )
        acquire.assert_not_called()
        check.assert_called_once_with(
            config,
            source_filter="mn-state-roads",
            save=False,
            execution_profile="cloud",
        )
        self.assertEqual(result["overall"], "ok")

    def test_run_lock_recovers_immediately_after_process_termination(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            script = ("import sys; from pathlib import Path; "
                      "from clearparcel.datawatch.watch import _acquire_run_lock; "
                      "lock=_acquire_run_lock(Path(sys.argv[1])); "
                      "print('ready',flush=True); sys.stdin.read()")
            with subprocess.Popen([sys.executable, "-c", script, str(state)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as child:
                try:
                    self.assertEqual(child.stdout.readline().strip(), "ready")
                    child.kill(); child.wait(timeout=5)
                    owner = watch._acquire_run_lock(state)
                    watch._release_run_lock(owner)
                finally:
                    if child.poll() is None:
                        child.kill(); child.wait(timeout=5)

    def test_local_cas_recovers_after_writer_termination(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / "input.json"; source.write_text("{}", encoding="utf-8")
            script = """import sys
from pathlib import Path
from clearparcel.datawatch.storage import LocalStorage
original=Path.replace
def paused(path,target):
    print('ready',flush=True)
    sys.stdin.read()
    return original(path,target)
Path.replace=paused
LocalStorage(sys.argv[1]).upload_if_version('state.json',Path(sys.argv[2]),None)
"""
            with subprocess.Popen([sys.executable, "-c", script, str(root / "objects"), str(source)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as child:
                try:
                    self.assertEqual(child.stdout.readline().strip(), "ready")
                    child.kill(); child.wait(timeout=5)
                    LocalStorage(root / "objects").upload_if_version("state.json", source, None)
                finally:
                    if child.poll() is None:
                        child.kill(); child.wait(timeout=5)

    def test_local_uploads_use_independent_temporary_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); storage = LocalStorage(root / "objects")
            first = root / "a"; second = root / "b"
            first.write_bytes(b"A"); second.write_bytes(b"B")
            first_ready = threading.Event(); second_done = threading.Event(); errors = []
            original = Path.replace
            def paused(path, target):
                if threading.current_thread().name == "first-upload":
                    first_ready.set()
                    if not second_done.wait(5):
                        raise TimeoutError("second upload did not finish")
                return original(path, target)
            def upload_first():
                try:
                    atomic_write(storage.root / "object.json", first.read_bytes())
                except Exception as exc:
                    errors.append(exc)
            with patch.object(Path, "replace", paused):
                thread = threading.Thread(target=upload_first, name="first-upload")
                thread.start()
                try:
                    self.assertTrue(first_ready.wait(5))
                    atomic_write(storage.root / "object.json", second.read_bytes())
                finally:
                    second_done.set(); thread.join(timeout=5)
            self.assertEqual(errors, [])
            self.assertEqual((root / "objects" / "object.json").read_bytes(), b"A")
            self.assertFalse(list((root / "objects").glob("*.tmp")))

    def test_overlapping_publishers_cannot_revert_newer_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, hour in (("old", 11), ("new", 12)):
                (root / name).mkdir()
                (root / name / "aggregate-state.json").write_text(json.dumps(report(hour, {})), encoding="utf-8")
            ready = threading.Event(); release = threading.Event(); errors = []
            destination = LocalStorage(root / "destination")
            original_upload = destination.upload
            original_cas = destination.upload_if_version
            def pause_then(method, *args):
                if threading.current_thread().name == "old-publisher":
                    ready.set()
                    if not release.wait(5):
                        raise TimeoutError("new publisher did not finish")
                return method(*args)
            def run_old():
                try:
                    publish_public_snapshot(LocalStorage(root / "old"), destination, workdir=root / "work")
                except Exception as exc:
                    errors.append(exc)
            with patch.object(destination, "upload", side_effect=lambda *args: pause_then(original_upload, *args)), \
                 patch.object(destination, "upload_if_version", side_effect=lambda *args: pause_then(original_cas, *args)):
                thread = threading.Thread(target=run_old, name="old-publisher"); thread.start()
                try:
                    self.assertTrue(ready.wait(5))
                    publish_public_snapshot(LocalStorage(root / "new"), destination, workdir=root / "work")
                finally:
                    release.set(); thread.join(timeout=5)
            self.assertEqual(errors, [])
            self.assertFalse(thread.is_alive())
            final = json.loads((root / "destination" / "aggregate-state.json").read_text(encoding="utf-8"))
            self.assertEqual(final["generated_at"], report(12, {})["generated_at"])
            self.assertEqual(list((root / "work").iterdir()), [])

    def test_wms_wfs_preserve_existing_queries_and_remove_fragments(self):
        for adapter, xml in ((watch._wms, b"<WMS_Capabilities/>"), (watch._wfs, b"<WFS_Capabilities/>")):
            with self.subTest(adapter=adapter.__name__):
                urls = []
                with patch.object(watch, "_request", side_effect=lambda url,*a,**kw: (urls.append(url) or (xml, {"status": 200}))):
                    adapter({"url": "https://example.invalid/service?map=parcels.map&SERVICE=old#ignored"}, 1)
                parts = urlsplit(urls[0]); params = parse_qs(parts.query)
                self.assertEqual(params["map"], ["parcels.map"])
                self.assertEqual(parts.fragment, "")
                self.assertEqual([v for k, v in params.items() if k.lower() == "service"],
                                 [["WMS" if adapter == watch._wms else "WFS"]])

    def test_dashboard_refresh_checks_only_configured_execution_profile(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); calls = []
            config = {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
                      "retries": 0, "sources": [{"id": p, "name": p, "kind": "arcgis_service",
                           "url": "https://example.invalid", "execution_profiles": [p]} for p in ("cloud", "local")]}
            class InlineThread:
                def __init__(self, target, **kwargs): self.target = target
                def start(self): self.target()
            class Server:
                def __init__(self, addr, handler, **kwargs): self.handler = handler
                def serve_forever(self):
                    handler = object.__new__(self.handler)
                    raw = urlencode({"csrf_token": config["_csrf_token"]}).encode()
                    handler.path = "/refresh"; handler.headers = {"Content-Length": str(len(raw)), "Sec-Fetch-Site": "same-origin"}
                    handler.rfile = io.BytesIO(raw); handler._require_auth = lambda: False
                    handler.send_response = lambda *a: None; handler.send_header = lambda *a: None
                    handler.end_headers = lambda: None
                    handler.do_POST()
                def server_close(self): pass
            with patch.dict(os.environ, {"WATCHTOWER_EXECUTION_PROFILE": "cloud"}), \
                 patch.object(dashboard, "_BoundedThreadingHTTPServer", Server), \
                 patch.object(dashboard.threading, "Thread", InlineThread), \
                 patch.object(watch, "_source_check", side_effect=lambda source,timeout: (calls.append(source["id"]) or {"problems": []})):
                dashboard.serve(config)
            self.assertEqual(calls, ["cloud"])


if __name__ == "__main__":
    unittest.main()
