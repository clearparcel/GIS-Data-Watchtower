"""Publication and projection from the follow-up review of f8f0997 (F01, F11, F12).

Offline: synthetic aggregates, temporary local storage and in-process rendering.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.dashboard_counties import render_counties
from clearparcel.datawatch.dashboard_exports import _snapshot_csv, _snapshot_xlsx
from clearparcel.datawatch.dashboard_summary import catalog_summary
from clearparcel.datawatch.public_projection import InvalidSnapshotError, sanitize_public_render_state
from clearparcel.datawatch.public_publish import publish_public_snapshot, validate_private_aggregate
from clearparcel.datawatch.public_values import catalog_date
from clearparcel.datawatch.storage import LocalStorage

NOW = dt.datetime.now(dt.timezone.utc)
FRESH = (NOW - dt.timedelta(hours=1)).isoformat()


def _aggregate(counts: dict, sources: dict | None = None) -> dict:
    return {"schema_version": 3, "generated_at": FRESH, "overall": "ok", "counts": counts,
            "sources": sources or {}, "workers": {}}


class InvalidTallyTests(unittest.TestCase):
    """F01: invalid or disagreeing counts are refused before projection drops them."""

    def _publish(self, root: Path, aggregate: dict) -> dict:
        (root / "source").mkdir(parents=True, exist_ok=True)
        (root / "source" / "aggregate-state.json").write_text(json.dumps(aggregate), encoding="utf-8")
        return publish_public_snapshot(LocalStorage(root / "source"), LocalStorage(root / "dest"),
                                       workdir=root / "work")

    def test_invalid_counts_are_rejected(self):
        for counts in ({"ok": 0, "warn": 0, "error": -1}, {"ok": "5"}, {"error": "x"}, {"ok": True},
                       {"ok": 1.0}, {"ok": 2, "warn": 0, "error": 0}):
            with self.subTest(counts=counts), self.assertRaises(InvalidSnapshotError):
                validate_private_aggregate(_aggregate(counts))

    def test_rejection_leaves_empty_and_existing_destinations_intact(self):
        good = _aggregate({"ok": 1, "warn": 0, "error": 0},
                          {"s": {"id": "s", "status": "ok", "checked_at": FRESH}})
        bad = _aggregate({"ok": 0, "warn": 0, "error": -1})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(InvalidSnapshotError):
                self._publish(root, bad)
            self.assertFalse((root / "dest" / "aggregate-state.json").exists())
            self.assertTrue(self._publish(root, good)["published"])
            before = (root / "dest" / "aggregate-state.json").read_bytes()
            with self.assertRaises(InvalidSnapshotError):
                self._publish(root, {**bad, "generated_at": (NOW - dt.timedelta(minutes=5)).isoformat()})
            self.assertEqual((root / "dest" / "aggregate-state.json").read_bytes(), before)

    def test_deliberately_empty_fleet_still_publishes(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._publish(Path(td), _aggregate({"ok": 0, "warn": 0, "error": 0}))
        self.assertTrue(result["published"])
        self.assertEqual(result["source_count"], 0)


def _catalog_state(record: dict) -> dict:
    return {"generated_at": FRESH, "counts": {"ok": 1, "warn": 0, "error": 0}, "workers": {},
            "sources": {"mn-parcel-county-catalog": {
                "id": "mn-parcel-county-catalog", "status": "ok", "checked_at": FRESH,
                "county_records": {"Aitkin": {"countyname": "Aitkin", **record}}}}}


def _county(state: dict) -> dict:
    with patch.object(dashboard, "_dashboard_state", return_value=state):
        return dashboard._county_snapshot({"sources": []}, "aitkin", state=state)


class PaddedApprovalTests(unittest.TestCase):
    """F11: padded yes/no values survive anonymous publication into the export."""

    def test_publication_to_export(self):
        for value, expected, cell in ((" YES ", True, "True"), (" No ", False, "False"), (None, None, "")):
            with self.subTest(value=value):
                record = {} if value is None else {"gac_open_approval": value}
                public = sanitize_public_render_state(_catalog_state(record))
                snapshot = _county(public)
                self.assertIs(snapshot["public_data_approved"], expected)
                row = next(csv.DictReader(io.StringIO(_snapshot_csv(snapshot))))
                self.assertEqual(row["public_data_approved"], cell)


class YearBoundaryDateTests(unittest.TestCase):
    """F12: an unrepresentable UTC date is unknown, and the county output still renders."""

    LATE = "9999-12-31T23:00:00-05:00"
    EARLY = "0001-01-01T00:30:00+01:00"

    def test_catalog_date_treats_overflow_as_unknown(self):
        self.assertIsNone(catalog_date(self.LATE, now=NOW))
        self.assertIsNone(catalog_date(self.EARLY, now=NOW))

    def test_projection_summary_rendering_and_export_survive(self):
        public = sanitize_public_render_state(_catalog_state({"acqdate": self.LATE, "rundate": self.EARLY}))
        summary = catalog_summary(public, ["Aitkin"], now=NOW)
        self.assertEqual(summary["buckets"]["Provider supplied no date"], 1)
        snapshot = _county(public)
        _snapshot_csv(snapshot)
        _snapshot_xlsx(snapshot)
        page = render_counties({"_render_state": public, "state_file": "unused.json"})
        self.assertIn('data-name="aitkin"', page)


if __name__ == "__main__":
    unittest.main()
