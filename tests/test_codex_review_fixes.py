"""Regressions for findings from the independent Codex review of the v0.3.0 stack."""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import aggregate, dashboard, file_lock, watch
from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles
from clearparcel.datawatch.dashboard_templates import _accessible_tables
from clearparcel.datawatch.parcel_access import load_parcel_access

NOW = dt.datetime(2026, 10, 13, 12, 0, tzinfo=dt.timezone.utc)


def stamp(minutes=0):
    return (NOW + dt.timedelta(minutes=minutes)).isoformat()


def report(minutes, sources, scope="fleet", **extra):
    return {"generated_at": stamp(minutes), "overall": "ok", "scope": {"type": scope},
            "sources": {sid: {"id": sid, "status": "ok", "checked_at": stamp(minutes)} for sid in sources}, **extra}


class RunConfig(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        env = patch.dict(os.environ, {"WATCHTOWER_EXECUTION_PROFILE": "", "WATCHTOWER_ALLOW_INVENTORY_SHRINK": ""})
        env.start()
        self.addCleanup(env.stop)

    def config(self, sources):
        return {"state_file": str(self.root / "state.json"), "history_file": str(self.root / "history.jsonl"),
                "alerts_file": str(self.root / "alerts.json"), "alerts_text_file": str(self.root / "alerts.txt"),
                "retries": 0, "sources": sources}


class RetryAfterTests(unittest.TestCase):
    def test_long_backoffs_are_kept_in_full_and_flagged_for_review(self):
        with tempfile.TemporaryDirectory() as td:
            config = {"state_file": str(Path(td) / "state.json"), "history_file": str(Path(td) / "h.jsonl"),
                      "alerts_file": str(Path(td) / "a.json"), "alerts_text_file": str(Path(td) / "a.txt"),
                      "retries": 0, "sources": [{"id": "a", "name": "A", "adapter": "arcgis_layer",
                                                  "url": "https://a.example/0"}]}
            month = str(30 * 24 * 3600)
            with patch.object(watch, "_source_check", side_effect=watch.ProviderRateLimitError(month, "a.example")):
                watch.check_sources(config, save=True)
            entry = json.loads(Path(config["state_file"]).read_text(encoding="utf-8"))["rate_limits"]["a.example"]
        wait = dt.datetime.fromisoformat(entry["not_before"]) - dt.datetime.fromisoformat(entry["recorded_at"])
        self.assertEqual(wait, dt.timedelta(days=30))
        self.assertTrue(entry["operator_review"])


class RedirectBackoffTests(RunConfig):
    def test_a_blocked_redirect_stops_the_source_without_retries(self):
        calls = []

        def check(source, timeout):
            calls.append(source["id"])
            if source["id"] == "first":
                raise watch.ProviderRateLimitError("120", "limited.example")
            watch._validated_redirect("https://b.example/x", "https://limited.example/y", "https://b.example/x")

        config = self.config([{"id": "first", "name": "First", "adapter": "arcgis_layer", "url": "https://limited.example/0"},
                              {"id": "second", "name": "Second", "adapter": "arcgis_layer", "url": "https://b.example/0"}])
        config["retries"] = 3
        with patch.object(watch, "_source_check", side_effect=check), patch.object(watch.time, "sleep"):
            result = watch.check_sources(config, save=False)
        self.assertEqual(calls, ["first", "second"])  # no retries against the origin
        self.assertEqual(result["sources"]["second"]["attempts"], 1)
        self.assertIn("HTTP 429 backoff", result["sources"]["second"]["error"])

    def test_redirect_to_a_host_under_backoff_is_refused_without_lookup(self):
        token = watch._RUN_BLOCKED_HOSTS.set({"limited.example"})
        try:
            with patch.object(watch, "resolve_addresses") as resolve, \
                    self.assertRaisesRegex(RuntimeError, "HTTP 429 backoff"):
                watch._validated_redirect("https://b.example/x", "https://limited.example/y", "https://b.example/x")
            resolve.assert_not_called()
        finally:
            watch._RUN_BLOCKED_HOSTS.reset(token)

    def test_a_429_in_a_run_blocks_later_redirects_and_the_set_resets(self):
        seen = []

        def check(source, timeout):
            if source["id"] == "first":
                raise watch.ProviderRateLimitError("120", "limited.example")
            with self.assertRaisesRegex(RuntimeError, "HTTP 429 backoff"):
                watch._validated_redirect("https://b.example/x", "https://limited.example/y", "https://b.example/x")
            seen.append(source["id"])
            return {"problems": []}

        sources = [{"id": "first", "name": "First", "adapter": "arcgis_layer", "url": "https://limited.example/0"},
                   {"id": "second", "name": "Second", "adapter": "arcgis_layer", "url": "https://b.example/0"}]
        with patch.object(watch, "_source_check", side_effect=check):
            watch.check_sources(self.config(sources), save=False)
        self.assertEqual(seen, ["second"])
        self.assertIsNone(watch._RUN_BLOCKED_HOSTS.get(None))


class HoldUntilClearedTests(unittest.TestCase):
    def test_requests_beyond_the_maximum_never_resume_automatically(self):
        now = NOW
        entry = {"not_before": (now + dt.timedelta(days=365)).isoformat(), "hold_until_cleared": True}
        later = now + dt.timedelta(days=800)
        self.assertIn("h.example", watch._active_rate_limits({"h.example": entry}, later))
        with tempfile.TemporaryDirectory() as td:
            config = {"state_file": str(Path(td) / "state.json"), "history_file": str(Path(td) / "h.jsonl"),
                      "alerts_file": str(Path(td) / "a.json"), "alerts_text_file": str(Path(td) / "a.txt"),
                      "retries": 0, "sources": [{"id": "a", "name": "A", "adapter": "arcgis_layer",
                                                  "url": "https://a.example/0"}]}
            with patch.object(watch, "_source_check", side_effect=watch.ProviderRateLimitError("9999999999", "a.example")):
                watch.check_sources(config, save=True)
            saved = json.loads(Path(config["state_file"]).read_text(encoding="utf-8"))["rate_limits"]["a.example"]
        self.assertTrue(saved["hold_until_cleared"])


class HoldForTermsRuntimeTests(RunConfig):
    def held_slug(self):
        research = load_parcel_access()
        counties = json.loads((Path(watch.__file__).with_name("minnesota_counties.json")).read_text(encoding="utf-8"))
        names = {c["name"]: c["slug"] for c in counties["counties"]}
        return next(names[n] for n, r in research.items() if (r.get("monitoring") or {}).get("decision") == "hold-for-terms")

    def test_enabled_held_county_parcel_source_is_never_polled(self):
        slug = self.held_slug()
        self.assertIn(slug, watch._held_county_slugs())
        sources = [{"id": "held", "name": "Held", "adapter": "arcgis_layer", "url": "https://h.example/0",
                    "county_slug": slug, "category": "Parcels", "execution_profiles": ["cloud"]},
                   {"id": "held-address", "name": "Held addresses", "adapter": "arcgis_layer",
                    "url": "https://h.example/1", "county_slug": slug, "category": "Address Points",
                    "execution_profiles": ["cloud"]}]
        with patch.object(watch, "_source_check", return_value={"problems": []}) as check:
            result = watch.check_sources(self.config(sources), save=False, execution_profile="cloud")
        self.assertEqual([c.args[0]["id"] for c in check.call_args_list], ["held-address"])
        self.assertEqual(result["skipped_sources"], {"held": "hold-for-terms"})

    def test_the_data_file_decides(self):
        slug = self.held_slug()
        sources = [{"id": "held", "name": "Held", "adapter": "arcgis_layer", "url": "https://h.example/0",
                    "county_slug": slug, "category": "Parcels"}]
        research = load_parcel_access()
        for record in research.values():
            if (record.get("monitoring") or {}).get("decision") == "hold-for-terms":
                record["monitoring"]["decision"] = "candidate-low-frequency"  # evidence changed
        with patch("clearparcel.datawatch.parcel_access.load_parcel_access", return_value=research), \
                patch.object(watch, "_source_check", return_value={"problems": []}) as check:
            watch.check_sources(self.config(sources), save=False)
        self.assertEqual(check.call_count, 1)

    def test_held_skips_count_as_intended_for_the_shrink_guard(self):
        base = aggregate.merge_states({}, report(0, ["a", "b", "c"]), "cloud", now=NOW)
        partial = {**report(10, ["a"]), "skipped_sources": {"b": "hold-for-terms", "c": "hold-for-terms"}}
        merged = aggregate.merge_states(base, partial, "cloud", now=NOW + dt.timedelta(hours=1))
        self.assertEqual(set(merged["retired_sources"]), {"b", "c"})


class EmptyReportTests(RunConfig):
    def test_reports_with_no_sources_are_refused_unless_an_explicit_drain(self):
        for partial in (report(0, []), report(0, [], scope="source"), {"generated_at": stamp(), "sources": {}}):
            with self.subTest(scope=(partial.get("scope") or {}).get("type")), \
                    self.assertRaisesRegex(ValueError, "no source observations"):
                aggregate.merge_states({}, partial, "cloud", now=NOW)
        drained = aggregate.merge_states({}, report(0, [], allow_inventory_shrink=True), "cloud", now=NOW)
        self.assertEqual(drained["sources"], {})

    def test_a_filter_that_matches_nothing_is_an_empty_run(self):
        sources = [{"id": "a", "name": "A", "adapter": "arcgis_layer", "url": "https://a.example/0"}]
        with patch.object(watch, "_source_check") as check:
            result = watch.check_sources(self.config(sources), source_filter="no-such-source", save=True)
        check.assert_not_called()
        self.assertEqual(result["scope"]["type"], "empty")
        self.assertEqual(result["overall"], "error")
        self.assertIn("source filter", result["error"])
        self.assertFalse((self.root / "state.json").exists())


class PublisherGuardTests(unittest.TestCase):
    def test_only_an_explicit_fleet_drain_may_publish_with_no_sources(self):
        from clearparcel.datawatch import cloud_job
        with patch.dict(os.environ, {"WATCHTOWER_AGGREGATE_OBJECT": "aggregate.json"}), \
                patch.object(cloud_job, "publish_partial", return_value={"published": True}) as publish, \
                patch.object(cloud_job, "backend_from_env"):
            for result in (report(0, []), report(0, [], scope="source", allow_inventory_shrink=True),
                           report(0, [], scope="empty", allow_inventory_shrink=True)):
                self.assertIsNone(cloud_job.publish_worker_result({}, result, "cloud", workdir=Path(".")))
            publish.assert_not_called()
            cloud_job.publish_worker_result({}, report(0, [], allow_inventory_shrink=True), "cloud", workdir=Path("."))
            publish.assert_called_once()


class RefusedShrinkTests(unittest.TestCase):
    def test_a_refused_shrink_keeps_fleet_level_worker_health(self):
        base = aggregate.merge_states({}, report(0, [f"s{i}" for i in range(10)]), "cloud", now=NOW)
        before = base["workers"]["cloud"]
        merged = aggregate.merge_states(base, report(10, ["s0"]), "cloud", now=NOW + dt.timedelta(hours=1))
        worker = merged["workers"]["cloud"]
        self.assertEqual(len(merged["sources"]), 10)
        self.assertEqual(worker["inventory_shrink_refused"], 9)
        for key in ("source_count", "last_success_at", "checked_at", "overall"):
            self.assertEqual(worker[key], before[key], key)
        self.assertEqual(worker["last_report_at"], stamp(10))

    def test_a_refused_shrink_cannot_take_sources_from_another_worker(self):
        base = aggregate.merge_states({}, report(0, [f"c{i}" for i in range(10)]), "cloud", now=NOW)
        base = aggregate.merge_states(base, report(1, ["local-only"]), "local", now=NOW)
        # A wrong registry: the local worker reports one cloud source and drops its own.
        wrong = report(10, ["c0"])
        merged = aggregate.merge_states(base, wrong, "local", now=NOW + dt.timedelta(hours=1))
        self.assertEqual(merged["sources"]["c0"]["worker"], "cloud")
        self.assertIn("local-only", merged["sources"])


class FreshnessTests(unittest.TestCase):
    def test_deferred_records_do_not_refresh_check_freshness(self):
        old = stamp(-3 * 24 * 60)
        state = {"workers": {"cloud": {"last_report_at": stamp()}},
                 "sources": {"old": {"status": "warn", "worker": "cloud", "deferred": True,
                                     "checked_at": old, "last_report_at": stamp()},
                             "never": {"status": "warn", "worker": "cloud", "deferred": True,
                                       "checked_at": None, "last_report_at": stamp()},
                             "fresh": {"status": "ok", "worker": "cloud", "checked_at": stamp(),
                                       "last_report_at": stamp()},
                             "legacy": {"status": "ok", "worker": "cloud", "last_report_at": stamp()}}}
        result = aggregate.with_freshness(state, now=NOW + dt.timedelta(minutes=5))
        self.assertEqual({sid: src["stale"] for sid, src in result["sources"].items()},
                         {"old": True, "never": True, "fresh": False, "legacy": False})

    def test_county_profiles_use_provider_check_time(self):
        now = dt.datetime.now(dt.timezone.utc)
        recent, old = now.isoformat(), (now - dt.timedelta(days=3)).isoformat()
        state = {"sources": {"p": {"id": "p", "county_slug": "wabasha", "category": "Parcels",
                                   "adapter": "arcgis_layer", "status": "warn", "deferred": True,
                                   "checked_at": old, "last_report_at": recent}}}
        profiles = compose_county_profiles(state, load_parcel_access(), now=now, freshness_policy=FreshnessPolicy())
        self.assertEqual(profiles["wabasha"]["monitoring"]["reporting"], "overdue")

    def test_public_state_keeps_only_a_deferral_flag(self):
        from clearparcel.datawatch.public_projection import sanitize_public_render_state
        public = sanitize_public_render_state({"sources": {"a": {"id": "a", "deferred": {
            "reason": "provider-rate-limit", "host": "private.example"}}}})
        self.assertIs(public["sources"]["a"]["deferred"], True)
        self.assertNotIn("private.example", json.dumps(public))

    def test_last_available_uses_the_source_check_time(self):
        partial = report(0, ["a"])
        partial["sources"]["a"]["checked_at"] = stamp(7)
        partial["generated_at"] = stamp(0)
        merged = aggregate.merge_states({}, partial, "cloud", now=NOW + dt.timedelta(hours=1))
        self.assertEqual(merged["sources"]["a"]["last_available_at"], stamp(7))


class ValueTests(unittest.TestCase):
    def test_huge_decimal_strings_never_become_infinity(self):
        self.assertIsNone(watch._coerce_scalar("9" * 400 + ".0"))
        self.assertEqual(watch._coerce_scalar("9" * 5000), "9" * 5000)
        self.assertEqual(watch._coerce_scalar("12.5"), 12.5)

    @unittest.skipUnless(os.name == "posix", "directory fsync is POSIX-only")
    def test_atomic_write_flushes_the_directory_after_replacing(self):
        with tempfile.TemporaryDirectory() as td, patch.object(file_lock, "_fsync_directory") as flush:
            target = Path(td) / "state.json"
            file_lock.atomic_write(target, b"{}")
        flush.assert_called_once_with(target.parent)


class CountyAndTableTests(unittest.TestCase):
    def test_stale_failures_count_as_overdue(self):
        from clearparcel.datawatch.dashboard_counties import render_counties
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).isoformat()
        state = {"generated_at": old, "sources": {"mn-wabasha-parcels": {
            "id": "mn-wabasha-parcels", "county_slug": "wabasha", "category": "Parcels", "status": "error",
            "checked_at": old, "last_report_at": old}}}
        page = render_counties({"_render_state": state, "state_file": "unused.json"})
        self.assertIn("1 of these is overdue for a new check.", page)
        self.assertNotIn("0 of these are overdue", page)

    def test_nested_tables_do_not_change_their_parents_header_scope(self):
        out = _accessible_tables("<h3>T</h3><table><thead><tr><th>Col</th></tr></thead><tbody><tr><th>Row1</th>"
                                 "<td><table><tbody><tr><th>Inner</th></tr></tbody></table></td></tr>"
                                 "<tr><th>Row2</th></tr></tbody></table>")
        for label in ("Row1", "Inner", "Row2"):
            self.assertIn(f'<th scope="row">{label}</th>', out)
        self.assertIn('<th scope="col">Col</th>', out)


if __name__ == "__main__":
    unittest.main()
