"""Prepare a separate hosted-wrapper candidate; never deploy or edit the input.

The operator must supply the SHA-256 verified from the retained immutable image.
Only the known legacy GAC route block is replaced. Authentication, storage,
headers and all other routes remain byte-for-byte unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


LEGACY_ROUTES = b'''        if p.path=="/mngac": return self.send_text(200,readonly_html(dashboard.render_mngac(config)))
        if p.path=="/mngac.json":
            data=dashboard._mngac_data(dashboard._dashboard_state(config))
            return self.send_text(200 if data else 404,json.dumps(data or {"error":"MNGAC completeness data unavailable"},indent=2),"application/json; charset=utf-8")
        if p.path=="/mngac.csv":
            data=dashboard._mngac_data(dashboard._dashboard_state(config))
            return self.send_text(200 if data else 404,dashboard._mngac_csv(data),"text/csv; charset=utf-8")
'''
REPLACEMENT = b'''        if dashboard.dispatch_gac_routes(
                p.path, p.query, config=config, send=self.send_text,
                render_html=readonly_html):
            return
'''


def migrate(source: bytes, expected_sha256: str) -> bytes:
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise ValueError("Wrapper SHA-256 does not match the verified predecessor")
    newline = b"\r\n" if b"\r\n" in source else b"\n"
    legacy = LEGACY_ROUTES.replace(b"\n", newline)
    replacement = REPLACEMENT.replace(b"\n", newline)
    if source.count(legacy) != 1:
        raise ValueError("Expected exactly one unchanged legacy GAC route block")
    candidate = source.replace(legacy, replacement, 1)
    compile(candidate, "dashboard_app.py", "exec")
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    candidate = migrate(args.input.read_bytes(), args.expected_sha256)
    # Exclusive creation preserves both the original and any prior candidate.
    with args.output.open("xb") as stream:
        stream.write(candidate)
    print("Candidate wrapper SHA-256:", hashlib.sha256(candidate).hexdigest())


if __name__ == "__main__":
    main()
