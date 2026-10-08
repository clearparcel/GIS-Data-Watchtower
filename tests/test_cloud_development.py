from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from clearparcel.datawatch.aggregate import with_freshness
from clearparcel.datawatch.public_dashboard import _PublicStateCache

ROOT = Path(__file__).resolve().parents[1]


class CloudDevelopmentTests(unittest.TestCase):
    def prepare(self, output, now):
        spec = importlib.util.spec_from_file_location(
            "prepare_cloud_development", ROOT / "scripts/prepare_cloud_development.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.prepare(output, now=now)

    def test_offline_fixture_preserves_health_and_stale_worker_provenance(self):
        now = dt.datetime(2026, 10, 8, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as td, patch(
            "socket.create_connection", side_effect=AssertionError("network forbidden")
        ):
            output = Path(td) / "preview"
            self.prepare(output, now)
            config = json.loads((output / "config.json").read_text())
            self.assertEqual(config["sources"], [])
            self.assertNotIn("aggregate_object", config)
            state = json.loads((output / "objects/aggregate-state.json").read_text())
            fresh = with_freshness(state, now=now)
            self.assertFalse(fresh["workers"]["cloud"]["stale"])
            self.assertTrue(fresh["workers"]["local"]["stale"])
            self.assertEqual(fresh["sources"]["synthetic-local"]["status"], "ok")
            self.assertEqual(fresh["sources"]["synthetic-local"]["worker"], "local")
            self.assertTrue(fresh["sources"]["synthetic-local"]["worker_stale"])
            with patch.dict("os.environ", {
                "WATCHTOWER_STORAGE": "local",
                "WATCHTOWER_STORAGE_ROOT": str(output / "objects"),
                "WATCHTOWER_PUBLIC_WORKDIR": str(output / "cache"),
                "WATCHTOWER_AGGREGATE_OBJECT": "aggregate-state.json",
            }):
                cache = _PublicStateCache()
                cache.refresh(force=True)
                public = json.loads(cache.public_path.read_text())
                self.assertEqual(set(public["workers"]), {"cloud", "local"})
                self.assertEqual(len(public["sources"]), 3)
                self.assertEqual(public["counts"], {"ok": 2, "warn": 1, "error": 0})

    def test_preparation_refuses_existing_directory_without_changing_it(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)
            sentinel = output / "config.json"
            sentinel.write_text("private sentinel")
            with self.assertRaises(FileExistsError):
                self.prepare(output, dt.datetime.now(dt.timezone.utc))
            self.assertEqual(sentinel.read_text(), "private sentinel")


if __name__ == "__main__":
    unittest.main()
