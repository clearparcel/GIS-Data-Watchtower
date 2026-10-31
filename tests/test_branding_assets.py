"""The supplied website identity is embedded locally and works offline."""
import base64
import re
import struct
import unittest
from pathlib import Path

from clearparcel.datawatch.dashboard_templates import _layout
from clearparcel.datawatch.product import PRODUCT_NAME

ASSETS = Path(__file__).resolve().parents[1] / "clearparcel" / "datawatch"


class WatchtowerBrandingTests(unittest.TestCase):
    def test_embedded_favicon_assets_on_private_pages_and_offline_exports(self):
        for static in (False, True):
            page = _layout(PRODUCT_NAME, "<p>test</p>", static=static, static_bundle=static, refresh_seconds=0)
            for size in (16, 32):
                with self.subTest(static=static, size=size):
                    pattern = r'<link rel="icon" type="image/png" sizes="' + str(size) + r'x' + str(size) + r'" href="data:image/png;base64,([^"]+)">'
                    matches = re.findall(pattern, page)
                    self.assertEqual(len(matches), 1)
                    decoded = base64.b64decode(matches[0], validate=True)
                    self.assertEqual(decoded, (ASSETS / f"favicon-{size}.png").read_bytes())
                    self.assertTrue(decoded.startswith(b"\x89PNG\r\n\x1a\n"))
                    self.assertEqual(struct.unpack(">II", decoded[16:24]), (size, size))

    def test_public_header_contains_accessible_home_link_and_logo(self):
        page = _layout(PRODUCT_NAME, "<p>test</p>", static=True, static_bundle=True, refresh_seconds=0)
        header = page.split('<header class="public-header">', 1)[1].split("</header>", 1)[0]
        # The link's name is its visible heading (audit WT31-13): no aria-label
        # that differs from the visible text, a decorative logo, and the
        # repeated eyebrow hidden from assistive technology.
        self.assertIn('<a class="public-brand" href="index.html">', header)
        self.assertNotIn("aria-label", header.split("</a>", 1)[0])
        self.assertIn('class="public-brand-logo"', header)
        self.assertIn('alt=""', header)
        self.assertIn('<div class="brand-eyebrow" aria-hidden="true">', header)
        self.assertIn(f'{PRODUCT_NAME}</h1>', header)
        self.assertLess(header.index('class="public-brand-logo"'), header.index("<h1>"))
        encoded = re.findall(r'<img class="public-brand-logo" src="data:image/webp;base64,([^"]+)"', header)
        self.assertEqual(len(encoded), 1)
        decoded = base64.b64decode(encoded[0], validate=True)
        self.assertEqual(decoded, (ASSETS / "watchtower-logo.webp").read_bytes())
        self.assertTrue(decoded.startswith(b"RIFF"))
        self.assertEqual(decoded[8:12], b"WEBP")

    def test_about_link_name_contains_its_visible_label(self):
        import re as _re
        from unittest.mock import patch
        from clearparcel.datawatch.public_dashboard import render_public_dashboard
        state = {"schema_version": 2, "generated_at": "2026-10-31T12:00:00+00:00", "overall": "ok",
                 "counts": {"ok": 0, "warn": 0, "error": 0}, "workers": {}, "sources": {}}
        with patch("clearparcel.datawatch.public_dashboard._dashboard_state", return_value=state):
            page = render_public_dashboard({"_public_mode": True})
        link = _re.search(r'<a class="public-about-link"[^>]*>(.*?)</a>', page, _re.S)
        self.assertNotIn("aria-label", link.group(0).split(">", 1)[0])
        self.assertTrue(link.group(1).startswith("View on GitHub"))
        self.assertIn('<span class="sr-only"> (opens in a new tab)</span>', link.group(1))
        self.assertIn('<span aria-hidden="true">↗</span>', link.group(1))
        self.assertIn(".sr-only{", page)

    def test_offline_static_export_uses_relative_brand_link(self):
        page = _layout(PRODUCT_NAME, "<p>test</p>", static=True, static_bundle=True, refresh_seconds=0)
        self.assertIn('<a class="public-brand" href="index.html"', page)
        self.assertIn('class="public-brand-logo"', page)
        self.assertIn('.public-brand-logo{width:38px;height:38px}', page)


if __name__ == "__main__":
    unittest.main()
