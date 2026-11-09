import contextlib
import datetime as dt
import http.client
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.dashboard_terms import render_terms_body
from clearparcel.datawatch.private_dashboard import prepare_private_dashboard
from clearparcel.datawatch.provider_terms import (
    CLIENT_ID_ENV, CLIENT_SECRET_ENV, URL_ENV, TermsCache, TermsStatusError, cache_from_env, days_waiting,
    fetch_status, is_due_this_week, is_overdue, parse_status, sort_for_attention, summarize,
)
from clearparcel.datawatch.storage import LocalStorage
from clearparcel.datawatch.weekly_digest import MAX_BODY, build_digest

NOW = dt.datetime(2026, 11, 4, 4, 30, tzinfo=dt.timezone.utc)  # 10:30 PM Central, Nov 3
TERMS_URL = "https://crm.example.test/api/terms/status"
ORIGIN = "https://crm.example.test"
CRM = ORIGIN + "/organizations/"


def _row(name, *, due=None, stage="inquiry-sent", sent=None, reply=None, open_=True, **extra):
    return {
        "organizationId": name.lower().replace(" ", "-"), "name": name, "organizationType": "county",
        "countyName": name.split()[0], "archived": False, "crmUrl": CRM + name.lower().replace(" ", "-"),
        "termsStopped": False,
        "openInquiry": {"stage": stage, "purposes": ["watchtower-monitoring"], "followUpDueOn": due,
                        "followUpOverdue": False, "openedAt": "2026-10-01T15:00:00.000Z",
                        "updatedAt": "2026-10-02T15:00:00.000Z"} if open_ else None,
        "latestOutcome": None, "latestDecidedAt": None, "watchtowerGateUrl": None,
        "lastEmailAt": sent, "lastReplyAt": reply, **extra,
    }


PAYLOAD = {"generatedAt": "2026-11-04T04:00:00.000Z", "providers": [
    _row("Soon County", due="2026-11-09"),
    _row("Overdue County", due="2026-11-02", stage="in-discussion"),
    _row("Silent County", sent="2026-10-10T15:00:00.000Z", reply="2026-10-05T15:00:00.000Z"),
    _row("Stopped County", open_=False, termsStopped=True, latestOutcome="stop-requested"),
    _row("Archived County", open_=False, archived=True, termsStopped=True, latestOutcome="stop-requested"),
]}


class FakeResponse:
    def __init__(self, body, *, status=200, content_type="application/json"):
        self.status, self.headers, self._body = status, {"Content-Type": content_type}, body

    def read(self, limit=-1):
        return self._body if limit < 0 else self._body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, result):
        self.result, self.requests = result, []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class ParseTests(unittest.TestCase):
    def test_keeps_only_allow_listed_fields(self):
        row = _row("Aitkin County", due="2026-11-10", contactEmail="person@example.gov", notes="Fee quote $500",
                   crmUrl="https://evil.example/x", watchtowerGateUrl="https://github.com/clearparcel/GIS-Data-Watchtower/pull/9")
        row["openInquiry"]["purposes"] = ["watchtower-monitoring", "bogus"]
        status = parse_status({"providers": [row, {"name": "no id"}, "junk"]}, ORIGIN)
        self.assertEqual(len(status["providers"]), 1)
        provider = status["providers"][0]
        self.assertEqual(set(provider), {"organization_id", "name", "organization_type", "archived", "crm_url",
                                         "terms_stopped", "open_inquiry", "latest_outcome", "latest_decided_at",
                                         "watchtower_gate_url", "last_email_at", "last_reply_at"})
        self.assertIsNone(provider["crm_url"])  # only the CRM's own record links
        self.assertEqual(provider["watchtower_gate_url"], "https://github.com/clearparcel/GIS-Data-Watchtower/pull/9")
        self.assertEqual(provider["open_inquiry"]["purposes"], ["watchtower-monitoring"])
        self.assertNotIn("person@example.gov", json.dumps(status))
        self.assertNotIn("Fee quote", json.dumps(status))

    def test_malformed_values_are_dropped_not_crashed_on(self):
        row = _row("Odd County", due="2026-13-45", stage=["in-discussion"], latestOutcome={"x": 1},
                   sent="2026-10-01T09:00:00Z", reply="2026-10-02T09:00:00")
        row["openInquiry"]["purposes"] = 7
        provider = parse_status({"providers": [row]}, ORIGIN)["providers"][0]
        self.assertIsNone(provider["open_inquiry"]["stage"])
        self.assertIsNone(provider["open_inquiry"]["follow_up_due_on"])
        self.assertEqual(provider["open_inquiry"]["purposes"], [])
        self.assertIsNone(provider["latest_outcome"])
        self.assertIsNone(provider["last_reply_at"])  # no time zone: dropped, so comparisons stay aware
        self.assertIn("Odd County", render_terms_body({"status": {"providers": [provider]}, "fetched_at": None,
                                                       "last_error": None}, now=NOW))
        self.assertIsNone(parse_status({"providers": [_row("D", due="2026-11-03\n")]}, ORIGIN)
                          ["providers"][0]["open_inquiry"]["follow_up_due_on"])

    def test_rejects_an_unexpected_shape(self):
        for payload in (None, [], {"providers": "x"}):
            with self.assertRaises(TermsStatusError):
                parse_status(payload, ORIGIN)


