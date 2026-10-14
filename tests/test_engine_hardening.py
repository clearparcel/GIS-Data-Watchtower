"""Engine and server hardening regressions (review package 7)."""
import base64
import contextlib
import datetime as dt
import io
import itertools
import json
import math
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import aggregate, cli, dashboard, public_dashboard, watch
from clearparcel.datawatch.public_projection import sanitize_public_render_state

NOW = dt.datetime(2026, 10, 13, 12, 0, tzinfo=dt.timezone.utc)


def run_report(minutes, status, **source):
    stamp = (NOW + dt.timedelta(minutes=minutes)).isoformat()
    return {"generated_at": stamp, "overall": status, "scope": {"type": "fleet"},
            "counts": {"ok": 0, "warn": 0, "error": 0},
            "sources": {"a": {"id": "a", "status": status, "checked_at": stamp, **source}}}


class ExitCodeTests(unittest.TestCase):
    def test_exit_codes_separate_warnings_source_errors_and_tool_failures(self):
        self.assertEqual([cli._exit_code({"overall": x}) for x in ("ok", "warn", "error", "unknown")], [0, 1, 2, 0])
        with patch("sys.argv", ["watchtower", "--config", "/nonexistent/watchtower.json", "status"]), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(), cli.EXIT_TOOL_FAILURE)


class ProviderValueTests(unittest.TestCase):
    def test_only_plain_decimal_strings_become_numbers(self):
        cases = {"42": 42, "-7": -7, "0": 0, "0.5": 0.5, " 12.25 ": 12.25,
                 "007": "007", "27001": 27001, "nan": "nan", "inf": "inf", "-Infinity": "-Infinity",
                 "1e5": "1e5", "1_000": "1_000", "": "", "12.": "12.", ".5": ".5"}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                value = watch._coerce_scalar(raw)
                self.assertEqual(value, expected)
                self.assertIs(type(value), type(expected))
        self.assertIsNone(watch._coerce_scalar(None))

    def test_non_finite_provider_numbers_are_read_as_missing(self):
        self.assertEqual(watch._provider_json(b'\xef\xbb\xbf{"count": 3}'), {"count": 3})
        self.assertEqual(watch._provider_json(b'{"a": NaN, "b": [Infinity, -Infinity], "c": 1e400, "d": 1.5}'),
                         {"a": None, "b": [None, None], "c": None, "d": 1.5})
        with patch.object(watch, "_request", return_value=(b'{"extent": {"xmin": NaN}}', {"status": 200})):
            data, _ = watch._json_request("https://example.invalid/0", 2)
        self.assertIsNone(data["extent"]["xmin"])
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                watch._save_json(Path(td) / "state.json", {"x": math.nan})
            self.assertFalse((Path(td) / "state.json").exists())

    def test_legacy_state_with_nan_still_saves_and_keeps_new_backoffs(self):
        # Before this change NaN could be written into state (SDA "nan" strings,
        # ArcGIS NaN extents) and is carried forward for deferred sources.
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).isoformat()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
                      "alerts_file": str(root / "alerts.json"), "alerts_text_file": str(root / "alerts.txt"),
                      "retries": 0, "sources": [
                          {"id": "a", "name": "A", "adapter": "arcgis_layer", "url": "https://a.example/0"},
                          {"id": "b", "name": "B", "adapter": "arcgis_layer", "url": "https://b.example/0"}]}
            (root / "state.json").write_text(
                '{"schema_version": 1, "sources": {"a": {"id": "a", "status": "ok", "spatial_extent": {"xmin": NaN}, '
                '"values": {"x": Infinity}}}, "rate_limits": {"a.example": {"not_before": "' + future + '"}}}',
                encoding="utf-8")
            with patch.object(watch, "_source_check", side_effect=watch.ProviderRateLimitError("120", "b.example")):
                result = watch.check_sources(config, save=True)
            saved = json.loads((root / "state.json").read_text(encoding="utf-8"))
        self.assertTrue(result["sources"]["a"].get("deferred"))
        self.assertIn("b.example", saved["rate_limits"])
        self.assertIsNone(saved["sources"]["a"]["spatial_extent"]["xmin"])

    def test_aggregate_with_legacy_nan_from_another_worker_still_merges_and_saves(self):
        base = ('{"generated_at": "2026-10-13T11:00:00+00:00", "sources": {"old": {"id": "old", "worker": "local", '
                '"status": "ok", "checked_at": "2026-10-13T11:00:00+00:00", "values": {"x": NaN}}}}')
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "aggregate.json"
            path.write_text(base, encoding="utf-8")
            merged = aggregate.merge_states(aggregate.load_json(path), run_report(0, "ok"), "cloud",
                                            now=NOW + dt.timedelta(hours=1))
            aggregate.save_json(path, merged)
            self.assertIsNone(json.loads(path.read_text(encoding="utf-8"))["sources"]["old"]["values"]["x"])


