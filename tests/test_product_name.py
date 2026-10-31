"""The official product name is defined once and used on user-facing surfaces."""
import io
import tomllib
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch as datawatch
from clearparcel.datawatch.alert_delivery import build_digest
from clearparcel.datawatch.alert_routing import prepare_alert_preview
from clearparcel.datawatch.dashboard import _snapshot_xlsx, _statewide_snapshot
from clearparcel.datawatch.dashboard_templates import _layout
from clearparcel.datawatch.product import PRODUCT_NAME, page_title

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_NAME = "ClearParcel GIS Data Watchtower"


def _record():
    return {
        "type": "source_error", "worker": "cloud", "source_id": "sample",
        "execution_id": "exec-1", "checked_at": "2026-10-29T00:00:00Z",
        "message": "Source check failed.", "event_key": "a" * 64,
    }


class ProductNameTests(unittest.TestCase):
    def test_official_name_is_defined_once(self):
        self.assertEqual(PRODUCT_NAME, OFFICIAL_NAME)
        self.assertEqual(page_title(None), PRODUCT_NAME)
        self.assertEqual(page_title("Minnesota Counties"), f"Minnesota Counties — {PRODUCT_NAME}")

    def test_header_title_meta_and_footer_use_the_constant(self):
        sentinel = "Sentinel Product Name"
        with patch("clearparcel.datawatch.dashboard_templates.PRODUCT_NAME", sentinel):
            public = _layout(sentinel, "<p>overview</p>", static=True, refresh_seconds=0)
            private = _layout(f"Minnesota Counties — {sentinel}", "<p>counties</p>", static=False, refresh_seconds=0)
        self.assertIn(f"<title>{sentinel}</title>", public)
        self.assertIn(f'<meta name="application-name" content="{sentinel}">', public)
        self.assertIn(f'<div class="brand-eyebrow" aria-hidden="true">{sentinel}</div>', public)
        self.assertIn(f"<h1>{sentinel}</h1>", public)
        self.assertIn(".brand-eyebrow{", public)
        self.assertIn("text-transform:uppercase", public.split(".brand-eyebrow{", 1)[1].split("}", 1)[0])
        self.assertNotIn(sentinel.upper(), public)
        footer = public.split('<footer class="public-footnote">', 1)[1].split("</footer>", 1)[0]
        self.assertIn(sentinel, footer)
        self.assertIn(f"<h1>{sentinel}</h1>", private)
        self.assertIn(f'<meta name="application-name" content="{sentinel}">', private)
        self.assertIn(f"<title>Minnesota Counties — {sentinel}</title>", private)
        private_footer = private.split('<footer class="app-footnote">', 1)[1].split("</footer>", 1)[0]
        self.assertEqual(private_footer, sentinel)
        rendered = _layout(PRODUCT_NAME, "<p>overview</p>", static=True, refresh_seconds=0)
        self.assertIn(f"<h1>{PRODUCT_NAME}</h1>", rendered)
        self.assertNotIn("Minnesota Open Data Watchtower", rendered)
        self.assertNotIn("CLEARPARCEL GIS DATA WATCHTOWER", rendered)

    def test_alert_subject_and_body_use_the_constant(self):
        sentinel = "Sentinel Product Name"
        with patch("clearparcel.datawatch.alert_delivery.PRODUCT_NAME", sentinel):
            digest = build_digest(
                [_record()], routing={"runbook_ref": "docs/operations-triage.md"},
                digest_id="digest-1", created_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
                pending_after=0,
            )
        self.assertEqual(digest["subject"], f"{sentinel} alerts: 1 (source_error)")
        self.assertTrue(digest["body"].startswith(sentinel + "\n"))
        self.assertIn(PRODUCT_NAME, build_digest(
            [_record()], routing={}, digest_id="digest-2",
            created_at=datetime(2026, 10, 29, tzinfo=timezone.utc), pending_after=0,
        )["subject"])

    def test_alert_preview_subject_uses_the_constant(self):
        sentinel = "Sentinel Product Name"
        start = "2026-10-20T10:00:00Z"
        execution = {
            "execution_id": "synthetic-20", "worker": "cloud",
            "started_at": start, "completed_at": "2026-10-20T10:05:00Z", "exit_code": 2,
            "report": {"generated_at": start, "scope": {"type": "fleet"}, "overall": "error",
                       "counts": {"ok": 0, "warn": 0, "error": 1},
                       "sources": {"sample": {"status": "error", "checked_at": "2026-10-20T10:00:01Z"}}},
        }
        with patch("clearparcel.datawatch.alert_routing.PRODUCT_NAME", sentinel):
            preview = prepare_alert_preview(
                [execution], expected_sources=[{"worker": "cloud", "source_id": "sample"}],
                routing={"channel": "email", "recipient": "operator@example.invalid",
                         "escalation_owner": "Synthetic operator", "runbook_ref": "docs/alert-routing.md"},
                as_of="2026-10-20T12:00:00Z",
            )
        subjects = [message["subject"] for message in preview["messages"]]
        self.assertTrue(subjects)
        self.assertTrue(all(subject.startswith(f"{sentinel}: ") for subject in subjects))

    def test_user_agent_carries_the_constant_without_changing_the_repository_url(self):
        self.assertIn(PRODUCT_NAME, datawatch.USER_AGENT)
        self.assertIn("GIS-Data-Watchtower/0.1", datawatch.USER_AGENT)
        self.assertIn("github.com/clearparcel/GIS-Data-Watchtower", datawatch.USER_AGENT)
        self.assertNotIn(" ", datawatch.USER_AGENT.split(" ", 1)[0])

    def test_export_and_package_metadata_use_the_constant(self):
        sentinel = "Sentinel Product Name"
        with patch("clearparcel.datawatch.dashboard_exports.PRODUCT_NAME", sentinel):
            raw = _snapshot_xlsx({"county": "Example", "contacts": [], "direct_sources": []})
        with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
            core = workbook.read("docProps/core.xml").decode("utf-8")
        self.assertIn(f"<dc:title>{sentinel} snapshot</dc:title>", core)
        self.assertIn(f"<dc:creator>{sentinel}</dc:creator>", core)
        self.assertIn("xl/workbook.xml", zipfile.ZipFile(io.BytesIO(raw)).namelist())
        snapshot = _statewide_snapshot({"_render_state": {"sources": {}}})
        self.assertEqual(snapshot["title"], f"{PRODUCT_NAME} snapshot")
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn(PRODUCT_NAME, project["project"]["description"])
        self.assertEqual(project["project"]["name"], "clearparcel-gis-data-watchtower")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith(f"# {PRODUCT_NAME}\n"))


if __name__ == "__main__":
    unittest.main()