class FetchTests(unittest.TestCase):
    def test_sends_the_access_service_token(self):
        opener = FakeOpener(FakeResponse(json.dumps(PAYLOAD).encode()))
        status = fetch_status(TERMS_URL, "id.access", "secret-value", opener=opener)
        self.assertEqual(len(status["providers"]), 5)
        self.assertTrue(status["providers"][0]["crm_url"].startswith(CRM))
        request = opener.requests[0]
        self.assertEqual(request.get_header("Cf-access-client-id"), "id.access")
        self.assertEqual(request.get_header("Cf-access-client-secret"), "secret-value")

    def test_failures_never_echo_response_content(self):
        cases = [
            FakeOpener(urllib.error.HTTPError(TERMS_URL, 403, "Forbidden", {}, io.BytesIO(b"secret page"))),
            FakeOpener(urllib.error.URLError("dns")),
            FakeOpener(FakeResponse(b"<html>Sign in</html>", content_type="text/html")),
            FakeOpener(FakeResponse(b"{not json")),
            FakeOpener(FakeResponse(b"x" * 1_000_001)),
            FakeOpener(http.client.IncompleteRead(b"partial")),
            FakeOpener(FakeResponse(b'{"providers": {"not": "a list"}}')),
        ]
        for opener in cases:
            with self.assertRaises(TermsStatusError) as caught:
                fetch_status(TERMS_URL, "id", "secret-value", opener=opener)
            self.assertNotIn("secret", str(caught.exception))
            self.assertNotIn("Sign in", str(caught.exception))

    def test_refuses_plain_http(self):
        with self.assertRaises(TermsStatusError):
            fetch_status("http://crm.example.test/api/terms/status", "id", "s", opener=FakeOpener(None))

    def test_not_configured_without_both_credentials(self):
        full = {URL_ENV: TERMS_URL, CLIENT_ID_ENV: "id", CLIENT_SECRET_ENV: "s"}
        self.assertIsNotNone(cache_from_env(full))
        for missing in full:
            self.assertIsNone(cache_from_env({k: v for k, v in full.items() if k != missing}), missing)


class CacheTests(unittest.TestCase):
    def test_failure_keeps_the_last_good_copy_and_disk_survives_a_restart(self):
        results = [parse_status(PAYLOAD, ORIGIN), TermsStatusError("CRM terms status returned HTTP 503")]

        def fetch():
            result = results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "terms.json"
            ticks = iter([0, 1000, 2000, 3000])
            cache = TermsCache(fetch, cache_path=path, clock=lambda: next(ticks), now=lambda: NOW)
            self.assertTrue(cache.refresh())
            self.assertFalse(cache.refresh())
            snap = cache.snapshot()
            self.assertEqual(len(snap["status"]["providers"]), 5)
            self.assertIn("503", snap["last_error"])
            restarted = TermsCache(lambda: (_ for _ in ()).throw(TermsStatusError("down")), cache_path=path)
            self.assertEqual(len(restarted.snapshot()["status"]["providers"]), 5)

    def test_maybe_refresh_is_rate_limited(self):
        calls = []
        clock = [0.0]
        cache = TermsCache(lambda: calls.append(1) or parse_status(PAYLOAD, ORIGIN), interval=900, clock=lambda: clock[0])
        cache.maybe_refresh(); cache.maybe_refresh()
        clock[0] = 899; cache.maybe_refresh()
        clock[0] = 900; cache.maybe_refresh()
        self.assertEqual(len(calls), 2)


