"""The repository is public: keep deployment identifiers out of tracked files.

Docs use placeholders such as ``<project-id>``, ``<preview-bucket>`` and
``<cloud-run-service-url>``; real values belong in private operations notes.
The patterns are generic shapes, so this file never contains real values, and
its own samples are assembled at runtime so the file can scan itself.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = {
    "Cloud Run service host": re.compile(r"\b[a-z0-9-]+\.[a-z0-9-]+\.run\.app\b", re.IGNORECASE),
    "service-account email": re.compile(r"[A-Za-z0-9._%+-]+@[a-z][a-z0-9-]{3,29}\.(?:iam\.)?gserviceaccount\.com", re.IGNORECASE),
    "auto-generated GCP project ID": re.compile(r"\b[a-z]{3,10}-[a-z]{3,10}-\d{6}-[a-z0-9]{2}\b"),
    "GCP project number": re.compile(r"(?:projects/\d{10,13}\b|\b\d{10,13}-compute@|-\d{12}\.[a-z0-9-]+\.run\.app)", re.IGNORECASE),
    "Artifact/Container Registry path": re.compile(r"\b(?:[a-z0-9-]+-docker\.pkg\.dev|(?:[a-z]+\.)?gcr\.io)/(?!<)[a-z][a-z0-9-]{4,29}/"),
    "Cloud Storage bucket": re.compile(r"\bgs://(?!<)[a-z0-9][a-z0-9._-]{2,62}"),
    "user profile path": re.compile(r"(?:\b[A-Za-z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/)|/Users/|/home/)(?!<|%)[A-Za-z0-9._-]+(?:\\\\|\\|/)"),
}
# AGENTS.md names the owner's authoritative checkout on purpose; allow exactly that line.
ALLOWED_LINES = {("AGENTS.md", "user profile path"): ("- Authoritative repository: `",)}


def tracked_files():
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        return None
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / name for name in out.decode("utf-8").split("\0") if name]


def scan(relative: str, text: str) -> list[str]:
    findings = []
    for label, pattern in FORBIDDEN.items():
        allowed = ALLOWED_LINES.get((relative, label), ())
        for match in pattern.finditer(text):
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.end())
            line_text = text[start:end if end != -1 else None]
            if allowed and line_text.startswith(allowed):
                continue
            findings.append(f"{relative}:{text.count(chr(10), 0, match.start()) + 1}: {label}")
    return findings


def _sample(*parts: str) -> str:
    return "".join(parts)


SAMPLES = {
    "Cloud Run service host": [_sample("https://svc-preview.us-central1.", "run", ".app/"), _sample("SVC.US-CENTRAL1.", "RUN.APP")],
    "service-account email": [_sample("worker@sample-proj.", "iam.gservice", "account.com"),
                              _sample("123@cloudbuild.", "gservice", "account.com")],
    "auto-generated GCP project ID": [_sample("--project sample-", "proj-123456-ab")],
    "GCP project number": [_sample("projects/", "123456789012", "/secrets/x"),
                           _sample("123456789012", "-compute@developer")],
    "Artifact/Container Registry path": [_sample("us-central1-docker.", "pkg.dev/sample-project/repo"),
                                         _sample("gcr.", "io/sample-project/image")],
    "Cloud Storage bucket": [_sample("gs:", "//sample-bucket/object.json")],
    "user profile path": [_sample("C:", "\\Users\\someone\\repo"), _sample("C:", "/Us", "ers/someone/AppData"),
                          _sample("D:", "\\\\Users\\\\someone\\\\repo"), _sample("/Users/", "someone/src"),
                          _sample("/home/", "someone/src")],
}
PLACEHOLDERS = ["<project-id>", "<preview-service-account-email>", "<cloud-run-service-url>",
                "us-central1-docker.pkg.dev/<project-id>/repo", "gs://<production-bucket>/production/state.json",
                "C:\\Users\\<user>\\", "%USERPROFILE%/AppData", "Watchtower-GIS-data-123456-ab"]


class PublicRepoHygieneTests(unittest.TestCase):
    def test_no_deployment_identifiers_in_tracked_files(self):
        files = tracked_files()
        if files is None:
            self.skipTest("not a git checkout")
        findings = []
        for path in files:
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue  # binary assets (images)
            findings.extend(scan(path.relative_to(ROOT).as_posix(), text))
        self.assertEqual(findings, [], "Replace with placeholders such as <project-id>:\n" + "\n".join(findings))

    def test_patterns_detect_the_shapes_they_target(self):
        for label, samples in SAMPLES.items():
            for sample in samples:
                self.assertTrue(scan("sample.md", sample), f"{label} missed {sample!r}")

    def test_placeholders_are_not_flagged(self):
        for placeholder in PLACEHOLDERS:
            self.assertEqual(scan("sample.md", placeholder), [], placeholder)

    def test_agents_allowance_covers_only_the_authoritative_checkout_line(self):
        line = _sample("- Authoritative repository: `C:", "\\Users\\someone\\source\\repos\\X`.")
        self.assertEqual(scan("AGENTS.md", line), [])
        self.assertTrue(scan("AGENTS.md", _sample("Another path: C:", "\\Users\\someone\\x")))



# Release records from v0.3.10 on keep secret names, versions and digests in
# the private deployment record (docs/release-policy.md, owner decision 2026-10-31).
RELEASE_RECORD_FORBIDDEN = {
    "Secret Manager secret name": re.compile(r"Secret Manager\s+`(?!<)[^`]+`"),
    "secret or registry version": re.compile(r"\bversion\s+\d+,\s*\d+\s+entries\b", re.IGNORECASE),
    "registry digest": re.compile(r"\bsha256\s+`[0-9a-f]{6,}", re.IGNORECASE),
    "Cloud Build ID": re.compile(r"Cloud Build\s+\**`?[0-9a-f]{8}-[0-9a-f]{4}-"),
}


def release_record_findings(relative: str, text: str) -> list[str]:
    return [f"{relative}: {label}" for label, pattern in RELEASE_RECORD_FORBIDDEN.items()
            if pattern.search(text)]


def _covered_release_records():
    for path in sorted((ROOT / "docs").glob("release-v*.md")):
        match = re.fullmatch(r"release-v(\d+)\.(\d+)\.(\d+)\.md", path.name)
        if match and tuple(int(part) for part in match.groups()) >= (0, 3, 10):
            yield path


class ReleaseRecordHygieneTests(unittest.TestCase):
    def test_new_release_records_keep_deployment_evidence_private(self):
        findings = []
        for path in _covered_release_records():
            findings.extend(release_record_findings(path.name, path.read_text(encoding="utf-8")))
        self.assertEqual(findings, [], "Move this evidence to the private deployment record:\n" + "\n".join(findings))

    def test_patterns_detect_the_v039_shapes(self):
        sample = _sample("Registry check passed: Secret Manager `sample-config` ", "version 13, 35 entries, sha256 `b0b01cd9…`.\n",
                         "Cloud Build **`", "08d5ecf8-ac21-4e59-9901-017340e1fc86`** passed.")
        self.assertEqual(len(release_record_findings("sample.md", sample)), 4)
        self.assertEqual(release_record_findings("sample.md", "The private registry check passed."), [])


if __name__ == "__main__":
    unittest.main()
