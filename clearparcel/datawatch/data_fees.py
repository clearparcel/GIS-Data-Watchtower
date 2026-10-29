"""Validated county data-fee records for parcels, address points and road centerlines.

Fee research is separate from parcel-access classification and from monitoring.
A county or layer without a record is "not yet confirmed"; it is never free.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .public_values import safe_public_url

LAYERS = (
    ("parcels", "Parcels"),
    ("address_points", "Address points"),
    ("road_centerlines", "Road centerlines"),
)
LAYER_KEYS = tuple(key for key, _ in LAYERS)
FEE_STATUSES = {"fee": "Fee published", "no-fee": "No fee (county confirmed)"}
UNCONFIRMED_LABEL = "Not yet confirmed"
REST_STATUSES = {"fee": "Fee charged", "no-fee": "No fee", "unconfirmed": "Not confirmed",
                 "not-offered": "Not offered (data by request only)"}
SOURCE_KINDS = {"published-fee-schedule": "Published county fee schedule",
                "county-response": "County response to ClearParcel inquiry"}
LAYER_FIELDS = {"fee_status", "rest_download", "amount", "product", "source_kind",
                "source_url", "source_date", "note"}
FEE_FIELDS = ("county", "layer", "fee_status", "fee_status_label", "amount", "product",
              "rest_download", "rest_download_label", "source_kind", "source_url",
              "source_date", "note")


def _date(value: object) -> bool:
    try:
        return isinstance(value, str) and dt.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _text(value: object) -> bool:
    # Public text only: an "@" would usually mean a copied email address.
    return isinstance(value, str) and bool(value.strip()) and "@" not in value


def _validate_layer(entry: object) -> None:
    if not isinstance(entry, dict) or set(entry) != LAYER_FIELDS:
        raise ValueError("Invalid fee layer fields")
    status, rest = entry["fee_status"], entry["rest_download"]
    if (status not in FEE_STATUSES and status != "unconfirmed") or rest not in REST_STATUSES:
        raise ValueError("Invalid fee status")
    # A county may answer about access before it states any fee.
    if status == "unconfirmed" and (entry["source_kind"] != "county-response" or rest == "unconfirmed"
                                    or entry["amount"] is not None):
        raise ValueError("An unconfirmed fee entry must record a county's answer on access")
    if status == "no-fee" and rest != "no-fee":
        raise ValueError("A confirmed no-fee layer cannot charge for REST download")
    if rest == "fee" and status != "fee":
        raise ValueError("A REST download fee requires a fee status")
    # Only the county can say its service is withdrawn; a schedule cannot.
    if rest == "not-offered" and entry["source_kind"] != "county-response":
        raise ValueError("A withdrawn REST route requires a county response")
    if status == "fee" and not (_text(entry["amount"]) and _text(entry["product"])):
        raise ValueError("A published fee requires an amount and product")
    for key in ("amount", "product"):
        if entry[key] is not None and not _text(entry[key]):
            raise ValueError("Invalid fee " + key)
    if entry["source_kind"] not in SOURCE_KINDS:
        raise ValueError("Invalid fee source kind")
    if entry["source_url"] is not None and safe_public_url(entry["source_url"]) != entry["source_url"]:
        raise ValueError("Invalid fee source URL")
    # A published schedule must be citable; a county reply is cited by date
    # because private correspondence is never published.
    if entry["source_kind"] == "published-fee-schedule" and entry["source_url"] is None:
        raise ValueError("A published fee schedule requires its official URL")
    if not _date(entry["source_date"]):
        raise ValueError("Fee source date required")
    if not _text(entry["note"]):
        raise ValueError("Fee note required")


def validate_data_fees(data: dict, counties: list[str] | None = None) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("counties"), list):
        raise ValueError("Invalid data-fee document")
    known = set(counties) if counties is not None else None
    seen = set()
    for record in data["counties"]:
        if not isinstance(record, dict) or set(record) != {"county", "layers"}:
            raise ValueError("Invalid data-fee county record")
        name = record["county"]
        if name in seen or (known is not None and name not in known):
            raise ValueError("Unknown or duplicate fee county: " + str(name))
        seen.add(name)
        layers = record["layers"]
        if not isinstance(layers, dict) or not layers or not set(layers) <= set(LAYER_KEYS):
            raise ValueError("Invalid fee layers for " + name)
        for entry in layers.values():
            _validate_layer(entry)


def load_data_fees(path: Path | None = None) -> dict[str, dict]:
    """Return {county name: {layer key: entry}} for counties with any record."""
    path = path or Path(__file__).with_name("minnesota_county_data_fees.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    names = [c["name"] for c in json.loads(Path(__file__).with_name("minnesota_counties.json").read_text(encoding="utf-8"))["counties"]]
    validate_data_fees(data, names)
    return {record["county"]: record["layers"] for record in data["counties"]}


def county_fee_rows(layers: dict | None) -> list[dict]:
    """One row per layer; a missing layer is unconfirmed, never zero or free."""
    rows = []
    for key, label in LAYERS:
        entry = (layers or {}).get(key)
        if entry is None:
            rows.append({"layer": key, "layer_label": label, "fee_status": "unconfirmed",
                         "fee_status_label": UNCONFIRMED_LABEL, "amount": None, "product": None,
                         "rest_download": "unconfirmed", "rest_download_label": REST_STATUSES["unconfirmed"],
                         "source_kind": None, "source_label": None, "source_url": None,
                         "source_date": None, "note": None})
            continue
        rows.append({"layer": key, "layer_label": label, **entry,
                     "fee_status_label": FEE_STATUSES.get(entry["fee_status"], UNCONFIRMED_LABEL),
                     "rest_download_label": REST_STATUSES[entry["rest_download"]],
                     "source_label": SOURCE_KINDS[entry["source_kind"]]})
    return rows


def fee_counts(profiles: dict[str, dict]) -> dict[str, int]:
    """Count counties by what is known, keeping unconfirmed separate from free."""
    rows = [row for p in profiles.values() for row in p.get("data_fees") or []]
    by_county = [p.get("data_fees") or [] for p in profiles.values()]
    return {"counties": len(profiles),
            "with_published_fee": sum(any(r["fee_status"] == "fee" for r in c) for c in by_county),
            "with_confirmed_no_fee": sum(any(r["fee_status"] == "no-fee" for r in c) for c in by_county),
            "fully_unconfirmed": sum(all(r["fee_status"] == "unconfirmed" for r in c) for c in by_county),
            "rest_confirmed": sum(r["rest_download"] != "unconfirmed" for r in rows),
            "layer_slots": len(rows)}