class FailureTests(unittest.TestCase):
    def test_any_fetch_failure_is_recorded_and_never_raises(self):
        def broken():
            raise RuntimeError("secret-value in a message")

        cache = TermsCache(broken)
        self.assertFalse(cache.refresh())
        self.assertEqual(cache.snapshot()["last_error"], "CRM terms status failed (RuntimeError)")

    def test_digest_still_sends_when_the_crm_breaks(self):
        from clearparcel.datawatch import weekly_digest
        env = {URL_ENV: TERMS_URL, CLIENT_ID_ENV: "id", CLIENT_SECRET_ENV: "secret-value"}
        from clearparcel.datawatch import provider_terms
        with patch.object(provider_terms.urllib.request, "build_opener",
                          lambda *a: FakeOpener(http.client.IncompleteRead(b"partial"))):
            snap = weekly_digest._terms_snapshot(env)
        self.assertIn("IncompleteRead", snap["last_error"])
        digest = build_digest({}, {}, {}, now=NOW, terms=snap)
        self.assertIn("Provider terms: CRM not reachable", digest["body"])
        self.assertNotIn("secret-value", json.dumps(digest))


class DerivedViewTests(unittest.TestCase):
    def setUp(self):
        self.providers = parse_status(PAYLOAD, ORIGIN)["providers"]
        self.by_name = {p["name"]: p for p in self.providers}

    def test_central_calendar_dates(self):
        self.assertTrue(is_overdue(self.by_name["Overdue County"], NOW))
        self.assertTrue(is_due_this_week(self.by_name["Soon County"], NOW))  # Nov 3 + 6 = Nov 9
        self.assertFalse(is_due_this_week(self.by_name["Soon County"], NOW - dt.timedelta(days=1)))
        self.assertEqual(days_waiting(self.by_name["Silent County"], NOW), 24)
        self.assertEqual(summarize(self.providers, NOW),
                         {"open": 3, "overdue": 1, "due_this_week": 1, "no_follow_up": 1, "waiting": 1, "stopped": 2})
        self.assertEqual([p["name"] for p in sort_for_attention(self.providers, NOW)][:3],
                         ["Overdue County", "Soon County", "Silent County"])


class ViewTests(unittest.TestCase):
    def test_lists_overdue_first_with_crm_links(self):
        body = render_terms_body({"status": parse_status(PAYLOAD, ORIGIN), "fetched_at": "2026-11-04T04:00:00+00:00",
                                  "last_error": None, "last_attempt_at": None}, now=NOW)
        self.assertLess(body.index("Overdue County"), body.index("Soon County"))
        self.assertIn(f'href="{CRM}overdue-county"', body)
        self.assertIn("No reply in 24 days", body)
        self.assertIn("Stop requested", body)

    def test_renders_the_cached_copy_when_the_crm_is_down(self):
        body = render_terms_body({"status": parse_status(PAYLOAD, ORIGIN), "fetched_at": "2026-11-04T04:00:00+00:00",
                                  "last_error": "CRM terms status unreachable (URLError)", "last_attempt_at": None}, now=NOW)
        self.assertIn("CRM not reachable", body)
        self.assertIn("Showing the copy from", body)
        self.assertIn("Overdue County", body)

    def test_not_configured_and_first_load_states(self):
        self.assertIn("Not connected", render_terms_body(None, now=NOW))
        self.assertIn("No earlier copy", render_terms_body({"status": None, "fetched_at": None,
                                                            "last_error": "down", "last_attempt_at": None}, now=NOW))

    def test_private_route_and_nav(self):
        cache = TermsCache(lambda: parse_status(PAYLOAD, ORIGIN))
        cache.refresh()
        captured = {}

        class Server:
            def __init__(self, addr, handler, **kw):
                captured["handler"] = handler

            def serve_forever(self):
                pass

            def server_close(self):
                pass

        config = {"sources": [], "_render_state": {"sources": {}}, "state_file": "/nonexistent/state.json",
                  "history_file": "/nonexistent/history.jsonl", "_terms_cache": cache}
        with patch.object(dashboard, "_BoundedThreadingHTTPServer", Server), \
                patch.dict(dashboard.os.environ, {"K_SERVICE": "svc"}, clear=True), \
                contextlib.redirect_stdout(io.StringIO()):
            dashboard.serve(config, host="0.0.0.0", port=8080, read_only=True, trusted_frontend="cloud-run-iap")
        handler = object.__new__(captured["handler"])
        status = []
        handler.headers, handler.wfile, handler.path = {}, io.BytesIO(), "/terms"
        handler.send_response, handler.send_header, handler.end_headers = status.append, lambda *a: None, lambda: None
        handler.do_GET()
        page = handler.wfile.getvalue().decode("utf-8")
        self.assertEqual(status[-1], 200)
        self.assertIn("Overdue County", page)
        self.assertIn('href="/terms"', page)


