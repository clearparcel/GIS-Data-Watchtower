"""Prepare unsaved editor drafts from packaged public evidence, offline."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from .dashboard import _load_county_contact_records
from .parcel_access import DIRECT_CLASSIFICATIONS, load_parcel_access
from .public_values import safe_public_url


def _contacts(county: dict, record: dict) -> list[dict]:
    contacts = []
    for index, contact in enumerate(record.get("contacts", [])):
        fields = {
            "id": str(uuid5(NAMESPACE_URL, f"watchtower:county:{county['fips']}:seed:{index}")),
            "name": contact.get("name"), "role": contact.get("title"), "department": contact.get("department"),
            "phone": contact.get("phone"), "email": contact.get("email"),
            "website": safe_public_url(contact.get("website") or record.get("official_county_url")),
            "source_url": safe_public_url(record.get("source_url")), "verified_on": record.get("verified"),
        }
        contacts.append({key: value for key, value in fields.items() if value})
    return contacts


def _parcel_draft(record: dict) -> dict:
    direct = record.get("county_direct_classification")
    methods = []
    statewide = record.get("statewide_open_coverage") or {}
    if (statewide.get("available") is True and statewide.get("verified_date")
            and (url := safe_public_url(statewide.get("source_url")))):
        methods.append({"kind": "mngeo_open", "url": url, "evidence_date": statewide["verified_date"],
                        "scope": "MnGeo Plan Parcels Open statewide compilation"})
    if direct == "free-parcel-data":
        inventory = record.get("source_inventory") or {}
        for kind, category in (("direct_rest", "county_arcgis_rest"), ("direct_download", "county_download")):
            entry = inventory.get(category) or {}
            if entry.get("availability") != "yes" or entry.get("review_status") != "reviewed":
                continue
            for source in entry.get("sources", []):
                url = next((safe_public_url(link.get("href")) for link in source["approved_public_links"]
                            if safe_public_url(link.get("href"))), None)
                if url and source.get("review_date") and source.get("dataset_type"):
                    methods.append({"kind": kind, "url": url, "evidence_date": source["review_date"],
                                    "scope": source["dataset_type"]})
                    break
    classification = "open" if methods else "fee" if direct == "fee-based-parcel-data" else "unknown"
    note = DIRECT_CLASSIFICATIONS.get(direct, "County-direct access is unresolved")
    return {
        "classification": classification,
        "methods": methods,
        "restrictions": {"status": "unreviewed"},
        "county_direct_note": ". ".join(part for part in (
            note, record.get("parcel_dataset_fee"), record.get("fee_product"),
        ) if part),
    }


def packaged_county_drafts(counties: dict[str, dict]) -> dict[str, dict]:
    contacts = _load_county_contact_records()
    research = load_parcel_access()
    return {
        slug: {
            "fips": county["fips"],
            "contacts": _contacts(county, contacts.get(county["name"], {})),
            "access": {"parcel_polygons": _parcel_draft(research.get(county["name"], {}))},
            "policy": {},
            "correspondence": [],
        }
        for slug, county in counties.items()
    }
