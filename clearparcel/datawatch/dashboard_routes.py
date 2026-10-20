"""Read-only GAC and snapshot route dispatch for dashboard servers/adapters."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable

from clearparcel.datawatch.dashboard_exports import _snapshot_csv, _snapshot_xlsx

_SNAPSHOT_EXPORTS = {
    "/snapshot.json",
    "/snapshot.csv",
    "/snapshot.xlsx",
    "/county-snapshot.json",
    "/county-snapshot.csv",
    "/county-snapshot.xlsx",
}
_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def dispatch_gac_routes(
    path: str,
    query: str,
    *,
    config: dict,
    send: Callable[[int, str, str], object],
    render_html: Callable[[str], str] = lambda page: page,
) -> bool:
    """Route saved GAC results for hosted adapters without losing selection.

    Authentication and response security remain the caller's responsibility.
    No provider requests, state writes or operational refreshes occur here.
    """
    if path not in {"/mngac", "/mngac.json", "/mngac.csv"}:
        return False
    # Lazy import preserves dashboard's compatibility exports without a cycle.
    from clearparcel.datawatch import dashboard
    from clearparcel.datawatch.gac_standards import normalize_standard_key

    selection = urllib.parse.parse_qs(query)
    try:
        standard = normalize_standard_key(selection.get("standard", ["parcel"])[0])
    except ValueError:
        send(400, "Unsupported GAC standard", "text/plain; charset=utf-8")
        return True
    if path == "/mngac":
        try:
            page = dashboard.render_mngac(
                config, standard,
                county=selection.get("county", [""])[0],
                view=selection.get("view", ["county"])[0],
            )
        except ValueError:
            send(400, "Invalid MN GAC county or view. Choose a Minnesota county and "
                 "County results or Statewide overview.", "text/plain; charset=utf-8")
        else:
            send(200, render_html(page), "text/html; charset=utf-8")
        return True

    data = dashboard._gac_data(dashboard._dashboard_state(config), standard)
    if path == "/mngac.json":
        send(200 if data else 404,
             json.dumps(data or {"error": "GAC completeness data unavailable"}, indent=2),
             "application/json; charset=utf-8")
    else:
        send(200 if data else 404,
             dashboard._mngac_csv(data) if data else "GAC completeness data unavailable",
             "text/csv; charset=utf-8")
    return True


def dispatch_snapshot_exports(
    handler,
    path: str,
    query: str,
    *,
    statewide_snapshot: Callable[[], dict],
    county_snapshot: Callable[[str], dict | None],
    statewide_xlsx: Callable[[], bytes] | None = None,
) -> bool:
    """Send a shared snapshot export response; return False for other paths."""
    if path not in _SNAPSHOT_EXPORTS:
        return False

    if path.startswith("/county-snapshot"):
        slug = urllib.parse.parse_qs(query).get("slug", [""])[0]
        snapshot = county_snapshot(slug)
        available = bool(snapshot)
    else:
        slug = ""
        snapshot = statewide_snapshot()
        available = True

    if path.endswith(".json"):
        payload = json.dumps(snapshot if available else {"error": "county not found"}, indent=2)
        handler._send(200 if available else 404, payload, "application/json; charset=utf-8")
    elif path.endswith(".csv"):
        payload = _snapshot_csv(snapshot) if available else "county not found"
        handler._send(200 if available else 404, payload, "text/csv; charset=utf-8")
    elif not available:
        handler._send(404, "county not found", "text/plain; charset=utf-8")
    else:
        filename = f"{slug}-watchtower.xlsx" if slug else "watchtower-snapshot.xlsx"
        payload = statewide_xlsx() if path == "/snapshot.xlsx" and statewide_xlsx else _snapshot_xlsx(snapshot)
        handler._send_bytes(200, payload, _XLSX_CONTENT_TYPE, filename)
    return True
