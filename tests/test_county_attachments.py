import tempfile
import unittest
from pathlib import Path

from clearparcel.datawatch.county_attachments import CountyAttachments
from clearparcel.datawatch.storage import LocalStorage


PDF = b"%PDF-1.4\nSynthetic scan fixture\n%%EOF\n"


class CountyAttachmentTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.private = LocalStorage(root / "private")
        self.attachments = CountyAttachments(self.private)

    def test_restart_retains_quarantine_and_clean_verdict_is_required(self):
        item = self.attachments.upload("27001", "policy", None, "County policy.pdf", PDF)
        self.assertEqual(item["status"], "pending")
        restarted = CountyAttachments(self.private)
        self.assertEqual(restarted.info("27001", item["id"])["status"], "pending")
        self.assertIsNone(restarted.download("27001", item["id"]))
        self.assertIsNone(restarted.info("27003", item["id"]))
        self.assertEqual(restarted.scan("27001", item["id"], lambda data: data == PDF)["status"], "clean")
        metadata, data = self.attachments.download("27001", item["id"])
        self.assertEqual((metadata["filename"], data), ("County policy.pdf", PDF))

    def test_rejected_file_and_failed_scan_never_become_downloadable(self):
        item = self.attachments.upload("27001", "correspondence", "event-1", "Email.pdf", PDF)

        def unavailable(_data):
            raise OSError("synthetic scanner outage")

        with self.assertRaises(OSError):
            self.attachments.scan("27001", item["id"], unavailable)
        self.assertIsNone(self.attachments.download("27001", item["id"]))
        self.assertEqual(self.attachments.scan("27001", item["id"], lambda _: False)["status"], "rejected")
        self.assertEqual(self.attachments.scan("27001", item["id"], lambda _: True)["status"], "rejected")
        self.assertIsNone(self.attachments.download("27001", item["id"]))

    def test_filename_content_and_association_are_validated(self):
        for filename, data, kind, event in [
            ("../escape.pdf", PDF, "policy", None),
            ("Policy.html", PDF, "policy", None),
            ("Policy.pdf", b"<html>", "policy", None),
            ("Policy.pdf", PDF, "correspondence", None),
            ("Policy.pdf", PDF, "policy", "event-1"),
        ]:
            with self.subTest(filename=filename, kind=kind, event=event):
                with self.assertRaises(ValueError):
                    self.attachments.upload("27001", kind, event, filename, data)
        self.assertEqual(list(self.private.root.rglob("*.bin")), [])
