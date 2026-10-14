"""CSP: only scripts written by Watchtower's templates run; no inline handlers."""
import base64
import contextlib
import hashlib
import io
import re
import tempfile
import unittest
from unittest.mock import patch

from clearparcel.datawatch import dashboard, public_dashboard
from clearparcel.datawatch.csp import SCRIPT_TAG, policy, secure_html, strip_markers, trusted_script_hashes
from clearparcel.datawatch.dashboard_counties import render_counties, render_county
from clearparcel.datawatch.public_dashboard import render_public_dashboard

HANDLER = re.compile(r"<[a-z][^<>]*\son[a-z]+\s*=", re.IGNORECASE)
INLINE_SCRIPT = re.compile(r"<script\b(?![^<>]*\b(?:src|type)\s*=)[^<>]*>(.*?)</script>", re.IGNORECASE | re.S)


def sha(text):
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode()).digest()).decode() + "'"


def script_src(header):
    return next(part for part in header.split(";") if part.strip().startswith("script-src")).split()[1:]


class MarkerTests(unittest.TestCase):
    def test_only_marked_scripts_are_trusted_and_markers_never_leave(self):
        page = f"<p>İ ünïcode</p>{SCRIPT_TAG}ok()</script><p><script>evil()</script></p>{SCRIPT_TAG}ok()</SCRIPT>"
        html, header = secure_html(page)
        self.assertEqual(script_src(header), ["'self'", sha("ok()")])  # deduplicated; evil() not trusted
        self.assertNotIn("data-wt-", html)
        self.assertIn("<script>ok()</script>", html)
        self.assertNotIn(sha("evil()"), header)

    def test_hash_matches_browser_newline_normalization(self):
        self.assertEqual(trusted_script_hashes(f"{SCRIPT_TAG}a()\r\nb()</script>"), [sha("a()\nb()")])

    def test_marker_is_secret_per_process_and_strippable(self):
        self.assertRegex(SCRIPT_TAG, r"^<script data-wt-[0-9a-f]{24}>$")
        self.assertEqual(strip_markers(f'{{"html": "{SCRIPT_TAG}x()</script>"}}'), '{"html": "<script>x()</script>"}')

    def test_policy_directives(self):
        header = policy([sha("x()")], script_origins=("https://cdn.example",), connect_origins=("https://api.example",))
        self.assertEqual(script_src(header), ["'self'", sha("x()"), "https://cdn.example"])
        for directive in ("connect-src 'self' https://api.example", "object-src 'none'",
                          "frame-ancestors 'none'", "base-uri 'none'", "form-action 'self'"):
            self.assertIn(directive, header)
        self.assertNotIn("'unsafe-inline'", " ".join(script_src(header)))


class RenderedPageTests(unittest.TestCase):
    def pages(self):
        state = {"sources": {}, "generated_at": "2026-10-14T00:00:00+00:00"}
        with patch("clearparcel.datawatch.dashboard._dashboard_state", return_value=state), \
                patch("clearparcel.datawatch.public_dashboard._dashboard_state", return_value=state):
            yield "public overview", render_public_dashboard({"_public_mode": True})
            yield "counties", render_counties({"_public_mode": True})
            yield "county", render_county({"_public_mode": True}, "wabasha")
            for key in ("parcel", "address"):
                yield f"gac {key} statewide", dashboard.render_mngac({"_public_mode": True}, key, view="statewide")
                yield f"gac {key} county", dashboard.render_mngac({"_public_mode": True}, key, county="douglas")
            with tempfile.TemporaryDirectory() as td:
                private = {"_render_state": state, "state_file": "unused.json", "history_file": f"{td}/none.jsonl",
                           "_csrf_token": "t", "sources": []}
                yield "private overview", dashboard.render_dashboard(private)
                yield "private counties", render_counties(private)

    def test_pages_use_no_inline_handlers_or_javascript_urls(self):
        for name, page in self.pages():
            with self.subTest(page=name):
                self.assertIsNone(HANDLER.search(page))
                self.assertNotIn("javascript:", page.lower())

    def test_every_executable_inline_script_is_template_written_and_allowed(self):
        for name, page in self.pages():
            with self.subTest(page=name):
                html, header = secure_html(page)
                allowed = script_src(header)
                bodies = INLINE_SCRIPT.findall(html)
                self.assertTrue(bodies)
                for body in bodies:
                    self.assertIn(sha(body), allowed)


class ServerHeaderTests(unittest.TestCase):
    def handler(self, module, serve):
        captured = {}

        class Server:
            def __init__(self, addr, handler, **kwargs):
                captured["handler"] = handler

            def serve_forever(self):
                pass

            def server_close(self):
                pass

        class Cache:
            stale = False

            def refresh(self, **kwargs):
                pass

        with patch.object(module, "_BoundedThreadingHTTPServer", Server), \
                patch.object(public_dashboard, "_PublicStateCache", Cache), \
                patch.object(dashboard, "_dashboard_auth", return_value=(None, "watchtower")), \
                contextlib.redirect_stdout(io.StringIO()):
            serve()
        handler = object.__new__(captured["handler"])
        handler.headers, handler.command, handler.wfile, sent = {}, "GET", io.BytesIO(), {}
        handler.send_response = lambda status: None
        handler.send_header = lambda name, value: sent.__setitem__(name, value)
        handler.end_headers = lambda: None
        return handler, sent

    def test_both_servers_send_the_policy_and_strip_markers(self):
        page = f"<html><head></head><body>{SCRIPT_TAG}go()</script><script>evil()</script></body></html>"
        for module, serve in ((public_dashboard, public_dashboard.serve_public),
                              (dashboard, lambda: dashboard.serve({"sources": []}))):
            with self.subTest(server=module.__name__):
                handler, sent = self.handler(module, serve)
                handler._send(200, page)
                self.assertIn(sha("go()"), sent["Content-Security-Policy"])
                self.assertNotIn(sha("evil()"), sent["Content-Security-Policy"])
                self.assertNotIn(b"data-wt-", handler.wfile.getvalue())
                handler, sent = self.handler(module, serve)
                handler._send(200, '{"fragment": "' + SCRIPT_TAG + '"}', "application/json; charset=utf-8")
                self.assertNotIn(b"data-wt-", handler.wfile.getvalue())


if __name__ == "__main__":
    unittest.main()
