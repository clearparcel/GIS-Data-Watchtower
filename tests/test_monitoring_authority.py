import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from clearparcel.datawatch.monitoring_authority import evidence_hash, reconciliation_receipt
from clearparcel.datawatch.parcel_access import load_parcel_access
from clearparcel.datawatch.watch import _hold_skip_reason


TODAY = "2026-10-20"


def fixture():
    source = {"id": "sample-parcels", "county_slug": "sample", "category": "Parcels",
              "url": "https://example.invalid/parcels/0", "kind": "arcgis_layer",
              "execution_profiles": ["cloud"]}
    research = {"sample": {"monitoring": {"decision": "not-assessed",
                                         "terms_urls": ["https://example.invalid/terms"]}}}
    approval = {"source_id": source["id"], "county_slug": "sample", "decision": "approved",
                "source_sha256": evidence_hash(source), "research_sha256": evidence_hash(research["sample"]),
                "execution_profiles": ["cloud"], "reviewed_on": "2026-10-19", "review_due": "2026-11-19",
                "reviewer_ref": "synthetic-reviewer", "approval_ref": "synthetic-decision",
                "terms_ref": "synthetic-terms", "minimum_interval_hours": 24}
    cadence = {"source_id": source["id"], "source_sha256": evidence_hash(source),
               "execution_profiles": ["cloud"], "minimum_interval_hours": 24,
               "covers_all_dispatch_paths": True, "evidence_ref": "synthetic-schedule",
               "reviewed_on": "2026-10-19", "review_due": "2026-10-25"}
    return [source], research, [approval], [cadence]


