"""Public application identity, independent of provider and publication times."""
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re
import tomllib

BUILD_INFO_FILE = Path(__file__).with_name("build_info.json")


def application_identity() -> dict[str, str]:
    try:
        package_version = version("clearparcel-gis-data-watchtower")
    except PackageNotFoundError:
        project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
        package_version = (
            tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]["version"]
            if project_file.is_file() else "unknown"
        )
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
