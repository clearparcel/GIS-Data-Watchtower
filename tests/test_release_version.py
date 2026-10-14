import unittest
from unittest.mock import patch
from pathlib import Path

from scripts import check_release_version as version_check


class ReleaseVersionTests(unittest.TestCase):
    def test_canonical_candidate_version_is_valid_semver(self):
        self.assertEqual(len(version_check.version_tuple(version_check.candidate_version())), 3)

    def test_public_html_accepts_old_and_new_footer(self):
        self.assertEqual(version_check.version_from_public_html(
            '<footer><strong class="application-version" title="Source revision: abc">v0.2.0 · build bbc364d · Production</strong></footer>'), "0.2.0")
        self.assertEqual(version_check.version_from_public_html(
            '<footer><strong class="application-version">v0.2.1</strong></footer>'), "0.2.1")

    def test_rejects_missing_ambiguous_or_malformed_footer(self):
        for html in (
            "<html>v0.2.0</html>",
            '<strong class="application-version">unknown</strong>',
            '<strong class="application-version">v01.2.3</strong>',
            '<strong class="application-version">v0.2.0</strong><strong class="application-version">v0.2.1</strong>',
        ):
            with self.subTest(html=html), self.assertRaises(ValueError):
                version_check.version_from_public_html(html)

    def test_bump_required_per_coordinated_release(self):
        version_check.require_new_version("0.2.1", "0.2.0")
        version_check.require_new_version("0.3.0", "0.2.1")
        for candidate, deployed in (
            ("0.2.1", "0.2.1"),
            ("0.2.0", "0.2.1"),
            ("0.2.0", "0.3.0"),
            ("v0.2.2", "0.2.1"),
            ("0.02.2", "0.2.1"),
        ):
            with self.subTest(candidate=candidate, deployed=deployed), self.assertRaises(ValueError):
                version_check.require_new_version(candidate, deployed)

    def test_main_blocks_closed_when_live_version_unverifiable(self):
        with patch.object(version_check, "live_version", side_effect=ValueError("public page unavailable")):
            self.assertEqual(version_check.main([]), 1)

    def test_main_blocks_closed_on_truncated_response(self):
        import http.client
        with patch.object(version_check, "live_version", side_effect=http.client.IncompleteRead(b"partial")), \
                patch("sys.stderr"):
            self.assertEqual(version_check.main([]), 1)

    def test_main_passes_with_bumped_release(self):
        with patch.object(version_check, "live_version", return_value="0.2.0"):
            self.assertEqual(version_check.main([]), 0)


if __name__ == "__main__":
    unittest.main()
