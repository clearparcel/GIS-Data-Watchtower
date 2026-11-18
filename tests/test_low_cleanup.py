"""Low-severity cleanup from the review of ff9f9a7.

Findings 13, 16, 19, 20, 22, 23, 26, 27, 29 and 30. Offline: synthetic state,
temporary files and mocked storage only.
"""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import cli, cloud_job, county_monitoring, dashboard, watch
from clearparcel.datawatch.dashboard_exports import _snapshot_csv, _snapshot_xlsx
from clearparcel.datawatch.dashboard_summary import catalog_summary
from clearparcel.datawatch.public_values import catalog_approval, catalog_date

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.timezone.utc)
REPORTED = "2026-11-18T11:00:00+00:00"


def _xlsx_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as book:
        return "".join(book.read(name).decode("utf-8") for name in book.namelist()
                       if name.startswith("xl/worksheets/"))


def _statewide(state: dict) -> dict:
    with patch.object(dashboard, "_dashboard_state", return_value=state):
        return dashboard._statewide_snapshot({"sources": []})


class DeferredCheckTimeTests(unittest.TestCase):
    """13: a never-checked source exports no check time."""

    def test_deferred_source_keeps_a_null_check_time_in_every_format(self):
        state = {"sources": {"mn-x": {"name": "X", "status": "deferred", "checked_at": None,
                                      "worker": "cloud", "last_report_at": REPORTED, "stale": True}}}
        snapshot = _statewide(state)
        row = next(s for s in snapshot["sources"] if s["id"] == "mn-x")
        self.assertIsNone(row["checked_at"])
        self.assertEqual(row["last_report_at"], REPORTED)
        csv_row = next(r for r in csv.DictReader(io.StringIO(_snapshot_csv(snapshot))) if r["source_id"] == "mn-x")
        self.assertEqual((csv_row["checked_at"], csv_row["last_report_at"]), ("", REPORTED))
        sheets = _xlsx_text(_snapshot_xlsx(snapshot))
        self.assertIn("Worker last reported", sheets)
        self.assertIn(REPORTED, sheets)

    def test_checked_source_keeps_its_own_time(self):
        checked = "2026-11-18T10:00:00+00:00"
        snapshot = _statewide({"sources": {"s": {"status": "ok", "checked_at": checked, "last_report_at": REPORTED}}})
        self.assertEqual(snapshot["sources"][0]["checked_at"], checked)


class CatalogApprovalTests(unittest.TestCase):
    """19: yes/no and true/false agree; absent stays unknown."""

    def test_normalization(self):
        for value, expected in ((True, True), ("true", True), ("Yes", True), (" YES ", True),
                                (False, False), ("false", False), ("No", False),
                                (None, None), ("", None), ("maybe", None), (1, None)):
            with self.subTest(value=value):
                self.assertIs(catalog_approval(value), expected)

    def test_county_export_preserves_yes_no_and_unknown(self):
        def county(value):
            record = {"countyname": "Aitkin"} if value is None else {"countyname": "Aitkin", "gac_open_approval": value}
            state = {"sources": {"mn-parcel-county-catalog": {"status": "ok", "county_records": {"Aitkin": record}}}}
            with patch.object(dashboard, "_dashboard_state", return_value=state):
                return dashboard._county_snapshot({"sources": []}, "aitkin", state=state)
        for value, expected, cell in (("yes", True, "True"), ("true", True, "True"), ("No", False, "False"),
                                      ("false", False, "False"), (None, None, "")):
            with self.subTest(value=value):
                snapshot = county(value)
                self.assertIs(snapshot["public_data_approved"], expected)
                row = next(csv.DictReader(io.StringIO(_snapshot_csv(snapshot))))
                self.assertEqual(row["public_data_approved"], cell)
                # Column N of the Counties sheet is "Public data approved".
                sheets = _xlsx_text(_snapshot_xlsx(snapshot))
                self.assertIn('<c r="N1" t="inlineStr"><is><t xml:space="preserve">Public data approved</t>', sheets)
                cell = {True: '<c r="N2" t="b"><v>1</v></c>', False: '<c r="N2" t="b"><v>0</v></c>',
                        None: '<c r="N2" t="inlineStr"><is><t xml:space="preserve"></t></is></c>'}[expected]
                self.assertIn(cell, sheets)


