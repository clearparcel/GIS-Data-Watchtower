from __future__ import annotations

import base64
import datetime as dt
import hmac
import ipaddress
import json
import os
import secrets
import threading
import urllib.parse
import re
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from clearparcel.datawatch.dashboard_templates import (
    _esc,
    _layout,
    _public_layout_v2,
    _refresh_script,
)

from clearparcel.datawatch.watch import check_sources, load_history, load_state
from clearparcel.datawatch.transport import RequestDeadline
from clearparcel.datawatch.aggregate import with_freshness
from clearparcel.datawatch.parcel_access import access_label, load_parcel_access, statewide_access_label
from clearparcel.datawatch.county_profile_panel import render_county_profile_panel, render_county_profile_body, percentage_legend, percentage_color_js, profile_time, research_summary, PERCENT_COLORS, NO_DATA_COLOR
from clearparcel.datawatch.county_profile_exports import county_profiles_csv, parcel_sources_csv
from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles, county_profile_counts
from clearparcel.datawatch.gac_standards import gac_defaults, load_gac_standard, normalize_standard_key, standard_keys

COUNTIES_FILE = Path(__file__).with_name("minnesota_counties.json")
COUNTY_CONTACTS_FILE = Path(__file__).with_name("minnesota_county_contacts.json")
COUNTY_CONTACT_VERIFICATION_FILE = Path(__file__).with_name("minnesota_county_contact_verification.json")
MNGAC_FIELDS_FILE = Path(__file__).with_name("mngac_parcel_fields.json")
COUNTY_BOUNDARIES_FILE = Path(__file__).with_name("minnesota_county_boundaries.json")


def _safe_url(value) -> str | None:
    if not value:
        return None
    try:
        parsed = urllib.parse.urlparse(str(value))
    except ValueError:
        return None
    return str(value) if parsed.scheme.lower() in ("http", "https") and bool(parsed.netloc) else None


CENTRAL_TZ = ZoneInfo("America/Chicago")

def _format_time_pair(value) -> str:
    parsed = _parse_time(value)
    if not parsed: return _esc(value or "—")
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=dt.timezone.utc)
    utc=parsed.astimezone(dt.timezone.utc); central=parsed.astimezone(CENTRAL_TZ)
    ct=f"{central.strftime('%b')} {central.day}, {central.year} {central.strftime('%I:%M:%S %p').lstrip('0')} {central.tzname()}"
    ut=f"{utc.strftime('%b')} {utc.day}, {utc.year} {utc.strftime('%I:%M:%S %p').lstrip('0')} UTC"
    return f'{ct}<br><span class="muted">{ut}</span>'

def _format_public_time_compact(value) -> str:
    parsed = _parse_time(value)
    if not parsed:
        return _esc(value or "—")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    central = parsed.astimezone(CENTRAL_TZ)
    return f"{central.strftime('%b')} {central.day}, {central.year} · {central.strftime('%I:%M %p').lstrip('0')} {central.tzname()}"


def _snapshot_time_fields(value, prefix: str) -> dict:
    parsed=_parse_time(value)
    if not parsed: return {f"{prefix}_central":None,f"{prefix}_utc":None}
    if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=dt.timezone.utc)
    return {f"{prefix}_central":parsed.astimezone(CENTRAL_TZ).isoformat(),f"{prefix}_utc":parsed.astimezone(dt.timezone.utc).isoformat()}

