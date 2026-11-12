"""Active documentation agrees on the current release, and cross-document anchors resolve."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _slug(heading: str) -> str:
    heading = re.sub(r"`", "", heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    found, fenced = set(), False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if match := re.match(r"#{1,6}\s+(.*)", line):
            found.add(_slug(match.group(1)))
        found.update(re.findall(r'<a id="([^"]+)"', line))
    return found


class DocumentationConsistencyTests(unittest.TestCase):
    def test_relative_markdown_anchors_resolve(self):
        broken = []
        for doc in [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")]:
            for target, anchor in re.findall(r"\]\(([^)\s#:]+\.md)#([^)\s]+)\)", doc.read_text(encoding="utf-8")):
                path = (doc.parent / target).resolve()
                if path.exists() and anchor not in _anchors(path):
                    broken.append(f"{doc.relative_to(ROOT)} -> {target}#{anchor}")
        self.assertEqual(broken, [])

    def test_release_policy_and_index_name_the_same_current_release(self):
        policy = (ROOT / "docs/release-policy.md").read_text(encoding="utf-8")
        opening = re.search(r"run \*\*v(\d+\.\d+\.\d+)\*\*", policy).group(1)
        closing = re.search(r"surfaces use v(\d+\.\d+\.\d+) as of", policy).group(1)
        self.assertEqual(closing, opening)
        self.assertIn(f"must advance beyond v{opening}", policy)
        index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        current = re.findall(r"\[Current v(\d+\.\d+\.\d+)[^\]]*\]\(release-v(\d+\.\d+\.\d+)\.md\)", index)
        self.assertEqual(current, [(opening, opening)])
        self.assertTrue((ROOT / f"docs/release-v{opening}.md").exists())


if __name__ == "__main__":
    unittest.main()