class MonitoringAuthorityTests(unittest.TestCase):
    def receipt(self, inputs):
        return reconciliation_receipt(*inputs, as_of=TODAY)

    def test_matching_evidence_does_not_grant_authority_or_change_research(self):
        inputs = fixture()
        before = copy.deepcopy(inputs)
        result = self.receipt(inputs)
        self.assertTrue(result["reconciliation_complete"])
        self.assertEqual(result["sources"][0]["status"], "documented")
        self.assertEqual(result["sources"][0]["research_decision"], "not-assessed")
        self.assertIs(result["activation_authorized"], False)
        self.assertIs(result["live_configuration_verified"], False)
        self.assertEqual(inputs, before)

    def test_missing_approval_is_not_inferred_from_research_or_health(self):
        inputs = fixture()
        inputs[0][0]["status"] = "ok"
        inputs[1]["sample"]["monitoring"]["decision"] = "candidate-low-frequency"
        inputs[2].clear()
        result = self.receipt(inputs)
        self.assertFalse(result["reconciliation_complete"])
        self.assertIn("missing_approval", result["sources"][0]["gaps"])

    def test_all_current_research_holds_match_runtime_exclusion(self):
        root = Path(__file__).resolve().parents[1]
        counties = json.loads((root / "clearparcel/datawatch/minnesota_counties.json").read_text())["counties"]
        by_name = load_parcel_access()
        research = {c["slug"]: by_name[c["name"]] for c in counties}
        held = {slug for slug, r in research.items() if r["monitoring"]["decision"] == "hold-for-terms"}
        self.assertTrue(held)
        for slug in held:
            inputs = fixture()
            inputs[0][0]["county_slug"] = slug
            # Even an apparent approval cannot override a current research hold.
            result = reconciliation_receipt(inputs[0], research, inputs[2], inputs[3], as_of=TODAY)
            self.assertEqual(result["sources"][0]["status"], "held_by_research")
            self.assertEqual(_hold_skip_reason(inputs[0][0], frozenset(held)), "hold-for-terms")
            self.assertIs(result["activation_authorized"], False)

    def test_disabled_source_stays_disabled_without_approval(self):
        inputs = fixture()
        inputs[0][0]["enabled"] = False
        inputs[2].clear()
        result = self.receipt(inputs)
        self.assertEqual(result["sources"][0]["status"], "disabled")
        self.assertEqual(result["counts"].get("documented", 0), 0)

    def test_endpoint_options_or_research_change_invalidates_hash_match(self):
        for change in ("endpoint", "options", "research"):
            inputs = fixture()
            if change == "endpoint":
                inputs[0][0]["url"] += "?layer=new"
            elif change == "options":
                inputs[0][0]["count"] = True
            else:
                inputs[1]["sample"]["monitoring"]["terms_urls"].append("https://example.invalid/new")
            with self.subTest(change=change):
                self.assertFalse(self.receipt(inputs)["reconciliation_complete"])

    def test_wrong_county_profile_and_missing_terms_fail_closed(self):
        for field, value in (("county_slug", "other"), ("execution_profiles", ["local"]),
                             ("terms_ref", ""), ("approval_ref", None),
                             ("reviewer_ref", " "), ("decision", "revoked")):
            inputs = fixture()
            inputs[2][0][field] = value
            with self.subTest(field=field):
                self.assertFalse(self.receipt(inputs)["reconciliation_complete"])

    def test_stale_future_and_invalid_dates_are_not_current_evidence(self):
        for index in (2, 3):
            for field, value in (("review_due", TODAY), ("reviewed_on", "2026-10-21"),
                                 ("review_due", "invalid")):
                inputs = fixture()
                inputs[index][0][field] = value
                with self.subTest(index=index, field=field):
                    self.assertFalse(self.receipt(inputs)["reconciliation_complete"])

    def test_duplicate_and_orphan_evidence_cannot_silently_win(self):
        for index in (2, 3):
            inputs = fixture()
            inputs[index].append(copy.deepcopy(inputs[index][0]))
            with self.subTest(index=index):
                self.assertFalse(self.receipt(inputs)["reconciliation_complete"])
        inputs = fixture()
        extra = copy.deepcopy(inputs[2][0])
        extra["source_id"] = "missing-source"
        inputs[2].append(extra)
        self.assertEqual(self.receipt(inputs)["unmatched_evidence_ids"], ["missing-source"])
        self.assertFalse(self.receipt(inputs)["reconciliation_complete"])

    def test_combined_cadence_and_subdaily_exception_require_evidence(self):
        for field, value in (("minimum_interval_hours", 12),
                             ("covers_all_dispatch_paths", False),
                             ("execution_profiles", ["local"]), ("evidence_ref", "")):
            inputs = fixture()
            inputs[3][0][field] = value
            with self.subTest(field=field):
                self.assertFalse(self.receipt(inputs)["reconciliation_complete"])
        inputs = fixture()
        inputs[2][0]["minimum_interval_hours"] = 12
        self.assertIn("subdaily_exception_evidence_required", self.receipt(inputs)["sources"][0]["gaps"])
        inputs[2][0]["cadence_exception_ref"] = "reviewed-provider-exception"
        self.assertTrue(self.receipt(inputs)["reconciliation_complete"])

    def test_missing_wildcard_and_invalid_intervals_are_unresolved(self):
        for profiles in (None, ["any"], [], ["cloud", "cloud"]):
            inputs = fixture()
            inputs[0][0]["execution_profiles"] = profiles
            self.assertIn("explicit_cloud_local_profiles_required", self.receipt(inputs)["sources"][0]["gaps"])
        for value in (0, -1, True, "24", None):
            inputs = fixture()
            inputs[3][0]["minimum_interval_hours"] = value
            self.assertFalse(self.receipt(inputs)["reconciliation_complete"])

    def test_unresolved_scope_missing_endpoint_and_inappropriate_research(self):
        for field, value in (("county_slug", None), ("category", None), ("url", None)):
            inputs = fixture()
            inputs[0][0][field] = value
            inputs[2][0]["source_sha256"] = evidence_hash(inputs[0][0])
            inputs[3][0]["source_sha256"] = evidence_hash(inputs[0][0])
            with self.subTest(field=field):
                self.assertFalse(self.receipt(inputs)["reconciliation_complete"])
        inputs = fixture()
        inputs[1]["sample"]["monitoring"]["decision"] = "not-appropriate"
        inputs[2][0]["research_sha256"] = evidence_hash(inputs[1]["sample"])
        self.assertIn("research_requires_hold_review", self.receipt(inputs)["sources"][0]["gaps"])

    def test_raw_evidence_and_endpoint_secrets_are_not_copied(self):
        inputs = fixture()
        inputs[0][0]["url"] += "?token=SECRET"
        inputs[2][0]["reviewer_ref"] = "PERSONAL"
        result = json.dumps(self.receipt(inputs))
        self.assertNotIn("SECRET", result)
        self.assertNotIn("PERSONAL", result)
        self.assertNotIn("https://", result)
        with self.assertRaises(ValueError):
            reconciliation_receipt([inputs[0][0], inputs[0][0]], inputs[1], [], [], as_of=TODAY)
        self.assertFalse(reconciliation_receipt([], {}, [], [], as_of=TODAY)["reconciliation_complete"])

    def test_cli_uses_current_research_and_preserves_existing_files(self):
        script = Path(__file__).resolve().parents[1] / "scripts/reconcile_monitoring_authority.py"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "registry.json"
            output = Path(directory) / "receipt.json"
            source.write_text(json.dumps({"sources": fixture()[0]}), encoding="utf-8-sig")
            original = source.read_bytes()
            cmd = [sys.executable, str(script), "--registry", str(source), "--output", str(output),
                   "--as-of", TODAY]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(json.loads(output.read_text())["activation_authorized"])
            receipt = output.read_bytes()
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            self.assertEqual(output.read_bytes(), receipt)
            cmd[cmd.index("--output") + 1] = str(source)
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            self.assertEqual(source.read_bytes(), original)

    def test_cli_rejects_ambiguous_keys_and_nonfinite_evidence_before_writing(self):
        script = Path(__file__).resolve().parents[1] / "scripts/reconcile_monitoring_authority.py"
        with tempfile.TemporaryDirectory() as directory:
            source, approvals, output = [Path(directory) / name
                                         for name in ("registry.json", "approvals.json", "receipt.json")]
            source.write_text(json.dumps({"sources": fixture()[0]}), encoding="utf-8")
            cmd = [sys.executable, str(script), "--registry", str(source),
                   "--approvals", str(approvals), "--output", str(output), "--as-of", TODAY]
            for value in ('[{"source_id":"sample","decision":"revoked","decision":"approved"}]',
                          '[{"source_id":"sample","minimum_interval_hours":NaN}]',
                          '[{"source_id":"sample","minimum_interval_hours":1e400}]'):
                approvals.write_text(value, encoding="utf-8")
                with self.subTest(value=value):
                    self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
