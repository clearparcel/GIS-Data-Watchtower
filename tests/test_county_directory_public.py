import io
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


class CountyDirectoryPublicTests(unittest.TestCase):
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
