"""Regressions from the fifth read-only review of 395e3cf (V01-V13).

Offline: synthetic worker reports, mocked provider calls and temporary local storage.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.aggregate import merge_states, publish_worker_retirement, retire_worker, with_freshness
from clearparcel.datawatch.data_freshness import data_freshness, publisher_updated_at
from clearparcel.datawatch.provider_watchdog import overdue_workers
from clearparcel.datawatch.public_projection import InvalidSnapshotError
from clearparcel.datawatch.public_publish import (QUARANTINE_LOG_KEY, _snapshot_is_superseded,
                                                  publish_public_snapshot, validate_private_aggregate)
from clearparcel.datawatch.public_values import catalog_date
from clearparcel.datawatch.storage import LocalStorage
from clearparcel.datawatch.weekly_digest import run_weekly_digest

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
META = {"status": 200, "transport": "test"}
TEN_DAYS = 10 * 24 * 60


def at(minutes: float) -> str:
    return (NOW + dt.timedelta(minutes=minutes)).isoformat()


def fleet(started: float, sources: dict, *, scope: str = "fleet") -> dict:
    return {"schema_version": 3, "generated_at": at(started), "overall": "ok", "scope": {"type": scope},
            "counts": {"ok": len(sources), "warn": 0, "error": 0}, "sources": sources}


def measured(checked: float, count: int, **extra) -> dict:
    return {"status": "ok", "checked_at": at(checked), "feature_count": count, **extra}


def deferred(**extra) -> dict:
    """A zero-attempt rate-limit deferral, as ``watch._deferred_record`` builds it without history."""
    source = {"id": "s1", "name": "S1", "adapter": "arcgis_layer", "url": "https://gis.example/0"}
    return {**watch._deferred_record(source, None, at(-1)), **extra}


class Publisher:
    def __init__(self, root: Path):
        self.root = root
        self.log = io.StringIO()
        (root / "source").mkdir(parents=True, exist_ok=True)

    def publish(self, state: dict) -> dict:
        (self.root / "source" / "aggregate-state.json").write_text(json.dumps(state), encoding="utf-8")
        return publish_public_snapshot(LocalStorage(self.root / "source"), LocalStorage(self.root / "dest"),
                                       workdir=self.root / "work", log_stream=self.log)

    def destination(self) -> dict:
        return json.loads((self.root / "dest" / "aggregate-state.json").read_text(encoding="utf-8"))


def _tally(state: dict) -> dict:
    counts = {key: sum(1 for row in state["sources"].values() if row.get("status") == key)
              for key in ("ok", "warn", "error")}
    overall = "error" if counts["error"] else "warn" if counts["warn"] else "ok"
    return {**state, "counts": counts, "overall": overall}


class StoredFutureClockTests(unittest.TestCase):
    """V01: one bad stored clock never stalls unrelated publication."""

    def test_pre_upgrade_future_source_does_not_block_other_work(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            state = merge_states(None, fleet(-30, {"s1": measured(-29, 100)}), "cloud", now=NOW)
            self.assertTrue(publisher.publish(state)["published"])
            # Seed the already affected private object (written before the Q02 guard).
            state["sources"]["s1"]["checked_at"] = at(TEN_DAYS)
            state["sources"]["s1"]["feature_count"] = 999
            state = merge_states(state, fleet(-5, {"s2": measured(-4, 7)}), "local", now=NOW)
            result = publisher.publish(state)
            self.assertTrue(result["published"])
            self.assertEqual(result["clock_quarantine"], {"sources": ["s1"]})
            public = publisher.destination()
            self.assertEqual(public["sources"]["s2"]["feature_count"], 7)
            # The last trustworthy measurement survives.
            self.assertEqual((public["sources"]["s1"]["feature_count"], public["sources"]["s1"]["checked_at"]),
                             (100, at(-29)))
            self.assertEqual(public["counts"], {"ok": 2, "warn": 0, "error": 0})
            # The bad clock is visible to the operator.
            logged = [json.loads(line) for line in publisher.log.getvalue().splitlines()]
            self.assertEqual(logged, [{"severity": "ERROR", QUARANTINE_LOG_KEY: {"sources": ["s1"]}}])
            self.assertTrue(with_freshness(state, now=NOW)["sources"]["s1"]["clock_skew"])
            # Documented recovery: the corrected worker reports again and publishes.
            state = merge_states(state, fleet(-2, {"s1": measured(-1, 101)}), "cloud", now=NOW)
            result = publisher.publish(state)
            self.assertNotIn("clock_quarantine", result)
            self.assertEqual(publisher.destination()["sources"]["s1"]["feature_count"], 101)

    def test_fast_worker_merging_on_its_own_clock_does_not_hold_others(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            state = merge_states(None, fleet(-30, {"s1": measured(-29, 100)}), "cloud", now=NOW)
            state = merge_states(state, fleet(-30, {"s2": measured(-29, 5)}), "local", now=NOW)
            self.assertTrue(publisher.publish(state)["published"])
            fast = NOW + dt.timedelta(days=10)
            report = {**fleet(TEN_DAYS, {"s1": measured(TEN_DAYS, 200)})}
            state = merge_states(state, report, "cloud", now=fast)  # accepted against its own clock
            with self.assertRaisesRegex(InvalidSnapshotError, "future"):
                publisher.publish(state)  # a future fleet time is still refused
            state = merge_states(state, fleet(-3, {"s2": measured(-2, 6)}), "local", now=NOW)
            result = publisher.publish(state)
            self.assertTrue(result["published"])
            self.assertEqual(result["clock_quarantine"], {"sources": ["s1"], "workers": ["cloud"]})
            public = publisher.destination()
            self.assertEqual(public["sources"]["s2"]["feature_count"], 6)
            self.assertEqual(public["sources"]["s1"]["feature_count"], 100)
            self.assertEqual(public["workers"]["cloud"]["last_report_at"], at(-30))

    def test_source_without_a_published_version_is_withheld(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            state = merge_states(None, fleet(-5, {"s2": measured(-4, 7)}), "local", now=NOW)
            state["sources"]["s1"] = {"status": "error", "checked_at": at(TEN_DAYS), "worker": "cloud"}
            result = publisher.publish(_tally(state))
            self.assertTrue(result["published"])
            public = publisher.destination()
            self.assertEqual((set(public["sources"]), public["counts"], public["overall"]),
                             ({"s2"}, {"ok": 1, "warn": 0, "error": 0}, "ok"))


class RetireOverFutureHeartbeatTests(unittest.TestCase):
    """V02: a stored future heartbeat never leaves an inactive worker unretirable."""

    def _state(self) -> dict:
        return {"schema_version": 3, "generated_at": at(-60), "overall": "ok",
                "counts": {"ok": 0, "warn": 0, "error": 0}, "sources": {},
                "workers": {"local": {"checked_at": at(-120), "last_report_at": at(TEN_DAYS)}}}

    def test_storage_backed_retirement_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            storage = LocalStorage(Path(td) / "store")
            (Path(td) / "store").mkdir()
            (Path(td) / "store" / "aggregate.json").write_text(json.dumps(self._state()), encoding="utf-8")
            result = publish_worker_retirement(storage, "aggregate.json", "local", at(-1), Path(td) / "work")
            stored = json.loads((Path(td) / "store" / "aggregate.json").read_text(encoding="utf-8"))
        self.assertIn("local", result["retired_workers"])
        self.assertNotIn("local", stored["workers"])

    def test_ownership_and_plausible_ordering_still_hold(self):
        state = self._state()
        with self.assertRaisesRegex(ValueError, "follow retained observations"):
            retire_worker(state, "local", at(-130), now=NOW)  # before its plausible check
        state["sources"] = {"s1": {"worker": "local", "status": "ok"}}
        with self.assertRaisesRegex(ValueError, "owns source"):
            retire_worker(state, "local", at(-1), now=NOW)


class DeferralReinstatementTests(unittest.TestCase):
    """V03: a zero-attempt deferral never reinstates a retired source."""

    def test_private_merge_keeps_the_retirement(self):
        state = merge_states(None, fleet(-30, {"s1": measured(-29, 100), "s2": measured(-29, 7)}), "cloud", now=NOW)
        state = merge_states(state, fleet(-20, {"s2": measured(-19, 8)}), "cloud", now=NOW)
        self.assertIn("s1", state["retired_sources"])
        state = merge_states(state, fleet(-10, {"s1": deferred()}, scope="source"), "local", now=NOW)
        self.assertNotIn("s1", state["sources"])
        self.assertIn("s1", state["retired_sources"])
        # A qualifying post-retirement check reinstates it.
        state = merge_states(state, fleet(-5, {"s1": measured(-4, 30)}, scope="source"), "local", now=NOW)
        self.assertEqual(state["sources"]["s1"]["feature_count"], 30)
        self.assertNotIn("s1", state["retired_sources"])

    def test_public_guard_refuses_the_reinstatement(self):
        retired = {"generated_at": at(-20), "workers": {}, "sources": {},
                   "retired_sources": {"s1": {"retired_at": at(-20)}}}
        reinstating = {"generated_at": at(-10), "workers": {},
                       "sources": {"s1": {"last_report_at": at(-10), "deferred": True, "status": "warn"}}}
        self.assertTrue(_snapshot_is_superseded(reinstating, retired, NOW))
        reinstating["sources"]["s1"].update(checked_at=at(-11), deferred=None)
        self.assertFalse(_snapshot_is_superseded(reinstating, retired, NOW))


class UnreadableCheckTimeTests(unittest.TestCase):
    """V04: an unreadable clock or a rebuilt deferral never replaces a measurement."""

    def test_malformed_check_time_is_refused_at_the_private_write(self):
        base = merge_states(None, fleet(-20, {"s1": measured(-19, 100)}), "cloud", now=NOW)
        with self.assertRaisesRegex(ValueError, "checked_at is not a valid time"):
            merge_states(base, fleet(-5, {"s1": {"status": "ok", "checked_at": "unreadable-time",
                                                  "feature_count": 50}}), "cloud", now=NOW)
        # An absent legacy check time is still accepted.
        merged = merge_states(base, fleet(-5, {"s1": {"status": "ok", "feature_count": 50}}), "cloud", now=NOW)
        self.assertEqual(merged["sources"]["s1"]["feature_count"], 50)

    def test_publisher_quarantines_a_stored_malformed_check_time(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            state = merge_states(None, fleet(-20, {"s1": measured(-19, 100)}), "cloud", now=NOW)
            publisher.publish(state)
            state["sources"]["s1"].update(checked_at="unreadable-time", feature_count=50, last_report_at=at(-2),
                                          last_success_at=at(-2))
            result = publisher.publish(state)
            self.assertEqual(result["clock_quarantine"], {"sources": ["s1"]})
            public = publisher.destination()["sources"]["s1"]
            self.assertEqual((public["feature_count"], public["checked_at"]), (100, at(-19)))

    def test_rebuilt_deferral_keeps_the_published_measurement(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            publisher.publish(merge_states(None, fleet(-20, {"s1": measured(-19, 100)}), "cloud", now=NOW))
            rebuilt = merge_states(None, fleet(-5, {"s1": deferred()}), "cloud", now=NOW)
            self.assertIsNone(rebuilt["sources"]["s1"]["checked_at"])
            self.assertTrue(publisher.publish(rebuilt)["published"])
            public = publisher.destination()
            record = public["sources"]["s1"]
            self.assertEqual((record["feature_count"], record["checked_at"], record["status"]),
                             (100, at(-19), "warn"))
            self.assertEqual(public["counts"], {"ok": 0, "warn": 1, "error": 0})


class ArrivalOrderTests(unittest.TestCase):
    """V05: last success and availability converge whatever the arrival order."""

    def _run(self, order):
        reports = {"success": ("cloud", fleet(-26, {"s1": measured(-25, 10)}, scope="source")),
                   "error": ("local", fleet(-19, {"s1": {"status": "error", "checked_at": at(-18),
                                                          "error": "HTTP 500"}}, scope="source"))}
        state = None
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            for name in order:
                worker, report = reports[name]
                state = merge_states(state, report, worker, now=NOW)
                publisher.publish(state)
            return state["sources"]["s1"], publisher.destination()["sources"]["s1"]

    def test_both_orders_converge(self):
        for order in (("success", "error"), ("error", "success")):
            with self.subTest(order=order):
                private, public = self._run(order)
                for record in (private, public):
                    self.assertEqual((record["status"], record["checked_at"]), ("error", at(-18)))
                    self.assertEqual((record["last_success_at"], record["last_available_at"]), (at(-25), at(-25)))


class PaddedWorkerTests(unittest.TestCase):
    """V06: padded worker names are refused consistently."""

    def _aggregate(self) -> dict:
        return {"schema_version": 3, "generated_at": at(-1), "overall": "ok",
                "counts": {"ok": 1, "warn": 0, "error": 0}, "workers": {"cloud": {"last_report_at": at(-2)}},
                "sources": {"a": {"status": "ok", "worker": " cloud ", "checked_at": at(-2)}}}

    def test_publication_and_digest_refuse_and_watchdog_does_not_invent_a_worker(self):
        with self.assertRaisesRegex(InvalidSnapshotError, "invalid worker"):
            validate_private_aggregate(self._aggregate())
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "aggregate.json").write_text(json.dumps(self._aggregate()), encoding="utf-8")
            with self.assertRaisesRegex(InvalidSnapshotError, "invalid worker"):
                run_weekly_digest({}, LocalStorage(td), io.StringIO(), aggregate_object="aggregate.json", now=NOW)
        findings, checked = overdue_workers(self._aggregate(), now=NOW)
        self.assertEqual((findings, checked), ([], 1))

    def test_merge_refuses_a_padded_worker(self):
        with self.assertRaisesRegex(ValueError, "worker name"):
            merge_states(None, fleet(-1, {"s1": measured(-1, 1)}), " cloud ", now=NOW)


def _metadata_row(name, gac_open="Yes") -> dict:
    return {"attributes": {"county_name": name, "county_code": "01", "county_fips": "27001",
                           "gac_open": gac_open, "ng911_upload": "Yes"}}


def _metadata(features: list) -> dict:
    with patch.object(watch, "_json_request", return_value=({"features": features}, META)):
        return watch._arcgis_gac_metadata("https://example.invalid/1", 5, standard_key="address")


class ParticipationRowTests(unittest.TestCase):
    """V07: one usable row never conceals another county's malformed row."""

    def test_unidentified_row_beside_a_good_row_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "no county identifier"):
            _metadata([_metadata_row("Aitkin"), _metadata_row(None)])

    def test_unreadable_flag_is_refused_and_genuine_unknown_kept(self):
        with self.assertRaisesRegex(RuntimeError, "unreadable gac_open value for Anoka"):
            _metadata([_metadata_row("Aitkin"), _metadata_row("Anoka", "Yse")])
        result = _metadata([_metadata_row("Aitkin"), _metadata_row("Anoka", None)])
        self.assertIsNone(result["Anoka"]["gac_open"])

    def test_named_non_county_row_is_still_an_exclusion(self):
        self.assertEqual(set(_metadata([_metadata_row("Aitkin"), _metadata_row("Statewide")])), {"Aitkin"})

    def test_previous_participation_stays_visible(self):
        good = {"observed_at": at(-60), "record_count": 10,
                "county_metadata": {"Aitkin": {"gac_open": True}, "Anoka": {"gac_open": True}}}
        source = {"id": "s", "name": "S", "adapter": "arcgis_layer", "url": "https://gis.example/FeatureServer/0",
                  "gac_completeness": {"standard": "address"}}
        with tempfile.TemporaryDirectory() as td:
            config = {"state_file": str(Path(td) / "state.json"), "history_file": str(Path(td) / "h.jsonl"),
                      "retries": 0, "sources": [source]}
            try:
                _metadata([_metadata_row("Aitkin"), _metadata_row(None)])
            except RuntimeError as exc:
                failure = str(exc)
            for outcome in ({"schema_hash": "h", "gac_completeness": good, "problems": []},
                            {"schema_hash": "h", "gac_completeness": None, "gac_check_status": "error",
                             "gac_check_error": failure, "problems": []}):
                with patch.object(watch, "_source_check", side_effect=lambda s, t, o=outcome: dict(o)):
                    result = watch.check_sources(config)
        record = result["sources"]["s"]
        self.assertEqual(record["status"], "warn")
        self.assertEqual(set(record["gac_completeness"]["county_metadata"]), {"Aitkin", "Anoka"})
        self.assertEqual(record["gac_completeness"]["observed_at"], at(-60))