class CatalogDateTests(unittest.TestCase):
    """20: one calendar-date reading for every view; implausible future is unknown."""

    def test_epoch_iso_date_and_datetime_agree(self):
        epoch = int(dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        for value in (epoch, "2026-11-01", "2026-11-01T00:00:00Z", "2026-10-31T19:00:00-05:00"):
            with self.subTest(value=value):
                self.assertEqual(catalog_date(value, now=NOW), dt.date(2026, 11, 1))
                self.assertEqual(dashboard._format_arcgis_date(value), "2026-11-01")

    def test_future_and_unreadable_dates_are_unknown(self):
        for value in ("2027-06-01", "not a date", None, 1.5, True, "2026-02-30"):
            with self.subTest(value=value):
                self.assertIsNone(catalog_date(value, now=NOW))
        self.assertEqual(catalog_date("2026-11-19", now=NOW), dt.date(2026, 11, 19))  # within tolerance

    def test_age_buckets_match_the_export(self):
        records = {"A": {"acqdate": "2026-11-01"}, "B": {"acqdate": "2027-06-01"},
                   "C": {"acqdate": "2025-01-01"}}
        state = {"sources": {"mn-parcel-county-catalog": {"status": "ok", "county_records": records}}}
        buckets = catalog_summary(state, ["A", "B", "C"], now=NOW)["buckets"]
        self.assertEqual((buckets["0–30 days"], buckets["Provider supplied no date"], buckets["Over 1 year"]), (1, 1, 1))
        self.assertEqual(dashboard._format_arcgis_date("2027-06-01"), "—")


class CountyIdentityReadTests(unittest.TestCase):
    """22: a statewide snapshot reads the county identity file a bounded number of times."""

    def test_identity_file_is_read_once_per_snapshot_build(self):
        real, reads = dashboard._load_counties, []

        def counting():
            reads.append(1)
            return real()

        with patch.object(dashboard, "_load_counties", side_effect=counting):
            snapshot = _statewide({"sources": {}})
        self.assertEqual(snapshot["county_count"], 87)
        self.assertLessEqual(len(reads), 3)

    def test_standalone_slug_lookup_still_works(self):
        self.assertEqual(dashboard._county_snapshot({"sources": []}, "aitkin", state={})["county"], "Aitkin")
        self.assertIsNone(dashboard._county_snapshot({"sources": []}, "nowhere", state={}))
        # A mismatched identity is ignored rather than trusted.
        wrong = {"name": "Aitkin", "slug": "aitkin"}
        self.assertEqual(dashboard._county_snapshot({"sources": []}, "anoka", state={}, county=wrong)["county"], "Anoka")


class UninitializedStatusTests(unittest.TestCase):
    """23: a missing state file is not a healthy status."""

    def run_status(self, state_file: Path):
        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / "config.json"
            config.write_text(json.dumps({"state_file": str(state_file), "sources": []}), encoding="utf-8")
            out = io.StringIO()
            with patch("sys.argv", ["watchtower", "--config", str(config), "status", "--json"]), \
                    contextlib.redirect_stdout(out):
                code = cli.main()
            return code, json.loads(out.getvalue())

    def test_missing_state_is_uninitialized_with_exit_1(self):
        with tempfile.TemporaryDirectory() as td:
            code, body = self.run_status(Path(td) / "missing.json")
        self.assertEqual(code, cli.EXIT_WARN)
        self.assertIs(body["uninitialized"], True)
        self.assertEqual(body["overall"], "unknown")

    def test_existing_state_keeps_its_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            state.write_text(json.dumps({"schema_version": 1, "overall": "ok", "sources": {}}), encoding="utf-8")
            code, body = self.run_status(state)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertNotIn("uninitialized", body)


class RestLayerUrlTests(unittest.TestCase):
    """16: bounded segment validation keeps every supported ArcGIS layer link."""

    def kind(self, url):
        return county_monitoring._source_kind({"kind": "direct_rest", "url": url})

    def test_supported_links(self):
        for url in ("https://gis.example.gov/arcgis/rest/services/Parcels/MapServer/0",
                    "https://gis.example.gov/server/rest/services/Folder/Parcels/FeatureServer/12?f=pjson",
                    "https://services.arcgis.com/abc/ArcGIS/REST/Services/Parcels/featureserver/3/"):
            with self.subTest(url=url):
                self.assertEqual(self.kind(url)[0], "arcgis_layer")

    def test_rejected_links(self):
        for url in ("https://gis.example.gov/arcgis/rest/services/MapServer/0",
                    "https://gis.example.gov/arcgis/rest/services//MapServer/0",
                    "https://gis.example.gov/arcgis/rest/services/Parcels/MapServer",
                    "https://gis.example.gov/arcgis/rest/services/Parcels/MapServer/x",
                    "https://gis.example.gov/arcgis/rest/services/Parcels/ImageServer/0",
                    "https://gis.example.gov/arcgis/services/Parcels/MapServer/0"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.kind(url)

    def test_adversarial_path_is_linear(self):
        path = "/rest/services/" + "a/" * 20000 + "MapServer/x"
        started = time.monotonic()
        self.assertFalse(county_monitoring._is_rest_layer_path(path))
        self.assertFalse(county_monitoring._is_rest_layer_path("/rest/services" * 150 + "/FeatureServer/0x"))
        self.assertLess(time.monotonic() - started, 0.5)


class RemovedStatisticsHelperTests(unittest.TestCase):
    """26: the unused, mislabeled statistics helper is gone."""

    def test_helper_removed(self):
        self.assertFalse(hasattr(watch, "_arcgis_statistics_query"))


class BuildEvidenceNameTests(unittest.TestCase):
    """27: the CI value is named as an image configuration digest."""

    def run_script(self, *extra):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "runtime.json").write_text(json.dumps({"python": "3.14.0", "components": []}), encoding="utf-8")
            (root / "os.tsv").write_text("", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "generate_supply_chain.py"),
                 "--revision", "a" * 40, "--base-image", "python@sha256:" + "b" * 64,
                 "--runtime-inventory", str(root / "runtime.json"), "--os-inventory", str(root / "os.tsv"),
                 "--sbom", str(root / "sbom.json"), "--provenance", str(root / "prov.json"), *extra],
                cwd=ROOT, capture_output=True, text=True)
            prov = json.loads((root / "prov.json").read_text(encoding="utf-8")) if result.returncode == 0 else None
            return result, prov

    def test_config_digest_and_optional_manifest_digest(self):
        config, manifest = "sha256:" + "c" * 64, "sha256:" + "d" * 64
        _result, prov = self.run_script("--image-config-digest", config, "--registry-manifest-digest", manifest)
        self.assertEqual(prov["schema"], "clearparcel.watchtower.build-provenance.v2")
        self.assertEqual((prov["image_config_digest"], prov["registry_manifest_digest"]), (config, manifest))
        self.assertNotIn("image_digest", prov)

    def test_legacy_flag_still_accepted_and_bad_digest_refused(self):
        _result, prov = self.run_script("--image-digest", "sha256:" + "c" * 64)
        self.assertIsNone(prov["registry_manifest_digest"])
        result, _ = self.run_script("--image-config-digest", "latest")
        self.assertNotEqual(result.returncode, 0)


