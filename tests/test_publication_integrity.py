"""Public output is validated before it replaces anything (audit WT31-03, WT31-15)."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.public_projection import InvalidSnapshotError, validate_snapshot_structure
from clearparcel.datawatch.public_publish import (
    PublisherAliasError,
    publish_public_snapshot,
    publish_public_snapshot_from_env,
)
from clearparcel.datawatch.storage import LocalStorage, gcs_object_identity


def aggregate(hour, status="ok", counts=None, overall=None):
    stamp = f"2026-10-30T{hour:02}:00:00+00:00"
    derived = {"ok": int(status == "ok"), "warn": int(status == "warn"), "error": int(status == "error")}
    return {"schema_version": 2, "generated_at": stamp,
            "overall": overall or ("error" if status == "error" else "warn" if status == "warn" else "ok"),
            "counts": counts or derived,
            "workers": {"cloud": {"overall": "ok", "source_count": 1, "last_report_at": stamp}},
            "sources": {"a": {"id": "a", "name": "A", "status": status, "worker": "cloud",
                              "checked_at": stamp, "last_report_at": stamp}}}


class PublisherValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = LocalStorage(self.root / "source")
        self.destination = LocalStorage(self.root / "destination")
        self.source.root.mkdir()
        self.destination.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, document):
        (self.source.root / "aggregate-state.json").write_text(json.dumps(document), encoding="utf-8")
        return publish_public_snapshot(self.source, self.destination, workdir=self.root / "work")

    def destination_bytes(self):
        return (self.destination.root / "aggregate-state.json").read_bytes()

    def test_contradictory_totals_never_replace_the_last_accepted_publication(self):
        self.assertTrue(self.publish(aggregate(10))["published"])
        good = self.destination_bytes()
        _exists, good_version = self.destination.download_versioned("aggregate-state.json", self.root / "probe.json")
        # One error source while counts and overall still say all clear, one hour later.
        bad = aggregate(11, status="error", counts={"ok": 1, "warn": 0, "error": 0}, overall="ok")
        with self.assertRaises(InvalidSnapshotError):
            self.publish(bad)
        self.assertEqual(self.destination_bytes(), good)
        _exists, version = self.destination.download_versioned("aggregate-state.json", self.root / "probe.json")
        self.assertEqual(version, good_version)
        self.assertEqual(list((self.root / "work").iterdir()), [])
        # Correct totals publish normally.
        self.assertTrue(self.publish(aggregate(12, status="error"))["published"])

    def test_first_publication_of_an_invalid_snapshot_writes_nothing(self):
        for document in ({}, {"sources": {}}, {**aggregate(10), "schema_version": None},
                         {**aggregate(10), "generated_at": "yesterday"}):
            with self.subTest(document=document):
                with self.assertRaises(InvalidSnapshotError):
                    self.publish(document)
                self.assertFalse((self.destination.root / "aggregate-state.json").exists())

    def test_valid_empty_fleet_publishes(self):
        empty = {"schema_version": 2, "generated_at": "2026-10-30T10:00:00+00:00", "overall": "ok",
                 "counts": {"ok": 0, "warn": 0, "error": 0}, "workers": {}, "sources": {}}
        self.assertTrue(self.publish(empty)["published"])

    def test_every_accepted_publication_passes_the_cold_reader_contract(self):
        for hour, status in ((10, "warn"), (11, "error"), (12, "ok")):
            self.publish(aggregate(hour, status=status))
            # The public reader validates the downloaded bytes with this check.
            validate_snapshot_structure(json.loads(self.destination_bytes()))


class PublisherAliasTests(unittest.TestCase):
    def test_two_clients_for_the_same_object_are_refused_before_any_io(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "store").mkdir()
            original = json.dumps({**aggregate(10), "private_observation": "keep-me"})
            (root / "store" / "aggregate-state.json").write_text(original, encoding="utf-8")
            source = LocalStorage(root / "store")
            # A second instance with a different spelling of the same root.
            destination = LocalStorage(root / "store" / ".." / "store")
            with patch.object(LocalStorage, "download", wraps=source.download) as download:
                with self.assertRaises(PublisherAliasError):
                    publish_public_snapshot(source, destination, workdir=root / "work")
                download.assert_not_called()
            self.assertEqual((root / "store" / "aggregate-state.json").read_text(encoding="utf-8"), original)
            self.assertFalse((root / "work").exists())

    def test_distinct_objects_in_one_store_are_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = LocalStorage(root / "store")
            store.root.mkdir()
            (store.root / "aggregate-state.json").write_text(json.dumps(aggregate(10)), encoding="utf-8")
            result = publish_public_snapshot(store, LocalStorage(root / "store"), destination_object="public.json",
                                             workdir=root / "work")
            self.assertTrue(result["published"])

    def test_gcs_identity_normalizes_prefix_spelling(self):
        self.assertEqual(gcs_object_identity("Bucket", "/a//b/", "x.json"), gcs_object_identity("bucket", "a/b", "x.json"))
        self.assertNotEqual(gcs_object_identity("bucket", "a", "x.json"), gcs_object_identity("bucket", "b", "x.json"))

    def test_env_configuration_is_refused_before_any_client_is_built(self):
        env = {"WATCHTOWER_PUBLIC_SOURCE_BUCKET": "private-bucket", "WATCHTOWER_PUBLIC_SOURCE_PREFIX": "agg/",
               "WATCHTOWER_PUBLIC_DEST_BUCKET": "private-bucket", "WATCHTOWER_PUBLIC_DEST_PREFIX": "/agg"}
        with patch.dict(os.environ, env, clear=False), \
                patch("clearparcel.datawatch.public_publish.GCSStorage") as client:
            for key in ("WATCHTOWER_PUBLIC_SOURCE_OBJECT", "WATCHTOWER_PUBLIC_DEST_OBJECT"):
                os.environ.pop(key, None)
            with self.assertRaises(PublisherAliasError):
                publish_public_snapshot_from_env()
            client.assert_not_called()


class StaticExportValidationTests(unittest.TestCase):
    def test_contradictory_state_leaves_an_existing_export_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "site"
            dashboard.build_static_site({"_render_state": aggregate(10, status="warn")}, out)
            before = {path.name: path.read_bytes() for path in out.iterdir()}
            bad = aggregate(11, status="warn", counts={"ok": 0, "warn": 0, "error": 0}, overall="ok")
            with self.assertRaises(InvalidSnapshotError):
                dashboard.build_static_site({"_render_state": bad}, out)
            self.assertEqual({path.name: path.read_bytes() for path in out.iterdir()}, before)

    def test_contradictory_state_creates_no_new_output_directory(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "site"
            bad = aggregate(11, status="error", counts={"ok": 1, "warn": 0, "error": 0}, overall="ok")
            with self.assertRaises(InvalidSnapshotError):
                dashboard.build_static_site({"_render_state": bad}, out)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
