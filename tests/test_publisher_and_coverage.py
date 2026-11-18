"""Publication and coverage must not count what was never observed.

Review of ff9f9a7, findings 04, 10 and 11. Offline: synthetic aggregates and
temporary local storage only.
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from clearparcel.datawatch.aggregate import with_freshness
from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles
from clearparcel.datawatch.parcel_access import load_parcel_access
from clearparcel.datawatch.public_projection import InvalidSnapshotError
from clearparcel.datawatch.public_publish import publish_public_snapshot
from clearparcel.datawatch.storage import LocalStorage

NOW = dt.datetime.now(dt.timezone.utc)
FRESH = (NOW - dt.timedelta(hours=1)).isoformat()
STALE = (NOW - dt.timedelta(days=5)).isoformat()
FUTURE = (NOW + dt.timedelta(days=5)).isoformat()


class MalformedAggregateTests(unittest.TestCase):
    """04: a malformed private aggregate never becomes a healthy empty publication."""

    def publish(self, root: Path, aggregate: dict):
        source = LocalStorage(root / "source")
        (root / "source").mkdir(parents=True)
        (root / "source" / "aggregate-state.json").write_text(json.dumps(aggregate), encoding="utf-8")
        return publish_public_snapshot(source, LocalStorage(root / "dest"), workdir=root / "work")

    def test_malformed_containers_create_no_destination(self):
        base = {"schema_version": 3, "generated_at": FRESH}
        for broken in ({**base, "sources": [{"id": "a", "status": "ok"}], "counts": {}, "workers": {}},
                       {**base, "sources": {}, "workers": {}},
                       {**base, "sources": {"a": "ok"}, "counts": {}, "workers": {}},
                       {**base, "sources": {}, "counts": {}, "workers": {}, "retired_workers": []}):
            with self.subTest(aggregate=broken), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                with self.assertRaises(InvalidSnapshotError):
                    self.publish(root, broken)
                self.assertFalse((root / "dest" / "aggregate-state.json").exists())

    def test_structurally_valid_empty_fleet_still_publishes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = self.publish(root, {"schema_version": 3, "generated_at": FRESH, "overall": "ok",
                                         "counts": {"ok": 0, "warn": 0, "error": 0}, "sources": {}, "workers": {}})
            self.assertTrue(result["published"])
            self.assertEqual(result["source_count"], 0)


def _direct(slug: str, *, worker: str | None = "cloud") -> dict:
    source = {"id": f"mn-{slug}-parcels", "county_slug": slug, "category": "Parcels", "adapter": "arcgis_layer",
              "status": "ok", "checked_at": FRESH, "last_success_at": FRESH}
    if worker:
        source["worker"] = worker
    return source


def _profiles(state: dict) -> dict:
    return compose_county_profiles(state, load_parcel_access(), now=NOW, freshness_policy=FreshnessPolicy())


class MissingWorkerReportTests(unittest.TestCase):
    """10: an assigned source needs its worker's report to count as current."""

    def test_worker_record_cases_against_the_same_fresh_source(self):
        cases = {"missing": None, "stale": STALE, "future": FUTURE, "fresh": FRESH}
        expected = {"missing": "unknown", "stale": "overdue", "future": "unknown", "fresh": "current"}
        for case, report in cases.items():
            workers = {} if report is None else {"cloud": {"last_report_at": report}}
            with self.subTest(case=case):
                profile = _profiles({"generated_at": FRESH, "workers": workers,
                                     "sources": {"s": _direct("wabasha")}})["wabasha"]
                self.assertEqual(profile["monitoring"]["reporting"], expected[case])

    def test_legacy_unassigned_source_keeps_its_own_clock(self):
        profile = _profiles({"generated_at": FRESH, "sources": {"s": _direct("wabasha", worker=None)}})["wabasha"]
        self.assertEqual(profile["monitoring"]["reporting"], "current")

    def test_aggregate_freshness_marks_a_missing_worker_stale(self):
        state = with_freshness({"workers": {}, "sources": {"s": _direct("wabasha"),
                                                          "legacy": _direct("wabasha", worker=None)}}, now=NOW)
        self.assertTrue(state["sources"]["s"]["worker_stale"])
        self.assertEqual(state["sources"]["s"]["reporting"], "stale")
        self.assertFalse(state["sources"]["legacy"]["worker_stale"])


class HeldDirectCoverageTests(unittest.TestCase):
    """11: a stored observation from a held county-direct source is history, not coverage."""

    def test_held_direct_only_county_has_no_active_path(self):
        research = load_parcel_access()
        self.assertEqual(research["Brown"]["monitoring"]["decision"], "hold-for-terms")
        observed = {**_direct("brown", worker=None), "id": "mn-brown-parcels-direct", "feature_count": 42}
        profile = _profiles({"generated_at": FRESH, "sources": {observed["id"]: observed}})["brown"]
        self.assertEqual(profile["monitoring"]["paths"], [])
        self.assertFalse(profile["monitoring"]["active"])
        # The observation itself is retained in the county profile.
        source = profile["county_arcgis_rest"]["sources"][0]
        self.assertEqual((source["monitored_source_id"], source["feature_count"]), (observed["id"], 42))

    def test_held_county_with_a_statewide_path_keeps_only_that_path(self):
        research = load_parcel_access()
        self.assertEqual(research["Murray"]["monitoring"]["decision"], "not-appropriate")
        statewide = {"id": "statewide", "category": "Parcels", "status": "ok", "checked_at": FRESH,
                     "last_success_at": FRESH, "mngac_completeness": {"fields": {"PIN": {}},
                                                                     "counties": {"Murray": {"record_count": 10}}}}
        profile = _profiles({"generated_at": FRESH, "sources": {
            "statewide": statewide, "m": _direct("murray", worker=None)}})["murray"]
        self.assertEqual(profile["monitoring"]["paths"], ["mngeo-open"])
        self.assertEqual(profile["monitoring"]["active_parcel_source_count"], 1)


if __name__ == "__main__":
    unittest.main()