class SharedWorkdirTests(unittest.TestCase):
    """29: a configured work directory is a parent; each run gets its own child."""

    def test_two_runs_use_distinct_children(self):
        seen = []
        with tempfile.TemporaryDirectory() as td, \
                patch.dict(os.environ, {"WATCHTOWER_WORKDIR": td}), \
                patch.object(cloud_job, "_run_cloud_job",
                             side_effect=lambda path, workdir, **kw: seen.append(workdir) or {}):
            cloud_job.run_cloud_job("config.json")
            cloud_job.run_cloud_job("config.json")
            self.assertEqual([p.parent for p in seen], [Path(td), Path(td)])
            self.assertNotEqual(seen[0], seen[1])
            self.assertFalse(any(p.exists() for p in seen))  # removed after each run

    def test_missing_parent_is_created(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td) / "nested" / "work"
            with patch.dict(os.environ, {"WATCHTOWER_WORKDIR": str(parent)}), \
                    patch.object(cloud_job, "_run_cloud_job", return_value={}):
                cloud_job.run_cloud_job("config.json")
            self.assertTrue(parent.is_dir())


class RingMetricTests(unittest.TestCase):
    """30: the multipart fields count shapes with more than one ring, holes included."""

    def test_polygon_with_a_hole_counts_as_multiple_ring(self):
        shell = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        hole = [[2, 2], [2, 4], [4, 4], [4, 2], [2, 2]]
        payload = {"features": [{"geometry": {"rings": [shell, hole]}}, {"geometry": {"rings": [shell]}}]}
        with patch.object(watch, "_json_request", return_value=(payload, None)):
            sample = watch._arcgis_geometry_sample("https://gis.example/0", 5, sample_size=2)
        self.assertEqual((sample["geometry_sample_multipart"], sample["geometry_sample_multipart_percent"]), (1, 50.0))
        guide = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
        self.assertIn("more than one\nring", guide)


if __name__ == "__main__":
    unittest.main()
