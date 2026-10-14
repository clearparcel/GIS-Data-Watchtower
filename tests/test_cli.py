"""Command-line contract: commands, exit codes and argument validation."""
import contextlib
import io
import unittest
from unittest.mock import patch

from clearparcel.datawatch import cli
from clearparcel.datawatch.watch import _EXECUTION_PROFILES


class CliTests(unittest.TestCase):
    def test_documented_commands_exist(self):
        parser = cli.build_parser()
        subparsers = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
        for command in ("check", "status", "history", "aggregate", "worker-retire", "dashboard",
                        "public-dashboard", "public-publish", "cloud-job", "dashboard-build"):
            self.assertIn(command, subparsers.choices)

    def test_exit_code_constants_are_distinct(self):
        codes = (cli.EXIT_OK, cli.EXIT_WARN, cli.EXIT_SOURCE_ERROR, cli.EXIT_TOOL_FAILURE)
        self.assertEqual(codes, (0, 1, 2, 3))

    def test_aggregate_worker_choices_follow_the_execution_profiles(self):
        parser = cli.build_parser()
        args = parser.parse_args(["aggregate", "--base", "b", "--partial", "p", "--worker", "local", "--output", "o"])
        self.assertEqual(args.worker, "local")
        for worker in sorted(_EXECUTION_PROFILES):
            parser.parse_args(["aggregate", "--base", "b", "--partial", "p", "--worker", worker, "--output", "o"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            parser.parse_args(["aggregate", "--base", "b", "--partial", "p", "--worker", "any", "--output", "o"])
        self.assertEqual(raised.exception.code, 2)

    def test_worker_retire_still_accepts_legacy_names(self):
        args = cli.build_parser().parse_args(["worker-retire", "--base", "b", "--worker", "legacy-host",
                                              "--at", "2026-10-13T00:00:00+00:00", "--output", "o"])
        self.assertEqual(args.worker, "legacy-host")

    def test_unexpected_exceptions_are_reported_without_a_traceback(self):
        stderr = io.StringIO()
        with patch("sys.argv", ["watchtower", "public-publish"]), \
                patch("clearparcel.datawatch.public_publish.publish_public_snapshot_from_env",
                      side_effect=RuntimeError("storage unavailable")), contextlib.redirect_stderr(stderr):
            self.assertEqual(cli.main(), cli.EXIT_TOOL_FAILURE)
        self.assertTrue(stderr.getvalue().startswith("ERROR: RuntimeError: storage unavailable"))
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
