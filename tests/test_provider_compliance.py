"""Regression tests for provider-compliance controls in the run loop.

Covers: enabled:false, per-host HTTP 429 stop with persisted Retry-After
backoff, default execution-profile enforcement, and the research dataset as
the sole authority for hold-for-terms decisions.
"""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles
from clearparcel.datawatch.hybrid_validation import candidate_manifest
from clearparcel.datawatch.parcel_access import load_parcel_access


def _ok(source, timeout):
    return {"feature_count": 1, "problems": []}


class ProviderComplianceBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in list(os.environ):
            # Never let a developer's operational overrides redirect test writes.
            if name == "WATCHTOWER_EXECUTION_PROFILE" or name.startswith("CLEARPARCEL_WATCHTOWER_") \
                    or name in {"WATCHTOWER_AGGREGATE_OBJECT", "WATCHTOWER_STORAGE", "WATCHTOWER_GCS_BUCKET"}:
                os.environ.pop(name, None)

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, sources, **extra):
        return {
            "state_file": str(self.root / "state.json"),
            "history_file": str(self.root / "history.jsonl"),
            "retries": 2,
            "retry_delay_seconds": 0,
            "sources": sources,
            **extra,
        }


class EnabledFlagTests(ProviderComplianceBase):
    def test_disabled_source_is_never_polled(self):
        sources = [
            {"id": "on", "name": "On", "adapter": "arcgis_layer", "url": "https://a.example/0", "execution_profiles": ["cloud"]},
            {"id": "off", "name": "Off", "adapter": "arcgis_layer", "url": "https://b.example/0", "execution_profiles": ["cloud"], "enabled": False},
        ]
        with patch.object(watch, "_source_check", side_effect=_ok) as check:
            report = watch.check_sources(self.config(sources), save=False, execution_profile="cloud")
        self.assertEqual([c.args[0]["id"] for c in check.call_args_list], ["on"])
        self.assertEqual(set(report["sources"]), {"on"})
        self.assertEqual(report["skipped_sources"], {"off": "disabled"})

    def test_worker_inventory_matches_candidate_manifest_when_a_source_is_disabled(self):
        sources = [
            {"id": "on", "name": "On", "adapter": "arcgis_layer", "url": "https://a.example/0", "execution_profiles": ["cloud"]},
            {"id": "off", "name": "Off", "adapter": "arcgis_layer", "url": "https://b.example/0", "execution_profiles": ["cloud"], "enabled": False},
        ]
        config = self.config(sources)
        with patch.object(watch, "_source_check", side_effect=_ok):
            report = watch.check_sources(config, save=False, execution_profile="cloud")
        manifest = candidate_manifest(config, {"version": "test", "revision": ""})
        self.assertEqual(sorted(report["sources"]), manifest["expected_sources"]["cloud"])


