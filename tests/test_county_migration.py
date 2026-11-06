import datetime as dt
import json
import unittest

from clearparcel.datawatch.county_migration import verify_county_migration
from clearparcel.datawatch.dashboard import _statewide_snapshot


class CountyMigrationTests(unittest.TestCase):
    def snapshot(self):
        return _statewide_snapshot({"_public_mode": True, "_render_state": {"sources": {}}})

    def verify(self, snapshot, **kwargs):
        return verify_county_migration(json.dumps(snapshot).encode(), **kwargs)

    def test_verifier_keeps_monitoring_observations_separate_from_migration(self):
        snapshot = self.snapshot()
        report = self.verify(snapshot)
        self.assertTrue(report["ready"], report["exceptions"])
        self.assertEqual(report["counties"], 87)
        self.assertEqual(report["deployed_contacts"], report["packaged_contacts"])
        self.assertTrue(report["statewide_observation_differences"])

    def test_verifier_blocks_contact_drift_and_reports_only_county_and_field(self):
        snapshot = self.snapshot()
        snapshot["counties"][0]["contacts"][0]["email"] = "synthetic-drift@example.org"
        report = self.verify(snapshot)
        self.assertFalse(report["ready"])
        self.assertIn({"county": "Aitkin", "field": "contacts"}, report["exceptions"])
        self.assertNotIn("synthetic-drift", json.dumps(report))

    def test_rejects_incomplete_duplicate_and_stale_exports(self):
        snapshot = self.snapshot()
        snapshot["counties"][-1] = snapshot["counties"][0]
        with self.assertRaisesRegex(ValueError, "duplicate or invalid"):
            self.verify(snapshot)
        with self.assertRaisesRegex(ValueError, "outside the freshness window"):
            self.verify(self.snapshot(), now=dt.datetime.now(dt.UTC) + dt.timedelta(days=2))
