"""Storage backends: every shared write is compare-and-swap."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch.storage import LocalStorage, StorageBackend, StorageConflictError, backend_from_env


class LocalStorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.backend = LocalStorage(self.root / "objects")

    def source(self, text):
        path = self.root / ("src-" + hashlib.sha256(text.encode()).hexdigest()[:8])
        path.write_text(text, encoding="utf-8")
        return path

    def test_round_trip(self):
        self.backend.upload_if_version("state.json", self.source('{"ok":true}'), None)
        destination = self.root / "downloaded.json"
        self.assertTrue(self.backend.download("state.json", destination))
        self.assertEqual(destination.read_text(encoding="utf-8"), '{"ok":true}')
        self.assertFalse(self.backend.download("missing.json", self.root / "missing.json"))

    def test_version_token_is_bound_to_the_downloaded_bytes(self):
        self.assertEqual(self.backend.download_versioned("x.json", self.root / "x.json"), (False, None))
        self.backend.upload_if_version("x.json", self.source("one"), None)
        exists, token = self.backend.download_versioned("x.json", self.root / "x.json")
        self.assertTrue(exists)
        self.assertEqual(token, hashlib.sha256(b"one").hexdigest())

    def test_stale_tokens_conflict_and_leave_the_object_unchanged(self):
        self.backend.upload_if_version("x.json", self.source("one"), None)
        _, token = self.backend.download_versioned("x.json", self.root / "x.json")
        with self.assertRaises(StorageConflictError):
            self.backend.upload_if_version("x.json", self.source("two"), None)  # expected absent
        self.backend.upload_if_version("x.json", self.source("two"), token)
        with self.assertRaises(StorageConflictError):
            self.backend.upload_if_version("x.json", self.source("three"), token)  # token now stale
        self.assertEqual((self.backend.root / "x.json").read_text(encoding="utf-8"), "two")

    def test_no_backend_offers_an_unconditional_upload(self):
        self.assertFalse(hasattr(StorageBackend, "upload"))
        self.assertFalse(hasattr(self.backend, "upload"))


class LocalStorageContainmentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.backend = LocalStorage(self.root / "objects")
        self.outside = self.root / "outside.txt"
        self.outside.write_text("sibling", encoding="utf-8")
        self.payload = self.root / "payload.txt"
        self.payload.write_text("overwrite", encoding="utf-8")

    ESCAPES = ("../outside.txt", "nested/../../outside.txt", "/etc/passwd", "C:/Windows/win.ini",
               "C:outside.txt", "\\\\server\\share\\x", "..\\outside.txt", "a\\b", "", ".", "..",
               "a//b", "a/./b", "objects/", "x\x00y")

    def test_escaping_names_cannot_read_or_overwrite_files(self):
        target = self.root / "copy.txt"
        for name in self.ESCAPES:
            with self.subTest(name=name):
                for call in (lambda: self.backend.download(name, target),
                             lambda: self.backend.download_versioned(name, target),
                             lambda: self.backend.upload_if_version(name, self.payload, None)):
                    with self.assertRaises(ValueError):
                        call()
        self.assertEqual(self.outside.read_text(encoding="utf-8"), "sibling")
        self.assertFalse(target.exists())

    def test_absolute_path_inside_root_is_still_rejected(self):
        with self.assertRaises(ValueError):
            self.backend.download(str(self.root / "objects" / "a.json"), self.root / "copy.txt")

    def test_nested_relative_keys_still_work(self):
        self.backend.upload_if_version("runs/dispatch-guard-cloud.json", self.payload, None)
        exists, token = self.backend.download_versioned("runs/dispatch-guard-cloud.json", self.root / "copy.txt")
        self.assertTrue(exists)
        self.assertEqual(token, hashlib.sha256(b"overwrite").hexdigest())
        self.assertTrue((self.root / "objects" / "runs" / "dispatch-guard-cloud.json").is_file())
        self.assertEqual(self.backend.download("history.jsonl.1", self.root / "missing.txt"), False)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_leaving_the_root_is_refused(self):
        (self.root / "objects").mkdir(exist_ok=True)
        link = self.root / "objects" / "link"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation not permitted")
        with self.assertRaises(ValueError):
            self.backend.download("link/outside.txt", self.root / "copy.txt")
        with self.assertRaises(ValueError):
            self.backend.upload_if_version("link/outside.txt", self.payload, None)
        self.assertEqual(self.outside.read_text(encoding="utf-8"), "sibling")


class BackendSelectionTests(unittest.TestCase):
    def test_local_is_the_default_and_unknown_backends_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict("os.environ", {}, clear=True):
                backend = backend_from_env(td)
                self.assertIsInstance(backend, LocalStorage)
                self.assertEqual(backend.root, Path(td).resolve())
            with patch.dict("os.environ", {"WATCHTOWER_STORAGE": ""}, clear=True), \
                    self.assertRaisesRegex(RuntimeError, "unsupported WATCHTOWER_STORAGE"):
                backend_from_env(td)  # set but empty is not a known backend
            with patch.dict("os.environ", {"WATCHTOWER_STORAGE": "LOCAL", "WATCHTOWER_STORAGE_ROOT": td}, clear=True):
                self.assertIsInstance(backend_from_env("/unused"), LocalStorage)
            with patch.dict("os.environ", {"WATCHTOWER_STORAGE": "s3"}, clear=True), \
                    self.assertRaisesRegex(RuntimeError, "unsupported WATCHTOWER_STORAGE"):
                backend_from_env(td)
            with patch.dict("os.environ", {"WATCHTOWER_STORAGE": "gcs"}, clear=True), \
                    self.assertRaisesRegex(RuntimeError, "WATCHTOWER_GCS_BUCKET is required"):
                backend_from_env(td)


if __name__ == "__main__":
    unittest.main()
