"""A runnable source missing its identity fields is rejected before any request."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch


def config(root, sources):
    return {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
            "alerts_file": str(root / "alerts.json"), "alerts_text_file": str(root / "alerts.txt"),
            "retries": 0, "sources": sources}


GOOD = {"id": "first", "name": "First", "url": "https://example.invalid/first", "adapter": "http_file"}


class RequiredSourceFieldTests(unittest.TestCase):
    def test_missing_or_blank_identity_fields_fail_preflight_with_zero_dispatch(self):
        second = {"id": "second", "name": "Second", "url": "https://example.invalid/second", "adapter": "http_file"}
        cases = {"name": None, "url": None, "adapter": None}
        for field in cases:
            for value in (None, "", "   ", 7):
                broken = dict(second)
                if value is None:
                    broken.pop(field)
                else:
                    broken[field] = value
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    with patch.object(watch, "_source_check") as check:
                        with self.assertRaises(watch.InvalidSourceRegistryError):
                            watch.prepare_check_config(config(root, [dict(GOOD), broken]))
                        with self.assertRaises(watch.InvalidSourceRegistryError):
                            watch.check_sources(config(root, [dict(GOOD), broken]))
                    check.assert_not_called()
                    self.assertFalse((root / "state.json").exists())

    def test_legacy_kind_satisfies_the_adapter_requirement(self):
        legacy = {"id": "legacy", "name": "Legacy", "url": "https://example.invalid/l", "kind": "http-file"}
        watch.validate_source_registry([GOOD, legacy])

    def test_disabled_entries_may_stay_minimal(self):
        watch.validate_source_registry([GOOD, {"id": "parked", "enabled": False}])
        with tempfile.TemporaryDirectory() as td:
            with patch.object(watch, "_source_check", return_value={"problems": []}) as check:
                result = watch.check_sources(config(Path(td), [dict(GOOD), {"id": "parked", "enabled": False}]),
                                             source_filter="first", save=False)
        self.assertEqual([c.args[0]["id"] for c in check.call_args_list], ["first"])
        self.assertIn("first", result["sources"])


if __name__ == "__main__":
    unittest.main()
