"""Regression checks for the sixth review using synthetic data and local storage."""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import public_dashboard, watch
from clearparcel.datawatch.aggregate import merge_states, retire_worker, with_freshness
from clearparcel.datawatch.county_profiles import FreshnessPolicy, _health
from clearparcel.datawatch.data_freshness import data_freshness
from clearparcel.datawatch.public_projection import InvalidSnapshotError, sanitize_public_render_state
from clearparcel.datawatch.public_publish import _snapshot_is_superseded
from clearparcel.datawatch.storage import LocalStorage
from tests.test_fifth_review import (META, NOW, TEN_DAYS, Publisher, _group, _metadata_row,
                                     at, deferred, fleet, measured)


class PublicationRecoveryTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.publisher = Publisher(self.root)

    def publish(self, state):
        self.assertTrue(self.publisher.publish(state)["published"])
        snapshot = self.publisher.destination()
        self.assertEqual(snapshot, sanitize_public_render_state(snapshot))
        return snapshot

    def seed_destination(self, state):
        path = self.root / "dest" / "aggregate-state.json"
        path.write_text(json.dumps(state), encoding="utf-8")

    def baseline(self, worker="cloud"):
        return merge_states(None, fleet(-40, {"s1": measured(-39, 100)}), worker, now=NOW)

    def test_unusable_destination_clock_allows_other_source_and_recovers(self):
        state = self.baseline()
        previous = self.publish(state)
        for document in (previous, state):
            document["sources"]["s1"]["last_success_at"] = at(TEN_DAYS)
        self.seed_destination(previous)
        state = merge_states(state, fleet(-20, {"s2": measured(-19, 80)}), "local", now=NOW)
        held = self.publish(state)
        self.assertEqual(held["sources"]["s2"]["feature_count"], 80)
        self.assertEqual(held["sources"]["s1"]["status"], "error")
        self.assertEqual(with_freshness(held, now=NOW)["sources"]["s1"]["reporting"], "stale")
        state = merge_states(state, fleet(-5, {"s1": measured(-4, 101)}), "cloud", now=NOW)
        self.assertEqual(self.publish(state)["sources"]["s1"]["feature_count"], 101)

    def test_unusable_retirement_clocks_keep_markers_and_allow_healthy_updates(self):
        state = self.baseline()
        old = self.publish(state)
        for doc in (state, old):
            doc["retired_workers"] = {"local": {"retired_at": at(TEN_DAYS)}}
            doc["retired_sources"] = {"removed": {"retired_at": at(TEN_DAYS)}}
        self.seed_destination(old)
        state = merge_states(state, fleet(-10, {"s1": measured(-9, 150)}), "cloud", now=NOW)
        public = self.publish(state)
        self.assertEqual(public["sources"]["s1"]["feature_count"], 150)
        self.assertEqual(public["retired_workers"], {"local": {}})
        self.assertEqual(public["retired_sources"], {"removed": {}})
        self.publish(state)

    def test_reinstatement_with_an_unusable_retirement_time_needs_a_new_check(self):
        self.publish(self.baseline())
        for retired_at in (None, "unreadable", at(TEN_DAYS)):
            with self.subTest(retired_at=retired_at):
                state = self.baseline()
                marker = {"retired_at": retired_at} if retired_at is not None else {}
                state["retired_sources"]["removed"] = marker
                # Model an upgrade where both stores already know the retirement.
                self.seed_destination(sanitize_public_render_state(state))
                for index, row in enumerate((deferred(), deferred(checked_at=at(-35)),
                                             {"status": "ok"}, measured(-50, 9))):
                    start = -30 + index * 4
                    partial = fleet(start, {"s1": measured(start + 1, index), "removed": row})
                    private = merge_states(state, partial, "cloud", now=NOW)
                    self.assertNotIn("removed", private["sources"])
                    self.assertIn("removed", private["retired_sources"])
                    # A rebuilt private state has no local copy of the tombstone.
                    rebuilt = merge_states(None, partial, "cloud", now=NOW)
                    self.assertTrue(_snapshot_is_superseded(rebuilt, self.publisher.destination(), NOW))
                    public = self.publish(rebuilt)
                    self.assertNotIn("removed", public["sources"])
                    self.assertIn("removed", public["retired_sources"])
                    self.assertEqual(public["sources"]["s1"]["feature_count"], index)
                    state = private
                omitted = merge_states(None, fleet(-10, {"s1": measured(-9, 12)}), "cloud", now=NOW)
                self.assertIn("removed", self.publish(omitted)["retired_sources"])
                fresh = fleet(-5, {"s1": measured(-4, 20), "removed": measured(-4, 30)})
                private = merge_states(state, fresh, "cloud", now=NOW)
                self.assertNotIn("removed", private["retired_sources"])
                self.assertEqual(self.publish(private)["sources"]["removed"]["feature_count"], 30)

    def test_migration_during_quarantine_honors_retirement(self):
        state = self.baseline("local")
        state = merge_states(state, fleet(-34, {"s2": measured(-33, 40)}), "cloud", now=NOW)
        self.publish(state)
        state = merge_states(state, fleet(-20, {"s1": measured(-19, 101), "s2": measured(-19, 80)}),
                             "cloud", now=NOW)
        state = retire_worker(state, "local", at(-10), now=NOW)
        state["sources"]["s1"]["checked_at"] = at(TEN_DAYS)
        public = self.publish(state)
        self.assertIn("local", public["retired_workers"])
        self.assertNotIn("local", public["workers"])
        self.assertNotIn("worker", public["sources"]["s1"])
        self.assertNotIn("feature_count", public["sources"]["s1"])
        self.assertTrue(public["sources"]["s1"]["check_withheld"])
        self.assertEqual(public["sources"]["s2"]["feature_count"], 80)
        self.assertEqual(self.publish(state)["sources"], public["sources"])

    def test_failure_and_warning_following_a_clock_correction(self):
        for status in ("error", "warn"):
            with self.subTest(status=status):
                state = self.baseline()
                self.seed_or_reset(state)
                fast = NOW + dt.timedelta(days=10)
                state = merge_states(state, fleet(TEN_DAYS, {"s1": measured(TEN_DAYS, 111)}), "cloud", now=fast)
                report = fleet(-10, {"s1": {"status": status, "checked_at": at(-9)}})
                report.update(overall=status, counts={status: 1})
                state = merge_states(state, report, "cloud", now=NOW)
                self.assertNotIn("last_success_at", state["sources"]["s1"])
                public = self.publish(state)
                row, worker = public["sources"]["s1"], public["workers"]["cloud"]
                self.assertEqual((row["status"], worker["overall"], public["overall"]), (status,) * 3)
                self.assertEqual((row["last_success_at"], worker["last_success_at"]), (at(-39), at(-40)))
                self.assertEqual(row["last_available_at"], at(-9) if status == "warn" else at(-39))
                self.assertEqual(worker["last_report_at"], at(-10))

    def seed_or_reset(self, state):
        (self.root / "dest" / "aggregate-state.json").unlink(missing_ok=True)
        self.publish(state)

    def test_reader_sees_empty_inventory_then_withheld_then_measured(self):
        state = self.baseline()
        empty = {**state, "sources": {}, "counts": {"ok": 0}, "overall": "ok"}
        state["sources"]["s1"]["checked_at"] = at(TEN_DAYS)
        recovered = merge_states(state, fleet(-5, {"s1": measured(-4, 101)}), "cloud", now=NOW)
        with patch.dict(os.environ, {"WATCHTOWER_PUBLIC_WORKDIR": str(self.root / "reader")}), \
                patch.object(public_dashboard, "backend_from_env", return_value=LocalStorage(self.root / "dest")):
            cache = public_dashboard._PublicStateCache()
            for candidate, expected in ((empty, "ok"), (state, "error"), (recovered, "ok")):
                self.publish(candidate)
                cache.refresh(force=True)
                public = json.loads(cache.public_path.read_text(encoding="utf-8"))
                self.assertEqual(public["overall"], expected)
                if expected == "error":
                    self.assertTrue(public["sources"]["s1"]["check_withheld"])
                    self.assertEqual(public["counts"]["error"], 1)

    def test_explicit_empty_check_is_overdue_and_cannot_replace_measurement(self):
        state = self.baseline()
        self.publish(state)
        record = state["sources"]["s1"]
        record.update(checked_at="", last_report_at=at(-1), feature_count=50)
        for snapshot in (state, sanitize_public_render_state(state)):
            self.assertEqual(with_freshness(snapshot, now=NOW)["sources"]["s1"]["reporting"], "stale")
            self.assertEqual(_health(snapshot["sources"]["s1"], snapshot, NOW, FreshnessPolicy())[1], "unknown")
        self.assertEqual(self.publish(state)["sources"]["s1"]["feature_count"], 100)
        del record["checked_at"]
        self.assertEqual(with_freshness(state, now=NOW)["sources"]["s1"]["reporting"], "current")

    def test_rebuilt_deferrals_match_private_merge_for_each_worker(self):
        for worker in ("cloud", "local"):
            state = self.baseline()
            self.seed_or_reset(state)
            report = fleet(-5, {"s1": deferred()})
            merged = merge_states(state, report, worker, now=NOW)
            rebuilt = merge_states(None, report, worker, now=NOW)
            if worker != "cloud":
                rebuilt["workers"]["cloud"] = state["workers"]["cloud"]
            public = self.publish(rebuilt)
            expected = sanitize_public_render_state(merged)["sources"]["s1"]
            self.assertEqual(public["sources"]["s1"], expected)
            for key in ("last_success_at", "last_available_at", "checked_at"):
                self.assertEqual(expected[key], at(-39))
            self.assertEqual(expected["worker"], "cloud")
            self.assertEqual(public["workers"][worker]["last_report_at"], at(-5))

    def test_legacy_destination_filtered_after_quarantine_and_carry(self):
        state = self.baseline()
        original = self.publish(state)
        original["sources"]["s1"].update(old_display_option="old", error=None)
        self.seed_destination(original)
        state["sources"]["s1"]["checked_at"] = "invalid"
        self.assertNotIn("old_display_option", self.publish(state)["sources"]["s1"])
        original["sources"]["s1"]["status"] = "error"
        original.update(counts={"error": 1}, overall="error")
        self.seed_destination(original)
        rebuilt = merge_states(None, fleet(-5, {"s1": deferred()}), "cloud", now=NOW)
        row = self.publish(rebuilt)["sources"]["s1"]
        self.assertEqual((row["status"], row["feature_count"]), ("error", 100))
        self.assertNotIn("old_display_option", row)
        self.assertNotIn("error", row)

    def test_unknown_worker_is_refused_at_input_and_publication(self):
        with self.assertRaisesRegex(ValueError, "worker name"):
            merge_states(None, fleet(-1, {"s1": measured(-1, 1)}), "archive", now=NOW)
        state = self.baseline()
        good = self.publish(state)
        state["sources"]["s1"]["worker"] = "archive"
        with self.assertRaisesRegex(InvalidSnapshotError, "invalid worker"):
            self.publisher.publish(state)
        self.assertEqual(self.publisher.destination(), good)
        for snapshot in (state, sanitize_public_render_state(state)):
            self.assertEqual(with_freshness(snapshot, now=NOW)["sources"]["s1"]["reporting"], "stale")
            self.assertEqual(_health(snapshot["sources"]["s1"], snapshot, NOW, FreshnessPolicy())[1], "unknown")


class ProviderEvidenceTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        self.source = {"id": "s", "name": "Parcels", "adapter": "arcgis_layer",
                       "url": "https://gis.example/FeatureServer/0", "count": True,
                       "gac_completeness": {"standard": "parcel", "batch_size": 1, "population_scope": "all"}}
        self.config = {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
                       "retries": 0, "sources": [self.source]}
        self.fields = [{"field": name, "data_type": "Text", "inclusion": "Mandatory"}
                       for name in ("CO_NAME", "CO_CODE")]
        self.layer = {"name": "Parcels", "geometryType": "esriGeometryPolygon", "objectIdField": "OBJECTID",
                      "fields": [{"name": n} for n in ("OBJECTID", "CO_NAME", "CO_CODE")]}

    def check(self, excluded_counts=(3, 3), metadata=None):
        batches = iter(excluded_counts)

        def request(url, timeout, **kwargs):
            if "/participation/" in url:
                return {"features": metadata}, META
            if "/query?" in url:
                return {"features": [_group("Aitkin", 7), _group(None, next(batches))]}, META
            if "/FeatureServer/0?" in url:
                return self.layer, META
            return {"layers": [{"name": "Parcels", "id": 0}]}, META

        watch.validate_source_registry([self.source])
        with patch.object(watch, "_json_request", side_effect=request), \
                patch.object(watch, "_arcgis_count_query", return_value=10), \
                patch.object(watch, "load_gac_standard", return_value={"fields": self.fields}):
            return watch.check_sources(self.config)["sources"]["s"]

    def test_direct_and_discovered_layers_retain_results_and_grade_failures(self):
        for adapter in ("arcgis_layer", "arcgis_service"):
            with self.subTest(adapter=adapter):
                self.config["state_file"] = str(Path(self.config["state_file"]).with_name(f"{adapter}.json"))
                if adapter == "arcgis_service":
                    self.source.update(adapter=adapter, discover_parcel_layer=True, url="https://gis.example/FeatureServer")
                good = self.check()
                observed = good["gac_completeness"]["observed_at"]
                self.assertEqual(good["status"], "ok")
                self.assertEqual(good["gac_completeness"]["record_count"], 7)
                bad = self.check((3, 10))
                self.assertEqual((bad["status"], bad["gac_check_status"]), ("warn", "error"))
                self.assertIn("inconsistent", bad["gac_check_error"])
                self.assertEqual(bad["gac_completeness"]["observed_at"], observed)

    def test_excluded_denominators_must_agree_in_both_batch_orders(self):
        for counts in ((10, 3), (3, 10)):
            with self.subTest(counts=counts):
                record = self.check(counts)
                self.assertEqual(record["status"], "warn")
                self.assertIn("inconsistent", record["gac_check_error"])
                self.assertFalse(record.get("gac_completeness"))

    def test_incomplete_identifier_or_flags_keep_previous_participation(self):
        self.source["gac_completeness"]["metadata_url"] = "https://gis.example/participation/0"
        rows = [_metadata_row("Aitkin"), _metadata_row("Anoka")]
        good = self.check(metadata=rows)["gac_completeness"]
        for key, replacement in (("gac_open", None), ("ng911_upload", None), ("county_name", 27)):
            broken = _metadata_row("Anoka")
            if replacement is None:
                del broken["attributes"][key]
            else:
                broken["attributes"][key] = replacement
            result = self.check(metadata=[rows[0], broken])
            self.assertEqual(result["status"], "warn")
            self.assertEqual(result["gac_completeness"]["observed_at"], good["observed_at"])
            self.assertIs(result["gac_completeness"]["county_metadata"]["Anoka"]["gac_open"], True)
        unknown = self.check(metadata=[rows[0], _metadata_row("Anoka", None)])
        self.assertEqual(unknown["status"], "ok")
        self.assertIsNone(unknown["gac_completeness"]["county_metadata"]["Anoka"]["gac_open"])

    def test_run_accepts_the_same_parcel_scopes_as_preflight(self):
        for scope in ("all", " ALL "):
            with self.subTest(scope=scope):
                self.source["gac_completeness"]["population_scope"] = scope
                record = self.check()
                self.assertEqual(record["status"], "ok")
                self.assertEqual(record["gac_completeness"]["population_scope"], "all")

    def test_extent_uses_its_own_reference(self):
        def extent(wkid, bounds):
            self.layer.update(sourceSpatialReference={"wkid": 26915},
                              extent=dict(zip(("xmin", "ymin", "xmax", "ymax"), bounds),
                                          spatialReference={"wkid": wkid}))
            return self.check()["spatial_extent"]

        geographic = extent(4326, (-94, 45, -93, 46))
        # A prior release could have tagged geographic coordinates as projected.
        legacy = {key: value for key, value in geographic.items() if key != "reference_version"}
        legacy["wkid"] = 3857
        projected = extent(3857, (-10464032, 5621521, -10352713, 5780349))
        self.assertEqual((geographic["wkid"], projected["wkid"]), (4326, 3857))
        self.assertIsNone(watch._extent_change(legacy, projected))
        self.assertTrue(watch._extent_change(geographic, projected)["incomparable"])
        moved = extent(4326, (-93, 45, -92, 46))
        self.assertGreater(watch._extent_change(geographic, moved)["max_extent_shift_percent"], 0)


class CurrencyTests(unittest.TestCase):
    def test_catalog_acquisition_keeps_same_instant_across_threshold(self):
        acquired = dt.datetime(2026, 11, 18, 20, tzinfo=dt.timezone.utc)
        for encoded in (int(acquired.timestamp() * 1000), acquired.isoformat(), "2026-11-18T14:00:00-06:00"):
            for hours, expected in ((23, "current"), (25, "stale")):
                verdict = data_freshness({"county_records": {"Anoka": {"acqdate": encoded}}},
                                         source_config={"expected_update_days": 1},
                                         now=acquired + dt.timedelta(hours=hours))
                self.assertEqual((verdict["data_updated_at"], verdict["state"]), (acquired.isoformat(), expected))

    def test_future_history_affects_neither_cadence_nor_fallback_selection(self):
        history = [{"data_updated_at": (NOW + dt.timedelta(days=d)).isoformat()} for d in (-130, -120, 365)]
        for current in (history[1], {}):
            result = data_freshness(current, history=history, now=NOW)
            self.assertEqual((result["state"], result["expected_days"], result["basis"]), ("stale", 90, "default"))
            self.assertEqual(result["data_updated_at"], history[1]["data_updated_at"])
