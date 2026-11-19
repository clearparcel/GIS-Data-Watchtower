"""Regressions from the fourth read-only review of 754859e (Q01-Q11).

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

from clearparcel.datawatch import aggregate, watch
from clearparcel.datawatch.aggregate import merge_states, retire_worker, with_freshness
from clearparcel.datawatch.provider_watchdog import LOG_KEY, overdue_workers, run_provider_watchdog
from clearparcel.datawatch.public_projection import InvalidSnapshotError
from clearparcel.datawatch.public_publish import (_snapshot_is_superseded, publish_public_snapshot,
                                                  validate_private_aggregate)
from clearparcel.datawatch.storage import LocalStorage
from clearparcel.datawatch.weekly_digest import run_weekly_digest

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
META = {"status": 200, "transport": "test"}


def at(minutes: float) -> str:
    return (NOW + dt.timedelta(minutes=minutes)).isoformat()


def fleet(started: float, sources: dict, *, scope: str = "fleet") -> dict:
    return {"schema_version": 3, "generated_at": at(started), "overall": "ok", "scope": {"type": scope},
            "counts": {"ok": len(sources), "warn": 0, "error": 0}, "sources": sources}


def measured(checked: float, count: int, **extra) -> dict:
    return {"status": "ok", "checked_at": at(checked), "feature_count": count, **extra}


class Publisher:
    def __init__(self, root: Path):
        self.root = root
        (root / "source").mkdir(parents=True, exist_ok=True)

    def publish(self, state: dict, stream=None) -> dict:
        (self.root / "source" / "aggregate-state.json").write_text(json.dumps(state), encoding="utf-8")
        return publish_public_snapshot(LocalStorage(self.root / "source"), LocalStorage(self.root / "dest"),
                                       workdir=self.root / "work", watchdog_stream=stream)

    def destination(self) -> dict:
        return json.loads((self.root / "dest" / "aggregate-state.json").read_text(encoding="utf-8"))


class RetirementOrderTests(unittest.TestCase):
    """Q01: retirement keeps a newer measurement; reinstatement needs evidence after retirement."""

    def test_overlapping_fleet_does_not_retire_a_later_measurement(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            state = merge_states(None, fleet(-30, {"s1": measured(-16, 100), "s2": measured(-28, 7)}), "cloud",
                                 now=NOW)
            self.assertTrue(publisher.publish(state)["published"])
            # A fleet report that started before s1 was measured omits it.
            state = merge_states(state, fleet(-25, {"s2": measured(-24, 8)}), "cloud", now=NOW)
            self.assertEqual(state["sources"]["s1"]["feature_count"], 100)
            self.assertNotIn("s1", state["retired_sources"])
            self.assertTrue(publisher.publish(state)["published"])
            # A deferred report from another worker carries an older measurement.
            deferred = measured(-27, 20, status="warn", deferred={"reason": "provider-rate-limit"})
            state = merge_states(state, fleet(-10, {"s1": deferred}, scope="source"), "local", now=NOW)
            self.assertEqual(state["sources"]["s1"]["feature_count"], 100)
            publisher.publish(state)
            self.assertEqual(publisher.destination()["sources"]["s1"]["feature_count"], 100)

    def test_reinstatement_requires_a_check_after_retirement(self):
        state = merge_states(None, fleet(-30, {"s1": measured(-29, 100), "s2": measured(-29, 7)}), "cloud", now=NOW)
        state = merge_states(state, fleet(-20, {"s2": measured(-19, 8)}), "cloud", now=NOW)
        self.assertEqual(state["retired_sources"]["s1"]["retired_at"], at(-20))
        # A later report whose record carries a measurement from before the retirement.
        stale = measured(-27, 20, status="warn", deferred={"reason": "provider-rate-limit"})
        state = merge_states(state, fleet(-10, {"s1": stale}, scope="source"), "local", now=NOW)
        self.assertNotIn("s1", state["sources"])
        state = merge_states(state, fleet(-5, {"s1": measured(-4, 30)}, scope="source"), "local", now=NOW)
        self.assertEqual(state["sources"]["s1"]["feature_count"], 30)
        self.assertNotIn("s1", state["retired_sources"])

    def test_publisher_applies_the_same_ordering(self):
        current = {"generated_at": at(-30), "workers": {},
                   "sources": {"s1": {"last_report_at": at(-30), "checked_at": at(-16)}}}
        retiring = {"generated_at": at(-25), "workers": {}, "sources": {},
                    "retired_sources": {"s1": {"worker": "cloud", "retired_at": at(-25)}}}
        self.assertTrue(_snapshot_is_superseded(retiring, current, NOW))
        retiring["retired_sources"]["s1"]["retired_at"] = at(-10)
        retiring["generated_at"] = at(-10)
        self.assertFalse(_snapshot_is_superseded(retiring, current, NOW))
        retired = {"generated_at": at(-20), "workers": {}, "sources": {},
                   "retired_sources": {"s1": {"retired_at": at(-20)}}}
        reinstating = {"generated_at": at(-10), "workers": {},
                       "sources": {"s1": {"last_report_at": at(-10), "checked_at": at(-27)}}}
        self.assertTrue(_snapshot_is_superseded(reinstating, retired, NOW))
        reinstating["sources"]["s1"]["checked_at"] = at(-11)
        self.assertFalse(_snapshot_is_superseded(reinstating, retired, NOW))


class FutureClockTests(unittest.TestCase):
    """Q02: future per-source checks and retirements never enter private storage."""

    def test_future_source_check_is_refused_at_the_private_write(self):
        base = merge_states(None, fleet(-10, {"s1": measured(-9, 1)}), "cloud", now=NOW)
        bad = fleet(-1, {"s1": measured(10 * 24 * 60, 2)})
        with self.assertRaisesRegex(ValueError, "checked_at is in the future"):
            merge_states(base, bad, "cloud", now=NOW)
        # Within the skew tolerance is accepted.
        merged = merge_states(base, fleet(-1, {"s1": measured(4, 3)}), "cloud", now=NOW)
        self.assertEqual(merged["sources"]["s1"]["feature_count"], 3)

    def test_future_retirement_is_refused(self):
        state = {"generated_at": at(-60), "sources": {}, "workers": {"old": {"last_report_at": at(-60)}}}
        with self.assertRaisesRegex(ValueError, "future"):
            retire_worker(state, "old", at(10 * 24 * 60), now=NOW)
        self.assertIn("old", retire_worker(state, "old", at(-1), now=NOW)["retired_workers"])

    def test_unrelated_worker_keeps_publishing_after_a_refused_report(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            state = merge_states(None, fleet(-20, {"s1": measured(-19, 1)}), "cloud", now=NOW)
            state = merge_states(state, fleet(-20, {"s2": measured(-19, 5)}), "local", now=NOW)
            self.assertTrue(publisher.publish(state)["published"])
            with self.assertRaises(ValueError):
                merge_states(state, fleet(-5, {"s1": measured(10 * 24 * 60, 2)}), "cloud", now=NOW)
            state = merge_states(state, fleet(-4, {"s2": measured(-3, 6)}), "local", now=NOW)
            self.assertTrue(publisher.publish(state)["published"])
            self.assertEqual(publisher.destination()["sources"]["s2"]["feature_count"], 6)


class RetirementOverFutureHeartbeatTests(unittest.TestCase):
    """Q03: an implausible stored heartbeat never blocks a valid worker retirement."""

    def _states(self, heartbeat: str):
        current = {"generated_at": at(-60), "sources": {}, "workers": {"old": {"last_report_at": heartbeat}}}
        candidate = {"generated_at": at(-1), "sources": {}, "workers": {},
                     "retired_workers": {"old": {"retired_at": at(-1)}}}
        return candidate, current

    def test_future_heartbeat_does_not_block_retirement(self):
        candidate, current = self._states(at(10 * 24 * 60))
        self.assertFalse(_snapshot_is_superseded(candidate, current, NOW))

    def test_genuine_newer_heartbeat_or_owned_source_still_blocks(self):
        candidate, current = self._states(at(-0.5))
        self.assertTrue(_snapshot_is_superseded(candidate, current, NOW))
        candidate, current = self._states(at(10 * 24 * 60))
        candidate["sources"] = {"s1": {"worker": "old", "last_report_at": at(-2)}}
        self.assertTrue(_snapshot_is_superseded(candidate, current, NOW))


class DeferredCarryTests(unittest.TestCase):
    """Q04: a same-worker deferred first check keeps the shared measurement."""

    SOURCE = {"id": "s1", "name": "S1", "adapter": "arcgis_layer", "url": "https://gis.example/0"}

    def _deferred(self) -> dict:
        record = watch._deferred_record(self.SOURCE, None, at(-5))
        self.assertIsNone(record["checked_at"])
        return record

    def test_same_worker_backoff_keeps_measurement_and_time(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            state = merge_states(None, fleet(-20, {"s1": measured(-19, 100)}), "cloud", now=NOW)
            publisher.publish(state)
            state = merge_states(state, fleet(-5, {"s1": self._deferred()}), "cloud", now=NOW)
            record = state["sources"]["s1"]
            self.assertEqual((record["feature_count"], record["checked_at"]), (100, at(-19)))
            self.assertEqual(record["status"], "warn")
            self.assertEqual(record["deferred"], {"reason": "provider-rate-limit"})
            self.assertEqual(state["workers"]["cloud"]["last_report_at"], at(-5))
            self.assertTrue(publisher.publish(state)["published"])
            public = publisher.destination()["sources"]["s1"]
            self.assertEqual((public["feature_count"], public["status"]), (100, "warn"))

    def test_previous_error_stays_an_error(self):
        failed = {"status": "error", "checked_at": at(-19), "error": "HTTP 500"}
        state = merge_states(None, fleet(-20, {"s1": failed}), "cloud", now=NOW)
        state = merge_states(state, fleet(-5, {"s1": self._deferred()}), "cloud", now=NOW)
        self.assertEqual((state["sources"]["s1"]["status"], state["sources"]["s1"]["error"]), ("error", "HTTP 500"))

    def test_cross_worker_backoff_never_replaces_the_measurement(self):
        state = merge_states(None, fleet(-20, {"s1": measured(-19, 100)}), "cloud", now=NOW)
        state = merge_states(state, fleet(-5, {"s1": self._deferred()}, scope="source"), "local", now=NOW)
        self.assertEqual((state["sources"]["s1"]["worker"], state["sources"]["s1"]["status"]), ("cloud", "ok"))


def _source(**extra) -> dict:
    return {"id": "s", "name": "S", "adapter": "arcgis_layer", "url": "https://gis.example/FeatureServer/0", **extra}


class CompletenessSettingTests(unittest.TestCase):
    """Q05: completeness settings are a boolean or an object before any request."""

    def test_other_types_are_refused(self):
        for key in watch._GAC_SETTING_OPTIONS:
            for value in ("false", "true", "", 0, 1, []):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(
                        watch.InvalidSourceRegistryError, f"{key} must be true, false or a settings object"):
                    watch.validate_source_registry([_source(**{key: value})])
            for value in (True, False, None, {}, {"standard": "parcel"}):
                with self.subTest(key=key, value=value):
                    watch.validate_source_registry([_source(**{key: value})])

    def test_dispatch_follows_the_typed_value(self):
        layer = {"name": "Parcels", "fields": [], "geometryType": "esriGeometryPolygon"}
        for key in watch._GAC_SETTING_OPTIONS:
            for value, expected in (("false", 0), (False, 0), ({}, 0), (True, 1), ({"batch_size": 4}, 1)):
                with self.subTest(key=key, value=value), \
                        patch.object(watch, "_json_request", return_value=(layer, META)) as request, \
                        patch.object(watch, "_arcgis_gac_completeness",
                                     return_value={"record_count": 0, "counties": {}}) as stats:
                    watch._arcgis_layer(_source(**{key: value}), 5)
                self.assertEqual(stats.call_count, expected)
                self.assertEqual(request.call_count, 1)


def _gac(features: list[dict], standard_key: str = "parcel") -> dict:
    fields = [{"field": "CO_NAME", "inclusion": "Mandatory", "data_type": "Text"}]
    with patch.object(watch, "load_gac_standard", return_value={"fields": fields}), \
            patch.object(watch, "_json_request", return_value=({"features": features}, META)):
        return watch._arcgis_gac_completeness("https://example.invalid/0", ["OBJECTID", "CO_NAME", "CO_CODE"],
                                              "OBJECTID", 10, standard_key=standard_key)


def _group(name, count: int = 10) -> dict:
    return {"attributes": {"CO_NAME": name, "record_count": count, "p0": count}}


class ParcelCountyIdentityTests(unittest.TestCase):
    """Q06: parcel statistics join on the canonical Minnesota county."""

    def test_alias_is_canonical_and_a_duplicate_is_refused(self):
        self.assertEqual(set(_gac([_group("Saint Louis")])["counties"]), {"St. Louis"})
        with self.assertRaisesRegex(RuntimeError, "duplicate GAC county group"):
            _gac([_group("St. Louis"), _group("Saint Louis")])

    def test_typo_is_excluded_and_non_text_is_malformed(self):
        result = _gac([_group("Aitkn"), _group("Aitkin")])
        self.assertEqual((result["covered_counties"], result["excluded_county_names"]), (1, ["Aitkn"]))
        with self.assertRaisesRegex(RuntimeError, "non-text CO_NAME"):
            _gac([_group(123)])

    def test_null_group_keeps_its_meaning(self):
        result = _gac([_group(None, 3), _group("Aitkin")])
        self.assertEqual((result["covered_counties"], result["record_count"]), (1, 10))


def _metadata_row(name: str, gac_open: str = "Yes") -> dict:
    return {"attributes": {"county_name": name, "county_code": "01", "county_fips": "27001",
                           "gac_open": gac_open, "ng911_upload": "Yes"}}


class ParticipationMetadataTests(unittest.TestCase):
    """Q07: participation metadata never silently disappears or reverses."""

    def _metadata(self, features: list) -> dict:
        with patch.object(watch, "_json_request", return_value=({"features": features}, META)):
            return watch._arcgis_gac_metadata("https://example.invalid/1", 5, standard_key="address")

    def test_conflicting_duplicate_is_refused_and_identical_duplicate_kept(self):
        with self.assertRaisesRegex(RuntimeError, "conflicting rows for Aitkin"):
            self._metadata([_metadata_row("Aitkin", "Yes"), _metadata_row("Aitkin", "No")])
        self.assertEqual(set(self._metadata([_metadata_row("Aitkin"), _metadata_row("Aitkin")])), {"Aitkin"})

    def test_malformed_or_empty_response_is_refused(self):
        for features in ([{"attributes": "x"}], [], [_metadata_row("Nowhere")]):
            with self.subTest(features=features), self.assertRaises(RuntimeError):
                self._metadata(features)

    def test_last_valid_metadata_stays_visible(self):
        good = {"observed_at": at(-60), "record_count": 10, "county_metadata": {"Aitkin": {"gac_open": True}}}
        source = _source(gac_completeness={"standard": "address"})
        with tempfile.TemporaryDirectory() as td:
            config = {"state_file": str(Path(td) / "state.json"), "history_file": str(Path(td) / "h.jsonl"),
                      "retries": 0, "sources": [source]}
            for outcome in ({"schema_hash": "h", "gac_completeness": good, "problems": []},
                            {"schema_hash": "h", "gac_completeness": None, "gac_check_status": "error",
                             "gac_check_error": "conflicting rows", "problems": []}):
                with patch.object(watch, "_source_check", side_effect=lambda s, t, o=outcome: dict(o)):
                    result = watch.check_sources(config)
        record = result["sources"]["s"]
        self.assertEqual(record["status"], "warn")
        self.assertEqual(record["gac_completeness"], good)


class GroupedCountReconciliationTests(unittest.TestCase):
    """Q08: grouped records larger than the layer total are inconsistent, not complete."""

    def _layer(self, grouped: int) -> dict:
        layer = {"name": "Parcels", "fields": [], "geometryType": "esriGeometryPolygon"}
        with patch.object(watch, "_json_request", return_value=(layer, META)), \
                patch.object(watch, "_arcgis_count_query", return_value=5), \
                patch.object(watch, "_arcgis_gac_completeness",
                             return_value={"record_count": grouped, "counties": {}}):
            return watch._arcgis_layer(_source(count=True, gac_completeness=True), 5)

    def test_grouped_sum_above_total_fails_the_quality_check(self):
        result = self._layer(10)
        self.assertEqual(result["gac_check_status"], "error")
        self.assertIn("exceeds the layer count", result["gac_check_error"])
        self.assertIsNone(result["gac_completeness"])

    def test_smaller_grouped_sum_keeps_ungrouped_records(self):
        result = self._layer(3)
        self.assertEqual((result["gac_completeness"]["source_feature_count"],
                          result["gac_completeness"]["ungrouped_record_count"]), (5, 2))


class MissingExtentTests(unittest.TestCase):
    """Q09: a missing extent keeps the last usable bounds and their time."""

    def test_shift_after_a_missing_extent_is_a_spatial_event(self):
        def extent(x):
            return {"xmin": x, "ymin": 0, "xmax": x + 10, "ymax": 10, "wkid": 26915}
        source = _source(thresholds={"extent_change_severity": "warn"})
        with tempfile.TemporaryDirectory() as td:
            config = {"state_file": str(Path(td) / "state.json"), "history_file": str(Path(td) / "h.jsonl"),
                      "retries": 0, "sources": [source]}
            observed = None
            for value in (extent(0), None, extent(500)):
                outcome = {"schema_hash": "h", "spatial_extent": value, "problems": []}
                with patch.object(watch, "_source_check", side_effect=lambda s, t, o=outcome: dict(o)):
                    result = watch.check_sources(config)
                observed = observed or result["sources"]["s"]["checked_at"]
        changes = {change["type"]: change for change in result["sources"]["s"]["changes"]}
        self.assertEqual(changes["spatial_extent"]["severity"], "warn")
        self.assertEqual(changes["spatial_extent"]["previous_observed_at"], observed)
        self.assertEqual(result["sources"]["s"]["status"], "warn")


class MalformedAssignmentTests(unittest.TestCase):
    """Q10: one unreadable assignment never hides other workers' alerts."""

    def _aggregate(self) -> dict:
        return {"schema_version": 3, "generated_at": at(-1), "overall": "ok",
                "counts": {"ok": 2, "warn": 0, "error": 0},
                "workers": {"cloud": {"last_report_at": at(-3 * 24 * 60)}},
                "sources": {"a": {"status": "ok", "worker": "cloud", "checked_at": at(-3 * 24 * 60)},
                            "b": {"status": "ok", "worker": ["local"], "checked_at": at(-2)}}}

    def test_watchdog_reports_valid_overdue_workers(self):
        findings, checked = overdue_workers(self._aggregate(), now=NOW)
        self.assertEqual(([f["worker"] for f in findings], checked), (["cloud"], 1))
        with_freshness(self._aggregate(), now=NOW)  # never raises on the malformed value

    def test_publisher_alerts_then_refuses_the_input(self):
        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as td, self.assertRaisesRegex(InvalidSnapshotError, "invalid worker"):
            Publisher(Path(td)).publish(self._aggregate(), stream)
        lines = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([line[LOG_KEY]["worker"] for line in lines if LOG_KEY in line], ["cloud"])
        summary = run_provider_watchdog(self._aggregate(), io.StringIO(), now=NOW, environ={})
        self.assertNotIn("error", summary)

    def test_digest_refuses_the_input_explicitly(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "aggregate.json").write_text(json.dumps(self._aggregate()), encoding="utf-8")
            out = io.StringIO()
            with self.assertRaisesRegex(InvalidSnapshotError, "invalid worker"):
                run_weekly_digest({}, LocalStorage(td), out, aggregate_object="aggregate.json", now=NOW)
        self.assertEqual(out.getvalue(), "")
        with self.assertRaises(InvalidSnapshotError):
            validate_private_aggregate({**self._aggregate(), "sources": {"b": {"status": "ok", "worker": " "}}})


