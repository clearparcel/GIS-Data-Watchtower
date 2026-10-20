import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from clearparcel.datawatch import cli
from clearparcel.datawatch.alert_delivery import AlertLedger, DEFAULT_LEDGER_NAME
from clearparcel.datawatch.alert_test import TEST_LEDGER, TEST_SOURCE, run_alert_test
from clearparcel.datawatch.storage import LocalStorage

PRIVATE = json.dumps({"delivery": {"enabled": False, "transport": "fake"},
                      "routing": {"channel": "email", "recipient": "operator@example.invalid",
                                  "escalation_owner": "Synthetic operator",
                                  "runbook_ref": "docs/alert-routing.md"}})


class Fake:
    name, replay_safe, sent = "fake", False, []

    def send(self, digest):
        Fake.sent.append(digest)
        return {"provider_ref": "fake"}


class AlertTestCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.storage = LocalStorage(self._tmp.name)
        Fake.sent = []

    def tearDown(self):
        self._tmp.cleanup()

    def send(self, kind, nonce):
        return run_alert_test(kind, storage=self.storage, transports={"fake": Fake},
                              environ={"WATCHTOWER_ALERT_DELIVERY_CONFIG": PRIVATE,
                                       "CLOUD_RUN_EXECUTION": nonce})

    def test_failure_and_recovery_send_labeled_synthetic_digests(self):
        self.assertEqual(self.send("failure", "a")["notification_delivery"], "handed_off")
        self.assertEqual(self.send("recovery", "b")["notification_delivery"], "handed_off")
        self.assertEqual([e["type"] for d in Fake.sent for e in d["events"]],
                         ["source_error", "recovered"])
        for digest in Fake.sent:
            self.assertTrue(digest["subject"].startswith("TEST - "))
            self.assertIn("SYNTHETIC DELIVERY TEST", digest["body"])
            self.assertEqual({e["source_id"] for e in digest["events"]}, {TEST_SOURCE})
            self.assertNotIn("operator@example.invalid", json.dumps(digest))

    def test_uses_its_own_ledger_and_ignores_the_production_flag(self):
        self.send("failure", "a")
        root = Path(self._tmp.name)
        self.assertTrue((root / TEST_LEDGER).exists())
        self.assertFalse((root / DEFAULT_LEDGER_NAME).exists())
        self.assertEqual(len(AlertLedger(self.storage, TEST_LEDGER).read()[0]["events"]), 1)
        again = self.send("failure", "a")
        self.assertEqual(again["notification_delivery"], "nothing_to_send")
        self.assertEqual(len(Fake.sent), 1)

    def test_requires_routing_configuration(self):
        with self.assertRaises(ValueError):
            run_alert_test("failure", storage=self.storage, transports={"fake": Fake}, environ={})
        with self.assertRaises(ValueError):
            run_alert_test("other", storage=self.storage, transports={"fake": Fake},
                           environ={"WATCHTOWER_ALERT_DELIVERY_CONFIG": PRIVATE})

    def test_cli_requires_explicit_confirmation_and_never_loads_sources(self):
        stderr = io.StringIO()
        with patch("sys.argv", ["watchtower", "alert-test", "--kind", "failure"]), \
                patch("clearparcel.datawatch.watch.check_sources") as polled, \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(cli.main(), cli.EXIT_TOOL_FAILURE)
        polled.assert_not_called()
        self.assertIn("confirm-test-send", stderr.getvalue())

    def test_cli_sends_through_the_configured_transport(self):
        stdout = io.StringIO()
        env = {"WATCHTOWER_ALERT_DELIVERY_CONFIG": PRIVATE, "WATCHTOWER_STORAGE": "local",
               "WATCHTOWER_STORAGE_ROOT": self._tmp.name}
        with patch.dict(os.environ, env), \
                patch.dict("clearparcel.datawatch.alert_delivery.TRANSPORTS", {"fake": Fake}), \
                patch("sys.argv", ["watchtower", "alert-test", "--kind", "failure",
                                   "--confirm-test-send"]), \
                patch("clearparcel.datawatch.watch.check_sources") as polled, \
                contextlib.redirect_stdout(stdout):
            self.assertEqual(cli.main(), cli.EXIT_OK)
        polled.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue())["delivery"], "handed_off")


if __name__ == "__main__":
    unittest.main()
