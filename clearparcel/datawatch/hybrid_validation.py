"""Offline candidate identity and end-to-end hybrid observation receipts.

These helpers never run providers, publish objects, or modify schedules.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .build_info import application_identity
from .aggregate import _parse_time


def runtime_identity(config: dict, build: dict | None = None) -> dict:
    build = build if build is not None else application_identity()
    package = hashlib.sha256()
    for path in sorted(path for path in Path(__file__).parent.iterdir()
                       if path.suffix in {".py", ".json"}):
        package.update(path.name.encode())
        package.update(path.read_text(encoding="utf-8").encode())
    # Runtime artifact locations legitimately differ between local and cloud.
    registry = {k: v for k, v in config.items() if not k.startswith("_")
                and not k.endswith("_file") and k not in {"aggregate_object", "dashboard_execution_profile"}}
    return {"version": build.get("version"), "revision": build.get("revision"),
            "package_sha256": package.hexdigest(),
            "configuration_sha256": hashlib.sha256(json.dumps(registry, sort_keys=True,
                separators=(",", ":"), default=str).encode()).hexdigest()}


def candidate_manifest(config: dict, build: dict | None = None) -> dict:
    expected = {"cloud": [], "local": []}
    seen = set()
    for source in config.get("sources", []):
        if source.get("enabled") is False:
            continue
        sid = source.get("id")
        profiles = source.get("execution_profiles")
        if not sid or sid in seen or not isinstance(profiles, list) or not profiles or set(profiles) - {"cloud", "local", "any"}:
            raise ValueError("candidate requires unique source IDs and explicit cloud/local/any assignments")
        seen.add(sid)
        for profile in expected:
            if profile in profiles or "any" in profiles:
                expected[profile].append(sid)
    return {"schema_version": 1, "runtime_identity": runtime_identity(config, build),
            "expected_sources": {key: sorted(value) for key, value in expected.items()},
            "required_distinct_daily_cycles": 5, "activation_authorized": False}


def validation_receipt(manifest: dict, reports: dict, aggregate: dict, public: dict) -> dict:
    problems = []
    expected = manifest["expected_sources"]
    union = set().union(*(set(ids) for ids in expected.values()))
    if set(aggregate.get("sources", {})) != union:
        problems.append("aggregate inventory mismatch")
    if set(public.get("sources", {})) != union:
        problems.append("public inventory mismatch")
    for profile, ids in expected.items():
        report = reports.get(profile, {})
        stamp = report.get("generated_at")
        if report.get("runtime_identity") != manifest["runtime_identity"]:
            problems.append(f"runtime identity mismatch: {profile}")
        if set(report.get("sources", {})) != set(ids):
            problems.append(f"worker inventory mismatch: {profile}")
        worker = aggregate.get("workers", {}).get(profile, {})
        if _parse_time(stamp) is None or worker.get("last_report_at") != stamp:
            problems.append(f"worker report mismatch: {profile}")
        if public.get("workers", {}).get(profile, {}).get("last_report_at") != stamp:
            problems.append(f"public worker report mismatch: {profile}")
        for sid in ids:
            incoming = report.get("sources", {}).get(sid, {})
            merged = aggregate.get("sources", {}).get(sid, {})
            projected = public.get("sources", {}).get(sid, {})
            assigned = [p for p in expected if sid in expected[p]]
            winner = merged.get("worker")
            if winner not in assigned:
                problems.append(f"worker provenance mismatch: {sid}")
            if _parse_time(incoming.get("checked_at")) is None or incoming.get("status") != "ok":
                problems.append(f"source health mismatch or failure: {sid}")
            # Shared IDs retain the report with the latest publication time.
            # Validate every worker above, then compare only the accepted winner.
            if winner != profile:
                continue
            accepted_time = _parse_time(stamp)
            if accepted_time is not None and any(
                (other_time := _parse_time(reports.get(p, {}).get("generated_at"))) is not None
                and other_time > accepted_time for p in assigned
            ):
                problems.append(f"aggregate winner mismatch: {sid}")
            if projected.get("worker") != merged.get("worker"):
                problems.append(f"public worker provenance mismatch: {sid}")
            if _parse_time(incoming.get("checked_at")) is None or merged.get("checked_at") != incoming.get("checked_at"):
                problems.append(f"aggregate observation mismatch: {sid}")
            if projected.get("checked_at") != incoming.get("checked_at"):
                problems.append(f"public observation mismatch: {sid}")
            if projected.get("last_success_at") != merged.get("last_success_at"):
                problems.append(f"public success timestamp mismatch: {sid}")
            if incoming.get("status") != "ok" or merged.get("status") != incoming.get("status") or projected.get("status") != incoming.get("status"):
                problems.append(f"source health mismatch or failure: {sid}")
            for key in ("gac_completeness", "mngac_completeness"):
                if key in incoming:
                    observed = incoming[key].get("observed_at")
                    if not observed or projected.get(key, {}).get("observed_at") != observed:
                        problems.append(f"metric observation mismatch: {sid}")
            observed = incoming.get("catalog_observed_at")
            if observed and projected.get("catalog_observed_at") != observed:
                problems.append(f"catalog observation mismatch: {sid}")
    return {"schema_version": 1, "passed": not problems, "problems": sorted(set(problems)),
            "runtime_identity": manifest["runtime_identity"],
            "worker_observations": {p: reports.get(p, {}).get("generated_at") for p in expected},
            "source_count": len(union), "public_published_at": public.get("public_published_at"),
            "activation_authorized": False}
