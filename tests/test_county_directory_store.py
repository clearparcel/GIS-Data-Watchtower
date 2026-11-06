import json
import tempfile
import unittest
from pathlib import Path

from clearparcel.datawatch.county_directory_store import (
    CountyDirectoryStore,
    CountyRevisionConflict,
    read_public_directory,
)
from clearparcel.datawatch.storage import LocalStorage, StorageConflictError


AITKIN = {"fips": "27001", "name": "Aitkin", "slug": "aitkin"}
ANOKA = {"fips": "27003", "name": "Anoka", "slug": "anoka"}
SENTINEL = "PRIVATE_SYNTHETIC_NOTE"


def draft(county=AITKIN, text="Public policy", note=SENTINEL):
    return {
        "fips": county["fips"],
        "policy": {"text": text, "attachment_id": SENTINEL},
        "correspondence": [{"subject": note}],
    }


class InterleavedStorage(LocalStorage):
    before_upload = None
    after_upload = None
    before_read = None

    def download_versioned(self, name, destination):
        if self.before_read:
            callback, self.before_read = self.before_read, None
            callback()
        return super().download_versioned(name, destination)

    def upload_if_version(self, name, source, version):
        if self.before_upload:
            callback, self.before_upload = self.before_upload, None
            callback()
        super().upload_if_version(name, source, version)
        if self.after_upload:
            callback, self.after_upload = self.after_upload, None
            callback()


def unavailable():
    raise OSError("synthetic interruption")


