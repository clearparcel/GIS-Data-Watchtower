"""Validated parcel-access research, independent of monitoring observations."""
from __future__ import annotations

import datetime as dt
import copy
import json
from pathlib import Path
from urllib.parse import urlsplit
from .public_values import safe_public_url, public_access_classification, safe_geometry_type, safe_file_type

DIRECT_CLASSIFICATIONS = {
    "free-parcel-data": "Open parcel data",
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
INVENTORY_CATEGORIES = (
    "mngac_public_parcels", "mngeo_public_repository",
    "county_arcgis_rest", "county_download",
)
MONITORING_DECISIONS = {"candidate-low-frequency", "hold-for-terms", "not-appropriate", "not-assessed"}
INVENTORY_FIELDS = {"review_status", "availability", "review_date", "finding", "evidence", "sources"}
SOURCE_FIELDS = {"inventory_id", "name", "authority", "dataset_type", "layer_id", "approved_public_links", "review_date", "monitoring_decision", "evidence"}
SOURCE_OPTIONAL_FIELDS = {"monitored_source_id", "geometry_type", "file_type"}


def _date(value: object) -> bool:
    try:
        return isinstance(value, str) and dt.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _validate_inventory(record: dict) -> None:
    inventory = record["source_inventory"]
    if not isinstance(inventory, dict) or set(inventory) != set(INVENTORY_CATEGORIES):
        raise ValueError("All four inventory categories required")
    if not isinstance(record["comments"], str):
        raise ValueError("Comments must be text")
    evidence_urls = {e["url"] for e in record["evidence"]}
    official_urls = {e["url"] for e in record["evidence"] if e["authority"] in {"county", "county-authorized-provider", "statewide"}}
    ids = set()
    for category in inventory.values():
        if not isinstance(category, dict) or set(category) != INVENTORY_FIELDS:
            raise ValueError("Invalid inventory category fields")
        status, available = category["review_status"], category["availability"]
        if status not in {"pending", "reviewed", "not-found", "blocked"} or available not in {"yes", "no", "unknown"}:
            raise ValueError("Invalid inventory assessment")
        if not isinstance(category["finding"], str) or not category["finding"].strip():
            raise ValueError("Inventory finding required")
        refs = category["evidence"]
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref in evidence_urls for ref in refs):
            raise ValueError("Unknown inventory evidence reference")
        if category["review_date"] is not None and not _date(category["review_date"]):
            raise ValueError("Invalid inventory review date")
        if status in {"reviewed", "not-found"} and (not _date(category["review_date"]) or not refs):
            raise ValueError("Reviewed category requires date and evidence")
        if available == "yes" and not refs:
            raise ValueError("Positive availability requires evidence")
        if available == "no" and (status not in {"reviewed", "not-found"} or not set(refs).intersection(official_urls)):
            raise ValueError("Absence requires completed official evidence review")
        if status == "not-found" and available != "no":
            raise ValueError("Not-found category must document absence")
        sources = category["sources"]
        if not isinstance(sources, list) or (available == "yes" and not sources) or (available != "yes" and sources):
            raise ValueError("Inventory availability must match sources")
        for source in sources:
            if not isinstance(source, dict) or not SOURCE_FIELDS <= set(source) <= SOURCE_FIELDS | SOURCE_OPTIONAL_FIELDS:
                raise ValueError("Invalid static source fields")
            for key, validate in (("geometry_type", safe_geometry_type), ("file_type", safe_file_type)):
                if source.get(key) is not None and validate(source[key]) is None:
                    raise ValueError("Invalid stable source " + key)
            for key in ("inventory_id", "name", "dataset_type"):
                if not isinstance(source[key], str) or not source[key].strip():
                    raise ValueError("Source identity, name and type required")
            if source["inventory_id"] in ids:
                raise ValueError("Duplicate inventory source ID")
            ids.add(source["inventory_id"])
            if source["authority"] not in {"county", "county-authorized-provider", "statewide"}:
                raise ValueError("Invalid inventory source authority")
            if source["layer_id"] is not None and (type(source["layer_id"]) not in {str, int} or str(source["layer_id"]) == ""):
                raise ValueError("Invalid layer ID")
            if not _date(source["review_date"]) or source["monitoring_decision"] not in MONITORING_DECISIONS:
                raise ValueError("Source requires review date and monitoring decision")
            if "monitored_source_id" in source and source["monitored_source_id"] is not None and (not isinstance(source["monitored_source_id"], str) or not source["monitored_source_id"].strip()):
                raise ValueError("Invalid monitored source ID")
            if not isinstance(source["evidence"], list) or not source["evidence"] or not all(isinstance(ref, str) and ref in evidence_urls for ref in source["evidence"]):
                raise ValueError("Source requires existing evidence references")
            links = source["approved_public_links"]
            if not isinstance(links, list) or not links:
                raise ValueError("Source public links required")
            for link in links:
                if not isinstance(link, dict) or set(link) != {"label", "href"} or not isinstance(link["label"], str) or not link["label"].strip() or safe_public_url(link["href"]) is None or link["href"] not in evidence_urls:
                    raise ValueError("Invalid approved public link")


