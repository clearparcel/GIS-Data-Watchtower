"""Module attributes that v0.2.3 exposed and later releases removed or moved.

Code built against v0.2.3, such as deployment-specific wrappers kept outside
this repository, may import these names. Each affected module defines a
module-level ``__getattr__`` that resolves them here lazily, so current code
paths do not import them but old imports keep working. Do not use these names
in new code; ``tests/test_compat.py`` pins the full list.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

_PACKAGE = "clearparcel.datawatch"

MNGAC_FIELDS_FILE = Path(__file__).with_name("mngac_parcel_fields.json")


def _load_mngac_schema() -> dict:
    """Parcel-standard loader formerly in ``watch``."""
    from clearparcel.datawatch.gac_standards import load_gac_standard
    return load_gac_standard("parcel")


def _destination_publicity(url: str, *, deadline=None) -> bool | None:
    """Return True for globally routable, False for local/reserved, None if unresolved.

    Formerly ``watch._destination_publicity``; redirect validation does its own
    stricter check and never calls this.
    """
    import ipaddress
    import socket
    import urllib.parse
    from clearparcel.datawatch.transport import RequestDeadline, resolve_addresses
    from clearparcel.datawatch.watch import _url_host

    if deadline is None:
        with RequestDeadline(20) as bounded:
            return _destination_publicity(url, deadline=bounded)
    parsed = urllib.parse.urlparse(url)
    host = _url_host(url)
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".internal")):
        return False
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        try:
            infos = resolve_addresses(host, port, deadline)
        except socket.gaierror:
            return None
        addresses = []
        for info in infos:
            try:
                addresses.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
        if not addresses:
            return None
    return all(address.is_global for address in addresses)


def _county_mngac_summary(state: dict, county: dict) -> dict:
    """Formerly ``dashboard._county_mngac_summary`` / ``dashboard_gac._county_mngac_summary``."""
    from clearparcel.datawatch import dashboard
    data, county_stats = dashboard._mngac_county_record(state, county["name"])
    source_id, source = dashboard._mngac_source(state)
    return {
        "data": data,
        "county": county_stats,
        "source_id": source_id,
        "source": source,
        "checked_at": (source or {}).get("checked_at") or (source or {}).get("last_success_at"),
    }


def _json(value: object) -> str:
    """Formerly ``county_profile_panel._json``: JSON safe to embed in a script element."""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


_PANEL = "county_profile_panel"
_EXPORTS = "dashboard_exports"
_PROJECTION = "public_projection"

# module -> {legacy name: "module:attribute" (relative to the package) or "@stdlib-module"}
LEGACY: dict[str, dict[str, str]] = {
    "dashboard": {
        "MNGAC_FIELDS_FILE": "_compat:MNGAC_FIELDS_FILE",
        "_county_mngac_summary": "_compat:_county_mngac_summary",
        "_refresh_script": "dashboard_templates:_refresh_script",
        **{name: f"{_PANEL}:{name}" for name in (
            "NO_DATA_COLOR", "PERCENT_COLORS", "percentage_color_js", "percentage_legend",
            "profile_time", "render_county_profile_panel")},
        **{name: f"{_EXPORTS}:{name}" for name in (
            "_csv_safe", "_gac_xlsx_sheets", "_mngac_xlsx_sheets", "_xlsx_col_name", "_xlsx_sheet_xml")},
        "re": "@re",
    },
    "dashboard_gac": {"_county_mngac_summary": "_compat:_county_mngac_summary"},
    "public_dashboard": {
        **{name: f"{_PROJECTION}:{name}" for name in (
            "_approval", "_catalog_date", "_project", "_public_count", "_public_date", "_public_number",
            "_public_status", "_records", "_sanitize_catalog_records", "_sanitize_completeness",
            "_sanitize_gac", "_sanitize_mngac")},
        "_county_monitoring_counts": "dashboard:_county_monitoring_counts",
        "_snapshot_csv": f"{_EXPORTS}:_snapshot_csv",
    },
    "watch": {
        "MNGAC_FIELDS_FILE": "_compat:MNGAC_FIELDS_FILE",
        "_destination_publicity": "_compat:_destination_publicity",
        "_load_mngac_schema": "_compat:_load_mngac_schema",
        "sys": "@sys",
    },
    "county_profile_panel": {"_json": "_compat:_json"},
    "county_profiles": {"provider_edit_timestamp": "public_values:provider_edit_timestamp"},
    "parcel_access": {"public_access_classification": "public_values:public_access_classification"},
    "county_profile_exports": {"re": "@re"},
    "dashboard_exports": {"re": "@re"},
}


def resolve(module_name: str, name: str):
    """Look up a legacy attribute for ``module_name``; raise AttributeError otherwise."""
    short = module_name.rsplit(".", 1)[-1]
    target = LEGACY.get(short, {}).get(name)
    if target is None:
        raise AttributeError(f"module {module_name!r} has no attribute {name!r}")
    if target.startswith("@"):
        return importlib.import_module(target[1:])
    module, attribute = target.split(":", 1)
    return getattr(importlib.import_module(f"{_PACKAGE}.{module}"), attribute)