def _group(name, count: int) -> dict:
    return {"attributes": {"CO_NAME": name, "record_count": count, "p0": count}}


class AllGroupReconciliationTests(unittest.TestCase):
    """V08: every returned group counts toward the whole-layer consistency check."""

    def _layer(self, groups: list[dict], layer_count: int = 10) -> dict:
        layer = {"name": "Parcels", "fields": [{"name": n} for n in ("OBJECTID", "CO_NAME", "CO_CODE")],
                 "geometryType": "esriGeometryPolygon", "objectIdField": "OBJECTID"}
        fields = [{"field": "CO_NAME", "inclusion": "Mandatory", "data_type": "Text"}]

        def request(url, timeout, **_):
            return ({"features": groups}, META) if "/query" in url else (layer, META)
        with patch.object(watch, "_json_request", side_effect=request), \
                patch.object(watch, "_arcgis_count_query", return_value=layer_count), \
                patch.object(watch, "load_gac_standard", return_value={"fields": fields}):
            return watch._arcgis_layer({"id": "s", "name": "S", "adapter": "arcgis_layer",
                                        "url": "https://gis.example/FeatureServer/0", "count": True,
                                        "gac_completeness": True}, 5)

    def test_null_group_beyond_the_layer_total_is_inconsistent(self):
        result = self._layer([_group("Aitkin", 7), _group(None, 10)])
        self.assertEqual(result["gac_check_status"], "error")
        self.assertIn("17 exceeds the layer count 10", result["gac_check_error"])
        self.assertIsNone(result["gac_completeness"])

    def test_consistent_null_group_keeps_the_represented_distinction(self):
        result = self._layer([_group("Aitkin", 7), _group(None, 2), _group("Elsewhere", 1)])
        completeness = result["gac_completeness"]
        self.assertEqual((completeness["record_count"], completeness["ungrouped_record_count"],
                          completeness["unrepresented_group_record_count"]), (7, 3, 3))