def _url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"https", "http"} and bool(parsed.hostname) and not parsed.username


def validate_parcel_access(data: dict) -> None:
    """Reject ambiguous/unsupported published research; no network access."""
    if set(data) != {"schema_version", "scope", "counties"} or data["schema_version"] not in {2, 3}:
        raise ValueError("Unsupported parcel-access schema")
    if not isinstance(data["scope"], str) or not data["scope"].strip():
        raise ValueError("Research scope required")
    if not isinstance(data["counties"], list):
        raise ValueError("Counties must be a list")
    seen = set()
    for record in data["counties"]:
        expected_fields = RECORD_FIELDS | {"source_inventory", "comments"} if data["schema_version"] == 3 else RECORD_FIELDS
        if not isinstance(record, dict) or set(record) != expected_fields:
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
        unknown_statewide = data["schema_version"] == 3 and statewide["available"] is None and statewide["verified_date"] is None
        if type(statewide["available"]) is not bool and not unknown_statewide:
            raise ValueError("statewide open coverage must be boolean")
        if not isinstance(statewide["source"], str) or not statewide["source"].strip():
            raise ValueError("Statewide source name required")
        if not _url(statewide["source_url"]):
            raise ValueError("Statewide source URL required")
        if not unknown_statewide:
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
        if data["schema_version"] == 3:
            _validate_inventory(record)
    if data["schema_version"] == 3:
        canonical = json.loads(Path(__file__).with_name("minnesota_counties.json").read_text(encoding="utf-8"))["counties"]
        if seen != {c["name"] for c in canonical} or len(data["counties"]) != 87:
            raise ValueError("V3 inventory requires exactly 87 canonical Minnesota counties")


def migrate_parcel_access(data: dict, county_index: list[dict], official_urls: dict[str, str]) -> dict:
    """Preserve direct-access evidence; seed incomplete inventory without networking."""
    validate_parcel_access(data)
    if data["schema_version"] == 3:
        return copy.deepcopy(data)
    existing = {r["county"]: r for r in data["counties"]}
    if set(existing) - {c["name"] for c in county_index}:
        raise ValueError("Migration contains unknown county")
    migrated = {"schema_version": 3, "scope": data["scope"], "counties": []}
    for county in county_index:
        name = county["name"]
        if name in existing:
            record = copy.deepcopy(existing[name])
        else:
            record = dict.fromkeys(sorted(RECORD_FIELDS))
            record.update(county=name, official_county_url=official_urls[name], research_complete=False,
                source_authority="unverified", usable_direct_machine_readable_source=False,
                evidence_note="County-direct parcel access has not yet been reviewed.", evidence=[],
                review_log={area: {"status": "pending", "note": "Not yet reviewed.", "urls": []} for area in REVIEW_AREAS},
                monitoring={"decision": "not-assessed", "reason": "Discovery does not authorize monitoring.", "terms_urls": []},
                statewide_open_coverage={"available": None, "source": "MnGeo Plan Parcels Open", "source_url": "https://gisdata.mn.gov/dataset/plan-parcels-open", "verified_date": None})
        record["comments"] = ""
        record["source_inventory"] = {key: {"review_status": "pending", "availability": "unknown", "review_date": None, "finding": "Category not yet reviewed.", "evidence": [], "sources": []} for key in INVENTORY_CATEGORIES}
        url = record["download_or_service_url"]
        # Only a retained evidence URL supporting usable access establishes a source.
        if url and record["usable_direct_machine_readable_source"] and safe_public_url(url):
            refs = [e["url"] for e in record["evidence"] if e["url"] == url]
            parsed = urlsplit(url)
            rest = "/rest/services/" in parsed.path.lower() and any(t in parsed.path.lower() for t in ("featureserver", "mapserver"))
            download = parsed.path.lower().endswith((".zip", ".shp", ".gdb", ".geojson", ".gpkg"))
            if refs and (rest or download):
                key = "county_arcgis_rest" if rest else "county_download"
                category = record["source_inventory"][key]
                tail = parsed.path.rstrip("/").split("/")[-1]
                source = {"inventory_id": county["slug"] + ":" + key + ":1", "name": name + " parcel dataset", "authority": record["source_authority"], "dataset_type": "ArcGIS REST" if rest else "Parcel download", "layer_id": tail if rest and tail.isdigit() else None, "approved_public_links": [{"label": "Official parcel source", "href": url}], "review_date": record["review_date"], "monitoring_decision": record["monitoring"]["decision"], "evidence": refs}
                category.update(availability="yes", evidence=refs, sources=[source], finding="Retained evidence establishes this parcel source; full category review remains pending.")
        migrated["counties"].append(record)
    validate_parcel_access(migrated)
    return migrated


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
