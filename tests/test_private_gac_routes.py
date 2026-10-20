"""Hosted-wrapper routing regressions over synthetic saved observations."""
import hashlib
import html
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from clearparcel.datawatch import dashboard
from scripts.migrate_private_gac_wrapper import LEGACY_ROUTES, REPLACEMENT, migrate
from test_gac_county_view import county_state


# Minimal reproduction of the retained wrapper's request boundary. No cloud
# storage bootstrap, deployment settings, authentication material or providers.
PREFIX = b'''class Handler:
    def do_GET(self):
        import urllib.parse
        p=urllib.parse.urlparse(self.path)
'''
SUFFIX = b'''        return self.send_text(404,"Not found","text/plain; charset=utf-8")
    def do_POST(self):
        return self.send_text(405,"Read-only dashboard","text/plain; charset=utf-8")
'''


class PrivateGACRoutesTests(unittest.TestCase):
    def setUp(self):
        self.original = PREFIX + LEGACY_ROUTES + SUFFIX
        self.candidate = migrate(self.original, hashlib.sha256(self.original).hexdigest())

    def request(self, path, *, source=None, key="parcel", method="do_GET", state=None):
        namespace = {"dashboard": dashboard, "config": {}, "json": json,
                     "readonly_html": lambda page: "<!-- readonly wrapper -->" + page}
        exec(compile(source or self.candidate, "synthetic_wrapper.py", "exec"), namespace)
        handler = namespace["Handler"]()
        handler.path = path
        replies = []
        handler.send_text = lambda status, body, ctype="text/html; charset=utf-8": replies.append(
            (status, body, ctype))
        if state is None:
            state, _, _ = county_state(key)
        before = json.dumps(state, sort_keys=True)
        with patch.object(dashboard, "_dashboard_state", return_value=state):
            getattr(handler, method)()
        self.assertEqual(json.dumps(state, sort_keys=True), before)
        self.assertEqual(len(replies), 1)
        return replies[0]

    def test_retained_handler_reproduces_lost_selection_and_candidate_fixes_it(self):
        path = "/mngac?standard=parcel&view=county&county=Douglas"
        _, old, _ = self.request(path, source=self.original)
        self.assertIn("Explore county results", old)
        self.assertNotIn("Douglas County — Parcels", old)
        status, page, ctype = self.request(path)
        self.assertEqual((status, ctype), (200, "text/html; charset=utf-8"))
        self.assertIn("<!-- readonly wrapper -->", page)
        self.assertIn("Douglas County — Parcels", page)
        self.assertIn('value="Douglas"', page)
        self.assertIn(">5</td><td>20</td><td>25.00%</td>", page)
        self.assertNotIn("Explore county results", page)

    def test_form_map_and_standard_scope_links_preserve_selection(self):
        for key in ("parcel", "address", "road"):
            for county in ("douglas", "Douglas County"):
                with self.subTest(key=key, county=county):
                    query = urlencode({"standard": key, "view": "county", "county": county})
                    status, page, _ = self.request("/mngac?" + query, key=key)
                    self.assertEqual(status, 200)
                    self.assertIn("Douglas County", page)
                    for target in ("parcel", "address", "road"):
                        self.assertIn(f"standard={target}&view=county&county=douglas",
                                      html.unescape(page))
            _, statewide, _ = self.request(
                f"/mngac?standard={key}&view=statewide&county=douglas", key=key)
            heading = "Statewide MN GAC field completeness" if key == "parcel" else "Statewide field completeness"
            self.assertTrue(heading in statewide, f"{key}: statewide heading missing")
            self.assertIn("99.00%", statewide)
            self.assertIn(f"standard={key}&view=county&county=douglas",
                          html.unescape(statewide))

    def test_default_landing_retains_all_county_suggestions(self):
        status, page, _ = self.request("/mngac")
        self.assertEqual(status, 200)
        self.assertIn("Explore county results", page)
        options = page.split('<datalist id="gac-county-options">')[1].split("</datalist>")[0]
        self.assertEqual(options.count("<option"), 87)
        self.assertIn('<option value="Cass">', options)

    def test_invalid_selections_return_400_without_echoing_input(self):
        for query in ("standard=unsupported", "county=%3Cscript%3E", "view=invalid"):
            status, body, ctype = self.request("/mngac?" + query)
            self.assertEqual((status, ctype), (400, "text/plain; charset=utf-8"))
            self.assertNotIn("<script>", body)
            self.assertNotIn("readonly wrapper", body)
        for path in ("/mngac.json", "/mngac.csv"):
            self.assertEqual(self.request(path + "?standard=unsupported")[0], 400)

    def test_missing_county_observation_is_not_zero(self):
        status, page, _ = self.request("/mngac?county=aitkin")
        self.assertEqual(status, 200)
        self.assertIn("Not in MnGeo Open Parcels", page)
        self.assertNotIn(">0.00%", page)
        status, page, _ = self.request("/mngac?county=douglas&standard=road", state={})
        self.assertEqual(status, 200)
        self.assertIn("Statewide results unavailable", page)

    def test_exports_use_selected_standard_and_handle_missing_data(self):
        for key in ("parcel", "address", "road"):
            state, field, _ = county_state(key)
            status, payload, ctype = self.request(f"/mngac.json?standard={key}", state=state)
            self.assertEqual((status, ctype), (200, "application/json; charset=utf-8"))
            self.assertEqual(json.loads(payload)["standard_key"], key)
            status, payload, ctype = self.request(f"/mngac.csv?standard={key}", state=state)
            self.assertEqual((status, ctype), (200, "text/csv; charset=utf-8"))
            self.assertIn(field["field"], payload)
            self.assertNotIn("readonly wrapper", payload)
            for suffix in (".json", ".csv"):
                self.assertEqual(self.request(f"/mngac{suffix}?standard={key}", state={})[0], 404)

    def test_migration_preserves_other_routes_and_rejects_drift(self):
        self.assertEqual(self.candidate, PREFIX + REPLACEMENT + SUFFIX)
        windows_source = self.original.replace(b"\n", b"\r\n")
        windows_candidate = migrate(windows_source, hashlib.sha256(windows_source).hexdigest())
        self.assertEqual(windows_candidate, self.candidate.replace(b"\n", b"\r\n"))
        self.assertEqual(self.request("/unrelated")[0], 404)
        self.assertEqual(self.request("/mngac", method="do_POST")[0], 405)
        for source, expected in (
            (self.original, "0" * 64),
            (self.candidate, hashlib.sha256(self.candidate).hexdigest()),
            (self.original + LEGACY_ROUTES, hashlib.sha256(self.original + LEGACY_ROUTES).hexdigest()),
        ):
            with self.assertRaises(ValueError):
                migrate(source, expected)

    def test_migration_cli_never_overwrites_input_or_existing_output(self):
        script = Path(__file__).resolve().parents[1] / "scripts/migrate_private_gac_wrapper.py"
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "original.py"
            target = Path(temp) / "candidate.py"
            source.write_bytes(self.original)
            command = [sys.executable, str(script), "--input", str(source), "--output", str(target),
                       "--expected-sha256", hashlib.sha256(self.original).hexdigest()]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), self.candidate)
            for destination in (target, source):
                retry = command.copy()
                retry[retry.index("--output") + 1] = str(destination)
                self.assertNotEqual(subprocess.run(retry, capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), self.original)
            self.assertEqual(target.read_bytes(), self.candidate)