class CompletenessSettingsPreflightTests(unittest.TestCase):
    """V09: recognized completeness settings are validated before any request."""

    @staticmethod
    def _source(key: str, settings: dict) -> dict:
        return {"id": "s", "name": "S", "adapter": "arcgis_layer", "url": "https://gis.example/FeatureServer/0",
                key: settings}

    def test_malformed_settings_are_configuration_errors(self):
        cases = [{"standard": "nope"}, {"standard": 5}, {"timeout_seconds": None}, {"timeout_seconds": "60"},
                 {"timeout_seconds": 0}, {"batch_size": "oops"}, {"batch_size": 2.5}, {"batch_size": True},
                 {"metadata_url": 7}]
        for key in watch._GAC_SETTING_OPTIONS:
            for settings in cases:
                if key == "mngac_completeness" and "standard" in settings:
                    continue  # the legacy name is always parcel
                with self.subTest(key=key, settings=settings), \
                        patch.object(watch, "_json_request") as request, \
                        self.assertRaises(watch.InvalidSourceRegistryError):
                    watch.validate_source_registry([self._source(key, settings)])
                self.assertEqual(request.call_count, 0)
        for settings in ({"population_scope": "some"}, {"standard": "parcel", "population_scope": "mandatory"},
                         {"text_population_mode": "blank"}):
            with self.subTest(settings=settings), self.assertRaises(watch.InvalidSourceRegistryError):
                watch.validate_source_registry([self._source("gac_completeness", settings)])

    def test_documented_settings_still_dispatch(self):
        documented = {"standard": "address", "timeout_seconds": 90, "batch_size": 12, "population_scope": "mandatory",
                      "metadata_url": "https://example.invalid/1"}
        watch.validate_source_registry([self._source("gac_completeness", documented)])
        watch.validate_source_registry([self._source("mngac_completeness", {"timeout_seconds": 90,
                                                                            "batch_size": 12})])
        layer = {"name": "Parcels", "fields": [], "geometryType": "esriGeometryPolygon"}
        with patch.object(watch, "_json_request", return_value=(layer, META)), \
                patch.object(watch, "_arcgis_gac_completeness",
                             return_value={"record_count": 0, "counties": {}}) as stats, \
                patch.object(watch, "_arcgis_gac_metadata", return_value={}):
            watch._arcgis_layer(self._source("gac_completeness", documented), 5)
        self.assertEqual((stats.call_args.args[3], stats.call_args.kwargs["batch_size"]), (90, 12))


