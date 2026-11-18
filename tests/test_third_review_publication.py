"""Aggregation and publication from the third review of 2310764 (T01, T02, T03, T10).

Offline: synthetic worker reports and aggregates in temporary local storage.
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from clearparcel.datawatch.aggregate import merge_states
from clearparcel.datawatch.public_projection import InvalidSnapshotError
from clearparcel.datawatch.public_publish import publish_public_snapshot, validate_private_aggregate
from clearparcel.datawatch.storage import LocalStorage

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def at(minutes: float) -> str:
    return (NOW + dt.timedelta(minutes=minutes)).isoformat()


def report(started: float, checked: float | None, count: int, *, scope: str = "source", status: str = "ok",
           deferred: bool = False) -> dict:
    record = {"id": "s1", "status": status, "checked_at": None if checked is None else at(checked),
              "feature_count": count}
    if deferred:
        record["deferred"] = {"reason": "provider-rate-limit"}
    return {"schema_version": 3, "generated_at": at(started), "overall": status, "scope": {"type": scope},
            "counts": {"ok": 1, "warn": 0, "error": 0}, "sources": {"s1": record}}


class Publisher:
    def __init__(self, root: Path):
        self.root = root
        (root / "source").mkdir(parents=True, exist_ok=True)

    def publish(self, aggregate: dict) -> dict:
        (self.root / "source" / "aggregate-state.json").write_text(json.dumps(aggregate), encoding="utf-8")
        return publish_public_snapshot(LocalStorage(self.root / "source"), LocalStorage(self.root / "dest"),
                                       workdir=self.root / "work")

    def destination(self) -> dict:
        return json.loads((self.root / "dest" / "aggregate-state.json").read_text(encoding="utf-8"))


class ObservationOrderTests(unittest.TestCase):
    """T01: overlapping workers never roll a source's provider observation backward."""

    def _merge(self, order):
        cloud = report(-30, -16, 100)   # run started first, observed later
        local = report(-25, -24, 50)    # run started later, observed earlier
        reports = {"cloud": cloud, "local": local}
        state = None
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            for worker in order:
                state = merge_states(state, reports[worker], worker, now=NOW)
                self.assertTrue(publisher.publish(state)["published"], worker)
            return state, publisher.destination()

    def test_both_arrival_orders_keep_the_newest_observation(self):
        for order in (("cloud", "local"), ("local", "cloud")):
            with self.subTest(order=order):
                state, public = self._merge(order)
                for snapshot in (state, public):
                    source = snapshot["sources"]["s1"]
                    self.assertEqual((source["feature_count"], source["checked_at"], source["worker"]),
                                     (100, at(-16), "cloud"))
                self.assertEqual(state["sources"]["s1"]["last_success_at"], at(-16))
                # Both workers' heartbeats are still recorded.
                self.assertEqual(set(state["workers"]), {"cloud", "local"})

    def test_deferred_record_never_replaces_a_newer_measurement(self):
        state = merge_states(None, report(-30, -29, 100), "cloud", now=NOW)
        state = merge_states(state, report(-20, -19, 120), "local", now=NOW)
        # cloud's next run is deferred and carries its own older observation.
        deferred = report(-10, -29, 100, status="warn", deferred=True)
        state = merge_states(state, deferred, "cloud", now=NOW)
        self.assertEqual((state["sources"]["s1"]["feature_count"], state["sources"]["s1"]["worker"]), (120, "local"))
        # A deferred first check (no observation) does not displace it either.
        state = merge_states(state, report(-5, None, 0, status="warn", deferred=True), "cloud", now=NOW)
        self.assertEqual(state["sources"]["s1"]["feature_count"], 120)

    def test_same_worker_updates_still_apply(self):
        state = merge_states(None, report(-30, -29, 100), "cloud", now=NOW)
        state = merge_states(state, report(-10, -9, 90), "cloud", now=NOW)
        state = merge_states(state, report(-5, -9, 90, status="warn", deferred=True), "cloud", now=NOW)
        self.assertEqual((state["sources"]["s1"]["status"], state["sources"]["s1"]["checked_at"]), ("warn", at(-9)))

    def test_publisher_refuses_an_older_observation(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            newer = merge_states(None, report(-30, -16, 100), "cloud", now=NOW)
            self.assertTrue(publisher.publish(newer)["published"])
            older = merge_states(None, report(-25, -24, 50), "cloud", now=NOW)
            self.assertEqual(publisher.publish(older)["reason"], "superseded")
            self.assertEqual(publisher.destination()["sources"]["s1"]["feature_count"], 100)


class FutureClockTests(unittest.TestCase):
    """T02: a future-dated aggregate cannot block later valid publications."""

    @staticmethod
    def _fleet(when: dt.datetime) -> dict:
        stamp = when.isoformat()
        return {"schema_version": 3, "generated_at": stamp, "overall": "ok", "counts": {"ok": 1, "warn": 0, "error": 0},
                "sources": {"s1": {"id": "s1", "status": "ok", "checked_at": stamp, "last_report_at": stamp,
                                   "worker": "cloud"}},
                "workers": {"cloud": {"last_report_at": stamp, "checked_at": stamp, "overall": "ok"}}}

    def test_future_aggregate_is_refused_and_recovery_publishes(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            self.assertTrue(publisher.publish(self._fleet(NOW - dt.timedelta(minutes=5)))["published"])
            with self.assertRaisesRegex(InvalidSnapshotError, "future"):
                publisher.publish(self._fleet(NOW + dt.timedelta(days=10)))
            self.assertEqual(publisher.destination()["generated_at"], at(-5))
            self.assertTrue(publisher.publish(self._fleet(NOW))["published"])
            # Anti-rollback still holds for plausible times.
            self.assertEqual(publisher.publish(self._fleet(NOW - dt.timedelta(minutes=10)))["reason"], "superseded")

    def test_already_poisoned_destination_does_not_block_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            poisoned = self._fleet(NOW + dt.timedelta(days=10))
            poisoned["public_published_at"] = at(0)
            (publisher.root / "dest").mkdir()
            (publisher.root / "dest" / "aggregate-state.json").write_text(json.dumps(poisoned), encoding="utf-8")
            result = publisher.publish(self._fleet(NOW))
            self.assertTrue(result["published"])
            self.assertEqual(publisher.destination()["generated_at"], at(0))

    def test_merge_ignores_stored_future_times(self):
        poisoned = self._fleet(NOW + dt.timedelta(days=10))
        state = merge_states(poisoned, report(-1, -1, 7, scope="fleet"), "cloud", now=NOW)
        self.assertEqual(state["generated_at"], at(-1))
        self.assertEqual(state["workers"]["cloud"]["last_report_at"], at(-1))
        self.assertEqual(state["sources"]["s1"]["feature_count"], 7)


class MalformedStatusTests(unittest.TestCase):
    """T03: a mistyped source status cannot publish beside an all-clear fleet."""

    @staticmethod
    def _aggregate(status) -> dict:
        source = {"id": "s1", "checked_at": at(-5)}
        if status is not ...:
            source["status"] = status
        return {"schema_version": 3, "generated_at": at(-5), "overall": "ok",
                "counts": {"ok": 0, "warn": 0, "error": 0}, "sources": {"s1": source}, "workers": {}}

    def test_invalid_status_is_rejected_and_good_publication_kept(self):
        for status in ("erorr", "OK", "", 1, "unsupported"):
            with self.subTest(status=status), self.assertRaisesRegex(InvalidSnapshotError, "invalid status"):
                validate_private_aggregate(self._aggregate(status))
        with tempfile.TemporaryDirectory() as td:
            publisher = Publisher(Path(td))
            good = FutureClockTests._fleet(NOW - dt.timedelta(minutes=10))
            self.assertTrue(publisher.publish(good)["published"])
            before = (publisher.root / "dest" / "aggregate-state.json").read_bytes()
            with self.assertRaises(InvalidSnapshotError):
                publisher.publish(self._aggregate("erorr"))
            self.assertEqual((publisher.root / "dest" / "aggregate-state.json").read_bytes(), before)

    def test_legacy_unknown_and_absent_status_remain_supported(self):
        for status in ("unknown", None, ...):
            with self.subTest(status=status):
                validate_private_aggregate(self._aggregate(status))


if __name__ == "__main__":
    unittest.main()
