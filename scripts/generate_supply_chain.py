from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tomllib
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--constraints", default="constraints.txt")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--runtime-inventory", required=True)
    parser.add_argument("--os-inventory", required=True)
    parser.add_argument("--sbom", required=True)
    parser.add_argument("--provenance", required=True)
    args = parser.parse_args()

    constraints = Path(args.constraints)
    lock_bytes = constraints.read_bytes()
    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    package_metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = package_metadata["project"]
    runtime = json.loads(Path(args.runtime_inventory).read_text(encoding="utf-8"))
    components = []
    for row in runtime.get("components", []):
        name, version = str(row["name"]), str(row["version"])
        if name.lower().replace("_", "-") == project["name"].lower().replace("_", "-"):
            continue
        components.append({
            "type": "library", "name": name, "version": version,
            "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
        })
    for raw in Path(args.os_inventory).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        name, version = raw.split("\t", 1)
        clean_name = name.split(":", 1)[0]
        components.append({
            "type": "operating-system", "name": clean_name, "version": version,
            "purl": f"pkg:deb/debian/{clean_name}@{version}",
        })
    components.sort(key=lambda row: (row["type"], row["name"].lower()))

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": generated,
            "component": {
                "type": "application",
                "name": project["name"],
                "version": project["version"],
            },
            "properties": [
                {"name": "clearparcel:source_revision", "value": args.revision},
                {"name": "clearparcel:base_image", "value": args.base_image},
                {"name": "clearparcel:constraints_sha256", "value": hashlib.sha256(lock_bytes).hexdigest()},
                {"name": "clearparcel:constraints_inventory_scope", "value": "dependency-input-only"},
                {"name": "clearparcel:artifact_subject", "value": args.image_digest},
                {"name": "clearparcel:runtime_interpreter", "value": runtime["python"]},
            ],
        },
        "components": components,
    }
    provenance = {
        "schema": "clearparcel.watchtower.build-provenance.v1",
        "generated_at": generated,
        "source_revision": args.revision,
        "base_image": args.base_image,
        "image_digest": args.image_digest,
        "constraints_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "runtime_python_components": sum(
            1 for row in runtime.get("components", [])
            if str(row.get("name", "")).lower().replace("_", "-") != project["name"].lower().replace("_", "-")
        ),
        "runtime_os_components": sum(1 for row in components if row["type"] == "operating-system"),
        "runtime_python": runtime["python"],
        "build_host_python": sys.version.split()[0],
    }
    Path(args.sbom).write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    Path(args.provenance).write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