class QueryStringUrlTests(unittest.TestCase):
    """V10: child operations are built from the parsed layer URL."""

    URL = "https://gis.example/arcgis/rest/services/P/FeatureServer/0?f=pjson&token=public"

    def test_child_url_keeps_path_and_overrides_operation_parameters(self):
        import urllib.parse as up
        built = up.urlparse(watch._arcgis_child_url(self.URL, "query", {"where": "1=1", "f": "json"}))
        self.assertEqual(built.path, "/arcgis/rest/services/P/FeatureServer/0/query")
        self.assertEqual(up.parse_qs(built.query), {"f": ["json"], "token": ["public"], "where": ["1=1"]})
        sub = up.urlparse(watch._arcgis_child_url("https://gis.example/MapServer/?f=pjson", "3"))
        self.assertEqual((sub.path, sub.query), ("/MapServer/3", "f=pjson"))
        # A URL without a query string is built exactly as before.
        plain = "https://gis.example/FeatureServer/0"
        self.assertEqual(watch._arcgis_child_url(plain, "query", {"f": "json"}), plain + "/query?f=json")

    def test_count_metadata_and_statistics_reach_the_layer_paths(self):
        import urllib.parse as up
        paths = []

        def request(url, timeout, **_):
            parsed = up.urlparse(url)
            paths.append(parsed.path)
            if parsed.path.endswith("/query"):
                return {"count": 5}, META
            return {"name": "Parcels", "fields": [], "geometryType": "esriGeometryPolygon"}, META
        source = {"id": "s", "name": "S", "adapter": "arcgis_layer", "url": self.URL, "count": True}
        with patch.object(watch, "_json_request", side_effect=request):
            result = watch._arcgis_layer(source, 5)
        self.assertEqual(result["feature_count"], 5)
        self.assertEqual(paths, ["/arcgis/rest/services/P/FeatureServer/0",
                                 "/arcgis/rest/services/P/FeatureServer/0/query"])