class PrivateWiringTests(unittest.TestCase):
    def test_private_dashboard_builds_a_cache_only_when_configured(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "store").mkdir()
            (root / "store" / "aggregate-state.json").write_text(json.dumps({"schema_version": 2, "generated_at": NOW.isoformat(), "sources": {}, "workers": {}, "counts": {}}), encoding="utf-8")
            registry = root / "registry.json"
            registry.write_text(json.dumps({"sources": []}), encoding="utf-8")
            env = {"WATCHTOWER_CONFIG": str(registry)}
            config, _, _ = prepare_private_dashboard(env, storage=LocalStorage(root / "store"), workdir=root / "a")
            self.assertIsNone(config["_terms_cache"])
            config, _, _ = prepare_private_dashboard({**env, URL_ENV: TERMS_URL, CLIENT_ID_ENV: "id", CLIENT_SECRET_ENV: "s"},
                                                     storage=LocalStorage(root / "store"), workdir=root / "b")
            self.assertIsInstance(config["_terms_cache"], TermsCache)
            self.assertEqual(config["_terms_cache"].cache_path, root / "b" / "provider-terms.json")


class DigestTests(unittest.TestCase):
    def snapshot(self):
        return {"status": parse_status(PAYLOAD, ORIGIN), "fetched_at": NOW.isoformat(), "last_error": None,
                "last_attempt_at": None}

    def test_terms_follow_ups_join_the_digest(self):
        digest = build_digest({}, {}, {}, now=NOW, terms=self.snapshot())
        body = digest["body"]
        self.assertIn("Provider terms: 1 follow-up(s) overdue, 1 due this week, 1 with no reply in 14+ days, 3 open.", body)
        self.assertIn("  Overdue County: due 2026-11-02", body)
        self.assertIn("  Silent County: 24 days", body)
        self.assertTrue(digest["subject"].endswith(", 1 terms follow-up(s) overdue"))
        self.assertEqual(digest["terms_overdue"], 1)

    def test_digest_still_sends_when_the_crm_is_down_or_not_configured(self):
        down = build_digest({}, {}, {}, now=NOW, terms={"status": None, "last_error": "CRM terms status returned HTTP 503"})
        self.assertIn("Provider terms: CRM not reachable (CRM terms status returned HTTP 503).", down["body"])
        self.assertNotIn("Provider terms", build_digest({}, {}, {}, now=NOW)["body"])

    def test_crowded_terms_still_fit(self):
        payload = {"providers": [_row(f"County {i:02d}", due="2026-10-01") for i in range(60)]}
        snap = {"status": parse_status(payload, ORIGIN), "fetched_at": NOW.isoformat(), "last_error": None}
        digest = build_digest({}, {}, {}, now=NOW, terms=snap)
        self.assertLessEqual(len(digest["body"]), MAX_BODY)
        self.assertIn("Provider terms: 60 follow-up(s) overdue", digest["body"])


if __name__ == "__main__":
    unittest.main()
