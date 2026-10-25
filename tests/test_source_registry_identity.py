"""Audit WT-A01: duplicate or missing source IDs fail before any check or write."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import cli, cloud_job, watch
from clearparcel.datawatch.watch import InvalidSourceRegistryError, validate_source_registry


def source(sid, name, url, **extra):
    return {"id": sid, "name": name, "adapter": "arcgis_layer", "url": url, **extra}


def _first_fails(src, timeout):
    return {"feature_count": 1, "problems": ["synthetic schema missing"] if src["name"].startswith("First") else []}


class RegistryIdentityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in list(os.environ):
            if name.startswith(("WATCHTOWER_", "CLEARPARCEL_WATCHTOWER_")):
                os.environ.pop(name, None)

    def config(self, sources):
        return {"state_file": str(self.root / "state.json"), "history_file": str(self.root / "history.jsonl"),
                "retries": 0, "sources": sources}

    def test_duplicate_ids_make_no_checks_and_leave_state_unchanged(self):
        valid = self.config([source("a", "A", "https://a.example.gov/0")])
        with patch.object(watch, "_source_check", side_effect=_first_fails):
            watch.check_sources(valid)
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        duplicate = self.config([source("dup", "First failing", "https://a.example.gov/0"),
                                 source("dup", "Second healthy", "https://b.example.gov/0")])
        for save in (True, False):
            with self.subTest(save=save), patch.object(watch, "_source_check", side_effect=_first_fails) as check:
                with self.assertRaisesRegex(InvalidSourceRegistryError, r"entry 0 \('dup'\) and entry 1 \('dup'\)"):
                    watch.check_sources(duplicate, save=save)
                check.assert_not_called()
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)

    def test_disabled_profile_filtered_and_case_variant_duplicates_are_rejected(self):
        cases = {
            "disabled": [source("x", "X", "https://a.example.gov/0"),
                         source("x", "X2", "https://b.example.gov/0", enabled=False)],
            "other profile": [source("x", "X", "https://a.example.gov/0", execution_profiles=["cloud"]),
                              source("x", "X2", "https://b.example.gov/0", execution_profiles=["local"])],
            "case": [source("mn-x", "X", "https://a.example.gov/0"), source("MN-X", "X2", "https://b.example.gov/0")],
        }
        for label, sources in cases.items():
            with self.subTest(label), patch.object(watch, "_source_check", side_effect=_first_fails) as check:
                with self.assertRaises(InvalidSourceRegistryError):
                    watch.check_sources(self.config(sources), save=False, execution_profile="cloud",
                                        source_filter="x")
                check.assert_not_called()

    def test_missing_blank_and_malformed_entries_are_rejected(self):
        for bad in ([{"name": "No id"}], [source("", "Blank", "u")], [source(" a", "Padded", "u")],
                    [source(7, "Number", "u")], ["not an object"], {"a": {}}):
            with self.subTest(bad=bad), self.assertRaises(InvalidSourceRegistryError):
                validate_source_registry(bad)

    def test_distinct_sources_keep_both_observations(self):
        result = None
        with patch.object(watch, "_source_check", side_effect=_first_fails):
            result = watch.check_sources(self.config([source("a", "First failing", "https://a.example.gov/0"),
                                                      source("b", "Second healthy", "https://b.example.gov/0")]),
                                         save=False)
        self.assertEqual(set(result["sources"]), {"a", "b"})
        self.assertEqual(result["overall"], "error")

    def test_cli_exits_3_before_claiming_the_provider_run_slot(self):
        cfg = self.root / "config.json"
        cfg.write_text(json.dumps(self.config([source("dup", "First failing", "https://a.example.gov/0"),
                                               source("dup", "Second healthy", "https://b.example.gov/0")])),
                       encoding="utf-8")
        err = io.StringIO()
        with patch.object(watch, "_source_check", side_effect=_first_fails) as check, \
                patch("clearparcel.datawatch.dispatch_guard.guard_dispatch") as guard, \
                patch("sys.argv", ["watchtower", "--config", str(cfg), "check"]), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main()
        self.assertEqual(code, cli.EXIT_TOOL_FAILURE)
        self.assertIn("duplicate source id", err.getvalue())
        guard.assert_not_called()
        check.assert_not_called()

    def test_cloud_job_preflight_refuses_duplicates(self):
        config = self.config([source("dup", "A", "https://a.example.gov/0"), source("dup", "B", "https://b.example.gov/0")])
        with patch.object(cloud_job, "require_publishable_profile"), \
                patch.object(cloud_job, "is_placeholder_config", return_value=False), \
                self.assertRaises(InvalidSourceRegistryError):
            cloud_job.preflight_cloud_job(config)

    def test_example_registry_is_valid(self):
        example = json.loads((Path(__file__).resolve().parents[1] / "config" / "example_sources.json").read_text(encoding="utf-8-sig"))
        validate_source_registry(example.get("sources", []))


if __name__ == "__main__":
    unittest.main()