class ExtentComparabilityTests(unittest.TestCase):
    """V11: extents in different references are incomparable; impossible bounds are unmeasured."""

    GEO = {"xmin": -97.2, "ymin": 43.5, "xmax": -89.5, "ymax": 49.4, "wkid": 4326}
    MERC = {"xmin": -10821000.0, "ymin": 5390000.0, "xmax": -9963000.0, "ymax": 6338000.0, "wkid": 3857}

    def test_reference_change_is_not_an_extent_shift(self):
        changes = watch._compare({"spatial_extent": self.GEO}, {"spatial_extent": self.MERC},
                                 {"thresholds": {"extent_change_severity": "error"}})
        types = {change["type"]: change for change in changes}
        self.assertNotIn("spatial_extent", types)
        self.assertEqual((types["spatial_reference"]["severity"], types["spatial_reference"]["current"]),
                         ("info", 3857))

    def test_inverted_bounds_are_unmeasured(self):
        self.assertIsNone(watch._extent_basis({"extent": {"xmin": 20, "ymin": 0, "xmax": 10, "ymax": 10}}))
        self.assertIsNone(watch._extent_basis({"extent": {"xmin": float("nan"), "ymin": 0, "xmax": 10, "ymax": 1}}))
        self.assertIsNone(watch._extent_change({"xmin": 20, "ymin": 0, "xmax": 10, "ymax": 10, "wkid": 1},
                                               {"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10, "wkid": 1}))

    def test_last_usable_baseline_is_kept_through_impossible_bounds(self):
        def extent(x):
            return {"xmin": x, "ymin": 0, "xmax": x + 10, "ymax": 10, "wkid": 26915}
        source = {"id": "s", "name": "S", "adapter": "arcgis_layer", "url": "https://gis.example/FeatureServer/0",
                  "thresholds": {"extent_change_severity": "warn"}}
        with tempfile.TemporaryDirectory() as td:
            config = {"state_file": str(Path(td) / "state.json"), "history_file": str(Path(td) / "h.jsonl"),
                      "retries": 0, "sources": [source]}
            for layer_extent in ({"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10},
                                 {"xmin": 20, "ymin": 0, "xmax": 10, "ymax": 10},
                                 {"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10}):
                data = {"extent": {**layer_extent, "spatialReference": {"wkid": 26915}}}
                outcome = {"schema_hash": "h", "spatial_extent": watch._extent_basis(data), "problems": []}
                with patch.object(watch, "_source_check", side_effect=lambda s, t, o=outcome: dict(o)):
                    result = watch.check_sources(config)
        record = result["sources"]["s"]
        self.assertEqual(record["status"], "ok")
        self.assertFalse([c for c in record.get("changes") or [] if c.get("type") == "spatial_extent"])
        self.assertEqual(extent(0), {**record["spatial_extent"]})


class CatalogDateEncodingTests(unittest.TestCase):
    """V12: both accepted acquisition-date encodings reach the digest's freshness."""

    def test_iso_and_epoch_dates_classify_alike(self):
        day = (NOW - dt.timedelta(days=2)).date()
        epoch = int(dt.datetime.combine(day, dt.time(), dt.timezone.utc).timestamp() * 1000)
        for value in (epoch, day.isoformat(), f"{day.isoformat()}T00:00:00Z"):
            with self.subTest(value=value):
                record = {"county_records": {"Aitkin": {"acqdate": value}}}
                self.assertEqual(catalog_date(value, now=NOW), day)
                self.assertEqual(publisher_updated_at(record)[:10], day.isoformat())
                self.assertEqual(data_freshness(record, now=NOW)["state"], "current")

    def test_future_iso_date_stays_unknown(self):
        future = (NOW + dt.timedelta(days=5)).date().isoformat()
        self.assertEqual(data_freshness({"county_records": {"Aitkin": {"acqdate": future}}}, now=NOW)["state"],
                         "unknown")


class DigestFutureClockTests(unittest.TestCase):
    """V13: a future-dated aggregate never yields a routine weekly digest."""

    def _digest(self, generated_at: str):
        body = {"schema_version": 3, "generated_at": generated_at, "counts": {"ok": 0, "warn": 0, "error": 0},
                "sources": {}, "workers": {}}
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "aggregate.json").write_text(json.dumps(body), encoding="utf-8")
            out = io.StringIO()
            try:
                return run_weekly_digest({}, LocalStorage(td), out, aggregate_object="aggregate.json", now=NOW)
            finally:
                self.output = out.getvalue()

    def test_future_generation_time_is_refused(self):
        with self.assertRaisesRegex(ValueError, "in the future"):
            self._digest(at(TEN_DAYS))
        self.assertEqual(self.output, "")

    def test_current_and_legacy_empty_fleets_still_pass(self):
        self.assertEqual(self._digest(at(4))["overdue_checks"], 0)
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "aggregate.json").write_text(json.dumps(
                {"counts": {"ok": 0, "warn": 0, "error": 0}, "sources": {}, "workers": {}}), encoding="utf-8")
            digest = run_weekly_digest({}, LocalStorage(td), io.StringIO(), aggregate_object="aggregate.json", now=NOW)
        self.assertEqual(digest["overdue_checks"], 0)


if __name__ == "__main__":
    unittest.main()
