import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from clearparcel.datawatch.alert_policies import build_policies
from clearparcel.datawatch.provider_watchdog import LOG_KEY

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "render_alert_policies.py"
ARGS = {"provider_job": "example-provider", "publisher_job": "example-publisher",
        "channel": "projects/example-project/notificationChannels/123"}


class BuildPoliciesTests(unittest.TestCase):
    def setUp(self):
        self.policies = build_policies(**ARGS)

    def test_three_policies_all_routed_to_the_channel(self):
        self.assertEqual(set(self.policies), {"provider-tool-failure", "provider-run-overdue", "publisher-absent"})
        for policy in self.policies.values():
            self.assertEqual(policy["notificationChannels"], [ARGS["channel"]])
            self.assertTrue(policy["enabled"])
            self.assertIn("operations-triage.md", policy["documentation"]["content"])

    def test_tool_failure_matches_only_exit_3_of_the_provider_job(self):
        condition = self.policies["provider-tool-failure"]["conditions"][0]["conditionMatchedLog"]
        self.assertIn('resource.labels.job_name="example-provider"', condition["filter"])
        self.assertIn('textPayload:"Container called exit(3)"', condition["filter"])
        for other in ("exit(1)", "exit(2)", "exit(4)"):
            self.assertNotIn(other, condition["filter"])

    def test_overdue_policy_matches_the_watchdog_log_key_on_the_publisher(self):
        policy = self.policies["provider-run-overdue"]
        condition = policy["conditions"][0]["conditionMatchedLog"]
        self.assertIn('resource.labels.job_name="example-publisher"', condition["filter"])
        self.assertIn(f"jsonPayload.{LOG_KEY}.worker:*", condition["filter"])
        self.assertIn("severity=ERROR", condition["filter"])
        # Log-match conditions require a notification rate limit.
        self.assertEqual(policy["alertStrategy"]["notificationRateLimit"]["period"], "21600s")

    def test_publisher_absence_fits_under_the_platform_cap(self):
        absent = self.policies["publisher-absent"]["conditions"][0]["conditionAbsent"]
        seconds = int(absent["duration"].rstrip("s"))
        self.assertLessEqual(seconds, int(23.5 * 3600))
        self.assertIn('job_name="example-publisher"', absent["filter"])
        self.assertIn("completed_execution_count", absent["filter"])

    def test_invalid_identifiers_are_refused(self):
        bad = [
            {**ARGS, "provider_job": "Bad_Name"},
            {**ARGS, "publisher_job": ARGS["provider_job"]},
            {**ARGS, "channel": "notificationChannels/123"},
            {**ARGS, "channel": 'projects/x"; DROP/notificationChannels/1'},
            {**ARGS, "provider_job": 'job" OR resource.type:*'},
        ]
        for args in bad:
            with self.assertRaises(ValueError):
                build_policies(**args)

    def test_policies_are_json_serializable(self):
        json.dumps(self.policies, allow_nan=False)


class RenderScriptTests(unittest.TestCase):
    def _run(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "--provider-job", ARGS["provider_job"],
                               "--publisher-job", ARGS["publisher_job"], "--channel", ARGS["channel"], *extra],
                              capture_output=True, text=True)

    def test_renders_three_files_and_prints_apply_commands(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._run("--output-dir", td)
            self.assertEqual(result.returncode, 0, result.stderr)
            files = sorted(p.name for p in Path(td).iterdir())
            self.assertEqual(files, ["provider-run-overdue.json", "provider-tool-failure.json",
                                     "publisher-absent.json"])
            self.assertEqual(result.stdout.count("gcloud monitoring policies create --policy-from-file="), 3)
            self.assertIn("not applied", result.stdout)

    def test_refuses_to_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self._run("--output-dir", td).returncode, 0)
            self.assertEqual(self._run("--output-dir", td).returncode, 2)

    def test_refuses_an_output_folder_inside_the_repository(self):
        result = self._run("--output-dir", str(REPO / "rendered-policies-test"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside the public repository", result.stderr)
        self.assertFalse((REPO / "rendered-policies-test").exists())


if __name__ == "__main__":
    unittest.main()
