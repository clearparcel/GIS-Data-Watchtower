import json
import tempfile
import unittest
from pathlib import Path

from clearparcel.datawatch.public_publish import (
    publish_public_snapshot,
    validate_public_state,
)
from clearparcel.datawatch.storage import LocalStorage


class PublicPublishTests(unittest.TestCase):
    def test_publish_public_snapshot_sanitizes_before_destination_upload(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_root = root / "source"
            dest_root = root / "dest"
            workdir = root / "work"
            source_root.mkdir()
            dest_root.mkdir()
            raw = {
                "schema_version": 2,
                "generated_at": "2026-10-05T20:00:00+00:00",
                "overall": "ok",
                "counts": {"ok": 1, "warn": 0, "error": 0},
                "workers": {
                    "cloud": {
                        "overall": "ok",
                        "source_count": 1,
                        "telemetry": {"secret_runtime": 123},
                    }
                },
                "sources": {
                    "county-parcels": {
                        "id": "county-parcels",
                        "name": "County Parcels",
                        "provider": "Example County",
                        "category": "Parcels",
                        "status": "ok",
                        "feature_count": 10,
                        "changes": [{"previous": "PRIVATE-OLD", "current": "PRIVATE-NEW"}],
                        "url": "https://secret.invalid/service",
                        "schema_hash": "PRIVATE-SCHEMA",
                        "observation_fingerprint": "PRIVATE-FINGERPRINT",
                        "tracked_values": {"secret": "PRIVATE"},
                    }
                },
            }
            (source_root / "aggregate-state.json").write_text(json.dumps(raw), encoding="utf-8")

            result = publish_public_snapshot(
                LocalStorage(source_root),
                LocalStorage(dest_root),
                workdir=workdir,
            )

            self.assertTrue(result["published"])
            self.assertTrue(result["public_published_at"])
            self.assertEqual(result["source_count"], 1)
            self.assertEqual(result["worker_count"], 1)

            public = json.loads((dest_root / "aggregate-state.json").read_text(encoding="utf-8"))
            self.assertEqual(public["public_published_at"], result["public_published_at"])
            source = public["sources"]["county-parcels"]
            self.assertEqual(source["change_count"], 1)
            self.assertNotIn("url", source)
            self.assertNotIn("changes", source)
            self.assertNotIn("schema_hash", source)
            self.assertNotIn("observation_fingerprint", source)
            self.assertNotIn("tracked_values", source)
            self.assertNotIn("telemetry", public["workers"]["cloud"])

    def test_validate_public_state_fails_closed_on_forbidden_nested_key(self):
        with self.assertRaisesRegex(RuntimeError, "forbidden fields"):
            validate_public_state(
                {
                    "sources": {
                        "x": {
                            "name": "X",
                            "nested": {"provenance": {"private": True}},
                        }
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
