"""Public application identity, independent of provider and publication times."""
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re
import tomllib

BUILD_INFO_FILE = Path(__file__).with_name("build_info.json")
PROJECT_FILE = Path(__file__).resolve().parents[2] / "pyproject.toml"


def application_identity() -> dict[str, str]:
    package_version = "unknown"
    if PROJECT_FILE.is_file():
        try:
            project = tomllib.loads(PROJECT_FILE.read_text(encoding="utf-8"))["project"]
            declared = project.get("version")
            if project.get("name") == "clearparcel-gis-data-watchtower" and isinstance(declared, str) and declared.strip():
                package_version = declared
        except (AttributeError, KeyError, OSError, TypeError, ValueError):
            pass
    if package_version == "unknown":
        try:
            package_version = version("clearparcel-gis-data-watchtower")
        except PackageNotFoundError:
            pass
    try:
        build = json.loads(BUILD_INFO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        build = {}
    if not isinstance(build, dict):
        build = {}
    revision = build.get("revision", "")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
        revision = ""
    environment = build.get("environment", "development")
    if environment not in ("preview", "production", "development"):
        environment = "development"
    return {"version": package_version, "revision": revision, "environment": environment}
