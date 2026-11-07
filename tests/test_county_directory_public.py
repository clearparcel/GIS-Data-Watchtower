import io
import contextlib
import copy
import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch.dashboard import render_county
from clearparcel.datawatch.dashboard_exports import _snapshot_csv, _snapshot_xlsx
from clearparcel.datawatch.county_directory_store import CountyDirectoryStore, read_public_directory
from clearparcel.datawatch.county_profiles import county_identities
from clearparcel.datawatch.public_dashboard import _PublicStateCache
from clearparcel.datawatch.storage import LocalStorage
from clearparcel.datawatch import public_dashboard


class CountyDirectoryPublicTests(unittest.TestCase):
    def test_published_access_is_consistent_across_routes_and_exports_after_apply(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        county = county_identities()["aitkin"]
        public = LocalStorage(root / "public")
        store = CountyDirectoryStore(LocalStorage(root / "private"), public)
        self.enterContext(patch.dict("os.environ", {"WATCHTOWER_PUBLIC_WORKDIR": str(root / "cache"),
                                                   "WATCHTOWER_STORAGE": "local"}))
        cache = _PublicStateCache()
        cache.public_path.write_text('{"sources":{}}', encoding="utf-8")
        before = cache.county_snapshot("aitkin")
        original_view = copy.deepcopy(cache.view())
        captured = {}

        class Server:
            def __init__(self, addr, handler, **kwargs):
                captured["handler"] = handler

            def serve_forever(self):
                pass

            def server_close(self):
                pass

        with patch.object(public_dashboard, "_PublicStateCache", return_value=cache), \
                patch.object(cache, "refresh"), \
                patch.object(public_dashboard, "hosted_public_county_bucket", return_value=None), \
                patch.object(public_dashboard, "_BoundedThreadingHTTPServer", Server), \
                contextlib.redirect_stdout(io.StringIO()):
            public_dashboard.serve_public(county_directory_root=public.root)

        def get(path):
            handler = object.__new__(captured["handler"])
            handler.path, handler.headers, handler.command = path, {}, "GET"
            replies = []
            handler._send = lambda status, body, *args: replies.append((status, body))
            with patch.object(cache, "refresh"):
                handler.do_GET()
            return replies[0]

        draft = {"fips": county["fips"], "contacts": [{"name": "Synthetic <GIS>"}],
                 "correspondence": [{"notes": "PRIVATE_SENTINEL"}],
                 "access": {"parcel_polygons": {
                     "classification": "open", "county_direct_note": "Terms still need review <note>",
                     "methods": [{"kind": "direct_rest", "url": "https://example.org/FeatureServer/0",
                                  "evidence_date": "2026-11-06", "scope": "Synthetic parcel polygons"}],
                     "restrictions": {"status": "restricted", "text": "Attribution <required>"}}}}
        draft["access"]["road_centerlines"] = {
            "classification": "open", "methods": [{"kind": "direct_download",
                "url": "https://example.org/roads.zip", "evidence_date": "2026-11-06", "scope": "Roads"}]}
        draft["access"]["address_points"] = {
            "classification": "open", "methods": [{"kind": "other", "description": "Public portal",
                "url": "https://example.org/addresses", "evidence_date": "2026-11-06", "scope": "Addresses"}]}
        prior_revision = json.loads(get("/api/summary")[1])["content_revision"]
        for number, classification, label in ((1, "open", "Open GIS Data · Direct REST"),
                                               (2, "fee", "Fee Based GIS Data"),
                                               (3, "unknown", "Unknown")):
            with self.subTest(classification=classification):
                draft["access"]["parcel_polygons"]["classification"] = classification
                if classification != "open":
                    draft["access"]["parcel_polygons"]["methods"] = []
                store.save(county, draft, expected_revision=number - 1, request_id=str(number))
                store.publish(county)
                revision = json.loads(get("/api/summary")[1])["content_revision"]
                self.assertNotEqual(revision, prior_revision)
                self.assertEqual(get(f"/api/county-profile?slug=aitkin&revision={prior_revision}")[0], 409)
                prior_revision = revision
                status, panel = get(f"/api/county-profile?slug=aitkin&revision={revision}")
                self.assertEqual(status, 200)
                page = get("/county?slug=aitkin")[1]
                index = get("/counties")[1]
                row = index.split('data-name="aitkin"', 1)[1].split('</tr>', 1)[0]
                self.assertIn({"open": "Open GIS data · Connect in GIS software", "fee": "Fee-based parcel data", "unknown": "Access not confirmed"}[classification], row)
                self.assertNotIn("not yet researched", row)
                self.assertIn(label.replace("Direct REST", "Connect in GIS software"), panel)
                self.assertLess(page.index("County GIS data access"), page.index("Earlier parcel-access research"))
                self.assertEqual(page.count('<h2>County GIS data access</h2>'), 1)
                for output in (page, panel):
                    self.assertIn("Terms still need review &lt;note&gt;", output)
                    self.assertIn("Attribution &lt;required&gt;", output)
                    self.assertNotIn("PRIVATE_SENTINEL", output)
                    if classification != "open":
                        self.assertNotIn("https://example.org/FeatureServer/0", output)
                snapshot = cache.county_snapshot("aitkin")
                self.assertEqual(snapshot["parcel_access"], before["parcel_access"])
                self.assertEqual(snapshot["parcel_source_profile"]["monitoring"], before["parcel_source_profile"]["monitoring"])
                self.assertEqual(snapshot["direct_sources"], before["direct_sources"])
                self.assertEqual(snapshot["access_field_basis"]["parcel_source_profile.access"], "packaged_research")
                exported = next(csv.DictReader(io.StringIO(_snapshot_csv(snapshot))))
                self.assertEqual(exported["profile_published_parcel_access"], label)
                self.assertEqual(exported["profile_published_road_access"], "Open GIS Data · Direct Download")
                self.assertEqual(exported["profile_published_address_access"], "Open GIS Data · Other")
                self.assertEqual(exported["county_direct_access_basis"], "packaged_research")
                profiles_csv = get("/county-profiles.csv")[1]
                summary = next(row for row in csv.DictReader(io.StringIO(profiles_csv)) if row["county_slug"] == "aitkin")
                self.assertEqual(summary["published_parcel_access"], label)
                with zipfile.ZipFile(io.BytesIO(_snapshot_xlsx(snapshot))) as workbook:
                    sheet = workbook.read("xl/worksheets/sheet1.xml").decode()
                self.assertIn(label, sheet)
                self.assertIn("County-direct access (packaged research)", sheet)
        self.assertEqual(cache.view(), original_view, "Directory composition must not mutate the monitoring cache")

    def test_mngeo_only_access_does_not_claim_direct_rest_or_change_research(self):
        from clearparcel.datawatch.county_directory import project_public_county
        from clearparcel.datawatch.county_directory_view import published_access_summary
        county = county_identities()["aitkin"]
        directory = project_public_county(county, {"fips": county["fips"], "access": {"parcel_polygons": {
            "classification": "open", "methods": [{"kind": "mngeo_open", "url": "https://example.org/open",
                "evidence_date": "2026-11-06", "scope": "Statewide compilation"}]}}})
        self.assertEqual(published_access_summary(directory), "Open GIS Data · MnGeo open")

    def test_page_and_exports_follow_the_confirmed_revision_and_omit_private_fields(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        county = county_identities()["aitkin"]
        public = LocalStorage(root / "public")
        store = CountyDirectoryStore(LocalStorage(root / "private"), public)
        self.enterContext(patch.dict("os.environ", {"WATCHTOWER_PUBLIC_WORKDIR": str(root / "cache"),
                                                   "WATCHTOWER_STORAGE": "local"}))
        cache = _PublicStateCache()
        cache.public_path.write_text('{"sources":{}}', encoding="utf-8")
        cache.directory_storage = public
        before = cache.county_snapshot("aitkin")
        self.assertNotIn("county_directory", before)
        draft = {
            "fips": county["fips"],
            "contacts": [{"name": "New <GIS> contact", "email": "contact@example.org"}],
            "policy": {"text": "=PUBLIC_POLICY <script>", "url": "https://example.org/policy",
                       "attachment_id": "PRIVATE_SENTINEL"},
            "correspondence": [{"notes": "PRIVATE_SENTINEL"}],
        }
        store.save(county, draft, expected_revision=0, request_id="first")
        self.assertNotIn("county_directory", cache.county_snapshot("aitkin"))
        store.publish(county)
        published = cache.county_snapshot("aitkin")
        page = render_county({**cache.config, "_county_directory": cache.directory()}, "aitkin")
        self.assertIn("New &lt;GIS&gt; contact", page)
        self.assertIn("=PUBLIC_POLICY &lt;script&gt;", page)
        self.assertNotIn("=PUBLIC_POLICY <script>", page)
        self.assertIn("Road Centerlines", page)
        self.assertIn("Use restrictions not yet reviewed", page)
        self.assertEqual(published["county_directory"]["public_revision"], 1)
        self.assertEqual(published["contacts"][0]["name"], "New <GIS> contact")
        with zipfile.ZipFile(io.BytesIO(_snapshot_xlsx(published))) as workbook:
            xml = "".join(workbook.read(name).decode() for name in workbook.namelist())
        for output in (page, json.dumps(published), _snapshot_csv(published), xml):
            self.assertIn("PUBLIC_POLICY", output)
            self.assertNotIn("PRIVATE_SENTINEL", output)
        self.assertIn("'=PUBLIC_POLICY", _snapshot_csv(published))

        store.save(county, {**draft, "contacts": [], "policy": {"text": "Second revision"}},
                   expected_revision=1, request_id="second")
        store.publish(county)
        refreshed = cache.county_snapshot("aitkin")
        self.assertEqual(refreshed["contacts"], [])
        self.assertEqual(refreshed["county_directory"]["public_revision"], 2)
        self.assertEqual(cache.snapshot()["counties"][0]["county_directory"]["policy"]["text"], "Second revision")

        directory_file = next(public.root.rglob("directory.json"))
        corrupted = json.loads(directory_file.read_text(encoding="utf-8"))
        corrupted["counties"]["27001"]["policy"]["attachment_id"] = "PRIVATE_SENTINEL"
        directory_file.write_text(json.dumps(corrupted), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid stored public county content"):
            read_public_directory(public)
