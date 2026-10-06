"""Validated parcel-access research, independent of monitoring observations."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlsplit

DIRECT_CLASSIFICATIONS = {
    "free-parcel-data": "Free parcel data",
    "fee-based-parcel-data": "Fee-based parcel data",
    "parcel-viewer-only": "Parcel viewer only",
    "request-restricted": "Parcel data by request / restricted",
    "no-direct-dataset-verified": "No direct parcel dataset verified",
}
CLASSIFICATIONS = DIRECT_CLASSIFICATIONS
STATEWIDE_OPEN_LABEL = "Available free through MnGeo Plan Parcels Open"
REVIEW_AREAS = (
    "county_site", "gis_assessor_land_records", "downloads_open_data",
    "arcgis_services", "data_policy", "fee_schedule", "request_forms",
    "resolutions_ordinances", "authorized_portals", "statewide_context",
)
URL_FIELDS = (
    "official_county_url", "parcel_page_url", "download_or_service_url",
    "viewer_url", "fee_policy_url",
)
RECORD_FIELDS = {
    "county", "review_date", "county_direct_classification", "research_complete",
    *URL_FIELDS, "parcel_dataset_fee", "fee_product", "evidence_note",
    "source_authority", "usable_direct_machine_readable_source",
    "statewide_open_coverage", "monitoring", "review_log", "evidence",
}
INTERIM_LABEL = "County-direct parcel access not yet researched"


def _url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"https", "http"} and bool(parsed.hostname) and not parsed.username


def validate_parcel_access(data: dict) -> None:
    """Reject ambiguous/unsupported published research; no network access."""
    if set(data) != {"schema_version", "scope", "counties"} or data["schema_version"] != 2:
        raise ValueError("Unsupported parcel-access schema")
    if not isinstance(data["scope"], str) or not data["scope"].strip():
        raise ValueError("Research scope required")
    if not isinstance(data["counties"], list):
        raise ValueError("Counties must be a list")
    seen = set()
    for record in data["counties"]:
        if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
            raise ValueError("Invalid county research fields")
        county = record["county"]
        if not isinstance(county, str) or not county.strip() or county in seen:
            raise ValueError("Missing or duplicate county")
        seen.add(county)
        if type(record["research_complete"]) is not bool:
            raise ValueError("research_complete must be boolean")
        complete = record["research_complete"]
        classification = record["county_direct_classification"]
        if classification not in DIRECT_CLASSIFICATIONS and classification is not None:
            raise ValueError("Unknown county-direct classification")
        if complete != (classification is not None):
            raise ValueError("Only completed research may carry a public classification")
        if record["review_date"] is not None:
            try:
                dt.date.fromisoformat(record["review_date"])
            except (ValueError, TypeError) as exc:
                raise ValueError("Invalid review date") from exc
        elif complete:
            raise ValueError("Completed research requires review date")
        for key in URL_FIELDS:
            value = record[key]
            if value is not None and not _url(value):
                raise ValueError(f"Invalid evidence URL: {key}")
        if not _url(record["official_county_url"]):
            raise ValueError("Official county URL required")
        statewide = record["statewide_open_coverage"]
        if not isinstance(statewide, dict) or set(statewide) != {"available", "source", "source_url", "verified_date"}:
            raise ValueError("Invalid statewide open-coverage record")
        if type(statewide["available"]) is not bool:
            raise ValueError("statewide open coverage must be boolean")
        if not isinstance(statewide["source"], str) or not statewide["source"].strip():
            raise ValueError("Statewide source name required")
        if not _url(statewide["source_url"]):
            raise ValueError("Statewide source URL required")
        try:
            dt.date.fromisoformat(statewide["verified_date"])
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid statewide coverage verification date") from exc
        if record["source_authority"] not in {"county", "county-authorized-provider", "statewide", "unverified"}:
            raise ValueError("Invalid source authority")
        direct = record["usable_direct_machine_readable_source"]
        if type(direct) is not bool or (direct and not record["download_or_service_url"]):
            raise ValueError("Direct source must have a usable URL")
        monitoring = record["monitoring"]
        if set(monitoring) != {"decision", "reason", "terms_urls"}:
            raise ValueError("Invalid monitoring assessment")
        if monitoring["decision"] not in {"candidate-low-frequency", "hold-for-terms", "not-appropriate", "not-assessed"}:
            raise ValueError("Invalid monitoring decision")
        if monitoring["decision"] == "candidate-low-frequency" and not direct:
            raise ValueError("Monitoring candidate requires direct source")
        if not isinstance(monitoring["reason"], str) or not monitoring["reason"].strip():
            raise ValueError("Monitoring reason required")
        if not isinstance(monitoring["terms_urls"], list) or not all(_url(u) for u in monitoring["terms_urls"]):
            raise ValueError("Invalid terms URLs")
        evidence = record["evidence"]
        if not isinstance(evidence, list):
            raise ValueError("Evidence must be a list")
        for item in evidence:
            if set(item) != {"url", "authority", "finding"} or not _url(item["url"]):
                raise ValueError("Invalid evidence item")
            if item["authority"] not in {"county", "county-authorized-provider", "statewide"} or not item["finding"].strip():
                raise ValueError("Evidence authority and finding required")
        log = record["review_log"]
        if not isinstance(log, dict) or set(log) != set(REVIEW_AREAS):
            raise ValueError("All review areas must be recorded")
        for area in log.values():
            if set(area) != {"status", "note", "urls"}:
                raise ValueError("Invalid review area")
            if area["status"] not in {"reviewed", "not-found", "not-applicable", "blocked", "pending"}:
                raise ValueError("Invalid review status")
            if not isinstance(area["note"], str) or not area["note"].strip():
                raise ValueError("Review notes required")
            if not isinstance(area["urls"], list) or not all(_url(u) for u in area["urls"]):
                raise ValueError("Invalid review URLs")
            if complete and area["status"] in {"blocked", "pending"}:
                raise ValueError("Incomplete review cannot be published")
        if complete and (not evidence or not record["evidence_note"].strip() or not record["parcel_page_url"]):
            raise ValueError("Completed research requires parcel-specific evidence")
        if classification == "free-parcel-data" and not direct:
            raise ValueError("Free data requires verified machine-readable access")
        if classification == "fee-based-parcel-data":
            if not record["fee_policy_url"] or not record["fee_product"] or not record["parcel_dataset_fee"]:
                raise ValueError("Dataset fee requires policy, product, and fee evidence")
            if record["fee_policy_url"] not in {e["url"] for e in evidence if e["authority"] == "county"}:
                raise ValueError("Dataset fee requires official county evidence")
        if classification == "parcel-viewer-only" and (not record["viewer_url"] or direct):
            raise ValueError("Viewer-only requires viewer and no verified direct dataset")


def load_parcel_access(path: Path | None = None) -> dict[str, dict]:
    path = path or Path(__file__).with_name("minnesota_county_parcel_access.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_parcel_access(data)
    return {r["county"]: r for r in data["counties"]}


def access_label(record: dict | None, *, monitored: bool = False) -> str:
    if record and record.get("research_complete") is True:
        return DIRECT_CLASSIFICATIONS[record["county_direct_classification"]]
    return "Parcel-access research pending" if monitored else INTERIM_LABEL


def statewide_access_label(record: dict | None, *, live_available: bool | None = None) -> str:
    if live_available is True:
        return STATEWIDE_OPEN_LABEL
    if live_available is False:
        return "Not represented in the current MnGeo Plan Parcels Open observation"
    coverage = (record or {}).get("statewide_open_coverage") or {}
    if coverage.get("available") is True:
        return STATEWIDE_OPEN_LABEL
    return "No MnGeo open parcel coverage verified in the audit"