class QueryFieldTests(unittest.TestCase):
    def test_unsafe_provider_field_names_never_reach_a_where_clause(self):
        for name in ("PIN", "_x1", "OWNER_NAME"):
            self.assertEqual(watch._sql_identifier(name), name)
        hostile = ("PIN OR 1=1", "PIN--", "a;b", "1PIN", "PIN'", "", "名前")
        for name in hostile:
            with self.subTest(name=name), self.assertRaises(ValueError):
                watch._sql_identifier(name)
        with patch.object(watch, "_request") as request:
            for call in (lambda f: watch._field_completeness("https://example.invalid/0", f, 10, 2),
                         lambda f: watch._arcgis_duplicate_id_summary("https://example.invalid/0", f, 2),
                         lambda f: watch._arcgis_statistics_query("https://example.invalid/0", f, 2)):
                with self.assertRaises(ValueError):
                    call("OWNER OR 1=1")
            request.assert_not_called()
        self.assertEqual(watch._field_candidate(["OWNER OR 1=1", "OWNER_NAME"], ["owner"], ["owner"]), "OWNER_NAME")
        self.assertIsNone(watch._field_candidate(["OWNER OR 1=1"], ["owner"], ["owner"]))


class RedirectTests(unittest.TestCase):
    def test_https_to_http_redirects_are_refused_before_any_lookup(self):
        with patch.object(watch, "resolve_addresses") as resolve:
            for current, initial in (("https://a.example/x", "https://a.example/x"),
                                     ("http://a.example/x", "https://a.example/x")):
                with self.subTest(current=current), self.assertRaisesRegex(RuntimeError, "plain HTTP"):
                    watch._validated_redirect(current, "http://b.example/y", initial)
            with patch.dict("os.environ", {"WATCHTOWER_REDIRECT_ALLOW_HOSTS": "b.example"}), \
                    self.assertRaisesRegex(RuntimeError, "plain HTTP"):
                watch._validated_redirect("https://a.example/x", "http://b.example/y", "https://a.example/x")
            resolve.assert_not_called()


