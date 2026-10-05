import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from clearparcel.datawatch.dashboard import render_counties
from clearparcel.datawatch.public_dashboard import (
    render_public_dashboard,
    sanitize_public_render_state,
)


class PublicDashboardTests(unittest.TestCase):
    def _state(self):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        return {
            "schema_version": 2,
            "generated_at": now,
            "overall": "ok",
            "counts": {"ok": 2, "warn": 0, "error": 0},
            "workers": {
                "cloud": {
                    "overall": "ok",
                    "source_count": 2,
                    "last_success_at": now,
                    "telemetry": {"private_runtime_detail": "hidden"},
                }
            },
            "sources": {
                "county-parcels-direct": {
                    "id": "county-parcels-direct",
                    "name": "County Parcels",
                    "provider": "Example County",
                    "category": "Parcels",
                    "county_slug": "olmsted",
                    "status": "ok",
                    "feature_count": 10,
                    "checked_at": now,
                    "worker": "cloud",
                    "changes": [{"type": "tracked_value", "previous": "PRIVATE-OLD", "current": "PRIVATE-NEW"}],
                    "tracked_values": {"secret": "PRIVATE-VALUE"},
                    "url": "https://secret.invalid/private",
                    "schema_hash": "PRIVATE-SCHEMA",
                    "observation_fingerprint": "PRIVATE-FINGERPRINT",
                    "field_count": 12,
                    "parcel_id_null_count": 0,
                },
                "mn-state-parcels": {
                    "id": "mn-state-parcels",
                    "name": "Minnesota State Parcels",
                    "provider": "MnGeo",
                    "category": "Parcels",
                    "status": "ok",
                    "checked_at": now,
                    "worker": "cloud",
                    "mngac_completeness": {
                        "standard": {"name": "MN GAC", "version": "1", "source_url": "https://example.invalid/standard"},
                        "method": "grouped statistics",
                        "record_count": 10,
                        "field_count": 1,
                        "covered_counties": 1,
                        "field_population_percent": 80.0,
                        "mandatory_field_count": 1,
                        "mandatory_population_percent": 100.0,
                        "source_schema_missing_fields": [],
                        "statistics_queries": [{"url": "https://secret.invalid/query"}],
                        "fields": {"PIN": {"percent": 100.0}},
                        "counties": {"Olmsted": {"record_count": 10, "fields": {"PIN": {"percent": 100.0}}}},
                    },
                },
            },
        }

    def test_public_state_removes_operational_details_and_keeps_public_metrics(self):
        public = sanitize_public_render_state(self._state())
        source = public["sources"]["county-parcels-direct"]
        self.assertEqual(source["change_count"], 1)
        self.assertNotIn("url", source)
        self.assertNotIn("changes", source)
        self.assertNotIn("tracked_values", source)
        self.assertNotIn("schema_hash", source)
        self.assertNotIn("observation_fingerprint", source)
        self.assertNotIn("telemetry", public["workers"]["cloud"])

        mngac = public["sources"]["mn-state-parcels"]["mngac_completeness"]
        self.assertEqual(mngac["field_population_percent"], 80.0)
        self.assertNotIn("statistics_queries", mngac)

    def test_public_overview_does_not_emit_private_values(self):
        public = sanitize_public_render_state(self._state())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state.json"
            history = root / "history.jsonl"
            state.write_text(json.dumps(public), encoding="utf-8")
            history.write_text("", encoding="utf-8")
            config = {
                "state_file": str(state),
                "aggregate_state_file": str(state),
                "history_file": str(history),
                "sources": [],
                "_public_mode": True,
            }
            page = render_public_dashboard(config)
            self.assertIn("County Parcels", page)
            self.assertNotIn("secret.invalid/private", page)
            self.assertNotIn("PRIVATE-SCHEMA", page)
            self.assertNotIn("PRIVATE-FINGERPRINT", page)
            self.assertNotIn('<form method="post" action="/refresh"', page)

    def test_public_county_index_hides_refresh_control(self):
        public = sanitize_public_render_state(self._state())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state.json"
            history = root / "history.jsonl"
            state.write_text(json.dumps(public), encoding="utf-8")
            history.write_text("", encoding="utf-8")
            config = {
                "state_file": str(state),
                "aggregate_state_file": str(state),
                "history_file": str(history),
                "sources": [],
                "_public_mode": True,
            }
            page = render_counties(config)
            self.assertIn("Minnesota county dashboards", page)
            self.assertNotIn('<form method="post" action="/refresh"', page)


if __name__ == "__main__":
    unittest.main()
