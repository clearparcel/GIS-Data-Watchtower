import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SupplyChainTests(unittest.TestCase):
    def test_runtime_dependencies_are_exactly_constrained(self):
        lines = [
            line.strip() for line in (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertGreaterEqual(len(lines), 20)
        self.assertTrue(all("==" in line for line in lines))
        self.assertFalse(any(">=" in line or "~=" in line for line in lines))

    def test_container_base_and_dependency_install_are_pinned(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("python:3.13-slim@sha256:", dockerfile)
        self.assertIn("COPY pyproject.toml README.md LICENSE constraints.txt", dockerfile)
        self.assertIn("--constraint constraints.txt", dockerfile)

    def test_ci_emits_supply_chain_artifacts(self):
        workflow = (ROOT / ".github" / "workflows" / "watchtower-ci.yml").read_text(encoding="utf-8")
        self.assertIn("generate_supply_chain.py", workflow)
        self.assertIn("watchtower-sbom.cdx.json", workflow)
        self.assertIn("watchtower-provenance.json", workflow)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", workflow)
        self.assertIn("aquasecurity/trivy-action@", workflow)
        self.assertIn("pypa/gh-action-pip-audit@1220774d901786e6f652ae159f7b6bc8fea6d266", workflow)
        self.assertIn("github/codeql-action/init@2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2", workflow)
        self.assertIn("github/codeql-action/analyze@2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2", workflow)

    def test_current_status_is_generated_from_authoritative_status(self):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sync_current_status.py"), "--check"],
            check=True,
        )

    def test_supply_chain_generator_emits_cyclonedx_and_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sbom = root / "sbom.json"
            provenance = root / "provenance.json"
            revision = "a" * 40
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "generate_supply_chain.py"),
                    "--constraints", str(ROOT / "constraints.txt"),
                    "--revision", revision,
                    "--base-image", "python:3.13-slim@sha256:" + "b" * 64,
                    "--sbom", str(sbom),
                    "--provenance", str(provenance),
                ],
                check=True,
            )
            sbom_data = json.loads(sbom.read_text(encoding="utf-8"))
            prov_data = json.loads(provenance.read_text(encoding="utf-8"))
            self.assertEqual(sbom_data["bomFormat"], "CycloneDX")
            self.assertEqual(sbom_data["specVersion"], "1.6")
            self.assertGreaterEqual(len(sbom_data["components"]), 20)
            self.assertEqual(prov_data["source_revision"], revision)
            self.assertEqual(prov_data["locked_python_components"], len(sbom_data["components"]))


if __name__ == "__main__":
    unittest.main()
