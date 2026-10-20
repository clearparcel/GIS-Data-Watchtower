"""A rehearsal must fail when storage protections or recovery behavior fail."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from clearparcel.datawatch import restore_rehearsal as rehearsal
from clearparcel.datawatch.storage import LocalStorage


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/rehearse_isolated_restore.py"


class RestoreRehearsalTests(unittest.TestCase):
    def test_real_local_restore_and_concurrent_retry(self):
        receipt = rehearsal.run_rehearsal()
        self.assertEqual(receipt["result"], "passed")
        self.assertEqual(receipt["observed_cas_conflicts"], 1)
        self.assertEqual(len(receipt["checks_passed"]), 9)
        self.assertTrue(receipt["temporary_storage_removed"])
        self.assertFalse(receipt["production_restore_verified"])
        self.assertFalse(receipt["gcs_verified"])
        self.assertFalse(receipt["activation_authorized"])
        self.assertNotEqual(receipt["backup_sha256"], receipt["final_aggregate_sha256"])
        self.assertEqual(len(receipt["implementation_sha256"]), 4)

    def test_environment_cannot_redirect_storage_or_load_cloud_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / "aggregate.json"
            marker.write_bytes(b"existing operational data")
            with patch.dict(os.environ, {
                "WATCHTOWER_STORAGE": "gcs", "WATCHTOWER_GCS_BUCKET": "must-not-connect",
                "WATCHTOWER_STORAGE_ROOT": td,
            }), patch("clearparcel.datawatch.storage.backend_from_env",
                      side_effect=AssertionError("environment backend invoked")), \
                    patch("clearparcel.datawatch.storage.GCSStorage",
                          side_effect=AssertionError("cloud backend invoked")):
                self.assertEqual(rehearsal.run_rehearsal()["result"], "passed")
            self.assertEqual(marker.read_bytes(), b"existing operational data")
            self.assertEqual([p.name for p in Path(td).iterdir()], ["aggregate.json"])

    def test_invalid_backup_fails_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            backend = LocalStorage(root / "objects")
            for raw in (b"not JSON", b"{}", b"[]"):
                with self.subTest(raw=raw), self.assertRaises((ValueError, TypeError)):
                    rehearsal._restore_empty(backend, raw, hashlib.sha256(raw).hexdigest(), root / "scratch")
                self.assertFalse((root / "objects").exists())
                self.assertFalse((root / "scratch").exists())

    def test_disabled_cas_is_detected_and_temporary_storage_is_removed(self):
        roots = []

        def unsafe_upload(backend, name, source, version):
            roots.append(backend.root)
            destination = backend.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())

        with patch.object(LocalStorage, "upload_if_version", unsafe_upload), \
                self.assertRaisesRegex(rehearsal.RehearsalFailure, "occupied destination"):
            rehearsal.run_rehearsal()
        self.assertTrue(roots)
        self.assertTrue(all(not path.exists() for path in roots))

    def test_missing_conflict_retry_cannot_produce_passing_receipt(self):
        original_publish = rehearsal.aggregate.publish_partial

        def no_retry(*args, **kwargs):
            return original_publish(*args, **kwargs, retries=1)

        with patch.object(rehearsal.aggregate, "publish_partial", no_retry), \
                self.assertRaises(rehearsal.StorageConflictError):
            rehearsal.run_rehearsal()

    def test_lost_worker_is_detected_even_if_upload_returns_success(self):
        original_publish = rehearsal.aggregate.publish_partial

        def lose_local(storage, name, partial, worker, workdir, **kwargs):
            if isinstance(storage, rehearsal._RacingLocalStorage) and worker == "local":
                partial = rehearsal._report("local", 0)
            return original_publish(storage, name, partial, worker, workdir, **kwargs)

        with patch.object(rehearsal.aggregate, "publish_partial", lose_local), \
                self.assertRaises(rehearsal.RehearsalFailure):
            rehearsal.run_rehearsal()

    def test_cli_writes_receipt_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "receipt.json"
            command = [sys.executable, str(SCRIPT), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = output.read_bytes()
            self.assertEqual(json.loads(original)["result"], "passed")
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
