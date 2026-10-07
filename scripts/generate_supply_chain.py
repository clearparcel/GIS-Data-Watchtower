from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

PROJECT = "clearparcel-gis-data-watchtower"
PROJECT_VERSION = "0.1.0.dev0"


def locked_components(path: Path) -> list[dict]:
    components = []
    pattern = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s#]+)$")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.fullmatch(line)
        if not match:
            raise ValueError(f"unsupported lock entry: {line}")
        name, version = match.groups()
        normalized = name.lower().replace("_", "-")
        components.append({
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{normalized}@{version}",
        })
    return sorted(components, key=lambda row: row["name"].lower())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--constraints", default="constraints.txt")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--sbom", required=True)
    parser.add_argument("--provenance", required=True)
    args = parser.parse_args()

    constraints = Path(args.constraints)
    lock_bytes = constraints.read_bytes()
    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    components = locked_components(constraints)

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": generated,
            "component": {
                "type": "application",
                "name": PROJECT,
                "version": PROJECT_VERSION,
            },
            "properties": [
                {"name": "clearparcel:source_revision", "value": args.revision},
                {"name": "clearparcel:base_image", "value": args.base_image},
                {"name": "clearparcel:constraints_sha256", "value": hashlib.sha256(lock_bytes).hexdigest()},
            ],
        },
        "components": components,
    }
    provenance = {
        "schema": "clearparcel.watchtower.build-provenance.v1",
        "generated_at": generated,
        "source_revision": args.revision,
        "base_image": args.base_image,
        "constraints_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "locked_python_components": len(components),
        "python": sys.version.split()[0],
    }
    Path(args.sbom).write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    Path(args.provenance).write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
