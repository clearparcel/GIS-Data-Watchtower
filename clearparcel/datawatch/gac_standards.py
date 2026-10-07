"""Minnesota GAC standard definitions shared by monitoring and presentation."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_STANDARD_FILES = {
    "parcel": "mngac_parcel_fields.json",
    "address": "mngac_address_fields.json",
    "road": "mngac_road_fields.json",
}

_STANDARD_DEFAULTS = {
    "parcel": {
        "key": "parcel",
        "county_name_field": "CO_NAME",
        "county_code_field": "CO_CODE",
        "dataset_label": "MnGeo Plan Parcels Open",
        "record_label": "parcel records",
        "record_label_singular": "parcel record",
        "metadata_submission_field": None,
        "routine_batch_size": 12,
        "routine_population_scope": "all",
        "routine_text_population_mode": "nonblank",
        "grouping_note": "Grouped by CO_NAME and CO_CODE.",
    },
    "address": {
        "key": "address",
        "county_name_field": "CO_NAME",
        "county_code_field": None,
        "dataset_label": "MnGeo Loc Addresses Open",
        "record_label": "address points",
        "record_label_singular": "address point",
        "metadata_submission_field": "s2e_date_adp",
        "routine_batch_size": 12,
        "routine_population_scope": "mandatory",
        "routine_text_population_mode": "nonblank",
        "grouping_note": (
            "Grouped by county name (CO_NAME), normalized to the 87 canonical "
            "Minnesota counties. County-code anomalies do not split a denominator."
        ),
    },
    "road": {
        "key": "road",
        "county_name_field": "CO_NAME_L",
        "county_code_field": None,
        "dataset_label": "MnGeo Trans Road Centerlines Open",
        "record_label": "road segments",
        "record_label_singular": "road segment",
        "metadata_submission_field": "s2e_date_rcl",
        "routine_batch_size": 12,
        "routine_population_scope": "mandatory",
        "routine_text_population_mode": "nonblank",
        "grouping_note": (
            "Grouped by left-side county name (CO_NAME_L), normalized to the 87 "
            "canonical Minnesota counties. Out-of-jurisdiction names are excluded; "
            "side county-code anomalies do not split a county denominator."
        ),
    },
}


def standard_keys() -> tuple[str, ...]:
    return tuple(_STANDARD_FILES)


def normalize_standard_key(value: object, *, default: str = "parcel") -> str:
    key = str(value or default).strip().lower()
    if key not in _STANDARD_FILES:
        raise ValueError(f"unsupported GAC standard: {key}")
    return key


def load_gac_standard(key: str = "parcel") -> dict:
    key = normalize_standard_key(key)
    path = Path(__file__).with_name(_STANDARD_FILES[key])
    document = json.loads(path.read_text(encoding="utf-8"))
    standard = document.setdefault("standard", {})
    standard.setdefault("key", key)
    return document


def gac_defaults(key: str = "parcel") -> dict:
    key = normalize_standard_key(key)
    return dict(_STANDARD_DEFAULTS[key])


_COUNTY_ALIASES = {
    "saint louis": "St. Louis",
}


@lru_cache(maxsize=1)
def _county_name_lookup() -> dict[str, str]:
    document = json.loads(Path(__file__).with_name("minnesota_counties.json").read_text(encoding="utf-8"))
    lookup = {str(row["name"]).casefold(): str(row["name"]) for row in document.get("counties") or []}
    lookup.update(_COUNTY_ALIASES)
    return lookup


def canonical_minnesota_county(value: object) -> str | None:
    name = " ".join(str(value or "").split()).strip()
    if not name:
        return None
    return _county_name_lookup().get(name.casefold())
