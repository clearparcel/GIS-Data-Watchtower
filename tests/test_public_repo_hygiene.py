"""The repository is public: keep deployment identifiers out of tracked files.

Docs use placeholders such as ``<project-id>``, ``<preview-bucket>`` and
``<cloud-run-service-url>``; real values belong in private operations notes.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Generic shapes, so this file never has to contain the real values.
FORBIDDEN = {
    "Cloud Run service URL": re.compile(r"\b[a-z0-9-]+(?:-\d{12})?\.[a-z0-9-]+\.run\.app\b"),
    "service-account email": re.compile(r"[A-Za-z0-9._%+-]+@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com"),
    "auto-generated GCP project ID": re.compile(r"\b[a-z]{3,10}-[a-z]{3,10}-\d{6}-[a-z0-9]{2}\b"),
    "Artifact Registry path": re.compile(r"\b[a-z0-9-]+-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/"),
    "Windows user profile path": re.compile(r"C:[\\/]Users[\\/](?!<)[A-Za-z0-9._-]+[\\/]", re.IGNORECASE),
}
# AGENTS.md names the owner's authoritative workstation and checkout on purpose.
ALLOWED = {"Windows user profile path": {"AGENTS.md"}}
TEXT_SUFFIXES = {".md", ".py", ".json", ".toml", ".yml", ".yaml", ".txt", ".cfg", ".ini", ".sh", ".ps1", ".cmd", ".html", ""}


def tracked_files():
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        return None
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / name for name in out.decode("utf-8").split("\0") if name]


class PublicRepoHygieneTests(unittest.TestCase):
    def test_no_deployment_identifiers_in_tracked_files(self):
        files = tracked_files()
        if files is None:
            self.skipTest("not a git checkout")
        findings = []
        for path in files:
            if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for label, pattern in FORBIDDEN.items():
                if relative in ALLOWED.get(label, set()):
                    continue
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    findings.append(f"{relative}:{line}: {label}")
        self.assertEqual(findings, [], "Replace with placeholders such as <project-id>:\n" + "\n".join(findings))

    def test_patterns_detect_the_shapes_they_target(self):
        samples = {
            "Cloud Run service URL": "https://svc-preview-123456789012.us-central1.run.app/",
            "service-account email": "worker@sample-proj-123456-ab.iam.gserviceaccount.com",
            "auto-generated GCP project ID": "--project sample-proj-123456-ab",
            "Artifact Registry path": "us-central1-docker.pkg.dev/sample-project/repo",
            "Windows user profile path": "C:\\Users\\someone\\source\\repos",
        }
        self.assertRegex("C:/Users/someone/AppData", FORBIDDEN["Windows user profile path"])
        for label, sample in samples.items():
            self.assertRegex(sample, FORBIDDEN[label], label)
        for placeholder in ("<project-id>", "<preview-service-account-email>", "<cloud-run-service-url>",
                            "us-central1-docker.pkg.dev/<project-id>/repo", "C:\\Users\\<user>\\"):
            for label, pattern in FORBIDDEN.items():
                self.assertNotRegex(placeholder, pattern, f"{label} flags placeholder {placeholder}")


if __name__ == "__main__":
    unittest.main()
