"""Versioned public field boundary for the county directory."""

from __future__ import annotations

import datetime as dt
import re

from .public_values import safe_public_url

SCHEMA_VERSION = 1
DATASETS = ("parcel_polygons", "road_centerlines", "address_points")
CLASSIFICATIONS = ("open", "fee", "unknown")
METHODS = ("mngeo_open", "direct_rest", "direct_download", "other")
RESTRICTION_STATES = ("unreviewed", "reviewed_none", "restricted")


def _object(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _list(value: object, field: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _choice(value: object, choices: tuple[str, ...], field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{field} has an invalid selection")
    return value


def _public_fields(record: dict, *, text: tuple[str, ...] = (), urls: tuple[str, ...] = ()) -> dict:
    public = {}
    for field in text + urls:
        value = record.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        if not value.strip():
            continue
        if field in urls and not safe_public_url(value):
            raise ValueError(f"{field} must be a public HTTP(S) URL")
        public[field] = value
    return public


def _require_date(value: object, field: str) -> None:
    try:
        if isinstance(value, str) and dt.date.fromisoformat(value).isoformat() == value:
            return
    except ValueError:
        pass
    raise ValueError(f"{field} must be a calendar date (YYYY-MM-DD)")


def _project_contacts(records: object) -> list[dict]:
    public = []
    for record in _list(records, "contacts"):
        contact = _object(record, "contact")
        removed = contact.get("removed", False)
        if type(removed) is not bool:
            raise ValueError("contact removed must be boolean")
        if removed:
            continue
        fields = _public_fields(
            contact,
            text=("name", "role", "department", "phone", "email", "verified_on"),
            urls=("website", "source_url"),
        )
        if not (fields.get("name") or fields.get("department")):
            raise ValueError("contact requires a name or department")
        if "email" in fields and not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", fields["email"]):
            raise ValueError("contact email must be an email address")
        if "verified_on" in fields:
            _require_date(fields["verified_on"], "contact verified_on")
        public.append(fields)
    return public


def _project_methods(records: object) -> list[dict]:
    public = []
    seen = set()
    for record in _list(records, "methods"):
        method = _object(record, "method")
        kind = _choice(method.get("kind"), METHODS, "method kind")
        if kind in seen:
            raise ValueError("access methods must be unique")
        seen.add(kind)
        fields = _public_fields(method, text=("evidence_date", "scope", "update_frequency"), urls=("url",))
        _require_date(fields.get("evidence_date"), "method evidence_date")
        if not fields.get("url") or not fields.get("scope"):
            raise ValueError("method requires an evidence URL and scope")
        if "update_frequency" in fields and kind not in {"direct_rest", "direct_download"}:
            raise ValueError("method update_frequency is only available for direct data")
        if len(fields.get("update_frequency", "")) > 240:
            raise ValueError("method update_frequency exceeds 240 characters")
        if kind == "other":
            fields.update(_public_fields(method, text=("description",)))
            if "description" not in fields:
                raise ValueError("other method requires a description")
        public.append({"kind": kind, **fields})
    if not public:
        raise ValueError("open access requires at least one supported method")
    return public


def _project_access(record: dict) -> dict:
    classification = _choice(record.get("classification", "unknown"), CLASSIFICATIONS, "classification")
    restriction = _object(record.get("restrictions", {}), "restrictions")
    status = _choice(restriction.get("status", "unreviewed"), RESTRICTION_STATES, "restrictions status")
    details = {"status": status}
    if status == "restricted":
        details.update(_public_fields(restriction, text=("text", "reviewed_on"), urls=("url",)))
        if "text" not in details:
            raise ValueError("restricted access requires public restriction details")
    elif status == "reviewed_none":
        details.update(_public_fields(restriction, text=("reviewed_on",)))
    if "reviewed_on" in details:
        _require_date(details["reviewed_on"], "restrictions reviewed_on")
    return {
        "classification": classification,
        "methods": _project_methods(record.get("methods", [])) if classification == "open" else [],
        "restrictions": details,
        **_public_fields(record, text=("county_direct_note",)),
    }


def project_public_county(county: dict, draft: dict) -> dict:
    """Project an editable record using a server-resolved county identity.

    Publication supplies its own revision metadata after validating this content.
    Callers must escape public text for their output format.
    """
    if draft.get("fips") != county["fips"]:
        raise ValueError("record county does not match the selected county")
    access = _object(draft.get("access", {}), "access")
    return {
        "schema_version": SCHEMA_VERSION,
        "county": {field: county[field] for field in ("fips", "slug", "name")},
        "contacts": _project_contacts(draft.get("contacts", [])),
        "access": {dataset: _project_access(_object(access.get(dataset, {}), dataset)) for dataset in DATASETS},
        "policy": _public_fields(_object(draft.get("policy", {}), "policy"), text=("text",), urls=("url",)),
    }
