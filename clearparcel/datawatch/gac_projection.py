"""Read-only county field projection for saved GAC observations.

County measurements and statewide schema/scan metadata belong to the same
observation. Never substitute statewide counts or percentages for county data.
"""
from __future__ import annotations


def county_field(values: dict | None, metadata: dict | None, *, observed: bool = True) -> dict:
    values = values if isinstance(values, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    result = dict(values)
    present = values.get("present_in_source_schema", metadata.get("present_in_source_schema"))
    result["present_in_source_schema"] = present if type(present) is bool else None
    count = values.get("record_count")
    measured = type(count) is int and count >= 0
    if not observed:
        scanned = None
    elif "population_scanned" in values:
        # Explicit false/unknown must not be overwritten by shared metadata.
        scanned = values["population_scanned"]
    elif "population_scanned" in metadata:
        shared = metadata["population_scanned"]
        scanned = False if shared is False else True if shared is True and measured else None
    else:
        # Older snapshots omit scan flags; a valid county denominator is
        # evidence of a measurement, including an empty or zero-populated group.
        scanned = True if measured else None
    result["population_scanned"] = scanned if type(scanned) is bool else None
    if result["population_scanned"] is not True:
        # Do not present stale/conflicting metrics as measured population.
        for key in ("populated", "record_count", "percent"):
            if key in result:
                result[key] = None
    return result


def project_gac(data: dict) -> dict:
    """Return a detached presentation view; persisted observations stay intact."""
    summaries = data.get("fields") or {}
    counties = {}
    for name, county in (data.get("counties") or {}).items():
        if not isinstance(county, dict):
            counties[name] = county
            continue
        fields = county.get("fields") or {}
        observed = bool(fields) or (type(county.get("record_count")) is int
                                    and county["record_count"] >= 0)
        counties[name] = {
            **county,
            "fields": {
                field: county_field(fields.get(field), summaries.get(field), observed=observed)
                for field in dict.fromkeys((*fields, *summaries))
            },
        }
    return {**data, "counties": counties}
