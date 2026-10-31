"""Settled alert-ledger records are pruned after the retention horizon (audit WT31-12 / A08)."""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from clearparcel.datawatch import alert_delivery as ad
from clearparcel.datawatch.storage import LocalStorage

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def record(key, state, days_ago):
    at = (NOW - timedelta(days=days_ago)).isoformat()
    return {"event_key": key, "state": state, "attempts": 1, "type": "failure", "worker": "cloud",
            "source_id": "s", "subject": "x", "message": "x", "accepted_at": at,
            "history": [{"at": at, "state": state}]}


class LedgerRetentionTests(unittest.TestCase):
    def ledger(self, *records):
        return {"schema_version": 1, "private_evidence": True,
                "events": {r["event_key"]: r for r in records}}

    def test_default_horizon_is_180_days(self):
        self.assertEqual(ad.normalize_config({})["retention_days"], 180)

    def test_old_settled_records_are_pruned_and_recent_ones_kept(self):
        data = self.ledger(record("old-sent", "sent", 200), record("new-sent", "sent", 10),
                           *[record(f"old-{s}", s, 400) for s in ("exhausted", "expired", "superseded",
                                                                  "acknowledged")])
        pruned = ad._prune(data, NOW, ad.normalize_config({}), set())
        self.assertEqual(set(data["events"]), {"new-sent"})
        self.assertEqual(len(pruned), 5)
        ad.validate_ledger(data)

    def test_unsettled_records_are_never_pruned(self):
        data = self.ledger(*[record(f"old-{s}", s, 400) for s in ("queued", "retry_wait", "ambiguous")])
        self.assertEqual(ad._prune(data, NOW, ad.normalize_config({}), set()), [])
        self.assertEqual(len(data["events"]), 3)

    def test_a_still_current_key_is_kept_so_it_is_not_sent_again(self):
        data = self.ledger(record("continuing", "acknowledged", 400))
        self.assertEqual(ad._prune(data, NOW, ad.normalize_config({}), {"continuing"}), [])
        self.assertIn("continuing", data["events"])

    def test_a_recent_transition_resets_the_age(self):
        old = record("reviewed", "acknowledged", 400)
        old["history"].append({"at": (NOW - timedelta(days=5)).isoformat(), "state": "acknowledged"})
        data = self.ledger(old)
        self.assertEqual(ad._prune(data, NOW, ad.normalize_config({}), set()), [])

    def test_retention_setting_is_bounded(self):
        for bad in (0, -1, 3651, True, "180"):
            with self.assertRaises(ValueError):
                ad.normalize_config({"retention_days": bad})
        self.assertEqual(ad.normalize_config({"retention_days": 30})["retention_days"], 30)


    def test_delivery_write_prunes_the_stored_ledger(self):
        from tests.test_alert_delivery import ENABLED, ROUTE, FakeTransport, err, expected
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = ad.AlertLedger(LocalStorage(root))
            path = root / "alerts" / "delivery-ledger.json"
            path.parent.mkdir(parents=True)
            stale = record("stale", "sent", 365)
            stale["accepted_at"] = stale["history"][0]["at"] = "2025-10-01T00:00:00+00:00"
            path.write_text(json.dumps(self.ledger(stale)), encoding="utf-8")
            ad.deliver_alerts([err(20)], expected_sources=expected(), routing=ROUTE,
                              as_of="2026-10-20T12:00:00Z", config=ENABLED,
                              transport=FakeTransport(), ledger=ledger)
            events, _ = ledger.read()
            self.assertNotIn("stale", events["events"])
            self.assertEqual(len(events["events"]), 1)


if __name__ == "__main__":
    unittest.main()
