"""Synthetic MnGeo county-catalog rows for tests (no provider data)."""
from __future__ import annotations

from clearparcel.datawatch.gac_standards import minnesota_county_names


def full_minnesota_catalog(features: list[dict], field: str = "countyname") -> dict:
    """A catalog page naming every Minnesota county once, keeping the given rows.

    The Minnesota catalog must be complete (third review T05); tests about one
    county add placeholder rows for the rest.
    """
    named = {(row.get("attributes") or {}).get(field) for row in features}
    filler = [{"attributes": {field: name}} for name in sorted(minnesota_county_names() - named)]
    return {"features": list(features) + filler}
