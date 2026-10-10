import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from clearparcel.datawatch.build_info import application_identity
from clearparcel.datawatch.dashboard import _public_layout_v2


class BuildIdentityTests(unittest.TestCase):
    def test_checkout_version_takes_precedence_over_stale_installed_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            project_file = Path(folder) / "pyproject.toml"
            project_file.write_text('[project]\nname="clearparcel-gis-data-watchtower"\nversion="1.2.3"\n', encoding="utf-8")
            with patch("clearparcel.datawatch.build_info.PROJECT_FILE", project_file), patch("clearparcel.datawatch.build_info.version", return_value="0.1.0.dev0"):
                identity = application_identity()
        self.assertEqual(identity["version"], "1.2.3")

    def test_packaged_version_ignores_missing_malformed_or_unrelated_projects(self):
        with tempfile.TemporaryDirectory() as folder:
            project_file = Path(folder) / "pyproject.toml"
            with patch("clearparcel.datawatch.build_info.PROJECT_FILE", project_file), patch("clearparcel.datawatch.build_info.version", return_value="1.2.3"):
                for content in (None, "invalid", '[project]\nname="unrelated"\nversion="9.9.9"', '[project]\nname="clearparcel-gis-data-watchtower"\nversion=42'):
                    if content is not None:
                        project_file.write_text(content, encoding="utf-8")
                    self.assertEqual(application_identity()["version"], "1.2.3")

    def test_baked_identity_is_displayed_on_public_pages(self):
        revision = "abc1234" + "0" * 33
        with tempfile.TemporaryDirectory() as folder:
            build_file = Path(folder) / "build_info.json"
            build_file.write_text(json.dumps({"revision": revision, "environment": "preview"}), encoding="utf-8")
            with patch("clearparcel.datawatch.build_info.BUILD_INFO_FILE", build_file), patch("clearparcel.datawatch.build_info.PROJECT_FILE", Path(folder) / "missing.toml"), patch("clearparcel.datawatch.build_info.version", return_value="0.1.1"):
                page = _public_layout_v2("Watchtower", "")
        self.assertIn("v0.1.1 · build abc1234 · Preview", page)
        self.assertIn(f'Source revision: {revision}', page)

    def test_footer_uses_transparent_png_logo(self):
        page = _public_layout_v2("Watchtower", "")
        self.assertIn("data:image/png;base64,", page)

    def test_missing_or_invalid_metadata_does_not_invent_a_build(self):
        with tempfile.TemporaryDirectory() as folder:
            build_file = Path(folder) / "build_info.json"
            with patch("clearparcel.datawatch.build_info.BUILD_INFO_FILE", build_file):
                for content in (None, "broken", "[]", '{"revision":"<script>","environment":"production<script>"}'):
                    if content is not None:
                        build_file.write_text(content, encoding="utf-8")
                    identity = application_identity()
                    self.assertEqual(identity["revision"], "")
                    self.assertEqual(identity["environment"], "development")


if __name__ == "__main__":
    unittest.main()
