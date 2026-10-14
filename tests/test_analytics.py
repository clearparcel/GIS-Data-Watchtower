"""Optional PostHog analytics for the public dashboard: dormant unless explicitly configured."""
import os
import unittest
from unittest.mock import patch

from clearparcel.datawatch.analytics import posthog_config, posthog_csp_sources, posthog_html


class PostHogIntegrationTests(unittest.TestCase):
    def test_analytics_is_dormant_without_project_token(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(posthog_config())
            self.assertIsNone(posthog_csp_sources())
            self.assertEqual(posthog_html(page="Overview", version="1", build="abc", environment="production"), "")

    def test_token_alone_does_not_enable_analytics_without_ip_discard_confirmation(self):
        with patch.dict(os.environ, {
            "WATCHTOWER_POSTHOG_PROJECT_TOKEN": "watchtower_test_project_token_123456789",
        }, clear=True):
            self.assertIsNone(posthog_config())

    def test_analytics_uses_privacy_first_configuration(self):
        env = {
            "WATCHTOWER_POSTHOG_PROJECT_TOKEN": "watchtower_test_project_token_123456789",
            "WATCHTOWER_POSTHOG_HOST": "https://us.i.posthog.com",
            "WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            config = posthog_config()
            html = posthog_html(page="MN GAC", version="1", build="abc", environment="production")
            self.assertEqual(config["api_host"], "https://us.i.posthog.com")
            self.assertEqual(posthog_csp_sources()[1], "https://us.i.posthog.com")
        for required in (
            "autocapture:false", "capture_pageview:false", "capture_pageleave:false",
            "capture_exceptions:false", "disable_session_recording:true",
            "person_profiles:'identified_only'", "persistence:'memory'",
            "advanced_disable_flags:true", "watchtower page viewed",
        ):
            self.assertIn(required, html)
        self.assertIn("$current_url", html)
        self.assertNotIn("posthog.identify", html)

    def test_analytics_rejects_non_https_host(self):
        env = {
            "WATCHTOWER_POSTHOG_PROJECT_TOKEN": "watchtower_test_project_token_123456789",
            "WATCHTOWER_POSTHOG_HOST": "http://posthog.example.com",
            "WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(posthog_config())

    def test_custom_script_url_must_be_https_array_js(self):
        base = {"WATCHTOWER_POSTHOG_PROJECT_TOKEN": "watchtower_test_project_token_123456789",
                "WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED": "1", "WATCHTOWER_POSTHOG_HOST": "https://eu.i.posthog.com"}
        with patch.dict(os.environ, base, clear=True):
            self.assertEqual(posthog_config()["script_origin"], "https://eu-assets.i.posthog.com")
        for script_url, ok in (("https://cdn.example.com/static/array.js", True),
                               ("http://cdn.example.com/static/array.js", False),
                               ("https://cdn.example.com/static/other.js", False),
                               ("https://user:pw@cdn.example.com/array.js", False)):
            with self.subTest(script_url=script_url), \
                    patch.dict(os.environ, {**base, "WATCHTOWER_POSTHOG_SCRIPT_URL": script_url}, clear=True):
                self.assertEqual(posthog_config() is not None, ok)

    def test_self_hosted_api_requires_an_explicit_script_url(self):
        env = {"WATCHTOWER_POSTHOG_PROJECT_TOKEN": "watchtower_test_project_token_123456789",
               "WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED": "yes", "WATCHTOWER_POSTHOG_HOST": "https://ph.example.org"}
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(posthog_config())

    def test_malformed_tokens_are_ignored(self):
        for token in ("short", "has space in it 123", "x" * 201, "<script>alert(1)</script>"):
            env = {"WATCHTOWER_POSTHOG_PROJECT_TOKEN": token, "WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED": "true"}
            with self.subTest(token=token[:20]), patch.dict(os.environ, env, clear=True):
                self.assertIsNone(posthog_config())


if __name__ == "__main__":
    unittest.main()
