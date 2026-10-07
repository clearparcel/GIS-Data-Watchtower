import json
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import threading
from pathlib import Path

from clearparcel.datawatch.public_publish import (
    publish_public_snapshot,
    validate_public_state,
)
from clearparcel.datawatch.storage import LocalStorage


class PublicPublishTests(unittest.TestCase):
    def test_validate_public_metadata_rejects_untyped_leaves(self):
        validate_public_state({'sources': {'x': {'public_metadata': {'file': {'size_bytes': 0}}}}})
        for metadata in ({'file': {'etag': {'private': 1}}}, {'unknown': 'private'}, {'provider_updated_at': 'invalid'}):
            with self.assertRaises(RuntimeError):
                validate_public_state({'sources': {'x': {'public_metadata': metadata}}})

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

            self.assertEqual(list(workdir.iterdir()), [])
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

    def test_publisher_cleans_scratch_on_validation_or_upload_failure(self):
        for failure in ('validation', 'upload'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                source_root = root / 'source'
                source = LocalStorage(source_root)
                source_root.mkdir()
                (source_root / 'aggregate-state.json').write_text('{}', encoding='utf-8')
                destination = LocalStorage(root / 'destination')
                workdir = root / 'work'
                target = ('clearparcel.datawatch.public_publish.validate_public_state' if failure == 'validation'
                          else 'clearparcel.datawatch.storage.LocalStorage.upload_if_version')
                with patch(target, side_effect=RuntimeError('injected failure')):
                    with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                        publish_public_snapshot(source, destination, workdir=workdir)
                self.assertEqual(list(workdir.iterdir()), [])

    def test_concurrent_publications_have_isolated_scratch(self):
        barrier = threading.Barrier(2)
        class Source:
            def __init__(self, name):
                self.name = name
            def download(self, name, path):
                path.write_text(json.dumps({'sources': {self.name: {'name': self.name}}}), encoding='utf-8')
                barrier.wait(timeout=10)
                return True
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            def run(name):
                return publish_public_snapshot(Source(name), LocalStorage(root / name), workdir=root / 'work')
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(run, ('first', 'second')))
            for name in ('first', 'second'):
                public = json.loads((root / name / 'aggregate-state.json').read_text(encoding='utf-8'))
                self.assertEqual(set(public['sources']), {name})
            self.assertEqual(list((root / 'work').iterdir()), [])

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
