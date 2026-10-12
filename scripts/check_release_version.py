"""Fail-closed, read-only version preflight for a coordinated production release.

The public website is authoritative for the version currently deployed to the
anonymous dashboard. Run BEFORE the first public/private rollout of each new
release, not separately for every service in the same coordinated rollout.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import tomllib
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILE = ROOT / "pyproject.toml"
PUBLIC_URL = "https://gis-watchtower.clear-parcel.com/"
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
VISIBLE_VERSION = re.compile(r"^v([0-9]+\.[0-9]+\.[0-9]+)(?:\s|$)")


def version_tuple(value: str) -> tuple[int, int, int]:
    found = SEMVER.fullmatch(value)
    if not found:
        raise ValueError(f"Not a stable X.Y.Z version: {value!r}")
    return tuple(int(n) for n in found.groups())


class _FooterVersion(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capture = False
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "strong" and "application-version" in dict(attrs).get("class", "").split():
            self._capture = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "strong":
            self._capture = False

    def handle_data(self, data: str) -> None:
        if self._capture:
            self.values.append(data)


def version_from_public_html(body: str) -> str:
    parser = _FooterVersion()
    parser.feed(body)
    if len(parser.values) != 1:
        raise ValueError("Could not uniquely verify a public footer version")
    match = VISIBLE_VERSION.match(parser.values[0].strip())
    if not match:
        raise ValueError("Public footer version is unavailable or malformed")
    value = match.group(1)
    version_tuple(value)
    return value


def candidate_version() -> str:
    project = tomllib.loads(PROJECT_FILE.read_text(encoding="utf-8"))["project"]
    if project.get("name") != "clearparcel-gis-data-watchtower":
        raise ValueError("Unexpected release package")
    declared = project["version"]
    if not isinstance(declared, str):
        raise ValueError("Release version must be a string")
    version_tuple(declared)
    return declared


def require_new_version(candidate: str, deployed: str) -> None:
    if version_tuple(candidate) <= version_tuple(deployed):
        raise ValueError(
            f"Release blocked: candidate v{candidate} must be newer than deployed v{deployed}. "
            "Bump pyproject.toml before building."
        )


def live_version() -> str:
    request = urllib.request.Request(
        PUBLIC_URL,
        headers={"User-Agent": "GIS-Data-Watchtower-Release-Preflight/1.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if urlsplit(response.geturl()).netloc != urlsplit(PUBLIC_URL).netloc:
            raise ValueError("Public website redirected to an unexpected host")
        if response.status != 200:
            raise ValueError(f"Public website returned HTTP {response.status}")
        payload = response.read(6 * 1024 * 1024 + 1)
        if len(payload) > 6 * 1024 * 1024:
            raise ValueError("Public page is too large for version verification")
        body = payload.decode("utf-8")
    return version_from_public_html(body)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="Block a production release unless pyproject.toml is newer than the currently deployed public footer. Read-only; no GIS-provider requests.",
    ).parse_args(argv)
    try:
        candidate = candidate_version()
        deployed = live_version()
        require_new_version(candidate, deployed)
    except (OSError, ValueError, KeyError, UnicodeError) as error:
        print(f"RELEASE BLOCKED: {error}", file=sys.stderr)
        return 1
    print(f"RELEASE PREFLIGHT PASSED: deployed v{deployed} -> candidate v{candidate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