class AvailabilityTests(unittest.TestCase):
    def merge(self, base, report):
        return aggregate.merge_states(base, report, "cloud", now=NOW + dt.timedelta(hours=1))

    def test_last_available_is_separate_from_last_success(self):
        state = self.merge({}, run_report(0, "ok"))
        first = state["sources"]["a"]
        self.assertEqual(first["last_success_at"], first["last_available_at"])
        state = self.merge(state, run_report(10, "warn"))
        warned = state["sources"]["a"]
        self.assertEqual(warned["last_success_at"], first["last_success_at"])
        self.assertEqual(warned["last_available_at"], run_report(10, "warn")["generated_at"])
        state = self.merge(state, run_report(20, "error"))
        self.assertEqual(state["sources"]["a"]["last_available_at"], warned["last_available_at"])
        state = self.merge(state, run_report(30, "warn", deferred=True))
        self.assertEqual(state["sources"]["a"]["last_available_at"], warned["last_available_at"])
        public = sanitize_public_render_state(state)
        self.assertEqual(public["sources"]["a"]["last_available_at"], warned["last_available_at"])

    def test_each_source_is_stamped_with_its_own_check_start(self):
        config = {"state_file": "", "sources": [{"id": "a", "name": "A", "adapter": "arcgis_layer", "url": "https://example.invalid/a"},
                                                 {"id": "b", "name": "B", "adapter": "arcgis_layer", "url": "https://example.invalid/b"}]}
        ticks = itertools.count()

        class Clock(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW + dt.timedelta(seconds=next(ticks))

        # Replace only watch's view of the datetime module, not datetime itself.
        fake_dt = types.SimpleNamespace(datetime=Clock, timezone=dt.timezone, timedelta=dt.timedelta)

        with tempfile.TemporaryDirectory() as td:
            config["state_file"] = str(Path(td) / "state.json")
            with patch.object(watch, "_source_check", return_value={"problems": []}), \
                    patch.object(watch, "dt", fake_dt):
                result = watch.check_sources(config, save=False)
        checked = [result["sources"][sid]["checked_at"] for sid in ("a", "b")]
        self.assertLess(result["generated_at"], checked[0])
        self.assertLess(checked[0], checked[1])
        self.assertEqual([result["sources"][sid]["provenance"]["observed_at"] for sid in ("a", "b")], checked)


class PublishingProfileTests(unittest.TestCase):
    def test_only_cloud_and_local_workers_may_publish_to_the_aggregate(self):
        from clearparcel.datawatch.cloud_job import require_publishable_profile
        with patch.dict("os.environ", {"WATCHTOWER_AGGREGATE_OBJECT": "aggregate-state.json"}):
            for profile in ("cloud", "local"):
                require_publishable_profile({}, profile)
            for profile in ("any", None, "laptop"):
                with self.subTest(profile=profile), self.assertRaises(ValueError):
                    require_publishable_profile({}, profile)
        with patch.dict("os.environ", {"WATCHTOWER_AGGREGATE_OBJECT": ""}):
            require_publishable_profile({}, "any")  # no shared aggregate: nothing to protect

    def test_cloud_job_refuses_an_unpublishable_profile_before_polling(self):
        from clearparcel.datawatch import cloud_job
        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / "config" / "sources.json"
            config.parent.mkdir()
            config.write_text(json.dumps({"state_file": "data/state.json", "aggregate_object": "aggregate.json",
                                          "sources": [{"id": "a", "name": "A", "adapter": "arcgis_layer",
                                                       "url": "https://gis.example.gov/0"}]}), encoding="utf-8")
            with patch.dict("os.environ", {"WATCHTOWER_EXECUTION_PROFILE": "any", "WATCHTOWER_STORAGE": "local",
                                           "WATCHTOWER_STORAGE_ROOT": td, "WATCHTOWER_WORKDIR": td}), \
                    patch.object(cloud_job, "check_sources") as check, self.assertRaises(ValueError):
                cloud_job.run_cloud_job(config)
            check.assert_not_called()


class PublicProjectionTests(unittest.TestCase):
    def test_only_known_execution_profiles_reach_the_public_state(self):
        state = {"workers": {"cloud": {"status": "ok"}, "gertken-pc": {"status": "ok"}},
                 "retired_workers": {"laptop-01": {"retired_at": NOW.isoformat()}},
                 "retired_sources": {"r": {"worker": "laptop-01", "retired_at": NOW.isoformat()}},
                 "sources": {"a": {"id": "a", "worker": "laptop-01"}, "b": {"id": "b", "worker": "local"}}}
        public = sanitize_public_render_state(state)
        self.assertEqual(set(public["workers"]), {"cloud"})
        self.assertEqual(public["retired_workers"], {})
        self.assertNotIn("worker", public["retired_sources"]["r"])
        self.assertNotIn("worker", public["sources"]["a"])
        self.assertEqual(public["sources"]["b"]["worker"], "local")
        from clearparcel.datawatch.public_projection import _PUBLIC_WORKERS
        self.assertEqual(_PUBLIC_WORKERS, watch._EXECUTION_PROFILES)
        with patch("sys.argv", ["watchtower", "aggregate", "--base", "b", "--partial", "p", "--worker", "laptop",
                                "--output", "o"]), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            cli.main()

    def test_gac_observation_status_none_is_public(self):
        gac = {"observation_status": "none", "observed_at": NOW.isoformat(),
               "fields": {"PIN": {"population_scanned": False}}, "counties": {"Aitkin": {}}}
        state = {"sources": {"a": {"id": "a", "mngac_completeness": gac}}}
        public = sanitize_public_render_state(state)
        self.assertEqual(public["sources"]["a"]["mngac_completeness"]["observation_status"], "none")


class DashboardTests(unittest.TestCase):
    def test_refresh_token_comparison_handles_non_ascii(self):
        self.assertFalse(dashboard._valid_refresh_request("tökén", "token", "same-origin"))
        self.assertTrue(dashboard._valid_refresh_request("tökén", "tökén", "same-origin"))

    def private_handler(self, password):
        captured = {}

        class Server:
            def __init__(self, addr, handler, **kwargs):
                captured["handler"] = handler

            def serve_forever(self):
                pass

            def server_close(self):
                pass

        with patch.object(dashboard, "_BoundedThreadingHTTPServer", Server), \
                patch.object(dashboard, "_dashboard_auth", return_value=(password, "wätchtower")), \
                contextlib.redirect_stdout(io.StringIO()):
            dashboard.serve({"sources": []})
        return object.__new__(captured["handler"])

    def test_basic_auth_handles_non_ascii_credentials(self):
        handler = self.private_handler("pässwörd")

        def header(user, password):
            return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}

        for headers, expected in ((header("wätchtower", "pässwörd"), True),
                                  (header("wätchtower", "password"), False),
                                  (header("watchtower", "pässwörd"), False),
                                  ({"Authorization": "Basic not-base64!"}, False),
                                  ({}, False)):
            handler.headers = headers
            with self.subTest(headers=headers):
                self.assertIs(handler._authorized(), expected)

    def test_static_site_counts_are_projected_to_integers(self):
        state = {"overall": "ok", "counts": {"ok": "<script>x</script>", "warn": 2, "error": -1}, "sources": {}}
        with tempfile.TemporaryDirectory() as td, \
                patch.object(dashboard, "_dashboard_state", return_value=state), \
                patch.object(dashboard, "_sanitize_public_state", side_effect=lambda value: value):
            dashboard.build_static_site({}, td)
            page = (Path(td) / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>x", page)
        self.assertIn('<div class="metric">2 / 0</div>', page)

    def test_private_links_use_the_public_url_sanitizer(self):
        self.assertEqual(dashboard._safe_url("https://gis.example.gov/x"), "https://gis.example.gov/x")
        for unsafe in ("https://gis.example.gov/x?token=abc", "http://127.0.0.1/admin",
                       "https://user:pw@gis.example.gov/", "javascript:alert(1)", None, ""):
            with self.subTest(unsafe=unsafe):
                self.assertIsNone(dashboard._safe_url(unsafe))


class PublicServerTests(unittest.TestCase):
    def public_handler(self):
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
            config = {"sources": []}

            def refresh(self, **kwargs):
                pass

            def snapshot(self):
                return {}

            def snapshot_xlsx(self):
                return b""

            def county_snapshot(self, slug):
                return None

        with patch.object(public_dashboard, "_BoundedThreadingHTTPServer", Server), \
                patch.object(public_dashboard, "_PublicStateCache", Cache), \
                contextlib.redirect_stdout(io.StringIO()):
            public_dashboard.serve_public()
        handler = object.__new__(captured["handler"])
        handler.headers = {}
        handler.wfile = io.BytesIO()
        sent = []
        handler.send_response = lambda status: sent.append(("status", status))
        handler.send_header = lambda name, value: sent.append((name, value))
        handler.end_headers = lambda: None
        return handler, sent

    def test_head_returns_get_headers_without_a_body(self):
        for command in ("GET", "HEAD"):
            handler, sent = self.public_handler()
            handler.command = command
            handler._send(200, "hello", "text/plain; charset=utf-8")
            with self.subTest(command=command):
                self.assertIn(("Content-Length", "5"), sent)
                self.assertEqual(handler.wfile.getvalue(), b"hello" if command == "GET" else b"")
        handler, sent = self.public_handler()
        handler.command, handler.path = "HEAD", "/not-a-page"
        handler.do_HEAD()
        self.assertIn(("status", 404), sent)
        self.assertIn(("Content-Length", str(len(b"Not found"))), sent)
        self.assertEqual(handler.wfile.getvalue(), b"")

    def test_county_exports_are_computed_once_per_published_state(self):
        with tempfile.TemporaryDirectory() as td, \
                patch.dict("os.environ", {"WATCHTOWER_PUBLIC_WORKDIR": td, "WATCHTOWER_STORAGE": "local"}):
            cache = public_dashboard._PublicStateCache()
            cache.public_path.write_text(json.dumps({"sources": {}}), encoding="utf-8")
            with patch.object(public_dashboard, "_county_profiles", return_value={}) as profiles, \
                    patch.object(public_dashboard, "_county_snapshot",
                                 side_effect=lambda config, slug, **kw: {"slug": slug} if slug == "douglas" else None) as county:
                self.assertEqual(cache.county_snapshot("douglas"), {"slug": "douglas"})
                self.assertEqual(cache.county_snapshot("douglas"), {"slug": "douglas"})
                self.assertIsNone(cache.county_snapshot("not-a-county"))
                self.assertIsNone(cache.county_snapshot("not-a-county"))
                self.assertEqual(county.call_count, 3)  # unknown slugs are not cached
                self.assertEqual(profiles.call_count, 1)  # statewide inputs built once per state
                self.assertNotIn("not-a-county", cache._county_values)
                cache.public_path.write_text(json.dumps({"sources": {"x": {}}}), encoding="utf-8")
                cache.county_snapshot("douglas")
                self.assertEqual((county.call_count, profiles.call_count), (4, 2))

    def test_cached_county_export_matches_a_direct_render(self):
        from tests.test_gac_county_view import county_state
        state, _, _ = county_state("parcel")
        state["generated_at"] = NOW.isoformat()
        state["sources"]["parcel"].update(id="parcel", name="Parcels", worker="cloud", county_slug="douglas",
                                          checked_at=NOW.isoformat(), last_report_at=NOW.isoformat())
        with tempfile.TemporaryDirectory() as td, \
                patch.dict("os.environ", {"WATCHTOWER_PUBLIC_WORKDIR": td, "WATCHTOWER_STORAGE": "local"}):
            cache = public_dashboard._PublicStateCache()
            cache.public_path.write_text(json.dumps(sanitize_public_render_state(state)), encoding="utf-8")
            for slug in ("douglas", "aitkin"):
                with self.subTest(slug=slug):
                    direct = public_dashboard._county_snapshot(cache.config, slug)
                    self.assertIsNotNone(direct)
                    def stable(value):  # creation timestamps differ between the two renders
                        if isinstance(value, dict):
                            return {k: stable(v) for k, v in value.items() if not k.startswith("snapshot_created")}
                        return [stable(v) for v in value] if isinstance(value, list) else value
                    self.assertEqual(stable(cache.county_snapshot(slug)), stable(direct))

if __name__ == "__main__":
    unittest.main()
