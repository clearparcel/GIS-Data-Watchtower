"""Compare the packaged county seed with a recent exported public snapshot."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import Counter

from .county_directory import project_public_county
from .county_directory_seed import packaged_county_drafts
from .county_profiles import county_identities
from .dashboard import _load_county_contact_records
from .parcel_access import load_parcel_access

MAX_SNAPSHOT_BYTES = 24 * 1024 * 1024
_ACCESS_FIELDS = ("county_direct_classification", "parcel_dataset_fee", "fee_product")
_STATEWIDE_FIELDS = ("available", "source_url", "verified_date")
_METHOD_CATEGORY = {"direct_rest": "county_arcgis_rest", "direct_download": "county_download"}


def _contact(contact):
    return tuple(str(contact.get(key) or "").strip() for key in ("name", "department", "phone", "email")) + (
        str(contact.get("role") or contact.get("title") or "").strip(),
    )


def _links(profile, category):
    inventory = profile.get(category) or {}
    if inventory.get("availability") != "yes" or inventory.get("review_status") != "reviewed":
        return set()
    return {link.get("href") for source in inventory.get("sources", []) for link in source.get("approved_public_links", [])}


def _recent_snapshot(raw, now):
    if not isinstance(raw, bytes) or len(raw) > MAX_SNAPSHOT_BYTES:
        raise ValueError("public snapshot exceeds the migration input limit")
    try:
        snapshot = json.loads(raw)
        stamp = dt.datetime.fromisoformat(snapshot["snapshot_created_utc"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("invalid public snapshot or creation timestamp") from None
    if stamp.utcoffset() != dt.timedelta(0) or not -dt.timedelta(minutes=5) <= now - stamp <= dt.timedelta(hours=36):
        raise ValueError("public snapshot is outside the freshness window")
    return snapshot


def verify_county_migration(raw: bytes, *, now=None) -> dict:
    snapshot = _recent_snapshot(raw, now if now is not None else dt.datetime.now(dt.UTC))
    identities = county_identities()
    rows = snapshot.get("counties")
    if not isinstance(rows, list) or len(rows) != len(identities) or snapshot.get("county_count") != len(identities):
        raise ValueError("public snapshot does not cover the full county directory")
    seeds = packaged_county_drafts(identities)
    source_contacts = _load_county_contact_records()
    research = load_parcel_access()
    seen = set()
    issues = []
    observations = []
    contacts = 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("parcel_source_profile"), dict):
            raise ValueError("invalid county in public snapshot")
        profile = row["parcel_source_profile"]
        county = profile.get("county") or {}
        slug = county.get("slug") if isinstance(county, dict) else None
        if (not isinstance(slug, str) or slug in seen or identities.get(slug) != county
                or row.get("county") != county["name"]):
            raise ValueError("duplicate or invalid county in public snapshot")
        seen.add(slug)
        name = county["name"]
        seed = seeds[slug]
        projected = project_public_county(county, seed)
        live_contacts = row.get("contacts")
        if not isinstance(live_contacts, list) or not all(isinstance(contact, dict) for contact in live_contacts):
            raise ValueError("invalid public county contacts")
        contacts += len(live_contacts)
        if Counter(map(_contact, live_contacts)) != Counter(map(_contact, seed["contacts"])):
            issues.append({"county": name, "field": "contacts"})
        for public_key, source_key in (("contact_source_url", "source_url"), ("contact_verified", "verified")):
            if row.get(public_key) != source_contacts.get(name, {}).get(source_key):
                issues.append({"county": name, "field": public_key})

        deployed = row.get("parcel_access")
        if not isinstance(deployed, dict) or not isinstance(deployed.get("statewide_open_coverage"), dict):
            raise ValueError("invalid public parcel access evidence")
        packaged = research.get(name, {})
        for field in _ACCESS_FIELDS:
            if deployed.get(field) != packaged.get(field):
                issues.append({"county": name, "field": field})
        coverage = deployed["statewide_open_coverage"]
        for field in _STATEWIDE_FIELDS:
            if coverage.get(field) != packaged.get("statewide_open_coverage", {}).get(field):
                issues.append({"county": name, "field": f"statewide_open_coverage.{field}"})
        if deployed.get("statewide_open_current") is not coverage.get("available"):
            observations.append(name)
        for method in projected["access"]["parcel_polygons"]["methods"]:
            category = _METHOD_CATEGORY.get(method["kind"])
            if category and method["url"] not in _links(profile, category):
                issues.append({"county": name, "field": method["kind"]})

    return {
        "ready": not issues,
        "counties": len(seen),
        "deployed_contacts": contacts,
        "packaged_contacts": sum(len(draft["contacts"]) for draft in seeds.values()),
        "snapshot_created_utc": snapshot["snapshot_created_utc"],
        "watchtower_last_checked_utc": snapshot.get("watchtower_last_checked_utc"),
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "seed_sha256": hashlib.sha256(json.dumps(seeds, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest(),
        "exceptions": issues,
        "statewide_observation_differences": observations,
    }