def _parse_time(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _history_stats(entries: list[dict]) -> dict:
    if not entries:
        return {"success_rate": None, "consecutive_ok": 0, "last_change": None, "change_age_days": None}
    ok_count = sum(1 for x in entries if x.get("status") == "ok")
    consecutive = 0
    for item in reversed(entries):
        if item.get("status") != "ok":
            break
        consecutive += 1
    last_change = None
    for item in reversed(entries):
        if item.get("changes"):
            last_change = item.get("generated_at")
            break
    age = None
    parsed = _parse_time(last_change)
    if parsed:
        now = dt.datetime.now(dt.timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        age = max(0, (now - parsed.astimezone(dt.timezone.utc)).days)
    return {
        "success_rate": round((ok_count / len(entries)) * 100.0, 1),
        "consecutive_ok": consecutive,
        "last_change": last_change,
        "change_age_days": age,
    }


def _svg_sparkline(values: list[float | int | None], *, width: int = 300, height: int = 72) -> str:
    clean = [(i, float(v)) for i, v in enumerate(values) if isinstance(v, (int, float))]
    if len(clean) < 2:
        return '<div class="muted">Not enough history yet</div>'
    vals = [v for _, v in clean]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return f'<div class="flat-note">No change across {len(clean)} retained observations <strong>({_esc(round(lo,2))})</strong>.</div>'
    span = hi - lo
    denom = max(1, len(values) - 1)
    points = " ".join(
        f"{8 + (i / denom) * (width - 16):.1f},{height - 8 - ((v - lo) / span) * (height - 16):.1f}"
        for i, v in clean
    )
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" aria-label="Trend across retained observations">'
        f'<polyline points="{points}" fill="none" stroke="currentColor" stroke-width="2"/>'
        f'</svg><div class="chart-range">{_esc(round(lo,2))} – {_esc(round(hi,2))}</div>'
    )


def _source_config_map(config: dict) -> dict:
    return {str(x.get("id")): x for x in config.get("sources", []) if x.get("id")}

def _dashboard_state(config: dict) -> dict:
    """Load unified aggregate state when configured, then annotate freshness."""
    path = config.get("aggregate_state_file") or config["state_file"]
    return with_freshness(
        load_state(path),
        worker_stale_minutes=int(config.get("worker_stale_minutes", 1560)),
        source_stale_minutes=int(config.get("source_stale_minutes", 1560)),
    )



def _load_mngac_schema() -> dict:
    """Backward-compatible parcel standard loader."""
    try:
        return load_gac_standard("parcel")
    except (OSError, json.JSONDecodeError):
        return {"standard": {}, "fields": []}


def _load_county_boundaries() -> dict:
    try:
        return json.loads(COUNTY_BOUNDARIES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"source": {}, "counties": []}


def _gac_source(state: dict, standard_key: str = "parcel") -> tuple[str | None, dict | None]:
    standard_key = normalize_standard_key(standard_key)
    for source_id, source in (state.get("sources") or {}).items():
        data = source.get("gac_completeness")
        if isinstance(data, dict):
            key = str(data.get("standard_key") or (data.get("standard") or {}).get("key") or "").lower()
            if key == standard_key and data.get("fields") and data.get("counties"):
                return source_id, source
        if standard_key == "parcel":
            legacy = source.get("mngac_completeness")
            if isinstance(legacy, dict) and legacy.get("fields") and legacy.get("counties"):
                return source_id, source
    return None, None


def _gac_data(state: dict, standard_key: str = "parcel") -> dict | None:
    standard_key = normalize_standard_key(standard_key)
    _, source = _gac_source(state, standard_key)
    if not isinstance(source, dict):
        return None
    data = source.get("gac_completeness")
    if isinstance(data, dict):
        key = str(data.get("standard_key") or (data.get("standard") or {}).get("key") or "").lower()
        if key == standard_key and data.get("fields"):
            return data
    if standard_key == "parcel":
        legacy = source.get("mngac_completeness")
        if isinstance(legacy, dict) and legacy.get("fields"):
            return legacy
    return None


def _mngac_source(state: dict) -> tuple[str | None, dict | None]:
    return _gac_source(state, "parcel")


def _mngac_data(state: dict) -> dict | None:
    return _gac_data(state, "parcel")


def _county_slug_map() -> dict[str, str]:
    return {str(x.get("name")): str(x.get("slug")) for x in _load_counties() if x.get("name") and x.get("slug")}


def _mngac_map_svg(width: int = 620, height: int = 700) -> str:
    boundaries = _load_county_boundaries()
    features = boundaries.get("counties") or []
    coords = [
        point for feature in features for ring in (feature.get("rings") or [])
        for point in ring if isinstance(point, list) and len(point) >= 2
    ]
    if not coords:
        return '<div class="muted">Minnesota county boundaries are unavailable.</div>'
    min_x = min(float(p[0]) for p in coords); max_x = max(float(p[0]) for p in coords)
    min_y = min(float(p[1]) for p in coords); max_y = max(float(p[1]) for p in coords)
    pad = 18.0
    scale = min((width - 2 * pad) / max(max_x - min_x, 1.0), (height - 2 * pad) / max(max_y - min_y, 1.0))
    xoff = (width - (max_x - min_x) * scale) / 2.0
    yoff = (height - (max_y - min_y) * scale) / 2.0
    slugs = _county_slug_map()
    paths = []
    for feature in features:
        name = str(feature.get("name") or "")
        d_parts = []
        for ring in feature.get("rings") or []:
            if not ring:
                continue
            pts = [
                (xoff + (float(pt[0]) - min_x) * scale, yoff + (max_y - float(pt[1])) * scale)
                for pt in ring if isinstance(pt, list) and len(pt) >= 2
            ]
            if len(pts) < 3:
                continue
            d_parts.append("M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z")
        if not d_parts:
            continue
        paths.append(
            f'<path class="mngac-county" data-county="{_esc(name)}" data-slug="{_esc(slugs.get(name, ""))}" '
            f'tabindex="0" role="button" aria-pressed="false" fill-rule="evenodd" aria-label="{_esc(name)} County" d="{" ".join(d_parts)}">'
            f'<title>{_esc(name)} County</title></path>'
        )
    return f'<svg id="mngac-map" class="mngac-map" viewBox="0 0 {width} {height}" role="group" aria-label="Interactive Minnesota county map">{"".join(paths)}</svg>'


def _mngac_county_record(state: dict, county_name: str) -> tuple[dict | None, dict | None]:
    data = _mngac_data(state)
    if not data:
        return None, None
    return data, (data.get("counties") or {}).get(county_name)


def _mngac_field_rows(county_stats: dict) -> str:
    schema = _load_mngac_schema()
    rows = []
    field_stats = county_stats.get("fields") or {}
    for spec in schema.get("fields") or []:
        field = str(spec.get("field") or "")
        stats = field_stats.get(field) or {}
        populated = stats.get("populated")
        total = stats.get("record_count")
        pct = stats.get("percent")
        present = stats.get("present_in_source_schema")
        scanned = stats.get("population_scanned") is True
        rows.append(
            f'<tr data-name="{_esc((str(spec.get("label") or "") + " " + field).lower())}" '
            f'data-inclusion="{_esc(spec.get("inclusion") or "")}">'
            f'<td><strong>{_esc(spec.get("label"))}</strong><br><code>{_esc(field)}</code></td>'
            f'<td>{_esc(spec.get("section_name"))}</td><td>{_esc(spec.get("inclusion"))}</td>'
            f'<td>{"Present" if present is True else "Missing" if present is False else "Unknown"}</td>'
            f'<td>{"Scanned" if scanned else "Not scanned"}</td>'
            f'<td>{_esc(f"{populated:,}" if isinstance(populated, int) else "—")}</td>'
            f'<td>{_esc(f"{total:,}" if isinstance(total, int) else "—")}</td>'
            f'<td><strong>{_esc(f"{pct:.2f}%" if isinstance(pct, (int,float)) else "—")}</strong></td></tr>'
        )
    return "".join(rows)


def _load_counties() -> list[dict]:
    try:
        data = json.loads(COUNTIES_FILE.read_text(encoding="utf-8"))
        return data.get("counties", [])
    except (OSError, json.JSONDecodeError):
        return []


def _load_county_contact_records() -> dict[str, dict]:
    try:
        baseline = json.loads(COUNTY_CONTACTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        baseline = {"source": {}, "counties": []}
    try:
        verification = json.loads(COUNTY_CONTACT_VERIFICATION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        verification = {"counties": []}

    mngeo_source = baseline.get("source") or {}
    verified = {str(x.get("county")): x for x in verification.get("counties", []) if x.get("county")}
    records = {}
    for item in baseline.get("counties", []):
        county = str(item.get("county") or "")
        if not county:
            continue
        check = verified.get(county) or {}
        official_contacts = check.get("contacts") or []
        use_county = check.get("authority") == "county" and bool(official_contacts)
        records[county] = {
            "contacts": official_contacts if use_county else (item.get("contacts") or []),
            "authority": "county" if use_county else ("mngeo" if check.get("verified") else "mngeo_unverified"),
            "source_name": "Official county website" if use_county else (mngeo_source.get("name") or "MnGeo County GIS Contacts"),
            "source_url": (check.get("official_contact_page_url") or check.get("official_county_url")) if use_county else mngeo_source.get("url"),
            "official_county_url": check.get("official_county_url"),
            "official_contact_page_url": check.get("official_contact_page_url"),
            "verified": check.get("verified"),
            "verification_note": check.get("evidence_note"),
        }
    for county, check in verified.items():
        if county in records or check.get("authority") != "county" or not check.get("contacts"):
            continue
        records[county] = {
            "contacts": check.get("contacts") or [], "authority": "county",
            "source_name": "Official county website",
            "source_url": check.get("official_contact_page_url") or check.get("official_county_url"),
            "official_county_url": check.get("official_county_url"),
            "official_contact_page_url": check.get("official_contact_page_url"),
            "verified": check.get("verified"), "verification_note": check.get("evidence_note"),
        }
    return records


def _load_county_contacts() -> dict:
    return {county: record.get("contacts", []) for county, record in _load_county_contact_records().items()}


def _county_profiles(config: dict, state: dict, research: dict) -> dict:
    return compose_county_profiles(state, research, now=dt.datetime.now(dt.timezone.utc), freshness_policy=FreshnessPolicy(
        source_stale_minutes=int(config.get('source_stale_minutes', 1560)),
        worker_stale_minutes=int(config.get('worker_stale_minutes', 1560))))


def _county_status(config: dict, county: dict, state: dict, *, profiles: dict | None = None, research: dict | None = None) -> dict:
    research = load_parcel_access() if research is None else research
    profiles = _county_profiles(config, state, research) if profiles is None else profiles
    profile = profiles[county['slug']]
    name = county["name"]
    matches = []
    for sid, src in (state.get("sources") or {}).items():
        if sid == "mn-parcel-county-catalog":
            continue
        source_slug = src.get("county_slug")
        if src.get('category') == 'Parcels' and source_slug == county["slug"]:
            matches.append(src)

    statewide_source_id, statewide_source = _mngac_source(state)
    statewide_data = (statewide_source or {}).get("mngac_completeness") or {}
    statewide_record = (statewide_data.get("counties") or {}).get(name)
    statewide_monitored = 'mngeo-open' in profile['monitoring']['paths']

    catalog = ((state.get("sources") or {}).get("mn-parcel-county-catalog") or {})
    catalog_record = (catalog.get("county_records") or {}).get(name)
    open_approved = str((catalog_record or {}).get("gac_open_approval", "")).lower() == "true"
    has_data = bool((catalog_record or {}).get("data_url"))

    monitored_sources = list(matches)
    if statewide_monitored and isinstance(statewide_source, dict):
        monitored_sources.append(statewide_source)

    if monitored_sources:
        status = (
            "error" if any(x.get("status") == "error" for x in monitored_sources)
            else "warn" if any(x.get("status") == "warn" for x in monitored_sources)
            else "ok"
        )
    elif catalog_record and open_approved and has_data and catalog.get("status") == "ok":
        status = "catalog"
    elif catalog_record:
        status = "needs-source"
    else:
        status = "not-configured"

    monitoring_paths = []
    if matches:
        monitoring_paths.append("county-direct")
    if statewide_monitored:
        monitoring_paths.append("mngeo-open")

    parcel_access = research.get(name)
    monitoring_paths = profile['monitoring']['paths']
    if profile['monitoring']['active']:
        status = profile['monitoring']['health']
    return {
        "name": name,
        "slug": county["slug"],
        "status": status,
        "sources": matches,
        "catalog": catalog_record,
        "parcel_access": parcel_access,
        "profile": profile,
        "actively_monitored": bool(monitoring_paths),
        "monitoring_paths": monitoring_paths,
        "statewide_source_id": statewide_source_id,
        "statewide_source": statewide_source if statewide_monitored else None,
        "statewide_record": statewide_record,
    }


def _monitoring_path_label(info: dict) -> str:
    paths = set(info.get("monitoring_paths") or [])
    if paths == {"county-direct", "mngeo-open"}:
        return "County-direct + MnGeo open parcels"
    if "county-direct" in paths:
        return "County-direct source"
    if "mngeo-open" in paths:
        return "MnGeo Plan Parcels Open"
    if info.get("status") == "catalog":
        return "MnGeo catalog only"
    return "Not actively checked"


def _county_monitoring_counts(config: dict, state: dict) -> dict:
    return county_profile_counts(_county_profiles(config, state, load_parcel_access()))


def _format_arcgis_date(value) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    try:
        return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return "—"


def _bar_chart(items: list[tuple[str, float]], *, title: str, suffix: str = "") -> str:
    items = [(label, value) for label, value in items if isinstance(value, (int, float))]
    if not items:
        return '<div class="muted">Not enough data yet</div>'
    peak = max(abs(v) for _, v in items) or 1
    rows = "".join(
        f'<div class="bar-row"><span>{_esc(label)}</span><div class="bar-track"><i style="width:{min(100,abs(value)/peak*100):.1f}%"></i></div><strong>{_esc(round(value,1))}{_esc(suffix)}</strong></div>'
        for label, value in items
    )
    return f'<h3>{_esc(title)}</h3><div class="bars">{rows}</div>'



def _gac_standard_selector(active: str) -> str:
    from clearparcel.datawatch.dashboard_gac import _gac_standard_selector as render
    return render(active)




def _render_gac_standard(config: dict, standard_key: str) -> str:
    from clearparcel.datawatch.dashboard_gac import _render_gac_standard as render
    return render(config, standard_key)




def render_mngac(config: dict, standard_key: str = "parcel") -> str:
    from clearparcel.datawatch.dashboard_gac import render_mngac as render
    return render(config, standard_key)




def render_counties(config: dict) -> str:
    from clearparcel.datawatch.dashboard_counties import render_counties as render
    return render(config)



def _render_county_mngac(state: dict, county: dict) -> str:
    from clearparcel.datawatch.dashboard_gac import _render_county_mngac as render
    return render(state, county)




def _county_mngac_summary(state: dict, county: dict) -> dict:
    from clearparcel.datawatch.dashboard_gac import _county_mngac_summary as build
    return build(state, county)





def _render_county_gac_summaries(state: dict, county: dict) -> str:
    from clearparcel.datawatch.dashboard_gac import _render_county_gac_summaries as render
    return render(state, county)




def render_county(config: dict, slug: str) -> str:
    from clearparcel.datawatch.dashboard_counties import render_county as render
    return render(config, slug)


def _gac_county_payload(state: dict, standard_key: str, county_name: str) -> dict | None:
    from clearparcel.datawatch.dashboard_gac import _gac_county_payload as build
    return build(state, standard_key, county_name)




def _county_snapshot(config: dict, slug: str, *, include_mngac: bool = True, state: dict | None = None,
                     profiles: dict | None = None, research: dict | None = None) -> dict | None:
    state = _dashboard_state(config) if state is None else state
    county = next((x for x in _load_counties() if x.get("slug") == slug), None)
    if not county:
        return None
    research = load_parcel_access() if research is None else research
    profiles = _county_profiles(config, state, research) if profiles is None else profiles
    info = _county_status(config, county, state, profiles=profiles, research=research)
    catalog = info.get("catalog") or {}
    mngac_data, mngac_county = _mngac_county_record(state, county["name"])
    mngac_payload = None
    gac_payload = {}
    if include_mngac:
        gac_payload = {
            key: payload for key in standard_keys()
            if (payload := _gac_county_payload(state, key, county["name"])) is not None
        }
    if include_mngac and mngac_data:
        mngac_payload = {
            "standard": mngac_data.get("standard") or {},
            "method": mngac_data.get("method"),
            "covered_counties": mngac_data.get("covered_counties"),
            "county": mngac_county,
        }
    return {
        "county": county["name"],
        "parcel_source_profile": profiles[slug],
        "status": info["status"],
        "actively_monitored": bool(info.get("actively_monitored")),
        "monitoring_paths": list(info.get("monitoring_paths") or []),
        "monitoring_path_label": _monitoring_path_label(info),
        "last_county_update": _format_arcgis_date(catalog.get("acqdate")),
        "catalog_refresh_date": _format_arcgis_date(catalog.get("rundate")),
        "public_data_approved": str(catalog.get("gac_open_approval") or "").lower() == "true",
        "parcel_data_url": _safe_url(catalog.get("data_url")) or "",
        "parcel_viewer_url": _safe_url(catalog.get("viewer_url")) or "",
        "parcel_access": {
            "county_direct_classification": (info.get("parcel_access") or {}).get("county_direct_classification"),
            "county_direct_label": access_label(info.get("parcel_access")),
            "statewide_open_coverage": (info.get("parcel_access") or {}).get("statewide_open_coverage") or {},
            "statewide_open_current": info.get("statewide_record") is not None,
            "statewide_open_label": statewide_access_label(
                info.get("parcel_access"),
                live_available=(info.get("statewide_record") is not None) if mngac_data else None,
            ),
            "research_complete": bool((info.get("parcel_access") or {}).get("research_complete")),
            "review_date": (info.get("parcel_access") or {}).get("review_date"),
            "parcel_dataset_fee": (info.get("parcel_access") or {}).get("parcel_dataset_fee"),
            "fee_product": (info.get("parcel_access") or {}).get("fee_product"),
            "evidence_note": (info.get("parcel_access") or {}).get("evidence_note"),
            "official_county_url": _safe_url((info.get("parcel_access") or {}).get("official_county_url")) or "",
            "parcel_page_url": _safe_url((info.get("parcel_access") or {}).get("parcel_page_url")) or "",
            "download_or_service_url": _safe_url((info.get("parcel_access") or {}).get("download_or_service_url")) or "",
            "viewer_url": _safe_url((info.get("parcel_access") or {}).get("viewer_url")) or "",
            "fee_policy_url": _safe_url((info.get("parcel_access") or {}).get("fee_policy_url")) or "",
            "usable_direct_machine_readable_source": bool((info.get("parcel_access") or {}).get("usable_direct_machine_readable_source")),
            "monitoring_assessment": (info.get("parcel_access") or {}).get("monitoring") or {},
        },
        "direct_sources": [
            {
                "name": x.get("name"), "status": x.get("status"),
                "feature_count": x.get("feature_count"), "checked_at": x.get("checked_at"),
                "worker": x.get("worker"), "last_success_at": x.get("last_success_at"),
                "reporting": x.get("reporting"), "stale": x.get("stale"), "worker_stale": x.get("worker_stale"),
            } for x in info.get("sources", [])
        ],
        "contacts": _load_county_contacts().get(county["name"], []),
        "contact_source": (_load_county_contact_records().get(county["name"], {}) or {}).get("authority"),
        "contact_source_url": (_load_county_contact_records().get(county["name"], {}) or {}).get("source_url"),
        "contact_verified": (_load_county_contact_records().get(county["name"], {}) or {}).get("verified"),
        "mngac": mngac_payload,
        "gac": gac_payload,
        **_snapshot_time_fields(dt.datetime.now(dt.timezone.utc).isoformat(), "snapshot_created"),
    }


def _statewide_snapshot(config: dict) -> dict:
    state = _dashboard_state(config)
    research = load_parcel_access()
    profiles = _county_profiles(config, state, research)
    counties = []
    for county in _load_counties():
        item = _county_snapshot(config, county["slug"], include_mngac=False, state=state, profiles=profiles, research=research)
        if item:
            counties.append(item)
    aggregate_sources = []
    for source_id, source in (state.get("sources") or {}).items():
        aggregate_sources.append({
            "id": source_id,
            "name": source.get("name") or source_id,
            "county": source.get("county_slug") or "",
            "status": source.get("status"),
            "feature_count": source.get("feature_count"),
            "worker": source.get("worker"),
            "reporting": source.get("reporting"),
            "stale": bool(source.get("stale")),
            "worker_stale": bool(source.get("worker_stale")),
            "last_success_at": source.get("last_success_at"),
            "checked_at": source.get("checked_at") or source.get("last_report_at"),
        })
    aggregate_sources.sort(key=lambda row: (str(row.get("county") or ""), str(row.get("name") or "")))
    return {
        "title": "Minnesota GIS Data Watchtower snapshot",
        **_snapshot_time_fields(dt.datetime.now(dt.timezone.utc).isoformat(), "snapshot_created"),
        **_snapshot_time_fields(state.get("generated_at"), "watchtower_last_checked"),
        "overall": _status_class(state.get("overall","unknown")),
        "county_count": len(counties),
        "source_count": len(aggregate_sources),
        "sources": aggregate_sources,
        "workers": state.get("workers") or {},
        "counties": counties,
        "mngac": _mngac_data(state),
        "gac": {key: data for key in standard_keys() if (data := _gac_data(state, key)) is not None},
    }


from clearparcel.datawatch.dashboard_exports import (
    _csv_safe,
    _gac_xlsx_sheets,
    _mngac_csv,
    _mngac_xlsx_sheets,
    _snapshot_csv,
    _snapshot_xlsx,
    _xlsx_col_name,
    _xlsx_sheet_xml,
)
from clearparcel.datawatch.dashboard_routes import dispatch_snapshot_exports

def _coverage_status(value: str) -> str:
    return {
        "ok": "Actively checked",
        "catalog": "MnGeo catalog only",
        "needs-source": "No active parcel monitoring",
        "not-configured": "No source information yet",
        "warn": "Needs attention",
        "error": "Check failed",
    }.get(value, value.replace("-", " ").title())


def _health_status(value: str) -> str:
    value = str(value or "unknown").strip().lower()
    return {
        "ok": "Healthy",
        "warn": "Warning",
        "error": "Error",
        "unknown": "Unknown",
    }.get(value, "Unknown")


def _status_class(value: str) -> str:
    value = str(value or "unknown").strip().lower()
    return value if value in {"ok", "warn", "error", "info", "unknown"} else "unknown"


def _friendly_status(value: str) -> str:
    return _coverage_status(value)


def render_dashboard(config: dict) -> str:
    from clearparcel.datawatch.dashboard_views import render_dashboard as render
    return render(config)


def render_source(config: dict, source_id: str) -> str:
    from clearparcel.datawatch.dashboard_views import render_source as render
    return render(config, source_id)


def _sanitize_public_state(state: dict) -> dict:
    """Return only user-facing monitoring facts safe for public/API use."""
    public = {
        "schema_version": state.get("schema_version"),
        "generated_at": state.get("generated_at"),
        "overall": _status_class(state.get("overall","unknown")),
        "counts": state.get("counts", {}),
        "sources": {},
    }
    for sid, src in (state.get("sources") or {}).items():
        summary = {
            key: src.get(key)
            for key in (
                "id", "name", "provider", "category", "status", "feature_count",
                "checked_at", "worker", "last_success_at", "last_report_at",
                "stale", "worker_stale", "health", "reporting",
            )
            if src.get(key) is not None
        }
        summary["status"] = _status_class(src.get("status","unknown"))
        summary["change_count"] = len(src.get("changes") or [])
        public["sources"][sid] = summary
    return public


def build_static_site(config: dict, output_dir: str | Path) -> dict:
    """Generate a sanitized, dependency-free static dashboard for Pages-style hosting."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    state = _dashboard_state(config)
    public = _sanitize_public_state(state)
    sources = public.get("sources", {})
    counts = public.get("counts", {})
    rows = []
    for sid, src in sorted(sources.items(), key=lambda x: str((x[1] or {}).get("name", x[0])).lower()):
        filename = "source-" + urllib.parse.quote(sid, safe="") + ".html"
        rows.append(
            f'<tr><td><a href="{_esc(filename)}"><strong>{_esc(src.get("name") or sid)}</strong></a>'
            f'<br><span class="muted">{_esc(sid)}</span></td>'
            f'<td><span class="pill {_status_class(src.get("status","unknown"))}">{_esc(_health_status(src.get("status","unknown")))}</span></td>'
            f'<td>{_esc(src.get("provider") or "—")}</td>'
            f'<td>{_esc(src.get("category") or "—")}</td>'
            f'<td>{_esc(f"{src.get("feature_count"):,}" if isinstance(src.get("feature_count"), int) else "—")}</td>'
            f'<td>{_esc(src.get("change_count", 0))}</td><td>{_esc(src.get("checked_at","—"))}</td></tr>'
        )
        detail = f'<p><a href="index.html">← All data sources</a></p><div class="grid">' \
            f'<div class="card"><div class="muted">Data source</div><h2>{_esc(src.get("name") or sid)}</h2></div>' \
            f'<div class="card"><div class="muted">Status</div><div class="metric {_status_class(src.get("status","unknown"))}">{_esc(_health_status(src.get("status","unknown")))}</div></div>' \
            f'<div class="card"><div class="muted">Record count</div><div class="metric">{_esc(f"{src.get("feature_count"):,}" if isinstance(src.get("feature_count"), int) else "—")}</div></div></div>' \
            f'<div class="card"><h2>About this data</h2><p><strong>Provided by:</strong> {_esc(src.get("provider") or "—")}<br>' \
            f'<strong>Data type:</strong> {_esc(src.get("category") or "—")}<br><strong>Last checked:</strong> {_esc(src.get("checked_at") or "—")}<br>' \
            f'<strong>Changes found this check:</strong> {_esc(src.get("change_count", 0))}</p></div>'
        (output / filename).write_text(_layout(f'Watchtower — {src.get("name") or sid}', detail, refresh_seconds=300, static=True), encoding="utf-8")

    body = f'<div class="grid"><div class="card"><div class="muted">Overall status</div><div class="metric {_status_class(public.get("overall","unknown"))}">{_esc(_health_status(public.get("overall","unknown")))}</div></div>' \
        f'<div class="card"><div class="muted">Data sources</div><div class="metric">{len(sources)}</div><span class="subtext">Total source observations currently represented in the unified Watchtower state.</span></div>' \
        f'<div class="card"><div class="muted">Working normally</div><div class="metric ok">{counts.get("ok",0)}</div></div>' \
        f'<div class="card"><div class="muted">Warnings / errors</div><div class="metric">{counts.get("warn",0)} / {counts.get("error",0)}</div></div></div>' \
        f'<div class="card"><div class="muted">Last checked</div><strong>{_esc(public.get("generated_at","No saved observation"))}</strong></div><br>' \
        '<div class="card"><h2>Data being watched</h2><table><thead><tr><th>Data source</th><th>Status</th><th>Provided by</th><th>Type</th><th>Records</th><th>Changes found</th><th>Last checked</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"
    page = _layout("GIS Data Watchtower", body, refresh_seconds=300, static=True)
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / "state.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    return {"output_dir": str(output), "source_count": len(sources), "files": len(sources) + 2}

def _valid_refresh_request(token: str, expected_token: str, sec_fetch_site: str | None) -> bool:
    sec_fetch = (sec_fetch_site or "").lower()
    return sec_fetch in ("same-origin", "same-site", "none", "") and hmac.compare_digest(token, expected_token)



def _dashboard_auth(config: dict, host: str = "127.0.0.1") -> tuple[str | None, str]:
    password = os.environ.get("CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD")
    username = os.environ.get("CLEARPARCEL_WATCHTOWER_DASHBOARD_USER", "watchtower")
    public_cfg = config.get("public_dashboard") or {}
    host_text = host.strip().lower()
    trusted_bind = host_text in ("127.0.0.1", "::1", "localhost")
    if not trusted_bind:
        try:
            addr = ipaddress.ip_address(host_text)
            trusted_bind = addr.is_loopback or (addr.is_private and not addr.is_unspecified)
        except ValueError:
            trusted_bind = False
    if (public_cfg.get("internet_exposure") or not trusted_bind) and not password:
        raise RuntimeError("Public, wildcard, or Internet dashboard exposure requires CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD")
    return password, username


def _validated_content_length(value: str | None, maximum: int = 4096) -> int:
    if value is None:
        raise ValueError("Content-Length is required")
    try:
        length = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Content-Length must be a nonnegative integer") from exc
    if length < 0:
        raise ValueError("Content-Length must be nonnegative")
    if length > maximum:
        raise OverflowError(f"request body exceeds {maximum} bytes")
    return length


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, server_address, handler_cls, *, max_connections: int = 32, request_timeout: float | None = None):
        self._request_timeout = request_timeout
        self._connection_slots = threading.BoundedSemaphore(max(1, int(max_connections)))
        super().__init__(server_address, handler_cls)

    def process_request(self, request, client_address):
        if not self._connection_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\nContent-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        deadline = None
        try:
            if self._request_timeout is not None:
                deadline = RequestDeadline(self._request_timeout)
                deadline.attach(request)
            super().process_request_thread(request, client_address)
        finally:
            if deadline is not None:
                deadline.close()
            self._connection_slots.release()


def _dashboard_execution_profile(config: dict) -> str | None:
    value = os.environ.get("WATCHTOWER_EXECUTION_PROFILE", config.get("dashboard_execution_profile"))
    if value is not None:
        value = str(value).strip().lower()
        if value not in ("cloud", "local"):
            raise ValueError("dashboard execution profile must be cloud or local")
        return value
    if any(source.get("execution_profiles") for source in config.get("sources", [])):
        raise ValueError("profiled dashboard sources require WATCHTOWER_EXECUTION_PROFILE or dashboard_execution_profile")
    return None


def serve(config: dict, host: str = "127.0.0.1", port: int = 8765) -> None:
    auth_password, auth_username = _dashboard_auth(config, host)
    execution_profile = _dashboard_execution_profile(config)
    csrf_token = secrets.token_urlsafe(32)
    config["_csrf_token"] = csrf_token
    refresh_lock = threading.Lock()
    refresh_state = {"last_started": 0.0}
    refresh_cooldown_seconds = int(config.get("dashboard_refresh_cooldown_seconds", 300))
    request_timeout_seconds = max(2, min(int(config.get("dashboard_request_timeout_seconds", 10)), 60))
    max_connections = max(1, min(int(config.get("dashboard_max_connections", 32)), 256))

    def _guarded_refresh():
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        if now - refresh_state["last_started"] < refresh_cooldown_seconds:
            return
        if not refresh_lock.acquire(blocking=False):
            return
        try:
            refresh_state["last_started"] = now
            check_sources(config, save=True, execution_profile=execution_profile)
        finally:
            refresh_lock.release()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(request_timeout_seconds)

        def _authorized(self) -> bool:
            if not auth_password:
                return True
            header = self.headers.get("Authorization") or ""
            if not header.startswith("Basic "):
                return False
            try:
                decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
                user, password = decoded.split(":", 1)
            except Exception:
                return False
            return hmac.compare_digest(user, auth_username) and hmac.compare_digest(password, auth_password)

        def _require_auth(self) -> bool:
            if self._authorized():
                return False
            raw = b"Authentication required"
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="GIS Data Watchtower"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return True

        def _send(self, status: int, content: str, content_type: str = "text/html; charset=utf-8"):
            raw = content.encode("utf-8")
            self.send_response(status); self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(raw)

        def _send_bytes(self, status: int, raw: bytes, content_type: str, filename: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self._require_auth():
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                return self._send(200, render_dashboard(config))
            if dispatch_snapshot_exports(
                self,
                parsed.path,
                parsed.query,
                statewide_snapshot=lambda: _statewide_snapshot(config),
                county_snapshot=lambda slug: _county_snapshot(config, slug),
            ):
                return
            if parsed.path in ("/county-profiles.csv", "/parcel-sources.csv"):
                snap = _statewide_snapshot(config)
                profiles = {row["parcel_source_profile"]["county"]["slug"]: row["parcel_source_profile"] for row in snap["counties"]}
                export = county_profiles_csv if parsed.path == "/county-profiles.csv" else parcel_sources_csv
                return self._send(200, export(profiles), "text/csv; charset=utf-8")
            if parsed.path in ("/mngac", "/mngac.json", "/mngac.csv"):
                try:
                    standard_key = normalize_standard_key(
                        urllib.parse.parse_qs(parsed.query).get("standard", ["parcel"])[0]
                    )
                except ValueError:
                    return self._send(400, "Unsupported GAC standard", "text/plain; charset=utf-8")
                if parsed.path == "/mngac":
                    return self._send(200, render_mngac(config, standard_key))
                data = _gac_data(_dashboard_state(config), standard_key)
                if parsed.path == "/mngac.json":
                    return self._send(
                        200 if data else 404,
                        json.dumps(data or {"error": "GAC completeness data unavailable"}, indent=2),
                        "application/json; charset=utf-8",
                    )
                return self._send(
                    200 if data else 404,
                    _mngac_csv(data) if data else "GAC completeness data unavailable",
                    "text/csv; charset=utf-8",
                )
            if parsed.path == "/counties":
                return self._send(200, render_counties(config))
            if parsed.path == "/county":
                slug = urllib.parse.parse_qs(parsed.query).get("slug", [""])[0]
                return self._send(200, render_county(config, slug))
            if parsed.path == "/source":
                sid = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
                return self._send(200, render_source(config, sid))
            if parsed.path == "/api/state":
                public_state = _sanitize_public_state(_dashboard_state(config))
                return self._send(200, json.dumps(public_state, indent=2), "application/json; charset=utf-8")
            self._send(404, "Not found", "text/plain; charset=utf-8")

        def do_POST(self):
            if self._require_auth():
                return
            if urllib.parse.urlparse(self.path).path != "/refresh":
                return self._send(404, "Not found", "text/plain; charset=utf-8")
            if self.headers.get("Transfer-Encoding"):
                return self._send(400, "Transfer-Encoding is not supported.", "text/plain; charset=utf-8")
            try:
                length = _validated_content_length(self.headers.get("Content-Length"), 4096)
            except OverflowError:
                return self._send(413, "Refresh request body is too large.", "text/plain; charset=utf-8")
            except ValueError:
                return self._send(400, "Invalid Content-Length.", "text/plain; charset=utf-8")
            form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
            token = (form.get("csrf_token") or [""])[0]
            if not _valid_refresh_request(token, csrf_token, self.headers.get("Sec-Fetch-Site")):
                return self._send(403, "Refresh request rejected.", "text/plain; charset=utf-8")
            threading.Thread(target=_guarded_refresh, daemon=True).start()
            self.send_response(303); self.send_header("Location", "/"); self.end_headers()

        def log_message(self, format, *args):
            return

    server = _BoundedThreadingHTTPServer((host, port), Handler, max_connections=max_connections, request_timeout=request_timeout_seconds)
    print(f"GIS Data Watchtower dashboard: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