class RateLimitTests(ProviderComplianceBase):
    def sources(self):
        return [
            {"id": "first", "name": "First", "adapter": "arcgis_layer", "url": "https://gis.example.gov/a/0", "execution_profiles": ["cloud"]},
            {"id": "second", "name": "Second", "adapter": "arcgis_layer", "url": "https://GIS.example.gov./b/0", "execution_profiles": ["cloud"]},
            {"id": "other", "name": "Other host", "adapter": "arcgis_layer", "url": "https://other.example.gov/c/0", "execution_profiles": ["cloud"]},
        ]

    def test_429_stops_every_source_on_the_same_host_for_the_run(self):
        def check(source, timeout):
            if source["id"] == "first":
                raise watch.ProviderRateLimitError("120")
            return _ok(source, timeout)

        with patch.object(watch, "_source_check", side_effect=check) as mocked:
            report = watch.check_sources(self.config(self.sources()), save=False, execution_profile="cloud")
        polled = [c.args[0]["id"] for c in mocked.call_args_list]
        self.assertEqual(polled, ["first", "other"])  # one request to the limited host; no retry
        self.assertEqual(report["sources"]["first"]["status"], "error")
        self.assertTrue(report["sources"]["first"]["rate_limited"])
        second = report["sources"]["second"]
        self.assertEqual(second["status"], "warn")
        self.assertEqual(second["attempts"], 0)
        self.assertEqual(second["deferred"]["reason"], "provider-rate-limit")
        self.assertEqual(report["sources"]["other"]["status"], "ok")

    def test_backoff_persists_and_expires(self):
        config = self.config(self.sources())

        def first_run(source, timeout):
            if source["id"] == "first":
                raise watch.ProviderRateLimitError("120")
            return _ok(source, timeout)

        with patch.object(watch, "_source_check", side_effect=first_run):
            watch.check_sources(config, execution_profile="cloud")
        state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        self.assertIn("gis.example.gov", state["rate_limits"])
        not_before = dt.datetime.fromisoformat(state["rate_limits"]["gis.example.gov"]["not_before"])
        delay = (not_before - dt.datetime.now(dt.timezone.utc)).total_seconds()
        self.assertTrue(60 <= delay <= 125, delay)

        # Next run before not_before: no request to the limited host at all.
        with patch.object(watch, "_source_check", side_effect=_ok) as mocked:
            report = watch.check_sources(config, execution_profile="cloud")
        self.assertEqual([c.args[0]["id"] for c in mocked.call_args_list], ["other"])
        self.assertEqual(report["sources"]["first"]["status"], "error")  # last real result was the 429
        self.assertEqual(report["sources"]["second"]["status"], "warn")

        # After expiry the host is polled again and the backoff is cleared.
        state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        state["rate_limits"]["gis.example.gov"]["not_before"] = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat()
        (self.root / "state.json").write_text(json.dumps(state), encoding="utf-8")
        with patch.object(watch, "_source_check", side_effect=_ok) as mocked:
            report = watch.check_sources(config, execution_profile="cloud")
        self.assertEqual(len(mocked.call_args_list), 3)
        self.assertTrue(all(r["status"] == "ok" for r in report["sources"].values()))
        state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["rate_limits"], {})

    def test_deferred_source_keeps_previous_check_time(self):
        config = self.config(self.sources()[:2])
        with patch.object(watch, "_source_check", side_effect=_ok):
            first = watch.check_sources(config, execution_profile="cloud")
        earlier = first["sources"]["second"]["checked_at"]

        def limited(source, timeout):
            raise watch.ProviderRateLimitError(None)

        with patch.object(watch, "_source_check", side_effect=limited):
            report = watch.check_sources(config, execution_profile="cloud")
        second = report["sources"]["second"]
        self.assertEqual(second["checked_at"], earlier)  # provider-check freshness not advanced
        self.assertEqual(second["feature_count"], 1)  # previous observation retained

    def test_backoff_timing_and_host_never_reach_reports_or_aggregate(self):
        from clearparcel.datawatch.aggregate import merge_states
        config = self.config(self.sources())

        def first_run(source, timeout):
            if source["id"] == "first":
                raise watch.ProviderRateLimitError("600", "gis.example.gov")
            return _ok(source, timeout)

        with patch.object(watch, "_source_check", side_effect=first_run):
            report = watch.check_sources(config, execution_profile="cloud")
        aggregate = merge_states({}, report, "cloud")
        not_before = json.loads((self.root / "state.json").read_text(encoding="utf-8"))["rate_limits"]["gis.example.gov"]["not_before"]
        for document in (report, aggregate):
            text = json.dumps(document)
            self.assertNotIn("rate_limits", document)
            self.assertNotIn(not_before, text)
            self.assertNotIn("not_before", text)
        self.assertNotIn("gis.example.gov", json.dumps(report["sources"]["second"]))

    def test_malformed_retry_after_does_not_abort_the_run(self):
        def check(source, timeout):
            if source["id"] == "first":
                raise watch.ProviderRateLimitError("\xb2" * 3)
            return _ok(source, timeout)

        with patch.object(watch, "_source_check", side_effect=check):
            report = watch.check_sources(self.config(self.sources()), execution_profile="cloud")
        self.assertEqual(report["sources"]["other"]["status"], "ok")
        state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        self.assertIn("gis.example.gov", state["rate_limits"])

    def test_429_from_a_metadata_host_backs_off_that_host(self):
        sources = [
            {"id": "layer", "name": "Layer", "adapter": "arcgis_layer", "url": "https://county.example.gov/0",
             "execution_profiles": ["cloud"], "gac_completeness": {"standard": "parcel", "metadata_url": "https://meta.example.gov/1"}},
            {"id": "statewide", "name": "Statewide", "adapter": "arcgis_layer", "url": "https://meta.example.gov/2",
             "execution_profiles": ["cloud"]},
            {"id": "county-other", "name": "County other", "adapter": "arcgis_layer", "url": "https://county.example.gov/5",
             "execution_profiles": ["cloud"]},
        ]

        def check(source, timeout):
            if source["id"] == "layer":
                raise watch.ProviderRateLimitError("300", "meta.example.gov")
            return _ok(source, timeout)

        with patch.object(watch, "_source_check", side_effect=check) as mocked:
            report = watch.check_sources(self.config(sources), execution_profile="cloud")
        self.assertEqual([c.args[0]["id"] for c in mocked.call_args_list], ["layer", "county-other"])
        self.assertEqual(report["sources"]["statewide"]["deferred"]["reason"], "provider-rate-limit")
        state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(set(state["rate_limits"]), {"meta.example.gov"})

        # Next run: the source whose metadata host is limited is not polled either.
        with patch.object(watch, "_source_check", side_effect=_ok) as mocked:
            watch.check_sources(self.config(sources), execution_profile="cloud")
        self.assertEqual([c.args[0]["id"] for c in mocked.call_args_list], ["county-other"])

    def test_deferral_never_reports_healthier_than_the_last_observation(self):
        config = self.config(self.sources()[:2])

        def limited(source, timeout):
            raise watch.ProviderRateLimitError("120")

        with patch.object(watch, "_source_check", side_effect=limited):
            watch.check_sources(config, execution_profile="cloud")
        with patch.object(watch, "_source_check", side_effect=_ok) as mocked:
            report = watch.check_sources(config, execution_profile="cloud")
        self.assertEqual(mocked.call_count, 0)
        self.assertEqual(report["sources"]["first"]["status"], "error")  # was the 429 source
        self.assertEqual(report["sources"]["second"]["status"], "warn")
        alert = next(a for a in report["active_alerts"] if a["source"] == "second")
        self.assertIn("backoff", alert["message"])
        self.assertTrue(alert["checked_at"])

    def test_rate_limited_source_keeps_its_last_good_observation(self):
        config = self.config(self.sources()[:1])
        with patch.object(watch, "_source_check", return_value={"feature_count": 7, "problems": [], "schema_hash": "abc"}):
            watch.check_sources(config, execution_profile="cloud")
        with patch.object(watch, "_source_check", side_effect=watch.ProviderRateLimitError("120")):
            report = watch.check_sources(config, execution_profile="cloud")
        record = report["sources"]["first"]
        self.assertEqual(record["status"], "error")
        self.assertEqual((record["feature_count"], record["schema_hash"]), (7, "abc"))
        self.assertNotIn("retry-after", record["error"])  # header value is private timing

    def test_stored_backoff_is_rebounded_on_load(self):
        now = dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc)
        active = watch._active_rate_limits(
            {"h.example": {"not_before": "2099-01-01T00:00:00+00:00"},
             "naive.example": {"not_before": "2099-01-01T00:00:00"},
             "expired.example": {"not_before": "2020-01-01T00:00:00+00:00"},
             "bad.example": {"not_before": "soon"}}, now)
        self.assertEqual(set(active), {"h.example"})
        self.assertEqual(dt.datetime.fromisoformat(active["h.example"]["not_before"]), now + dt.timedelta(days=7))

    def test_retry_after_parsing_is_bounded(self):
        now = dt.datetime(2026, 10, 13, 12, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(watch._retry_after_seconds("120", now), 120)
        self.assertEqual(watch._retry_after_seconds("5", now), 60)  # minimum
        self.assertEqual(watch._retry_after_seconds("99999999", now), 7 * 24 * 3600)  # maximum
        self.assertEqual(watch._retry_after_seconds(None, now), 3600)  # default
        self.assertEqual(watch._retry_after_seconds("soon", now), 3600)
        self.assertEqual(watch._retry_after_seconds("Tue, 13 Oct 2026 12:30:00 GMT", now), 1800)
        self.assertEqual(watch._retry_after_seconds(None, now, default=900), 900)
        self.assertEqual(watch._retry_after_seconds("\xb2", now), 3600)  # isdigit() but not int()
        self.assertEqual(watch._retry_after_seconds("9" * 5000, now), 3600)
        self.assertEqual(watch._retry_after_seconds("Mon, 99 Foo 2026 25:61:00 GMT", now), 3600)


class ExecutionProfileTests(ProviderComplianceBase):
    def sources(self):
        return [
            {"id": "cloud-only", "name": "Cloud", "adapter": "arcgis_layer", "url": "https://a.example/0", "execution_profiles": ["cloud"]},
            {"id": "local-only", "name": "Local", "adapter": "arcgis_layer", "url": "https://b.example/0", "execution_profiles": ["local"]},
            {"id": "anywhere", "name": "Any", "adapter": "arcgis_layer", "url": "https://c.example/0", "execution_profiles": ["any"]},
            {"id": "legacy", "name": "Legacy", "adapter": "arcgis_layer", "url": "https://d.example/0"},
        ]

    def polled(self, **kwargs):
        with patch.object(watch, "_source_check", side_effect=_ok) as mocked:
            report = watch.check_sources(self.config(self.sources()), save=False, **kwargs)
        return [c.args[0]["id"] for c in mocked.call_args_list], report

    def test_without_a_profile_assigned_sources_are_not_polled(self):
        polled, report = self.polled()
        self.assertEqual(polled, ["anywhere", "legacy"])
        self.assertEqual(report["skipped_sources"]["local-only"], "execution-profile-unresolved")
        self.assertEqual(report["skipped_sources"]["cloud-only"], "execution-profile-unresolved")

    def test_environment_profile_is_honored(self):
        os.environ["WATCHTOWER_EXECUTION_PROFILE"] = "cloud"
        polled, _ = self.polled()
        self.assertEqual(polled, ["cloud-only", "anywhere"])

    def test_explicit_profile_wins_over_environment(self):
        os.environ["WATCHTOWER_EXECUTION_PROFILE"] = "cloud"
        polled, _ = self.polled(execution_profile="local")
        self.assertEqual(polled, ["local-only", "anywhere"])

    def test_environment_profile_is_normalized(self):
        os.environ["WATCHTOWER_EXECUTION_PROFILE"] = " Local "
        polled, _ = self.polled()
        self.assertEqual(polled, ["local-only", "anywhere"])

    def test_unprofiled_run_preserves_assigned_sources_in_private_state(self):
        config = self.config(self.sources())
        with patch.object(watch, "_source_check", side_effect=_ok):
            watch.check_sources(config, execution_profile="local")
            watch.check_sources(config)
        state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        self.assertIn("local-only", state["sources"])

    def test_cli_publishes_with_the_profile_it_polled(self):
        from clearparcel.datawatch import cli
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.config(self.sources())), encoding="utf-8")
        os.environ["WATCHTOWER_EXECUTION_PROFILE"] = "local"
        with patch.object(watch, "_source_check", side_effect=_ok), \
                patch("clearparcel.datawatch.cloud_job.publish_worker_result") as publish, \
                patch("sys.argv", ["watchtower", "--config", str(config_path), "check", "--json"]), \
                patch("builtins.print"):
            cli.main()
        publish.assert_called_once()
        self.assertEqual(publish.call_args.args[2], "local")
        self.assertEqual(set(publish.call_args.args[1]["sources"]), {"local-only", "anywhere"})

    def test_invalid_profile_is_rejected(self):
        os.environ["WATCHTOWER_EXECUTION_PROFILE"] = "datacenter"
        with self.assertRaisesRegex(ValueError, "unsupported execution profile"):
            self.polled()


class HoldForTermsAuthorityTests(unittest.TestCase):
    def test_profile_decisions_follow_the_research_dataset(self):
        research = load_parcel_access()
        profiles = compose_county_profiles({}, research, now=dt.datetime.now(dt.timezone.utc), freshness_policy=FreshnessPolicy())
        held = {slug for slug, p in profiles.items() if p["access"]["monitoring_decision"] == "hold-for-terms"}
        expected = {p["county"]["slug"] for p in profiles.values()
                    if (research[p["county"]["name"]].get("monitoring") or {}).get("decision") == "hold-for-terms"}
        self.assertEqual(held, expected)
        self.assertGreaterEqual(len(held), 11)

    def test_no_code_override_when_evidence_changes(self):
        research = load_parcel_access()
        research["Lincoln"]["monitoring"]["decision"] = "candidate-low-frequency"
        profiles = compose_county_profiles({}, research, now=dt.datetime.now(dt.timezone.utc), freshness_policy=FreshnessPolicy())
        self.assertEqual(profiles["lincoln"]["access"]["monitoring_decision"], "candidate-low-frequency")


if __name__ == "__main__":
    unittest.main()
