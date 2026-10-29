"""Hosted pages reference cacheable brand images; offline exports keep them embedded."""
import io
import re
import unittest
from email.message import Message
from pathlib import Path

from clearparcel.datawatch.brand_assets import asset_url, dispatch_brand_asset
from clearparcel.datawatch.dashboard_templates import _layout
from clearparcel.datawatch.product import PRODUCT_NAME

ASSETS = Path(__file__).resolve().parents[1] / "clearparcel" / "datawatch"
_FILES = {
    "clearparcel-logo": "clearparcel-logo-transparent.png",
    "watchtower-logo": "watchtower-logo.webp",
    "favicon-16": "favicon-16.png",
    "favicon-32": "favicon-32.png",
}


class _Handler:
    def __init__(self, command="GET", if_none_match=None):
        self.command = command
        self.headers = Message()
        if if_none_match:
            self.headers["If-None-Match"] = if_none_match
        self.wfile = io.BytesIO()
        self.status = None
        self.sent = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent[name] = value

    def end_headers(self):
        pass


class HostedBrandAssetTests(unittest.TestCase):
    def test_hosted_page_references_versioned_urls_instead_of_embedding(self):
        page = _layout(PRODUCT_NAME, "<p>test</p>", static=True, refresh_seconds=0)
        self.assertNotIn("data:image/", page)
        for key in _FILES:
            with self.subTest(key=key):
                self.assertRegex(asset_url(key), r"^/assets/" + key + r"-[0-9a-f]{12}\.(png|webp)$")
                self.assertIn(asset_url(key), page)

    def test_hosted_page_is_much_smaller_than_offline_export(self):
        hosted = _layout(PRODUCT_NAME, "<p>test</p>", static=True, refresh_seconds=0)
        bundle = _layout(PRODUCT_NAME, "<p>test</p>", static=True, static_bundle=True, refresh_seconds=0)
        embedded = sum((ASSETS / name).stat().st_size for name in _FILES.values())
        self.assertGreater(len(bundle) - len(hosted), embedded)

    def test_offline_export_stays_self_contained(self):
        bundle = _layout(PRODUCT_NAME, "<p>test</p>", static=True, static_bundle=True, refresh_seconds=0)
        self.assertNotIn("/assets/", bundle)
        self.assertEqual(len(re.findall(r'src="data:image/', bundle)), 2)
        self.assertEqual(len(re.findall(r'href="data:image/png', bundle)), 2)

    def test_hosted_asset_bytes_and_immutable_cache_headers(self):
        for key, filename in _FILES.items():
            with self.subTest(key=key):
                handler = _Handler()
                self.assertTrue(dispatch_brand_asset(handler, asset_url(key)))
                self.assertEqual(handler.status, 200)
                self.assertEqual(handler.wfile.getvalue(), (ASSETS / filename).read_bytes())
                self.assertEqual(handler.sent["Cache-Control"], "public, max-age=31536000, immutable")
                self.assertEqual(handler.sent["Content-Type"], "image/webp" if filename.endswith(".webp") else "image/png")
                self.assertEqual(handler.sent["X-Content-Type-Options"], "nosniff")
                self.assertEqual(handler.sent["Content-Length"], str((ASSETS / filename).stat().st_size))

    def test_head_and_conditional_requests_send_no_body(self):
        url = asset_url("watchtower-logo")
        head = _Handler("HEAD")
        dispatch_brand_asset(head, url)
        self.assertEqual((head.status, head.wfile.getvalue()), (200, b""))
        cached = _Handler(if_none_match=head.sent["ETag"])
        dispatch_brand_asset(cached, url)
        self.assertEqual((cached.status, cached.wfile.getvalue()), (304, b""))
        self.assertNotIn("Content-Length", cached.sent)

    def test_unknown_or_stale_asset_paths_are_rejected(self):
        stale = re.sub(r"-[0-9a-f]{12}\.", "-000000000000.", asset_url("clearparcel-logo"))
        for path in ("/assets/", stale, "/assets/clearparcel-logo.webp", "/assets/../watch.py",
                     "/assets/favicon-16.png", asset_url("favicon-16") + "/x"):
            with self.subTest(path=path):
                handler = _Handler()
                self.assertTrue(dispatch_brand_asset(handler, path))
                self.assertEqual(handler.status, 404)
                self.assertEqual(handler.sent["Cache-Control"], "no-store")
                self.assertEqual(handler.wfile.getvalue(), b"Not found")

    def test_other_paths_fall_through(self):
        for path in ("/", "/mngac", "/assetsx", "/favicon.ico"):
            with self.subTest(path=path):
                handler = _Handler()
                self.assertFalse(dispatch_brand_asset(handler, path))
                self.assertIsNone(handler.status)


if __name__ == "__main__":
    unittest.main()