class CountyDirectoryStoreTests(unittest.TestCase):
    def setUp(self):
        scratch = self.enterContext(tempfile.TemporaryDirectory())
        self.private = InterleavedStorage(Path(scratch) / "private")
        self.public = InterleavedStorage(Path(scratch) / "public")
        self.store = self.restart()

    def restart(self):
        return CountyDirectoryStore(self.private, self.public)

    def save(self, revision, request_id, county=AITKIN, **changes):
        return self.store.save(county, draft(county, **changes), expected_revision=revision, request_id=request_id)

    def test_private_save_restarts_pending_and_only_allowlist_is_published(self):
        saved = self.save(0, "first")
        self.assertEqual((saved.revision, saved.publication_revision), (1, 1))
        self.assertEqual(read_public_directory(self.public), {})
        restarted = self.restart()
        self.assertEqual(restarted.read_private(AITKIN).draft, draft())
        self.assertFalse(restarted.publication_status(AITKIN).confirmed)
        self.assertTrue(restarted.publish(AITKIN).confirmed)

        public = read_public_directory(self.public)
        self.assertEqual(public["27001"]["policy"], {"text": "Public policy"})
        self.assertEqual(public["27001"]["public_revision"], 1)
        for path in self.public.root.rglob("*.json"):
            self.assertNotIn(SENTINEL, path.read_text(encoding="utf-8"))
        self.assertNotIn("correspondence", json.dumps(public))

    def test_private_only_save_preserves_pending_target_and_never_republishes(self):
        self.save(0, "first")
        private = self.save(1, "private", note="Updated private note")
        self.assertEqual((private.revision, private.publication_revision), (2, None))
        self.assertEqual(self.store.publication_status(AITKIN).target_revision, 1)
        self.assertTrue(self.store.publish(AITKIN).confirmed)
        public = read_public_directory(self.public)
        self.assertIsNone(self.save(2, "private-again", note="Latest private note").publication_revision)
        self.public.before_upload = unavailable
        self.assertTrue(self.store.publish(AITKIN).confirmed)
        self.assertEqual(read_public_directory(self.public), public)

    def test_request_replay_survives_new_saves_and_rejects_key_reuse(self):
        first = self.save(0, "first")
        self.save(1, "second", text="Updated")
        self.assertEqual(self.save(0, "first"), first)
        with self.assertRaisesRegex(ValueError, "request ID"):
            self.save(0, "first", text="Changed replay")
        with self.assertRaises(CountyRevisionConflict):
            self.save(0, "stale-editor")

    def test_concurrent_private_save_cannot_overwrite_winner(self):
        self.private.before_upload = lambda: self.save(0, "winner", text="Winner")
        with self.assertRaises(CountyRevisionConflict):
            self.save(0, "loser", text="Loser")
        self.assertEqual(self.store.read_private(AITKIN).draft["policy"]["text"], "Winner")

    def test_concurrent_identical_save_returns_durable_receipt(self):
        self.private.before_upload = lambda: self.save(0, "same")
        self.assertEqual(self.save(0, "same").revision, 1)
        self.assertEqual(self.store.read_private(AITKIN).revision, 1)

    def test_private_upload_acknowledgement_failure_can_be_replayed(self):
        self.private.after_upload = unavailable
        with self.assertRaises(OSError):
            self.save(0, "retry")
        self.store = self.restart()
        self.assertEqual(self.save(0, "retry").revision, 1)
        self.assertTrue(self.store.publish(AITKIN).confirmed)

    def test_failed_publish_retains_prior_public_version_and_retries(self):
        self.save(0, "first")
        self.store.publish(AITKIN)
        self.save(1, "second", text="Updated")
        self.public.before_upload = unavailable
        with self.assertRaises(OSError):
            self.store.publish(AITKIN)
        self.assertEqual(read_public_directory(self.public)["27001"]["policy"]["text"], "Public policy")
        restarted = self.restart()
        self.assertFalse(restarted.publication_status(AITKIN).confirmed)
        self.assertTrue(restarted.publish(AITKIN).confirmed)
        self.assertEqual(read_public_directory(self.public)["27001"]["policy"]["text"], "Updated")

    def test_successful_upload_with_failed_readback_is_reconciled_on_restart(self):
        self.save(0, "first")
        self.public.after_upload = lambda: setattr(self.public, "before_read", unavailable)
        with self.assertRaises(OSError):
            self.store.publish(AITKIN)
        self.public.before_upload = unavailable
        self.assertTrue(self.restart().publish(AITKIN).confirmed)

    def test_stale_publisher_cannot_replace_a_newer_revision(self):
        self.save(0, "first")

        def publish_newer():
            self.save(1, "second", text="Newer")
            self.store.publish(AITKIN)

        self.public.before_upload = publish_newer
        self.store.publish(AITKIN)
        entry = read_public_directory(self.public)["27001"]
        self.assertEqual((entry["public_revision"], entry["policy"]["text"]), (2, "Newer"))

    def test_interleaved_publications_preserve_both_counties(self):
        self.save(0, "same", county=AITKIN)
        self.save(0, "same", county=ANOKA)
        self.public.before_upload = lambda: self.store.publish(ANOKA)
        self.assertTrue(self.store.publish(AITKIN).confirmed)
        self.assertEqual(set(read_public_directory(self.public)), {"27001", "27003"})

    def test_same_revision_with_different_public_content_cannot_be_confirmed(self):
        self.save(0, "first")
        self.store.publish(AITKIN)
        path = next(self.public.root.rglob("*.json"))
        document = json.loads(path.read_text(encoding="utf-8"))
        document["counties"]["27001"]["policy"]["text"] = "Different policy"
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "content does not match"):
            self.restart().publish(AITKIN)

    def test_changed_private_content_cannot_be_published_under_old_intent(self):
        self.save(0, "first")
        path = next(self.private.root.rglob("*.json"))
        document = json.loads(path.read_text(encoding="utf-8"))
        document["draft"]["policy"]["text"] = "Changed after save"
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match its publication intent"):
            self.restart().publish(AITKIN)
        self.assertEqual(read_public_directory(self.public), {})

    def test_malformed_public_county_entry_fails_closed(self):
        self.save(0, "first")
        self.store.publish(AITKIN)
        path = next(self.public.root.rglob("*.json"))
        document = json.loads(path.read_text(encoding="utf-8"))
        document["counties"]["27001"] = [SENTINEL]
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid stored public county revision"):
            self.restart().publish(AITKIN)

    def test_validation_and_storage_namespace_alias_fail_closed(self):
        with self.assertRaises(ValueError):
            self.store.save(AITKIN, draft(ANOKA), expected_revision=0, request_id="mismatch")
        with self.assertRaises(ValueError):
            self.store.save(AITKIN, [], expected_revision=0, request_id="malformed")
        with self.assertRaises(ValueError):
            CountyDirectoryStore(self.private, LocalStorage(self.private.root))
        self.assertEqual(self.store.read_private(AITKIN).revision, 0)

    def test_exhausted_public_conflicts_preserve_pending_for_later_retry(self):
        self.save(0, "first")

        def conflict():
            self.public.before_upload = conflict
            raise StorageConflictError("synthetic compare-and-swap conflict")

        self.public.before_upload = conflict
        with self.assertRaises(StorageConflictError):
            self.store.publish(AITKIN)
        self.public.before_upload = None
        self.assertFalse(self.store.publication_status(AITKIN).confirmed)
        self.assertTrue(self.restart().publish(AITKIN).confirmed)