class DigestClockTests(unittest.TestCase):
    """Q11: an explicitly invalid aggregate time never yields a routine notice."""

    def _digest(self, body: dict):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "aggregate.json").write_text(json.dumps(body), encoding="utf-8")
            out = io.StringIO()
            try:
                return run_weekly_digest({}, LocalStorage(td), out, aggregate_object="aggregate.json", now=NOW)
            finally:
                self.output = out.getvalue()

    def test_invalid_time_or_version_is_refused(self):
        empty = {"counts": {"ok": 0, "warn": 0, "error": 0}, "sources": {}, "workers": {}}
        for extra in ({"schema_version": 3, "generated_at": "not-a-date"}, {"generated_at": 5},
                      {"schema_version": "3"}, {"schema_version": 0}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self._digest({**empty, **extra})
            self.assertEqual(self.output, "")

    def test_bare_empty_maps_are_refused(self):
        with self.assertRaisesRegex(ValueError, "explicit ok/warn/error tallies"):
            self._digest({"counts": {}, "sources": {}, "workers": {}})
        self.assertEqual(self.output, "")

    def test_supported_legacy_and_current_empty_fleets_pass(self):
        empty = {"counts": {"ok": 0, "warn": 0, "error": 0}, "sources": {}, "workers": {}}
        self.assertEqual(self._digest(empty)["overdue_checks"], 0)
        self.assertEqual(self._digest({**empty, "schema_version": 3, "generated_at": at(-1)})["overdue_checks"], 0)


if __name__ == "__main__":
    unittest.main()
