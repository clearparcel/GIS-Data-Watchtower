"""A provider 429 backoff survives a run that fails or is interrupted (audit WT31-02)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import cloud_job, watch
from clearparcel.datawatch.storage import LocalStorage


def _sources():
    return [
        {"id": "a", "name": "Host A", "adapter": "arcgis_layer", "url": "https://a.example/0"},
        {"id": "b", "name": "Host B", "adapter": "arcgis_layer", "url": "https://b.example/0"},
    ]


def _config(root: Path, sources=None, **extra):
    return {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
            "alerts_file": str(root / "alerts.json"), "retries": 0,
            "sources": sources if sources is not None else _sources(), **extra}


class Interrupted(BaseException):
    """Stands in for process loss: escapes every per-source handler."""


class DurableBackoffTests(unittest.TestCase):
    def run_once(self, config, behavior):
        calls = []

        def check(source, _timeout):
            calls.append(source["id"])
            return behavior(source)

        with patch.object(watch, "_source_check", side_effect=check):
            try:
                watch.check_sources(config, save=True)
            except Interrupted:
                pass
        return calls

    def test_backoff_is_on_disk_before_the_next_source_runs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = _config(root)
            # Existing good state, so the checkpoint must keep prior observations.
            (root / "state.json").write_text(json.dumps({"schema_version": 2, "sources": {"a": {"status": "ok"}}}),
                                             encoding="utf-8")

            def first(source):
                if source["id"] == "a":
                    raise watch.ProviderRateLimitError("86400", "a.example")
                raise Interrupted()

            self.assertEqual(self.run_once(config, first), ["a", "b"])
            saved = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertIn("a.example", saved["rate_limits"])
            self.assertEqual(saved["sources"], {"a": {"status": "ok"}})

            # A fresh invocation makes zero requests to the embargoed host.
            calls = self.run_once(config, lambda source: {"problems": []})
            self.assertEqual(calls, ["b"])

    def test_completed_run_still_persists_and_expired_backoff_allows_the_host_again(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = _config(root)

            def limited(source):
                if source["id"] == "a":
                    raise watch.ProviderRateLimitError("60", "a.example")
                return {"problems": []}

            self.run_once(config, limited)
            self.assertEqual(self.run_once(config, lambda s: {"problems": []}), ["b"])
            saved = json.loads((root / "state.json").read_text(encoding="utf-8"))
            saved["rate_limits"]["a.example"]["not_before"] = "2000-01-01T00:00:00+00:00"
            (root / "state.json").write_text(json.dumps(saved), encoding="utf-8")
            self.assertEqual(self.run_once(config, lambda s: {"problems": []}), ["a", "b"])

    def test_dry_run_writes_no_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = _config(root)
            with patch.object(watch, "_source_check", side_effect=watch.ProviderRateLimitError("60", "a.example")):
                watch.check_sources(config, save=False)
            self.assertFalse((root / "state.json").exists())

    def test_backoff_that_cannot_be_saved_stops_the_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = _config(root)
            calls = []

            def check(source, _timeout):
                calls.append(source["id"])
                raise watch.ProviderRateLimitError("60", "a.example")

            with patch.object(watch, "_source_check", side_effect=check), \
                    patch.object(watch, "_save_json", side_effect=OSError("disk full")):
                with self.assertRaises(watch.RateLimitPersistenceError):
                    watch.check_sources(config, save=True)
            self.assertEqual(calls, ["a"])

    def test_invalid_dispatch_option_on_a_later_entry_is_refused_before_any_request(self):
        for source_update, config_update in (
            ({"timeout_seconds": "slow"}, {}),
            ({"retries": -1}, {}),
            ({"timeout_seconds": True}, {}),
            ({}, {"retry_delay_seconds": "soon"}),
            ({}, {"timeout_seconds": None}),
            ({"retries": None}, {}),
            ({}, {"rate_limit_default_backoff_seconds": "x"}),
        ):
            with self.subTest(source=source_update, config=config_update), tempfile.TemporaryDirectory() as td:
                sources = _sources()
                sources[1].update(source_update)
                config = _config(Path(td), sources, **config_update)
                with patch.object(watch, "_source_check") as check:
                    with self.assertRaises(watch.InvalidSourceRegistryError):
                        watch.check_sources(config, save=True)
                check.assert_not_called()
                self.assertFalse((Path(td) / "state.json").exists())

    def test_numeric_strings_remain_valid_options(self):
        with tempfile.TemporaryDirectory() as td:
            sources = _sources()
            sources[0]["timeout_seconds"] = "15"
            config = _config(Path(td), sources, retry_delay_seconds="0.5")
            with patch.object(watch, "_source_check", return_value={"problems": []}) as check:
                watch.check_sources(config, save=False)
            self.assertEqual(check.call_count, 2)


class CloudCheckpointUploadTests(unittest.TestCase):
    def test_changed_state_is_uploaded_with_its_version_after_a_failed_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = LocalStorage(root / "store")
            (root / "store").mkdir()
            (root / "store" / "state.json").write_text('{"schema_version": 2, "sources": {}}', encoding="utf-8")
            local = root / "work" / "state.json"
            local.parent.mkdir()
            exists, version = storage.download_versioned("state.json", local)
            self.assertTrue(exists)
            before = cloud_job._file_digest(local)
            self.assertFalse(cloud_job._upload_backoff_checkpoint(storage, local, before, {"state.json": version}))
            local.write_text('{"schema_version": 2, "sources": {}, "rate_limits": {"a.example": {}}}', encoding="utf-8")
            self.assertTrue(cloud_job._upload_backoff_checkpoint(storage, local, before, {"state.json": version}))
            self.assertIn("rate_limits", (root / "store" / "state.json").read_text(encoding="utf-8"))

    def test_conflicting_upload_does_not_mask_the_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = LocalStorage(root / "store")
            (root / "store").mkdir()
            (root / "store" / "state.json").write_text("{}", encoding="utf-8")
            local = root / "state.json"
            local.write_text('{"rate_limits": {}}', encoding="utf-8")
            self.assertFalse(cloud_job._upload_backoff_checkpoint(storage, local, None, {"state.json": "stale"}))
            self.assertEqual((root / "store" / "state.json").read_text(encoding="utf-8"), "{}")


if __name__ == "__main__":
    unittest.main()
