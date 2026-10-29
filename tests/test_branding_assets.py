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
        self.assertIn(f'<a class="public-brand" href="index.html" aria-label="{PRODUCT_NAME} overview">', header)
        self.assertIn(f'alt="{PRODUCT_NAME} logo"', header)
        self.assertIn(f'{PRODUCT_NAME}</h1>', header)
        self.assertLess(header.index('class="public-brand-logo"'), header.index("<h1>"))
        encoded = re.findall(r'<img class="public-brand-logo" src="data:image/webp;base64,([^"]+)"', header)
        self.assertEqual(len(encoded), 1)
        decoded = base64.b64decode(encoded[0], validate=True)
        self.assertEqual(decoded, (ASSETS / "watchtower-logo.webp").read_bytes())
        self.assertTrue(decoded.startswith(b"RIFF"))
        self.assertEqual(decoded[8:12], b"WEBP")

    def test_offline_static_export_uses_relative_brand_link(self):
        page = _layout(PRODUCT_NAME, "<p>test</p>", static=True, static_bundle=True, refresh_seconds=0)
        self.assertIn('<a class="public-brand" href="index.html"', page)
        self.assertIn('class="public-brand-logo"', page)
        self.assertIn('.public-brand-logo{width:38px;height:38px}', page)


if __name__ == "__main__":
    unittest.main()
