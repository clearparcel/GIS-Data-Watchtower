from __future__ import annotations

import base64
import csv
import datetime as dt
import hmac
import html
import io
import ipaddress
import json
import os
import secrets
import threading
import urllib.parse
import zipfile
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from clearparcel.datawatch.watch import check_sources, load_history, load_state
from clearparcel.datawatch.aggregate import with_freshness
from clearparcel.datawatch.parcel_access import access_label, load_parcel_access, statewide_access_label
from clearparcel.datawatch.county_profile_panel import render_county_profile_panel, render_county_profile_body, percentage_legend, percentage_color_js, profile_time, PERCENT_COLORS, NO_DATA_COLOR
from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles, county_profile_counts

COUNTIES_FILE = Path(__file__).with_name("minnesota_counties.json")
COUNTY_CONTACTS_FILE = Path(__file__).with_name("minnesota_county_contacts.json")
COUNTY_CONTACT_VERIFICATION_FILE = Path(__file__).with_name("minnesota_county_contact_verification.json")
MNGAC_FIELDS_FILE = Path(__file__).with_name("mngac_parcel_fields.json")
COUNTY_BOUNDARIES_FILE = Path(__file__).with_name("minnesota_county_boundaries.json")


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


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


_PUBLIC_V2_CSS = """
:root{color-scheme:dark;--bg:#080b12;--panel:#111722;--panel2:#151d2b;--panel3:#0d131e;--line:#263247;--line2:#34445e;--text:#eef4ff;--muted:#8e9bb0;--blue:#6ea8fe;--blue2:#4b8ee8;--green:#5bd49a;--amber:#f5c66a;--red:#ff7b86;--shadow:0 12px 30px #0004;--radius:14px}
*{box-sizing:border-box}
html{scroll-behavior:smooth;background:var(--bg)}
body{margin:0;background:radial-gradient(circle at 30% -10%,#152039 0,transparent 38%),var(--bg);color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible,.mngac-county:focus{outline:2px solid var(--blue);outline-offset:2px}
.public-header{height:88px;padding:18px max(22px,calc((100vw - 1400px)/2));display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:#090d15cc;position:sticky;top:0;backdrop-filter:blur(16px);z-index:30}
.brand-eyebrow{font-size:10px;letter-spacing:.18em;color:var(--blue);font-weight:800}
.public-header h1{font-size:24px;margin:3px 0 0;letter-spacing:-.25px}
.live-state{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--green);font-weight:800;white-space:nowrap}.live-dot{width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 14px currentColor}
.public-main{max-width:1400px;margin:auto;padding:0 22px 64px}
.public-tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:0 0 24px;position:sticky;top:88px;background:#080b12ed;backdrop-filter:blur(14px);z-index:20}
.public-tabs a{color:var(--muted);padding:14px 13px 11px;border-bottom:2px solid transparent;font-weight:700;white-space:nowrap}.public-tabs a:hover{text-decoration:none;color:var(--text)}.public-tabs a.active{color:var(--text);border-bottom-color:var(--blue)}
.public-tools{margin-left:auto;display:flex;align-items:center}.public-export{position:relative}.public-export summary{list-style:none;cursor:pointer;border:1px solid var(--line);background:var(--panel);color:#c4d1e5;border-radius:8px;padding:8px 10px;font-weight:700}.public-export summary::-webkit-details-marker{display:none}.public-export[open] .export-pop{display:grid}
.export-pop{display:none;position:absolute;right:0;top:42px;min-width:160px;padding:6px;background:#0b1019;border:1px solid var(--line);border-radius:10px;box-shadow:0 16px 40px #0008;z-index:60}.export-pop a{padding:9px 10px;border-radius:7px}.export-pop a:hover{background:var(--panel2);text-decoration:none}
.page-kicker{padding:25px 0 16px}.page-kicker .eyebrow{font-size:10px;letter-spacing:.14em;color:var(--blue);font-weight:800;text-transform:uppercase}.page-kicker h2{font-size:27px;margin:4px 0 3px;letter-spacing:-.35px}.page-kicker p{margin:0;color:var(--muted);max-width:840px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:18px}.primary-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.worker-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.card{background:linear-gradient(145deg,var(--panel),#0d121c);border:1px solid var(--line);border-radius:var(--radius);padding:17px;box-shadow:var(--shadow);min-width:0}.card h2,.card h3{margin-top:0}.card h2{font-size:18px}.card h3{font-size:15px}
.metric{font-size:27px;font-weight:800;line-height:1.05;letter-spacing:-.5px;margin-top:4px}.muted{color:var(--muted)}.subtext{display:block;color:var(--muted);font-size:11px;line-height:1.45;margin-top:6px}.ok{color:var(--green)}.warn{color:var(--amber)}.error{color:var(--red)}.catalog{color:var(--blue)}.not-configured,.needs-source{color:var(--muted)}
.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:currentColor;margin-right:7px}.pill{display:inline-flex;align-items:center;height:24px;padding:4px 9px;border:1px solid var(--line);border-radius:999px;font-size:10px;text-transform:uppercase;font-weight:800}.pill.ok{border-color:#2d7155}.pill.warn,.pill.catalog{border-color:#705b2d}.pill.error{border-color:#773944}
.section-head{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:28px 2px 12px}.section-head h2{margin:0;font-size:18px}.section-head p,.section-head span{margin:3px 0 0;color:var(--muted);font-size:11px}.section-head>a{font-size:11px;font-weight:700}
.activity-strip{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}.worker-card{display:grid;grid-template-columns:1fr auto;gap:10px 18px}.worker-card h3{margin:0}.worker-meta{display:flex;gap:14px}.worker-meta div{min-width:90px}.worker-meta .muted,.worker-meta span{display:block;font-size:9px}.worker-meta strong{display:block;margin-top:3px;font-size:13px;overflow-wrap:anywhere}
.summary-v2{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:30px}.summary-v2 .card{padding:16px 18px}.summary-v2 .metric{font-size:24px}.summary-v2 .muted{font-size:11px}
.hero-panel{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(300px,.75fr);gap:14px;margin-bottom:26px}.hero-copy{padding:22px}.hero-copy h2{font-size:24px;margin:0 0 8px}.hero-copy p{color:#c4cede;max-width:720px;margin:0 0 18px}.hero-actions{display:flex;gap:8px;flex-wrap:wrap}.hero-actions a{display:inline-flex;padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:#121a27;color:#c4d1e5;font-weight:700}.hero-actions a.primary{border-color:#315078;color:#dceaff;background:#101827}
.hero-stat{display:grid;grid-template-columns:1fr 1fr;gap:8px}.hero-stat>div{background:var(--panel2);border:1px solid #ffffff0d;border-radius:10px;padding:13px}.hero-stat small{display:block;color:var(--muted);font-size:9px;letter-spacing:.07em;text-transform:uppercase}.hero-stat b{display:block;font-size:19px;margin-top:4px}
table{width:100%;border-collapse:collapse;background:transparent}th,td{padding:11px 12px;border-bottom:1px solid #1b2535;text-align:left;vertical-align:top}th{font-size:9px;text-transform:uppercase;color:var(--muted);letter-spacing:.08em;background:#0d131e}td{color:#c4cede}td strong{color:var(--text)}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.filters input,.filters select,.mngac-controls select,.mngac-controls input{background:#0d131e;border:1px solid var(--line);color:var(--text);border-radius:9px;padding:9px 11px;font:inherit;min-height:38px}.filters input{flex:1;min-width:200px}.filters input::placeholder{color:#68768b}
.bar-row{min-width:0;display:grid;grid-template-columns:minmax(120px,1.35fr) minmax(100px,3fr) 64px;gap:9px;align-items:center;margin:9px 0;font-size:11px}.bar-row>span{min-width:0;overflow-wrap:anywhere}.bar-track{height:7px;background:#202a3b;border-radius:999px;overflow:hidden}.bar-track i{display:block;height:100%;background:var(--blue);border-radius:999px}.chart-range{font-size:10px;color:var(--muted)}
.definition-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.definition-group{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:14px}.definition-list{display:grid;grid-template-columns:minmax(120px,.8fr) 1.4fr;gap:7px 12px;margin:0}.definition-list dt{font-weight:700;color:var(--muted)}.definition-list dd{margin:0;overflow-wrap:anywhere;color:#c4cede}
.mngac-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:14px}.mngac-controls label{display:grid;gap:4px;font-size:10px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.mngac-layout{display:grid;grid-template-columns:minmax(360px,1.35fr) minmax(260px,.65fr);gap:14px;align-items:start}.mngac-map-panel{background:#0b111b;border:1px solid var(--line);border-radius:11px;padding:10px;min-width:0}.mngac-map{display:block;width:100%;height:auto;max-height:690px}.mngac-county{fill:#1b2636;stroke:#51647e;stroke-width:1.1;vector-effect:non-scaling-stroke;cursor:pointer;transition:fill .12s ease,stroke .12s ease,stroke-width .12s ease}.mngac-county:hover,.mngac-county:focus{stroke:#d7e8ff;stroke-width:2.2;outline:none}.mngac-county.selected{stroke:#fff;stroke-width:3}.mngac-detail{min-height:220px}.mngac-detail h3{margin-bottom:4px}.mngac-kpi{font-size:25px;font-weight:800}.mngac-legend{display:flex;flex-wrap:wrap;gap:7px 12px;margin:10px 0 0;font-size:10px;color:var(--muted)}.mngac-legend span{display:inline-flex;align-items:center;gap:5px}.mngac-swatch{width:13px;height:13px;border-radius:3px;border:1px solid #ffffff33;display:inline-block}.mngac-note{border-left:3px solid var(--blue);padding:10px 12px;background:#0e1622;border-radius:0 8px 8px 0;color:#aeb9ca;margin:12px 0}.mngac-table-wrap{overflow-x:auto}.mngac-field-select{background:none;color:var(--blue);padding:0;border:0;text-align:left;font:inherit;cursor:pointer}.mngac-field-select:hover{text-decoration:underline}
code{font-size:11px;color:#b9c6d8}.technical summary,.diagnostics summary{cursor:pointer;font-weight:700;color:var(--blue);padding:4px 0}.diagnostics{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow);margin:18px 0}.flat-note{padding:20px 4px;color:var(--muted);font-size:12px}
.public-footnote{margin:30px 2px 0;padding-top:16px;border-top:1px solid var(--line);color:#66778f;font-size:10px;display:flex;justify-content:space-between;gap:20px}.public-footnote strong{color:#8da4c4}
@media(max-width:1050px){.summary-v2{grid-template-columns:repeat(3,minmax(0,1fr))}.primary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.hero-panel{grid-template-columns:1fr}.mngac-layout{grid-template-columns:1fr}.definition-grid{grid-template-columns:1fr}}
@media(max-width:760px){.public-header{height:74px;padding:13px 14px}.public-header h1{font-size:20px}.brand-eyebrow{font-size:8px}.live-state span:last-child{display:none}.public-main{padding:0 12px 76px}.public-tabs{top:74px;overflow-x:auto;margin:0 -12px 18px;padding:0 12px}.public-tabs a{padding:12px 10px 10px}.public-tools{margin-left:4px}.summary-v2{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.grid,.primary-grid,.worker-grid,.activity-strip{grid-template-columns:1fr;gap:9px}.card{padding:14px}.hero-copy{padding:16px}.hero-copy h2{font-size:21px}.hero-stat{grid-template-columns:1fr 1fr}.section-head{margin-top:22px}.section-head span{display:none}.filters{display:grid;grid-template-columns:1fr}.filters input,.filters select{width:100%;min-width:0}#counties thead,#datasets thead,.contacts-table thead,.history-table thead,#mngac-fields thead,#county-mngac-fields thead{display:none}#counties,#counties tbody,#counties tr,#counties td,#datasets,#datasets tbody,#datasets tr,#datasets td,.contacts-table,.contacts-table tbody,.contacts-table tr,.contacts-table td,.history-table,.history-table tbody,.history-table tr,.history-table td,#mngac-fields,#mngac-fields tbody,#mngac-fields tr,#mngac-fields td,#county-mngac-fields,#county-mngac-fields tbody,#county-mngac-fields tr,#county-mngac-fields td{display:block;width:100%}#counties tr,#datasets tr,.contacts-table tr,.history-table tr,#mngac-fields tr,#county-mngac-fields tr{padding:10px 0;border-bottom:1px solid #1b2535}#counties td,#datasets td,.contacts-table td,.history-table td,#mngac-fields td,#county-mngac-fields td{border:0;padding:4px 2px;white-space:normal;overflow-wrap:anywhere}.worker-card{grid-template-columns:1fr}.worker-meta{display:grid;grid-template-columns:1fr 1fr}.definition-list{grid-template-columns:1fr;gap:2px}.definition-list dd{margin-bottom:8px}.mngac-controls label,.mngac-controls select{width:100%}.public-footnote{flex-direction:column;gap:4px}}
@media(max-width:430px){.summary-v2{grid-template-columns:1fr 1fr}.summary-v2 .card{padding:12px}.summary-v2 .metric{font-size:21px}.hero-stat{grid-template-columns:1fr 1fr}.public-export summary{padding:7px 8px}.page-kicker{padding-top:18px}.page-kicker h2{font-size:23px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
"""

def _refresh_script(seconds: int) -> str:
    """Use a cancellable timer so reading a county dialog prevents page reload."""
    if not seconds:
        return ""
    return """<script>
(function(){let timer=null;const delay=""" + str(int(seconds)*1000) + """;
function pause(){clearTimeout(timer);timer=null}
function resume(){pause();timer=setTimeout(()=>{if(document.getElementById('county-profile-dialog')?.open){resume();return}location.reload()},delay)}
window.watchtowerRefresh={pause,resume};resume();})();
</script>"""


def _public_layout_v2(title: str, body: str, *, refresh_seconds: int = 30) -> str:
    refresh_meta = _refresh_script(refresh_seconds)
    lower = title.lower()
    active = "mngac" if "gac" in lower else "sources" if "source" in lower else "counties" if "county" in lower or "counties" in lower else "overview"
    tabs = [
        ("overview", "/", "Overview"),
        ("counties", "/counties", "Minnesota Counties"),
        ("mngac", "/mngac", "MN GAC"),
        ("sources", "/#datasets", "Data Sources"),
    ]
    nav = "".join(
        f'<a href="{href}" class="{"active" if key == active else ""}">{label}</a>'
        for key, href, label in tabs
    )
    page_name = (
        title.replace(" — GIS Data Watchtower", "")
        .replace(" — Watchtower", "")
        .replace("GIS Data Watchtower", "Overview")
    )
    subtitle = {
        "overview": "Availability, freshness, and structure of Minnesota public GIS data.",
        "counties": "County profiles, parcel availability, monitoring coverage, and GIS contact references.",
        "mngac": "Field population across the Minnesota GAC parcel-transfer standard and all 87 counties.",
        "sources": "Public source health and high-level structural observations.",
    }.get(active, "Minnesota public GIS data, summarized for practical exploration.")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{refresh_meta}<title>{_esc(title)}</title><style>{_PUBLIC_V2_CSS}</style></head><body>
<header class="public-header">
  <div><div class="brand-eyebrow">CLEARPARCEL GIS DATA WATCHTOWER</div><h1>Minnesota GIS Data Watchtower</h1></div>
  <div class="live-state"><span class="live-dot"></span><span>PUBLIC · LIVE</span></div>
</header>
<main class="public-main">
  <nav class="public-tabs" aria-label="Watchtower views">{nav}
    <div class="public-tools"><details class="public-export"><summary>Export</summary><div class="export-pop"><a href="/snapshot.xlsx">Excel (.xlsx)</a><a href="/snapshot.csv">CSV</a><a href="/snapshot.json">JSON</a></div></details></div>
  </nav>
  <div class="page-kicker"><div class="eyebrow">PUBLIC DATA INTELLIGENCE</div><h2>{_esc(page_name)}</h2><p>{_esc(subtitle)}</p></div>
  {body}
  <footer class="public-footnote"><span><strong>ClearParcel</strong> · Public read-only view</span><span>Monitoring results are informational and source-dependent.</span></footer>
</main></body></html>"""

def _layout(title: str, body: str, *, refresh_seconds: int = 30, static: bool = False, csrf_token: str = "") -> str:
    if static:
        return _public_layout_v2(title, body, refresh_seconds=refresh_seconds)
    auto_refresh = int(refresh_seconds or 0) > 0
    refresh_meta = _refresh_script(refresh_seconds)
    refresh_label = f"Dashboard view refreshes every {int(refresh_seconds)}s" if auto_refresh else "Interactive view · reload for latest saved data"
    refresh_form = "" if static else (
        '<form method="post" action="/refresh" class="refresh-form">'
        f'<input type="hidden" name="csrf_token" value="{_esc(csrf_token)}">'
        '<button>Check now</button></form>'
    )
    side_context = "Public read-only view" if static else "Private dashboard"
    def icon(kind: str) -> str:
        paths = {
            "overview": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
            "counties": '<path d="M4 5h16v14H4z"/><path d="M8 5v14M16 5v14M4 10h16M4 15h16"/>',
            "mngac": '<path d="M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2z"/><path d="M9 4v14M15 6v14"/>',
            "sources": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
            "changes": '<path d="M4 16l5-5 4 4 7-8"/><path d="M15 7h5v5"/>',
            "alerts": '<path d="M12 3l9 17H3L12 3z"/><path d="M12 9v5M12 17h.01"/>',
            "export": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>',
            "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
        }
        return f'<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">{paths.get(kind, paths["overview"])}</svg>'
    page_title = title.replace(" — GIS Data Watchtower", "").replace("GIS Data Watchtower", "Overview")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{refresh_meta}
<title>{_esc(title)}</title>
<style>
:root{{--navy:#10263b;--navy-2:#17324d;--green:#2d6a4f;--bg:#edf2f6;--card:#fff;--text:#17212b;--muted:#64727e;--accent:#0b6fa4;--soft:#f6f8fa;--line:#d9e1e7;--warn:#8a4600;--err:#a3342f;--shadow:0 3px 14px rgb(23 50 77 / 9%);--radius:13px}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);max-width:100%}}
a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}} a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible{{outline:3px solid #5bb6e8;outline-offset:2px}}
button{{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:9px 13px;font-weight:650;cursor:pointer}}
header{{height:64px;background:var(--navy);color:#fff;padding:0 24px;display:flex;align-items:center;justify-content:space-between;border-bottom:2px solid var(--accent);position:sticky;top:0;z-index:30}}
header h1{{margin:0;font-size:20px;letter-spacing:-.2px}}
.actions{{display:flex;gap:12px;align-items:center;font-size:12px}}
.app-shell{{display:flex;min-height:calc(100vh - 64px)}}
.sidebar{{width:216px;flex:0 0 216px;background:var(--navy);color:#b9d1e2;padding:18px 12px;position:sticky;top:64px;height:calc(100vh - 64px)}}
.side-brand{{padding:3px 10px 18px;border-bottom:1px solid #ffffff18}}
.side-brand strong{{display:block;color:#fff;font-size:16px}} .side-brand small{{color:#7f9bb0}}
.sidebar nav{{margin-top:15px}}
.sidebar nav a{{display:flex;align-items:center;gap:10px;color:#b8cbd9;padding:10px 11px;border-radius:8px;margin:3px 0;font-weight:550}}
.sidebar nav a:hover{{background:#ffffff0d;color:#fff;text-decoration:none}}
.nav-icon{{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}}
.side-note{{position:absolute;bottom:18px;left:22px;color:#6f8da4;font-size:11px}}
.content-shell{{flex:1;min-width:0;max-width:100%}}
.pagebar{{width:100%;min-width:0;min-height:52px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:8px 24px;position:sticky;top:64px;z-index:20}}
.pagebar-title{{font-size:15px;font-weight:700;color:var(--navy-2)}}
.page-actions{{display:flex;align-items:center;gap:10px;min-width:0;flex:none}}
.export-menu{{position:relative}} .export-menu summary{{list-style:none;cursor:pointer;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--soft);font-weight:650;color:var(--navy-2)}}
.export-menu summary::-webkit-details-marker{{display:none}}
.export-menu[open] .export-pop{{display:grid}}
.export-pop{{display:none;position:absolute;right:0;top:38px;min-width:150px;padding:6px;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);z-index:40}}
.export-pop a{{padding:8px 9px;border-radius:6px}} .export-pop a:hover{{background:var(--soft);text-decoration:none}}
main{{max-width:1280px;margin:22px auto;padding:0 20px 40px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-bottom:18px}}
.primary-grid{{grid-template-columns:repeat(4,minmax(0,1fr))}}
.worker-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:16px;box-shadow:var(--shadow);min-width:0}}
.card h2,.card h3{{margin-top:0}}
.metric{{font-size:28px;font-weight:750;line-height:1.05;letter-spacing:-.4px}}
.muted{{color:var(--muted)}} .subtext{{display:block;color:var(--muted);font-size:12.5px;line-height:1.4;margin-top:6px}}
.ok{{color:var(--green)}} .warn{{color:var(--warn)}} .error{{color:var(--err)}}
.status-dot{{display:inline-block;width:9px;height:9px;border-radius:50%;background:currentColor;margin-right:6px}}
.section-head{{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:26px 0 10px}}
.section-head h2{{margin:0;font-size:19px}} .section-head p{{margin:3px 0 0;color:var(--muted);font-size:12.5px}}
.worker-card{{display:grid;grid-template-columns:1fr auto;gap:10px 20px;align-items:start}}
.worker-card h3{{margin:0;font-size:16px}} .worker-meta{{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px}}
.worker-meta div{{min-width:0;flex:1 1 110px}} .worker-meta strong{{display:block;font-size:17px}}
.activity-strip{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px}}
table{{width:100%;border-collapse:collapse;background:#fff}}
th,td{{padding:11px 12px;border-bottom:1px solid #e6eaee;text-align:left;vertical-align:top}}
th{{background:#f8fafb;font-size:11px;text-transform:uppercase;color:var(--muted);letter-spacing:.2px}}
.pill{{font-weight:750;text-transform:uppercase;font-size:11px}}
code{{font-size:12px;overflow-wrap:anywhere}}
.filters{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px}}
.filters input,.filters select{{padding:9px 10px;border:1px solid #ccd4db;border-radius:8px;background:#fff;min-height:38px}}
.spark{{width:100%;height:78px;color:var(--accent);display:block}}
.bar-row{{min-width:0;display:grid;grid-template-columns:minmax(120px,1.35fr) minmax(100px,3fr) 64px;gap:9px;align-items:center;margin:9px 0;font-size:12px}}
.bar-row > span{{min-width:0;overflow-wrap:anywhere}} .bar-track{{height:9px;background:#e5ebf0;border-radius:999px;overflow:hidden}} .bar-track i{{display:block;height:100%;background:var(--accent);border-radius:999px}}
.not-configured,.needs-source{{color:var(--muted)}} .catalog{{color:var(--accent)}}
.chart-range{{font-size:11px;color:var(--muted);margin-top:2px}}
.delta-up{{color:var(--green)}} .delta-down{{color:var(--warn)}}
.technical summary,.diagnostics summary{{cursor:pointer;font-weight:700;color:var(--accent);padding:4px 0}}
.technical-body{{padding-top:10px}}
.diagnostics{{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow);margin:18px 0}}
.diagnostics > summary{{font-size:15px;color:var(--navy-2)}}
.definition-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}
.definition-group{{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:14px}}
.definition-group h3{{font-size:14px;margin:0 0 10px}}
.definition-list{{display:grid;grid-template-columns:minmax(120px,.8fr) 1.4fr;gap:6px 12px;margin:0}}
.definition-list dt{{font-weight:700;color:var(--muted)}} .definition-list dd{{margin:0;overflow-wrap:anywhere}}
.mobile-nav{{display:none}}
.history-table{{width:100%}}
.flat-note{{padding:20px 4px;color:var(--muted);font-size:13px}}
.mngac-controls{{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:14px}}
.mngac-controls label{{display:grid;gap:4px;font-size:12px;font-weight:700;color:var(--muted)}}
.mngac-controls select,.mngac-controls input{{min-height:40px;padding:8px 10px;border:1px solid #ccd4db;border-radius:8px;background:#fff;font:inherit;color:var(--text)}}
.mngac-layout{{display:grid;grid-template-columns:minmax(360px,1.35fr) minmax(260px,.65fr);gap:16px;align-items:start}}
.mngac-map-panel{{background:var(--soft);border:1px solid var(--line);border-radius:11px;padding:10px;min-width:0}}
.mngac-map{{display:block;width:100%;height:auto;max-height:690px}}
.mngac-county{{fill:#dfe5ea;stroke:#fff;stroke-width:1.2;vector-effect:non-scaling-stroke;cursor:pointer;transition:fill .12s ease,stroke .12s ease,stroke-width .12s ease}}
.mngac-county:hover,.mngac-county:focus{{stroke:#10263b;stroke-width:2.2;outline:none}}
.mngac-county.selected{{stroke:#10263b;stroke-width:3}}
.mngac-detail{{min-height:220px}}
.mngac-detail h3{{margin-bottom:4px}}
.mngac-kpi{{font-size:25px;font-weight:760;letter-spacing:-.3px}}
.mngac-legend{{display:flex;flex-wrap:wrap;gap:7px 12px;margin:10px 0 0;font-size:11px;color:var(--muted)}}
.mngac-legend span{{display:inline-flex;align-items:center;gap:5px}}
.mngac-swatch{{width:13px;height:13px;border-radius:3px;border:1px solid #0002;display:inline-block}}
.mngac-note{{border-left:3px solid var(--accent);padding:10px 12px;background:var(--soft);border-radius:0 8px 8px 0;color:var(--muted);margin:12px 0}}
.mngac-table-wrap{{overflow-x:auto}}
#mngac-fields code{{white-space:nowrap}} .mngac-field-select{{background:none;color:var(--accent);padding:0;border:0;text-align:left;font:inherit;cursor:pointer}} .mngac-field-select:hover{{text-decoration:underline}}
@media(max-width:960px){{
  .primary-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
  .definition-grid{{grid-template-columns:1fr}}
  .mngac-layout{{grid-template-columns:1fr}}
}}
@media(max-width:700px){{
  body{{padding-bottom:68px}}
  header{{height:58px;padding:0 14px;position:sticky;top:0;flex-direction:row}}
  header h1{{font-size:18px}}
  .actions{{font-size:11px;gap:7px}} .actions > span{{display:none}} .refresh-form button{{padding:7px 9px;font-size:11px}}
  .app-shell{{display:block;min-height:auto}}
  .sidebar{{display:none}}
  .pagebar{{top:58px;min-height:46px;padding:7px 12px}}
  .pagebar-title{{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;max-width:calc(100vw - 104px)}}
  .export-menu summary{{padding:6px 8px;font-size:12px}}
  main{{margin:12px auto;padding:0 10px 24px;max-width:100%}}
  .grid,.primary-grid,.worker-grid,.activity-strip{{grid-template-columns:1fr;gap:9px}}
  .card{{padding:13px;border-radius:11px;overflow:visible}}
  .metric{{font-size:24px}}
  .subtext{{font-size:13px}}
  .section-head{{margin:20px 2px 9px;align-items:start}}
  .section-head h2{{font-size:18px}}
  .worker-card{{grid-template-columns:minmax(0,1fr)}} .worker-meta{{gap:10px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}} .worker-meta div:last-child{{grid-column:1/-1}}
  .bar-row{{grid-template-columns:minmax(105px,1.3fr) minmax(80px,2fr) 46px;gap:6px;font-size:11.5px}}
  .spark{{height:82px}}
  .filters{{display:grid;grid-template-columns:1fr;gap:8px}} .filters input,.filters select{{width:100%;min-width:0}}
  #counties thead,#datasets thead,.history-table thead,.contacts-table thead{{display:none}}
  #counties,#counties tbody,#counties tr,#counties td,#datasets,#datasets tbody,#datasets tr,#datasets td,.history-table,.history-table tbody,.history-table tr,.history-table td,.contacts-table,.contacts-table tbody,.contacts-table tr,.contacts-table td{{display:block;width:100%}}
  #counties tr,#datasets tr,.history-table tr,.contacts-table tr{{padding:11px 0;border-bottom:1px solid #e6eaee}}
  #counties td,#datasets td,.history-table td,.contacts-table td{{border:0;padding:4px 2px;white-space:normal;overflow-wrap:anywhere}}
  #counties td:nth-child(2)::before{{content:"Monitoring coverage: ";font-weight:700;color:var(--muted)}}
  #counties td:nth-child(3)::before{{content:"County-direct access: ";font-weight:700;color:var(--muted)}}
  #counties td:nth-child(4)::before{{content:"Statewide open access: ";font-weight:700;color:var(--muted)}}
  #counties td:nth-child(5)::before{{content:"County-direct sources: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(2)::before{{content:"Provider / type: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(3)::before{{content:"Status: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(4)::before{{content:"Records / change: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(5)::before{{content:"Days since change: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(6)::before{{content:"Reliability: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(7)::before{{content:"Response: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(8)::before{{content:"Last success: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(1)::before{{content:"Checked: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(2)::before{{content:"Status: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(3)::before{{content:"Records: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(4)::before{{content:"Changes: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(5)::before{{content:"Response: ";font-weight:700;color:var(--muted)}}
  .contacts-table td:nth-child(2)::before{{content:"Title: ";font-weight:700;color:var(--muted)}}
  .contacts-table td:nth-child(3)::before{{content:"Department: ";font-weight:700;color:var(--muted)}}
  .contacts-table td:nth-child(4)::before{{content:"Phone: ";font-weight:700;color:var(--muted)}}
  .contacts-table td:nth-child(5)::before{{content:"Email: ";font-weight:700;color:var(--muted)}}
  #mngac-fields thead,#county-mngac-fields thead{{display:none}}
  #mngac-fields,#mngac-fields tbody,#mngac-fields tr,#mngac-fields td,#county-mngac-fields,#county-mngac-fields tbody,#county-mngac-fields tr,#county-mngac-fields td{{display:block;width:100%}}
  #mngac-fields tr,#county-mngac-fields tr{{padding:11px 0;border-bottom:1px solid #e6eaee}}
  #mngac-fields td,#county-mngac-fields td{{border:0;padding:4px 2px;white-space:normal;overflow-wrap:anywhere}}
  #mngac-fields td:nth-child(2)::before,#county-mngac-fields td:nth-child(2)::before{{content:"Section: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(3)::before,#county-mngac-fields td:nth-child(3)::before{{content:"Inclusion: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(4)::before{{content:"Counties with values: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(5)::before{{content:"Populated records: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(6)::before{{content:"Statewide population: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(7)::before{{content:"County median: ";font-weight:700;color:var(--muted)}}
  #county-mngac-fields td:nth-child(4)::before{{content:"Populated: ";font-weight:700;color:var(--muted)}}
  #county-mngac-fields td:nth-child(5)::before{{content:"Records: ";font-weight:700;color:var(--muted)}}
  #county-mngac-fields td:nth-child(6)::before{{content:"Population: ";font-weight:700;color:var(--muted)}}
  .mngac-controls label,.mngac-controls select{{width:100%}}
  .mngac-map-panel{{padding:6px}}
  .definition-list{{grid-template-columns:1fr;gap:2px}} .definition-list dd{{margin-bottom:8px}}
  .mobile-nav{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));width:100%;position:fixed;bottom:0;left:0;right:0;height:62px;background:var(--navy);border-top:1px solid #ffffff18;z-index:50;padding-bottom:env(safe-area-inset-bottom)}}
  .mobile-nav a{{color:#b9d1e2;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;font-size:10px;font-weight:600}}
  .mobile-nav a:hover{{text-decoration:none;color:#fff}} .mobile-nav .nav-icon{{width:18px;height:18px}}
}}
@media(max-width:480px){{
  .primary-grid{{grid-template-columns:1fr}}
  .bar-row{{grid-template-columns:100px minmax(60px,1fr) 40px}}
}}
</style></head><body>
<header><h1>GIS Data Watchtower</h1><div class="actions"><span>{_esc(refresh_label)}</span>{refresh_form}</div></header>
<div class="app-shell">
<aside class="sidebar"><div class="side-brand"><strong>ClearParcel</strong><small>GIS Data Watchtower</small></div><nav>
<a href="/">{icon("overview")}<span>Overview</span></a>
<a href="/counties">{icon("counties")}<span>Minnesota Counties</span></a>
<a href="/mngac">{icon("mngac")}<span>MN GAC Completeness</span></a>
<a href="/#datasets">{icon("sources")}<span>Data Sources</span></a>
<a href="/#changes">{icon("changes")}<span>Recent Changes</span></a>
<a href="/#alerts">{icon("alerts")}<span>Alerts</span></a>
<a href="/snapshot.xlsx">{icon("export")}<span>Export</span></a>
</nav><div class="side-note">{side_context}<br><small>Central Time primary</small></div></aside>
<section class="content-shell">
<div class="pagebar"><div class="pagebar-title">{_esc(page_title)}</div><div class="page-actions"><details class="export-menu"><summary>Export</summary><div class="export-pop"><a href="/snapshot.xlsx">Excel (.xlsx)</a><a href="/snapshot.csv">CSV</a><a href="/snapshot.json">JSON</a></div></details></div></div>
<main>{body}</main>
</section></div>
<nav class="mobile-nav" aria-label="Mobile navigation">
<a href="/">{icon("overview")}<span>Overview</span></a><a href="/counties">{icon("counties")}<span>Counties</span></a><a href="/mngac">{icon("mngac")}<span>MN GAC</span></a><a href="/#datasets">{icon("sources")}<span>Sources</span></a><a href="/snapshot.xlsx">{icon("export")}<span>Export</span></a>
</nav>
</body></html>"""


def _load_mngac_schema() -> dict:
    try:
        return json.loads(MNGAC_FIELDS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"standard": {}, "fields": []}


def _load_county_boundaries() -> dict:
    try:
        return json.loads(COUNTY_BOUNDARIES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"source": {}, "counties": []}


def _mngac_source(state: dict) -> tuple[str | None, dict | None]:
    for source_id, source in (state.get("sources") or {}).items():
        data = source.get("mngac_completeness")
        if isinstance(data, dict) and data.get("fields") and data.get("counties"):
            return source_id, source
    return None, None


def _mngac_data(state: dict) -> dict | None:
    _, source = _mngac_source(state)
    data = (source or {}).get("mngac_completeness")
    return data if isinstance(data, dict) and data.get("fields") else None


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
            f'tabindex="0" role="button" fill-rule="evenodd" aria-label="{_esc(name)} County" d="{" ".join(d_parts)}">'
            f'<title>{_esc(name)} County</title></path>'
        )
    return f'<svg id="mngac-map" class="mngac-map" viewBox="0 0 {width} {height}" role="img" aria-label="Interactive map of Minnesota counties">{"".join(paths)}</svg>'


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
        rows.append(
            f'<tr data-name="{_esc((str(spec.get("label") or "") + " " + field).lower())}" '
            f'data-inclusion="{_esc(spec.get("inclusion") or "")}">'
            f'<td><strong>{_esc(spec.get("label"))}</strong><br><code>{_esc(field)}</code></td>'
            f'<td>{_esc(spec.get("section_name"))}</td><td>{_esc(spec.get("inclusion"))}</td>'
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


def render_mngac(config: dict) -> str:
    state = _dashboard_state(config)
    data = _mngac_data(state)
    profiles = _county_profiles(config, state, load_parcel_access())
    profile_panel = render_county_profile_panel(profiles)
    publication = f'<p>Public publication: {_esc(profile_time(state.get("public_published_at")))}</p>'
    schema = _load_mngac_schema()
    standard = schema.get("standard") or {}
    all_counties = _load_counties()
    total_counties = len(all_counties)
    if not data:
        body = (
            '<p><a href="/counties">← Minnesota counties</a></p>'
            '<div class="card"><h2>MN GAC completeness data is not available yet</h2>'
            '<p>The statewide parcel source has not published a stored MNGAC completeness observation. '
            'Once the configured MnGeo statewide parcel check records it, this page will show county and field statistics.</p></div>'
            + _mngac_map_svg().replace('class="mngac-county"', f'class="mngac-county" style="fill:{NO_DATA_COLOR}"') + percentage_legend() + publication + profile_panel
        )
        return _layout("MN GAC Completeness — GIS Data Watchtower", body, refresh_seconds=300, static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))

    covered = int(data.get("covered_counties") or 0)
    uncovered = max(0, total_counties - covered)
    record_count = data.get("record_count")
    record_count_label = f"{record_count:,}" if isinstance(record_count, int) else "Not available"
    field_count = int(data.get("field_count") or len(schema.get("fields") or []))
    overall_pct = data.get("field_population_percent")
    mandatory_pct = data.get("mandatory_population_percent")
    source_id, source = _mngac_source(state)
    observed_at = (source or {}).get("checked_at") or (source or {}).get("last_success_at")
    standard_url = _safe_url((data.get("standard") or {}).get("source_url") or standard.get("source_url"))
    standard_link = (
        f'<a href="{_esc(standard_url)}" target="_blank" rel="noopener">official MN GAC Parcel Data Standard</a>'
        if standard_url else "official MN GAC Parcel Data Standard"
    )

    options = [
        '<option value="__overall__">All 91 fields — row population rate</option>',
        '<option value="__mandatory__">Mandatory fields — row population rate</option>',
        '<option value="__fields_with_values__">Fields with any values — share of standard fields</option>',
    ]
    last_section = None
    for spec in schema.get("fields") or []:
        section_name = str(spec.get("section_name") or "Other")
        if section_name != last_section:
            if last_section is not None:
                options.append("</optgroup>")
            options.append(f'<optgroup label="{_esc(section_name)}">')
            last_section = section_name
        options.append(
            f'<option value="{_esc(spec.get("field"))}">'
            f'{_esc(spec.get("section"))}.{_esc(spec.get("order"))} {_esc(spec.get("label"))} '
            f'({_esc(spec.get("field"))}) — {_esc(spec.get("inclusion"))}</option>'
        )
    if last_section is not None:
        options.append("</optgroup>")

    field_rows = []
    summaries = data.get("fields") or {}
    for spec in schema.get("fields") or []:
        field = str(spec.get("field") or "")
        stats = summaries.get(field) or {}
        populated = stats.get("populated")
        total = stats.get("record_count")
        pct = stats.get("percent")
        median = stats.get("county_median_percent")
        county_values = int(stats.get("counties_with_values") or 0)
        field_rows.append(
            f'<tr data-name="{_esc((str(spec.get("label") or "") + " " + field).lower())}" '
            f'data-inclusion="{_esc(spec.get("inclusion") or "")}">'
            f'<td><button type="button" class="mngac-field-select" data-field="{_esc(field)}">'
            f'<strong>{_esc(spec.get("label"))}</strong><br><code>{_esc(field)}</code></button></td>'
            f'<td>{_esc(spec.get("section_name"))}</td><td>{_esc(spec.get("inclusion"))}</td>'
            f'<td>{county_values}/{total_counties}<br><span class="subtext">{county_values}/{covered} represented counties</span></td>'
            f'<td>{_esc(f"{populated:,}" if isinstance(populated, int) else "—")} / '
            f'{_esc(f"{total:,}" if isinstance(total, int) else "—")}</td>'
            f'<td><strong>{_esc(f"{pct:.2f}%" if isinstance(pct, (int,float)) else "—")}</strong></td>'
            f'<td>{_esc(f"{median:.2f}%" if isinstance(median, (int,float)) else "—")}</td></tr>'
        )

    counties_payload = {}
    slug_map = _county_slug_map()
    for county in all_counties:
        name = str(county.get("name") or "")
        stats = (data.get("counties") or {}).get(name)
        if stats:
            counties_payload[name] = {
                "slug": slug_map.get(name),
                "record_count": stats.get("record_count"),
                "field_population_percent": stats.get("field_population_percent"),
                "mandatory_population_percent": stats.get("mandatory_population_percent"),
                "fields_with_values": stats.get("fields_with_values"),
                "field_count": stats.get("field_count"),
                "fields": stats.get("fields") or {},
            }
        else:
            counties_payload[name] = {"slug": slug_map.get(name), "available": False}

    payload = {
        "counties": counties_payload,
        "fields": summaries,
        "standard": data.get("standard") or standard,
        "total_counties": total_counties,
        "covered_counties": covered,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    map_svg = _mngac_map_svg()
    body = f"""
<p><a href="/counties">← Minnesota counties</a> · <a href="/mngac.csv">Download field summary (CSV)</a> · <a href="/mngac.json">Download MN GAC data (JSON)</a> · <a href="/snapshot.xlsx">Statewide Excel with MN GAC sheets</a></p>
<div class="grid primary-grid">
  <div class="card"><div class="muted">Standard fields</div><div class="metric">{field_count}</div><span class="subtext">{_esc(standard.get("name") or "MN GAC Parcel Data Standard")} v{_esc(standard.get("version") or "—")}.</span></div>
  <div class="card"><div class="muted">Counties represented</div><div class="metric">{covered}/{total_counties}</div><span class="subtext">Counties currently represented in MnGeo Plan Parcels Open.</span></div>
  <div class="card"><div class="muted">Not represented</div><div class="metric">{uncovered}</div><span class="subtext">Shown as No data on the map, not as 0% populated.</span></div>
  <div class="card"><div class="muted">Open parcel records</div><div class="metric">{record_count_label}</div><span class="subtext">Parcel records included in the current MnGeo statewide open layer.</span></div>
</div>
<div class="activity-strip">
  <div class="card"><div class="muted">All-field population</div><div class="metric">{_esc(f"{overall_pct:.2f}%" if isinstance(overall_pct,(int,float)) else "—")}</div><span class="subtext">Record-weighted populated cells across all 91 standard fields for represented counties. Descriptive only.</span></div>
  <div class="card"><div class="muted">Mandatory-field fill rate</div><div class="metric">{_esc(f"{mandatory_pct:.2f}%" if isinstance(mandatory_pct,(int,float)) else "—")}</div><span class="subtext">Record-weighted population across fields the standard classifies as Mandatory.</span></div>
</div>
<div class="mngac-note"><strong>How to read these percentages:</strong> this page measures whether standardized MNGAC fields contain values. It is <strong>not a compliance score</strong>. Conditional fields may be correctly blank when their condition does not apply; “If Available” fields are only required when the provider has the data; Optional fields may be blank. Mandatory-field population is shown separately. Source: {standard_link}. Observation: {_format_time_pair(observed_at)}</div>
<div class="card">
  <div class="section-head"><div><h2>Interactive Minnesota county map</h2><p>Select an MN GAC field or summary statistic, then click or keyboard-select any county to inspect it.</p></div></div>
  <div class="mngac-controls">
    <label>Map statistic<select id="mngac-metric">{"".join(options)}</select></label>
  </div>
  <div class="mngac-layout">
    <div class="mngac-map-panel">{map_svg}
      {percentage_legend()}
    </div>
    <div class="card mngac-detail" id="mngac-detail" aria-live="polite">
      <div class="muted">Selected county</div><h3 id="mngac-county-name">Select a county</h3>
      <div class="muted" id="mngac-metric-label">All 91 fields — row population rate</div>
      <div class="mngac-kpi" id="mngac-county-value">—</div>
      <div id="mngac-county-detail" class="subtext">Click a county on the map.</div>
      <p><a id="mngac-county-link" href="/counties" style="display:none">Open county dashboard →</a></p>
    </div>
  </div>
</div>
<div class="section-head"><div><h2>Statewide MN GAC field completeness</h2><p>Population across all parcel records currently represented by MnGeo, plus county-level coverage.</p></div></div>
<div class="card">
  <div class="filters">
    <input id="mngac-q" placeholder="Filter standard fields…" aria-label="Filter MN GAC fields">
    <select id="mngac-inclusion" aria-label="Filter inclusion category"><option value="">All inclusion categories</option><option>Mandatory</option><option>Conditional</option><option>If Available</option><option>Optional</option></select>
  </div>
  <div class="mngac-table-wrap"><table id="mngac-fields"><thead><tr>
    <th>Field</th><th>Section</th><th>Inclusion</th><th>Counties with values</th>
    <th>Populated records</th><th>Statewide population</th><th>Median county populated %</th>
  </tr></thead><tbody>{"".join(field_rows)}</tbody></table></div>
</div>
<script type="application/json" id="mngac-data">{payload_json}</script>
<script>
(function(){{
  const root=document;
  const data=JSON.parse(root.getElementById('mngac-data').textContent);
  const metric=root.getElementById('mngac-metric');
  const paths=[...root.querySelectorAll('.mngac-county')];
  const q=root.getElementById('mngac-q'),inc=root.getElementById('mngac-inclusion');
  let selected=null;
  function metricMeta(key){{
    if(key==='__overall__')return {{label:'All 91 fields — row population rate',inclusion:'Descriptive'}};
    if(key==='__mandatory__')return {{label:'Mandatory fields — row population rate',inclusion:'Mandatory'}};
    if(key==='__fields_with_values__')return {{label:'Fields with any values — share of 91 standard fields',inclusion:'Descriptive'}};
    return data.fields[key]||{{label:key,inclusion:''}};
  }}
  function valueFor(name,key){{
    const c=data.counties[name]; if(!c||c.available===false)return null;
    if(key==='__overall__')return c.field_population_percent;
    if(key==='__mandatory__')return c.mandatory_population_percent;
    if(key==='__fields_with_values__')return typeof c.fields_with_values==='number'&&c.field_count?Math.round((c.fields_with_values/c.field_count)*10000)/100:null;
    const f=(c.fields||{{}})[key]; return f&&typeof f.percent==='number'?f.percent:null;
  }}
  {percentage_color_js()}
  const color=percentageColor;
  function updateMap(){{
    const key=metric.value,meta=metricMeta(key);
    paths.forEach(p=>{{
      const v=valueFor(p.dataset.county,key); p.style.fill=color(v);
      p.setAttribute('aria-label',p.dataset.county+' County, '+meta.label+', '+(typeof v==='number'?v.toFixed(2)+'%':'no data'));
    }});
    if(selected)showCounty(selected);
  }}
  function showCounty(name){{
    selected=name; paths.forEach(p=>p.classList.toggle('selected',p.dataset.county===name));
    const c=data.counties[name],key=metric.value,meta=metricMeta(key),v=valueFor(name,key);
    root.getElementById('mngac-county-name').textContent=name+' County';
    root.getElementById('mngac-metric-label').textContent=meta.label+(meta.inclusion?' · '+meta.inclusion:'');
    root.getElementById('mngac-county-value').textContent=typeof v==='number'?v.toFixed(2)+'%':'No data';
    const detail=root.getElementById('mngac-county-detail');
    if(!c||c.available===false){{
      detail.textContent='This county is not represented in the current MnGeo Plan Parcels Open layer. No 0% value is inferred.';
    }}else if(key==='__fields_with_values__'){{
      detail.textContent=c.fields_with_values+' of '+c.field_count+' standard fields contain at least one value across '+(c.record_count==null?'Not available':Number(c.record_count).toLocaleString())+' parcel records.';
    }}else if(key==='__overall__'){{
      detail.textContent='Average populated cells across all 91 standard fields and '+(c.record_count==null?'Not available':Number(c.record_count).toLocaleString())+' parcel records. Conditional and optional blanks may be valid.';
    }}else if(key==='__mandatory__'){{
      detail.textContent='Population across the standard’s Mandatory fields for '+(c.record_count==null?'Not available':Number(c.record_count).toLocaleString())+' parcel records. This is not a full compliance determination.';
    }}else{{
      const f=(c.fields||{{}})[key]||{{}};
      detail.textContent=(f.populated==null?'Not available':Number(f.populated).toLocaleString())+' of '+(f.record_count==null?'Not available':Number(f.record_count).toLocaleString())+' parcel records contain a value.';
    }}
    const link=root.getElementById('mngac-county-link');
    if(c&&c.slug){{link.href='/county?slug='+encodeURIComponent(c.slug);link.style.display='inline'}} else link.style.display='none';
  }}
  paths.forEach(p=>{{
    p.addEventListener('click',()=>showCounty(p.dataset.county));
    p.addEventListener('keydown',e=>{{if(e.key==='Enter'||e.key===' '){{e.preventDefault();showCounty(p.dataset.county)}}}});
  }});
  metric.addEventListener('change',updateMap);
  root.querySelectorAll('.mngac-field-select').forEach(b=>b.addEventListener('click',()=>{{metric.value=b.dataset.field;updateMap();root.getElementById('mngac-map').scrollIntoView({{behavior:'smooth',block:'center'}})}}));
  function filterFields(){{
    const text=(q.value||'').toLowerCase(),cat=inc.value;
    root.querySelectorAll('#mngac-fields tbody tr').forEach(row=>{{row.style.display=(!text||row.dataset.name.includes(text))&&(!cat||row.dataset.inclusion===cat)?'':'none'}});
  }}
  q.addEventListener('input',filterFields); inc.addEventListener('change',filterFields);
  updateMap();
}})();
</script>
{publication}
{profile_panel}
"""
    return _layout("MN GAC Completeness — GIS Data Watchtower", body, refresh_seconds=0, static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))


def render_counties(config: dict) -> str:
    state = _dashboard_state(config)
    research = load_parcel_access()
    profiles = _county_profiles(config, state, research)
    counties = [_county_status(config, x, state, profiles=profiles, research=research) for x in _load_counties()]
    research_count = sum(p["research"]["complete"] for p in profiles.values())
    active_count = sum(1 for x in counties if x["actively_monitored"])
    direct_count = sum(1 for x in counties if "county-direct" in x["monitoring_paths"])
    mngeo_count = sum(1 for x in counties if "mngeo-open" in x["monitoring_paths"])
    status_counts = {}
    age_buckets = {"0–30 days": 0, "31–90 days": 0, "91–365 days": 0, "Over 1 year": 0, "No date": 0}
    mngac = _mngac_data(state)
    for x in counties:
        status_counts[x["status"]] = status_counts.get(x["status"], 0) + 1
        record = x.get("catalog") or {}
        d = _parse_time(_format_arcgis_date(record.get("acqdate")))
        if not d:
            age_buckets["No date"] += 1
        else:
            if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
            days = max(0, (dt.datetime.now(dt.timezone.utc) - d).days)
            bucket = "0–30 days" if days <= 30 else "31–90 days" if days <= 90 else "91–365 days" if days <= 365 else "Over 1 year"
            age_buckets[bucket] += 1
    rows = "".join(
        f'<tr data-name="{_esc(x["name"].lower())}" data-status="{_esc(x["status"])}">'
        f'<td><a href="/county?slug={urllib.parse.quote(x["slug"])}"><strong>{_esc(x["name"])} County</strong></a></td>'
        f'<td><span class="pill {_esc(x["status"])}">{_esc(_friendly_status(x["status"]))}</span>'
        f'<br><span class="subtext">{_esc(_monitoring_path_label(x))}</span></td>'
        f'<td><strong>{_esc(access_label(x.get("parcel_access")))}</strong></td>'
        f'<td><strong>{_esc(statewide_access_label(x.get("parcel_access"), live_available=(x.get("statewide_record") is not None) if mngac else None))}</strong></td>'
        f'<td>{len(x["sources"])}</td></tr>'
        for x in counties
    )
    if mngac:
        mngac_card = (
            f'<div class="card"><h2>MN GAC field completeness</h2><p><strong>{_esc(mngac.get("covered_counties") or 0)} of {len(counties)} counties</strong> are represented in MnGeo Plan Parcels Open for standardized field-population statistics.</p>'
            f'<p><a href="/mngac">Explore the interactive county map and all 91 fields →</a></p></div><br>'
        )
    else:
        mngac_card = '<div class="card"><h2>MN GAC field completeness</h2><p class="muted">A statewide completeness observation has not been stored yet.</p><p><a href="/mngac">Open MN GAC completeness →</a></p></div><br>'
    body = f'<div class="grid"><div class="card"><div class="muted">Minnesota counties</div><div class="metric">{len(counties)}</div><span class="subtext">Counties represented in the statewide county dashboard index.</span></div><div class="card"><div class="muted">Counties actively checked</div><div class="metric">{active_count}</div><span class="subtext">Actively monitored through a county-direct source, MnGeo Plan Parcels Open, or both.</span></div><div class="card"><div class="muted">County-direct checks</div><div class="metric">{direct_count}</div><span class="subtext">Counties with at least one county-specific source actively checked.</span></div><div class="card"><div class="muted">MnGeo open coverage</div><div class="metric">{mngeo_count}</div><span class="subtext">Counties represented in the current Plan Parcels Open observation.</span></div></div>' + mngac_card + \
        f'<div class="grid"><div class="card">{_bar_chart([( _friendly_status(k), v) for k,v in sorted(status_counts.items())], title="County monitoring coverage")}<span class="subtext">A county is actively checked when Watchtower observes it through a county-specific source, the statewide MnGeo open-parcels source, or both.</span></div><div class="card">{_bar_chart(list(age_buckets.items()), title="MnGeo parcel update age")}<span class="subtext">Age of the county acquisition/update date reported in the MnGeo parcel catalog; this is not Watchtower check time.</span></div></div><div class="card"><h2>Minnesota county dashboards</h2><p class="muted">Monitoring coverage, county-direct parcel access, and statewide open access are separate. A county can require payment for its county-supplied dataset while also being freely available through MnGeo Plan Parcels Open.</p><p class="subtext">Use Export in the page toolbar for statewide Excel, CSV, or JSON.</p>' \
        '<div class="filters"><input id="cq" placeholder="Filter counties…" oninput="filterCounties()"><select id="cs" onchange="filterCounties()"><option value="">All coverage types</option><option value="ok">Actively checked</option><option value="catalog">MnGeo catalog only</option><option value="needs-source">No active parcel monitoring</option><option value="not-configured">No source information yet</option><option value="warn">Needs attention</option><option value="error">Check failed</option></select></div>' \
        f'<table id="counties"><thead><tr><th>County</th><th>Monitoring coverage<br><span class="subtext">Health and active monitoring path</span></th><th>County-direct access<br><span class="subtext">Evidence-backed county access</span></th><th>Statewide open access<br><span class="subtext">Current MnGeo Plan Parcels Open coverage</span></th><th>County-direct sources<br><span class="subtext">County-specific sources actively checked</span></th></tr></thead><tbody>{rows}</tbody></table></div>' \
        "<script>function filterCounties(){const q=document.getElementById('cq').value.toLowerCase(),s=document.getElementById('cs').value;document.querySelectorAll('#counties tbody tr').forEach(r=>r.style.display=(!q||r.dataset.name.includes(q))&&(!s||r.dataset.status===s)?'':'none')}</script>"
    body += f'<div class="card"><h2>Parcel source research</h2><p>{research_count}/{len(profiles)} complete county inventories. Blocked and unresolved evidence remains Research incomplete.</p></div>'
    return _layout("Minnesota Counties — GIS Data Watchtower", '<p><a href="/">← Watchtower overview</a></p>'+body, static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))


def _render_county_mngac(state: dict, county: dict) -> str:
    data, stats = _mngac_county_record(state, str(county.get("name") or ""))
    if not data:
        return (
            '<div class="card"><h2>MN GAC field completeness</h2>'
            '<p class="muted">A stored statewide MN GAC completeness observation is not available yet.</p>'
            '<p><a href="/mngac">Open statewide MN GAC page →</a></p></div>'
        )
    standard = data.get("standard") or _load_mngac_schema().get("standard") or {}
    if not stats:
        return (
            '<div class="card"><h2>MN GAC field completeness</h2>'
            '<p>This county is not represented in the current MnGeo Plan Parcels Open layer. '
            'Watchtower reports this as <strong>No data</strong>, not 0% populated.</p>'
            f'<p class="subtext">The statewide open layer currently represents {_esc(data.get("covered_counties") or 0)} of 87 Minnesota counties.</p>'
            '<p><a href="/mngac">Explore the statewide MN GAC map →</a></p></div>'
        )
    record_count = int(stats.get("record_count") or 0)
    field_count = int(stats.get("field_count") or 0)
    fields_with_values = int(stats.get("fields_with_values") or 0)
    population_pct = stats.get("field_population_percent")
    mandatory_pct = stats.get("mandatory_population_percent")
    mandatory_full = int(stats.get("mandatory_fields_full") or 0)
    mandatory_count = int(stats.get("mandatory_field_count") or 0)
    rows = _mngac_field_rows(stats)
    return f"""
<div class="section-head"><div><h2>MN GAC field completeness</h2><p>Population of the official Minnesota GAC parcel-transfer fields for this county in MnGeo Plan Parcels Open.</p></div><a href="/mngac">Statewide map →</a></div>
<div class="grid primary-grid">
  <div class="card"><div class="muted">MnGeo parcel records</div><div class="metric">{record_count:,}</div><span class="subtext">Records used as the denominator for county field-population percentages.</span></div>
  <div class="card"><div class="muted">Fields with values</div><div class="metric">{fields_with_values}/{field_count}</div><span class="subtext">Standard fields containing at least one populated value in this county.</span></div>
  <div class="card"><div class="muted">All-field fill rate</div><div class="metric">{_esc(f"{population_pct:.2f}%" if isinstance(population_pct,(int,float)) else "—")}</div><span class="subtext">Populated cells across all standard fields. This is descriptive, not a compliance score.</span></div>
  <div class="card"><div class="muted">Mandatory-field fill rate</div><div class="metric">{_esc(f"{mandatory_pct:.2f}%" if isinstance(mandatory_pct,(int,float)) else "—")}</div><span class="subtext">{mandatory_full}/{mandatory_count} Mandatory fields are populated for 100% of records.</span></div>
</div>
<div class="mngac-note">The GAC standard uses four inclusion categories: Mandatory, Conditional, If Available, and Optional. A blank Conditional, If Available, or Optional field can be valid, so these percentages should not be interpreted as a pass/fail compliance grade. Standard: {_esc(standard.get("short_name") or "MN GAC Parcel Data Standard")} v{_esc(standard.get("version") or "—")}.</div>
<div class="card">
  <div class="filters"><input id="cmq" placeholder="Filter MNGAC fields…" aria-label="Filter county MNGAC fields"><select id="cmi" aria-label="Filter county inclusion category"><option value="">All inclusion categories</option><option>Mandatory</option><option>Conditional</option><option>If Available</option><option>Optional</option></select></div>
  <div class="mngac-table-wrap"><table id="county-mngac-fields"><thead><tr><th>Field</th><th>Section</th><th>Inclusion</th><th>Populated</th><th>Records</th><th>Population</th></tr></thead><tbody>{rows}</tbody></table></div>
</div>
<script>(function(){{const q=document.getElementById('cmq'),i=document.getElementById('cmi');function f(){{const t=(q.value||'').toLowerCase(),c=i.value;document.querySelectorAll('#county-mngac-fields tbody tr').forEach(r=>r.style.display=(!t||r.dataset.name.includes(t))&&(!c||r.dataset.inclusion===c)?'':'none')}}q.addEventListener('input',f);i.addEventListener('change',f)}})();</script>
"""


def _county_mngac_summary(state: dict, county: dict) -> dict:
    data, county_stats = _mngac_county_record(state, county["name"])
    source_id, source = _mngac_source(state)
    return {
        "data": data,
        "county": county_stats,
        "source_id": source_id,
        "source": source,
        "checked_at": (source or {}).get("checked_at") or (source or {}).get("last_success_at"),
    }


def render_county(config: dict, slug: str) -> str:
    state = _dashboard_state(config)
    county = next((x for x in _load_counties() if x.get("slug") == slug), None)
    if not county:
        return _layout("County not found", '<p><a href="/counties">← Minnesota counties</a></p><div class="card">County not found.</div>', static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))
    research = load_parcel_access()
    profiles = _county_profiles(config, state, research)
    info = _county_status(config, county, state, profiles=profiles, research=research)
    complete_profile = render_county_profile_body(profiles[slug])
    mngac_html = _render_county_mngac(state, county)
    parcel_access = info.get("parcel_access")
    direct_access_label = access_label(parcel_access)
    live_mngac = _mngac_data(state)
    statewide_live_available = (info.get("statewide_record") is not None) if live_mngac else None
    statewide_label = statewide_access_label(parcel_access, live_available=statewide_live_available)
    statewide_record_count = int((info.get("statewide_record") or {}).get("record_count") or 0)
    if parcel_access and parcel_access.get("research_complete"):
        evidence_links = []
        for item in parcel_access.get("evidence") or []:
            url = _safe_url(item.get("url"))
            if url:
                evidence_links.append(
                    f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(item.get("authority") or "Source")}</a>'
                )
        details = [
            f'<strong>Reviewed:</strong> {_esc(parcel_access.get("review_date") or "—")}',
            f'<strong>Evidence:</strong> {" · ".join(evidence_links) if evidence_links else "—"}',
        ]
        if parcel_access.get("parcel_dataset_fee"):
            details.append(f'<strong>County parcel dataset fee:</strong> {_esc(parcel_access.get("parcel_dataset_fee"))}')
        if parcel_access.get("fee_product"):
            details.append(f'<strong>County fee applies to:</strong> {_esc(parcel_access.get("fee_product"))}')
        service_url = _safe_url(parcel_access.get("download_or_service_url"))
        if service_url:
            details.append(f'<strong>County-direct machine-readable source:</strong> <a href="{_esc(service_url)}" target="_blank" rel="noopener">Open source</a>')
        viewer_url = _safe_url(parcel_access.get("viewer_url"))
        if viewer_url:
            details.append(f'<strong>County viewer:</strong> <a href="{_esc(viewer_url)}" target="_blank" rel="noopener">Open viewer</a>')
        statewide = parcel_access.get("statewide_open_coverage") or {}
        statewide_url = _safe_url(statewide.get("source_url"))
        if statewide_url:
            details.append(f'<strong>MnGeo source:</strong> <a href="{_esc(statewide_url)}" target="_blank" rel="noopener">Plan Parcels Open</a>')
        if info.get("statewide_record"):
            details.append(f'<strong>MnGeo parcel records currently observed:</strong> {_esc(f"{statewide_record_count:,}")}')
        parcel_access_detail = (
            '<div class="card"><h2>Parcel dataset access</h2>'
            f'<p><strong>County-direct access:</strong> {_esc(direct_access_label)}</p>'
            f'<p><strong>Statewide open access:</strong> {_esc(statewide_label)}</p>'
            f'<p>{_esc(parcel_access.get("evidence_note") or "")}</p>'
            f'<p class="subtext">{"<br>".join(details)}</p></div>'
        )
    else:
        parcel_access_detail = (
            '<div class="card"><h2>Parcel dataset access</h2>'
            f'<p><strong>County-direct access:</strong> {_esc(direct_access_label)}</p>'
            f'<p><strong>Statewide open access:</strong> {_esc(statewide_label)}</p>'
            '<p class="muted">A completed county-direct parcel-access review is not stored for this county.</p></div>'
        )
    source_cards = ""
    if info.get("statewide_record") and info.get("statewide_source"):
        src = info["statewide_source"]
        checked_value = src.get("checked_at") or src.get("last_success_at")
        checked = _format_public_time_compact(checked_value) if config.get("_public_mode") else _esc(checked_value or "—")
        source_cards += (
            '<div class="card"><h3>MnGeo Plan Parcels Open</h3>'
            f'<p><strong>Status:</strong> {_esc(_health_status(src.get("status") or "unknown"))}'
            f'<br><strong>County records:</strong> {_esc(f"{statewide_record_count:,}")}'
            f'<br><strong>Monitoring path:</strong> Statewide open parcel source'
            f'<br><strong>Last checked:</strong> {checked}</p></div>'
        )
    for src in info["sources"]:
        checked = _format_public_time_compact(src.get("checked_at")) if config.get("_public_mode") else _esc(src.get("checked_at", "—"))
        source_cards += f'<div class="card"><h3>{_esc(src.get("name"))}</h3><p><strong>Status:</strong> {_esc(_friendly_status(src.get("status") or "unknown"))}<br><strong>Records:</strong> {_esc(src.get("feature_count","—"))}<br><strong>Provided by:</strong> {_esc(src.get("provider","—"))}<br><strong>Last checked:</strong> {checked}</p></div>'
    catalog = info.get("catalog") or {}
    if not source_cards and catalog:
        approval = str(catalog.get("gac_open_approval") or "—")
        data_url = _safe_url(catalog.get("data_url"))
        viewer_url = _safe_url(catalog.get("viewer_url"))
        source_links = (f'<a href="{_esc(data_url)}" target="_blank" rel="noopener">Open parcel data</a>' if data_url else "No open data URL supplied")
        if viewer_url:
            source_links += f' · <a href="{_esc(viewer_url)}" target="_blank" rel="noopener">Viewer</a>'
        source_cards = f'<div class="card"><h3>County parcel update information</h3><p><strong>MnGeo public-data approval:</strong> {_esc(approval)}<br><strong>Last county update:</strong> {_esc(_format_arcgis_date(catalog.get("acqdate")))}<br><strong>MnGeo listing refreshed:</strong> {_esc(_format_arcgis_date(catalog.get("rundate")))}<br><strong>Parcel links:</strong> {source_links}</p></div>'
    elif not source_cards:
        source_cards = '<div class="card"><h3>No direct county parcel source currently monitored</h3><p>Monitoring coverage is separate from the parcel-data access research shown below.</p></div>'
    contact_record = _load_county_contact_records().get(county["name"], {})
    contacts = contact_record.get("contacts", [])
    contact_rows = ""
    for contact in contacts:
        email = str(contact.get("email") or "").strip().rstrip(".")
        phone = str(contact.get("phone") or "").strip()
        email_html = f'<a href="mailto:{_esc(email)}">{_esc(email)}</a>' if email else "—"
        phone_html = f'<a href="tel:{_esc(phone)}">{_esc(phone)}</a>' if phone else "—"
        contact_rows += f'<tr><td><strong>{_esc(contact.get("name") or "Department contact")}</strong></td><td>{_esc(contact.get("title") or "—")}</td><td>{_esc(contact.get("department") or "—")}</td><td>{phone_html}</td><td>{email_html}</td></tr>'
    if not contact_rows:
        contact_rows = '<tr><td colspan="5">No contact is currently listed in the MnGeo county GIS directory.</td></tr>'
    contact_source_url = _safe_url(contact_record.get("source_url"))
    contact_source_name = contact_record.get("source_name") or "MnGeo County GIS Contacts"
    contact_source = f'<a href="{_esc(contact_source_url)}" target="_blank" rel="noopener">{_esc(contact_source_name)}</a>' if contact_source_url else _esc(contact_source_name)
    if contact_record.get("authority") == "county":
        contact_source_note = "The official county website provides additional or changed GIS/land-records contact information, so the county website is authoritative."
    elif contact_record.get("verified"):
        contact_source_note = "The official county website was checked; because it did not provide additional or changed usable GIS contact information, the MnGeo county GIS directory is retained as the fallback."
    else:
        contact_source_note = "MnGeo is the current contact source; an official-county verification result is not recorded yet."
    verified_text = f' Verified {_esc(contact_record.get("verified"))}.' if contact_record.get("verified") else ""
    contacts_html = f'<div class="card"><h2>County GIS contacts</h2><p class="muted"><strong>Contact source:</strong> {contact_source}. {contact_source_note}{verified_text}</p><table class="contacts-table"><thead><tr><th>Name</th><th>Title</th><th>Department</th><th>Phone</th><th>Email</th></tr></thead><tbody>{contact_rows}</tbody></table></div>'
    export_links = f'<p><a href="/county-snapshot.csv?slug={urllib.parse.quote(slug)}">Download county snapshot (CSV)</a> · <a href="/county-snapshot.xlsx?slug={urllib.parse.quote(slug)}">Download county snapshot (Excel)</a> · <a href="/county-snapshot.json?slug={urllib.parse.quote(slug)}">Download county snapshot (JSON)</a></p>'
    body = f'<p><a href="/counties">← Minnesota counties</a></p>{export_links}<div class="grid"><div class="card"><div class="muted">County</div><h2>{_esc(county["name"])} County</h2></div><div class="card"><div class="muted">Monitoring coverage</div><div class="metric {_esc(info["status"])}">{_esc(_friendly_status(info["status"]).upper())}</div></div><div class="card"><div class="muted">Monitoring path</div><div class="metric" style="font-size:20px">{_esc(_monitoring_path_label(info))}</div></div><div class="card"><div class="muted">County-direct sources</div><div class="metric">{len(info["sources"])}</div></div></div><div class="grid">{source_cards}</div><br>{parcel_access_detail}<br>{mngac_html}<br><div class="card">{complete_profile}</div><br>{contacts_html}'
    return _layout(f'{county["name"]} County — Watchtower', body, static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))

def _county_snapshot(config: dict, slug: str, *, include_mngac: bool = True, state: dict | None = None,
                     profiles: dict | None = None, research: dict | None = None) -> dict | None:
    state = _dashboard_state(config) if state is None else state
    county = next((x for x in _load_counties() if x.get("slug") == slug), None)
    if not county:
        return None
    info = _county_status(config, county, state, profiles=profiles, research=research)
    catalog = info.get("catalog") or {}
    mngac_data, mngac_county = _mngac_county_record(state, county["name"])
    mngac_payload = None
    if include_mngac and mngac_data:
        mngac_payload = {
            "standard": mngac_data.get("standard") or {},
            "method": mngac_data.get("method"),
            "covered_counties": mngac_data.get("covered_counties"),
            "county": mngac_county,
        }
    return {
        "county": county["name"],
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
    }


def _mngac_csv(data: dict | None) -> str:
    out = io.StringIO()
    fields = [
        "element","field","section","inclusion","data_type","counties_with_values",
        "counties_represented","populated_records","record_count","statewide_population_percent",
        "median_county_population_percent",
    ]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    if not isinstance(data, dict):
        return out.getvalue()
    schema = _load_mngac_schema()
    summaries = data.get("fields") or {}
    for spec in schema.get("fields") or []:
        field = str(spec.get("field") or "")
        stats = summaries.get(field) or {}
        writer.writerow({key: _csv_safe(value) for key, value in {
            "element": spec.get("label"),
            "field": field,
            "section": spec.get("section_name"),
            "inclusion": spec.get("inclusion"),
            "data_type": spec.get("data_type"),
            "counties_with_values": stats.get("counties_with_values"),
            "counties_represented": stats.get("counties_covered"),
            "populated_records": stats.get("populated"),
            "record_count": stats.get("record_count"),
            "statewide_population_percent": stats.get("percent"),
            "median_county_population_percent": stats.get("county_median_percent"),
        }.items()})
    return out.getvalue()


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _snapshot_csv(snapshot: dict) -> str:
    out = io.StringIO()
    if "sources" in snapshot:
        fields = ["source_id","source_name","county","status","feature_count","worker","reporting","stale_source","stale_worker","last_success_at","checked_at"]
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for source in snapshot.get("sources", []):
            writer.writerow({key: _csv_safe(value) for key, value in {
                "source_id": source.get("id"),
                "source_name": source.get("name"),
                "county": source.get("county"),
                "status": source.get("status"),
                "feature_count": source.get("feature_count"),
                "worker": source.get("worker"),
                "reporting": source.get("reporting"),
                "stale_source": source.get("stale"),
                "stale_worker": source.get("worker_stale"),
                "last_success_at": source.get("last_success_at"),
                "checked_at": source.get("checked_at"),
            }.items()})
        return out.getvalue()
    fields = ["county","status","actively_monitored","monitoring_path","county_direct_access","statewide_open_access","county_direct_source_count","parcel_dataset_fee","fee_product","last_county_update","catalog_refresh_date","public_data_approved","parcel_data_url","parcel_viewer_url","worker_provenance","stale_source_count","contact_names","contact_source","contact_source_url","contact_verified","mngac_record_count","mngac_fields_with_values","mngac_field_count","mngac_field_population_percent","mngac_mandatory_population_percent"]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in [snapshot]:
        writer.writerow({key: _csv_safe(value) for key, value in {
            "county": row.get("county"), "status": row.get("status"),
            "actively_monitored": row.get("actively_monitored"),
            "monitoring_path": row.get("monitoring_path_label"),
            "county_direct_access": (row.get("parcel_access") or {}).get("county_direct_label"),
            "statewide_open_access": (row.get("parcel_access") or {}).get("statewide_open_label"),
            "county_direct_source_count": len(row.get("direct_sources") or []),
            "parcel_dataset_fee": (row.get("parcel_access") or {}).get("parcel_dataset_fee"),
            "fee_product": (row.get("parcel_access") or {}).get("fee_product"),
            "last_county_update": row.get("last_county_update"),
            "catalog_refresh_date": row.get("catalog_refresh_date"),
            "public_data_approved": row.get("public_data_approved"),
            "parcel_data_url": row.get("parcel_data_url"),
            "parcel_viewer_url": row.get("parcel_viewer_url"),
            "worker_provenance": "; ".join(sorted({str(x.get("worker")) for x in row.get("direct_sources",[]) if x.get("worker")})),
            "stale_source_count": sum(1 for x in row.get("direct_sources",[]) if x.get("stale") or x.get("worker_stale")),
            "contact_names": "; ".join(x.get("name","") for x in row.get("contacts",[]) if x.get("name")),
            "contact_source": row.get("contact_source"),
            "contact_source_url": row.get("contact_source_url"),
            "contact_verified": row.get("contact_verified"),
            "mngac_record_count": (((row.get("mngac") or {}).get("county") or {}).get("record_count")),
            "mngac_fields_with_values": (((row.get("mngac") or {}).get("county") or {}).get("fields_with_values")),
            "mngac_field_count": (((row.get("mngac") or {}).get("county") or {}).get("field_count")),
            "mngac_field_population_percent": (((row.get("mngac") or {}).get("county") or {}).get("field_population_percent")),
            "mngac_mandatory_population_percent": (((row.get("mngac") or {}).get("county") or {}).get("mandatory_population_percent")),
        }.items()})
    return out.getvalue()


def _xlsx_col_name(index: int) -> str:
    out = ""
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out

def _xlsx_sheet_xml(rows: list[list]) -> str:
    xml_rows = []
    for r_idx, row in enumerate(rows, 1):
        cells = []
        for c_idx, value in enumerate(row, 1):
            ref = f"{_xlsx_col_name(c_idx)}{r_idx}"
            if isinstance(value, bool):
                cells.append(f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>')
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = html.escape("" if value is None else str(value), quote=False)
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + '</sheetData></worksheet>'

def _mngac_xlsx_sheets(snapshot: dict) -> list[tuple[str, list[list]]]:
    data = snapshot.get("mngac")
    if not isinstance(data, dict):
        return []
    schema = _load_mngac_schema()
    specs = schema.get("fields") or []
    sheets = []
    if data.get("counties") and data.get("fields"):
        county_rows = [[
            "County","County code","Parcel records","Fields with any values","Standard fields",
            "All-field population percent","Mandatory population percent",
            "Mandatory fields 100% populated","Mandatory field count"
        ]]
        for name, county in sorted((data.get("counties") or {}).items()):
            county_rows.append([
                name,county.get("county_code"),county.get("record_count"),county.get("fields_with_values"),
                county.get("field_count"),county.get("field_population_percent"),county.get("mandatory_population_percent"),
                county.get("mandatory_fields_full"),county.get("mandatory_field_count"),
            ])
        field_rows = [[
            "Element","Field","Section","Inclusion","Data type","Counties with values",
            "Counties represented","Populated records","Record count","Statewide population percent",
            "Median county population percent"
        ]]
        for spec in specs:
            field = spec.get("field")
            stats = (data.get("fields") or {}).get(field) or {}
            field_rows.append([
                spec.get("label"),field,spec.get("section_name"),spec.get("inclusion"),spec.get("data_type"),
                stats.get("counties_with_values"),stats.get("counties_covered"),stats.get("populated"),
                stats.get("record_count"),stats.get("percent"),stats.get("county_median_percent"),
            ])
        detail_rows = [["County","Field","Element","Inclusion","Populated records","Record count","Population percent"]]
        for county_name, county in sorted((data.get("counties") or {}).items()):
            fields = county.get("fields") or {}
            for spec in specs:
                field = spec.get("field")
                stats = fields.get(field) or {}
                detail_rows.append([
                    county_name,field,spec.get("label"),spec.get("inclusion"),stats.get("populated"),
                    stats.get("record_count"),stats.get("percent"),
                ])
        sheets.extend([
            ("MNGAC Counties", county_rows),
            ("MNGAC Fields", field_rows),
            ("MNGAC Detail", detail_rows),
        ])
    elif isinstance(data.get("county"), dict):
        county = data.get("county") or {}
        field_rows = [["Field","Element","Section","Inclusion","Populated records","Record count","Population percent"]]
        for spec in specs:
            field = spec.get("field")
            stats = (county.get("fields") or {}).get(field) or {}
            field_rows.append([
                field,spec.get("label"),spec.get("section_name"),spec.get("inclusion"),stats.get("populated"),
                stats.get("record_count"),stats.get("percent"),
            ])
        sheets.append(("MNGAC Fields", field_rows))
    return sheets


def _snapshot_xlsx(snapshot: dict) -> bytes:
    county_rows = [["County","Status","Actively monitored","Monitoring path","County-direct access","Statewide open access","County-direct source count","Parcel dataset fee","Fee product","Last county update","Catalog refresh date","Public data approved","Parcel data URL","Parcel viewer URL","Contact names","Contact source","Contact source URL","Contact verified"]]
    source_rows = [["County","Source","Status","Record count","Worker","Reporting","Stale source","Stale worker","Last successful check","Last checked"]]
    contact_rows = [["County","Name","Title","Department","Phone","Email","Contact source","Contact source URL","Verified"]]
    rows = snapshot.get("counties") if "counties" in snapshot else [snapshot]
    for row in rows:
        county = row.get("county") or ""
        parcel_access = row.get("parcel_access") or {}
        county_rows.append([
            county,row.get("status"),bool(row.get("actively_monitored")),row.get("monitoring_path_label"),
            parcel_access.get("county_direct_label"),parcel_access.get("statewide_open_label"),
            len(row.get("direct_sources") or []),parcel_access.get("parcel_dataset_fee"),parcel_access.get("fee_product"),
            row.get("last_county_update"),row.get("catalog_refresh_date"),bool(row.get("public_data_approved")),
            row.get("parcel_data_url"),row.get("parcel_viewer_url"),
            "; ".join(x.get("name","") for x in row.get("contacts",[]) if x.get("name")),
            row.get("contact_source"),row.get("contact_source_url"),row.get("contact_verified"),
        ])
        for source in row.get("direct_sources", []):
            if "sources" not in snapshot:
                source_rows.append([county,source.get("name"),source.get("status"),source.get("feature_count"),source.get("worker"),source.get("reporting"),bool(source.get("stale")),bool(source.get("worker_stale")),source.get("last_success_at"),source.get("checked_at")])
        for contact in row.get("contacts", []):
            contact_rows.append([county,contact.get("name"),contact.get("title"),contact.get("department"),contact.get("phone"),contact.get("email"),row.get("contact_source"),row.get("contact_source_url"),row.get("contact_verified")])
    if "sources" in snapshot:
        for source in snapshot.get("sources", []):
            source_rows.append([source.get("county"),source.get("name"),source.get("status"),source.get("feature_count"),source.get("worker"),source.get("reporting"),bool(source.get("stale")),bool(source.get("worker_stale")),source.get("last_success_at"),source.get("checked_at")])
    sheets=[("Counties",county_rows),("Sources",source_rows),("Contacts",contact_rows)]
    sheets.extend(_mngac_xlsx_sheets(snapshot))
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>')
        zf.writestr("_rels/.rels",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{html.escape(name,quote=True)}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+'</Relationships>')
        for i,(_,data) in enumerate(sheets,1): zf.writestr(f"xl/worksheets/sheet{i}.xml",_xlsx_sheet_xml(data))
    return out.getvalue()


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
    state = _dashboard_state(config)
    sources = state.get("sources", {})
    counts = state.get("counts", {})
    alerts = state.get("active_alerts", [])
    config_map = _source_config_map(config)
    enriched = []
    changed_30 = 0
    for sid, src in sources.items():
        hist = load_history(config, source_filter=sid, limit=60).get("entries", [])
        stats = _history_stats(hist)
        if stats["change_age_days"] is not None and stats["change_age_days"] <= 30:
            changed_30 += 1
        meta = config_map.get(sid, {})
        enriched.append((sid, src, meta, stats, hist))
    telemetry = state.get("telemetry") or {}
    workers = state.get("workers") or {}
    worker_cards = []
    for worker_name in ("cloud", "local"):
        worker = workers.get(worker_name)
        if not worker:
            continue
        worker_status = str(worker.get("overall") or "unknown")
        worker_health = _health_status(worker_status)
        stale = bool(worker.get("stale"))
        worker_telemetry = worker.get("telemetry") or {}
        duration = worker_telemetry.get("wall_ms")
        duration_text = f"{duration / 1000.0:.1f}s" if isinstance(duration, (int, float)) else "—"
        source_count = worker.get("source_count")
        freshness_text = "Reporting overdue" if stale else "Reporting on time"
        worker_cards.append(f"""<div class="card worker-card">
<div><h3><span class="status-dot {_status_class(worker_status)}"></span>{_esc(worker_name.title())} worker</h3><span class="subtext">{_esc(worker_health)} · {_esc(freshness_text)}</span></div>
<div class="worker-meta">
<div><span class="muted">Sources</span><strong>{_esc(source_count if source_count is not None else "—")}</strong></div>
<div><span class="muted">Run time</span><strong>{_esc(duration_text)}</strong></div>
<div><span class="muted">Last success</span><strong style="font-size:13px">{_format_time_pair(worker.get("last_success_at") or worker.get("checked_at"))}</strong></div>
</div></div>""")
    body = f"""<div class="grid primary-grid">
<div class="card"><div class="muted">Overall health</div><div class="metric {_status_class(state.get('overall','unknown'))}">{_esc(_health_status(state.get('overall','unknown')))}</div><span class="subtext">Combined health of all cloud and local source checks.</span></div>
<div class="card"><div class="muted">Monitored sources</div><div class="metric">{len(sources)}</div><span class="subtext">Sources currently included across the cloud and local workers.</span></div>
<div class="card"><div class="muted">Source issues</div><div class="metric">{counts.get('warn',0) + counts.get('error',0)}</div><span class="subtext">Sources whose latest check reported a warning or error.</span></div>
<div class="card"><div class="muted">Reporting overdue</div><div class="metric">{state.get('stale_sources',0)}</div><span class="subtext">Sources that have not reported within the configured freshness window · {state.get('stale_workers',0)} worker(s) overdue.</span></div>
</div>
<div class="section-head"><div><h2>Workers</h2><p>Cloud and local worker health and their most recent successful runs.</p></div></div>
<div class="grid worker-grid">{''.join(worker_cards) or '<div class="card muted">Worker metadata has not been reported yet.</div>'}</div>
<div class="activity-strip">
<div class="card" id="changes"><div class="muted">Sources changed — 30 days</div><div class="metric">{changed_30}</div><span class="subtext">Sources where Watchtower detected a data change during the last 30 days.</span></div>
<div class="card"><div class="muted">Dashboard data updated</div><strong>{_format_time_pair(state.get('generated_at'))}</strong><span class="subtext">When Watchtower last combined the cloud and local worker results.</span><br><a href="/counties">View all 87 Minnesota county dashboards →</a></div>
</div>"""
    if alerts:
        body += '<div class="card" id="alerts"><h2>Active alerts</h2>' + "".join(
            f'<p class="{_status_class(a.get("severity","warn"))}"><strong>{_esc(a.get("name") or a.get("source"))}</strong> — {_esc(a.get("message"))}</p>'
            for a in alerts
        ) + "</div><br>"
    else:
        body += '<div class="card" id="alerts"><h2>Active alerts</h2><p class="ok"><strong>No active alerts.</strong></p><span class="subtext">No current Watchtower alert requires attention.</span></div><br>'
    rows = []
    categories = sorted({str(meta.get("category") or src.get("category") or "Other") for _,src,meta,_,_ in enriched})
    for sid, src, meta, stats, hist in sorted(enriched, key=lambda x: str(x[1].get("name", x[0])).lower()):
        changes = src.get("changes") or []
        provider = meta.get("provider") or src.get("provider") or "—"
        category = meta.get("category") or src.get("category") or "Other"
        prev_count = next((x.get("feature_count") for x in reversed(hist[:-1]) if x.get("feature_count") is not None), None) if len(hist) > 1 else None
        current_count = src.get("feature_count")
        delta = current_count - prev_count if isinstance(current_count,(int,float)) and isinstance(prev_count,(int,float)) else None
        delta_text = "—" if delta is None else f"{delta:+,}"
        delta_class = "delta-up" if isinstance(delta,(int,float)) and delta > 0 else "delta-down" if isinstance(delta,(int,float)) and delta < 0 else ""
        rows.append(f"""<tr data-name="{_esc((src.get('name') or sid).lower())}" data-category="{_esc(category)}" data-status="{_esc(src.get('status','unknown'))}">
<td><a href="/source?{urllib.parse.urlencode({'id':sid})}"><strong>{_esc(src.get('name') or sid)}</strong></a><br><span class="muted">{_esc(sid)}</span></td>
<td>{_esc(provider)}<br><span class="muted">{_esc(category)}</span></td>
<td><span class="pill {_status_class(src.get('status','unknown'))}">{_esc(_health_status(src.get('status','unknown')))}</span><br><span class="muted">{_esc(src.get('reporting','current'))} reporting · {_esc(src.get('worker') or 'default')} worker</span></td>
<td>{_esc(f"{current_count:,}" if isinstance(current_count,int) else current_count or '—')}<br><span class="{delta_class}">{_esc(delta_text)}</span></td>
<td>{_esc(stats.get('change_age_days') if stats.get('change_age_days') is not None else '—')}</td>
<td>{_esc(stats.get('success_rate') if stats.get('success_rate') is not None else '—')}%<br><span class="muted">{_esc(stats.get('consecutive_ok'))} consecutive</span></td>
<td>{_esc(src.get('elapsed_ms','—'))} ms</td><td>{_format_time_pair(src.get('last_success_at') or src.get('checked_at'))}</td></tr>""")
    options = "".join(f'<option value="{_esc(x)}">{_esc(x)}</option>' for x in categories)
    run_history = load_history(config, limit=60).get("entries", [])
    run_wall = [((x.get("telemetry") or {}).get("wall_ms") or 0) / 1000.0 for x in run_history if (x.get("telemetry") or {}).get("wall_ms") is not None]
    run_cpu = [((x.get("telemetry") or {}).get("cpu_ms") or 0) / 1000.0 for x in run_history if (x.get("telemetry") or {}).get("cpu_ms") is not None]
    run_mem = [((x.get("telemetry") or {}).get("peak_python_memory_kb") or 0) / 1024.0 for x in run_history if (x.get("telemetry") or {}).get("peak_python_memory_kb") is not None]
    run_sources = [(x.get("telemetry") or {}).get("sources_checked") for x in run_history if (x.get("telemetry") or {}).get("sources_checked") is not None]
    failure_rates = []
    for x in run_history:
        counts = x.get("counts") or {}
        total = sum(int(counts.get(k) or 0) for k in ("ok","warn","error"))
        if total:
            failure_rates.append(round(int(counts.get("error") or 0) / total * 100.0, 2))
    telemetry_charts = (
        '<div class="grid">'
        f'<div class="card"><h3>How long Watchtower checks have taken</h3>{_svg_sparkline(run_wall)}</div>'
        f'<div class="card"><h3>Computer processing time used</h3>{_svg_sparkline(run_cpu)}</div>'
        f'<div class="card"><h3>Memory used by Watchtower</h3>{_svg_sparkline(run_mem)}</div>'
        '</div><div class="grid">'
        f'<div class="card"><h3>Data sources checked per run</h3>{_svg_sparkline(run_sources)}</div>'
        f'<div class="card"><h3>Checks that could not be completed</h3>{_svg_sparkline(failure_rates)}</div>'
        '</div>'
    )
    body += '<details class="diagnostics"><summary>System diagnostics</summary><span class="subtext">Runtime telemetry from retained checks. These are operational diagnostics, not source-health scores.</span>' + telemetry_charts + '</details>'
    latency_chart = _bar_chart(sorted([(src.get("name") or sid, src.get("elapsed_ms")) for sid,src in sources.items() if isinstance(src.get("elapsed_ms"),(int,float))], key=lambda x:x[1], reverse=True)[:8], title="Sources taking longest to respond", suffix=" ms")
    category_counts = {}
    for _,src,meta,_,_ in enriched:
        cat = meta.get("category") or src.get("category") or "Other"
        category_counts[cat] = category_counts.get(cat,0)+1
    category_chart = _bar_chart(sorted(category_counts.items(), key=lambda x:x[1], reverse=True), title="Data sources by category")
    body += '<div class="section-head"><div><h2>Source overview</h2><p>Response behavior and source mix across the current cloud and local results.</p></div></div>'
    body += f'<div class="grid"><div class="card">{latency_chart}<span class="subtext">Latest source-check response time; longer does not necessarily mean unhealthy.</span></div><div class="card">{category_chart}<span class="subtext">Number of monitored source observations grouped by data category.</span></div></div>'
    county_direct = [(src.get("name") or sid, src.get("feature_count")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("feature_count"), (int,float))]
    county_fields = [(src.get("name") or sid, src.get("field_count")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("field_count"), (int,float))]
    county_counts_chart = _bar_chart(sorted(county_direct, key=lambda x:x[1], reverse=True)[:10], title="Counties with the most parcel records")
    county_fields_chart = _bar_chart(sorted(county_fields, key=lambda x:x[1], reverse=True)[:10], title="Number of information fields in county parcel data")
    null_ids = [(src.get("name") or sid, src.get("parcel_id_null_count")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("parcel_id_null_count"), (int,float))]
    duplicate_ids = [(src.get("name") or sid, src.get("duplicate_id_extra_rows")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("duplicate_id_extra_rows"), (int,float))]
    null_geometry = [(src.get("name") or sid, src.get("null_geometry_count")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("null_geometry_count"), (int,float))]
    quality_chart = _bar_chart(sorted(null_ids, key=lambda x:x[1], reverse=True), title="Parcel records missing an ID")
    duplicate_chart = _bar_chart(sorted(duplicate_ids, key=lambda x:x[1], reverse=True), title="Records that share the same parcel ID")
    geometry_chart = _bar_chart(sorted(null_geometry, key=lambda x:x[1], reverse=True), title="Parcel records with no mapped shape")
    owner_complete=[]; site_address_complete=[]; mailing_address_complete=[]
    for sid,src in sources.items():
        if not sid.endswith("-parcels-direct"): continue
        profiles=src.get("completeness_profiles") or {}
        if isinstance((profiles.get("owner") or {}).get("complete_percent"), (int,float)): owner_complete.append((src.get("name") or sid, profiles["owner"]["complete_percent"]))
        if isinstance((profiles.get("site_address") or {}).get("complete_percent"), (int,float)): site_address_complete.append((src.get("name") or sid, profiles["site_address"]["complete_percent"]))
        if isinstance((profiles.get("mailing_address") or {}).get("complete_percent"), (int,float)): mailing_address_complete.append((src.get("name") or sid, profiles["mailing_address"]["complete_percent"]))
    owner_chart=_bar_chart(sorted(owner_complete,key=lambda x:x[1]),title="Records with an owner name",suffix="%")
    site_address_chart=_bar_chart(sorted(site_address_complete,key=lambda x:x[1]),title="Records with a property address",suffix="%")
    mailing_address_chart=_bar_chart(sorted(mailing_address_complete,key=lambda x:x[1]),title="Records with an owner mailing address",suffix="%")
    multipart = [(src.get("name") or sid, src.get("geometry_sample_multipart_percent")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("geometry_sample_multipart_percent"),(int,float))]
    complexity = [(src.get("name") or sid, src.get("geometry_sample_avg_vertices")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("geometry_sample_avg_vertices"),(int,float))]
    multipart_chart=_bar_chart(sorted(multipart,key=lambda x:x[1],reverse=True),title="Sampled parcel shapes with multiple parts or holes",suffix="%")
    complexity_chart=_bar_chart(sorted(complexity,key=lambda x:x[1],reverse=True),title="Average parcel-shape complexity")
    body += '<div class="section-head"><div><h2>Parcel-source quality</h2><p>Comparative quality indicators for directly monitored county parcel layers.</p></div></div>'
    body += f'<div class="grid"><div class="card">{county_counts_chart}</div><div class="card">{county_fields_chart}</div></div><div class="grid"><div class="card">{quality_chart}</div><div class="card">{duplicate_chart}</div><div class="card">{geometry_chart}</div></div><div class="grid"><div class="card">{owner_chart}</div><div class="card">{site_address_chart}</div><div class="card">{mailing_address_chart}</div></div><div class="grid"><div class="card">{multipart_chart}</div><div class="card">{complexity_chart}</div></div>'
    body += f"""<div class="card"><h2>Data being watched</h2>
<div class="filters"><input id="q" placeholder="Filter datasets…" oninput="filterRows()"><select id="cat" onchange="filterRows()"><option value="">All categories</option>{options}</select><select id="health" onchange="filterRows()"><option value="">All statuses</option><option>ok</option><option>warn</option><option>error</option></select></div>
<table id="datasets"><thead><tr><th>Data source</th><th>Provided by / type</th><th>Status</th><th>Records / change<br><span class="subtext">Current count and change from the prior comparable check</span></th><th>Days since data changed<br><span class="subtext">Days since Watchtower last detected a source-data change</span></th><th>Recent reliability<br><span class="subtext">Successful checks across retained recent history</span></th><th>Response time<br><span class="subtext">Elapsed time for the source request/check</span></th><th>Last successful check<br><span class="subtext">Most recent successful observation, not merely last attempt</span></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<script>function filterRows(){{const q=document.getElementById('q').value.toLowerCase(),c=document.getElementById('cat').value,h=document.getElementById('health').value;document.querySelectorAll('#datasets tbody tr').forEach(r=>{{r.style.display=(!q||r.dataset.name.includes(q))&&(!c||r.dataset.category===c)&&(!h||r.dataset.status===h)?'':'none'}})}};</script>"""
    return _layout("GIS Data Watchtower", body, csrf_token=str(config.get("_csrf_token") or ""))

def render_source(config: dict, source_id: str) -> str:
    state = _dashboard_state(config)
    src = (state.get("sources") or {}).get(source_id)
    if not src:
        return _layout("Source not found", '<div class="card"><h2>Source not found</h2><p><a href="/">Return to dashboard</a></p></div>', csrf_token=str(config.get("_csrf_token") or ""))
    hist = load_history(config, source_filter=source_id, limit=60).get("entries", [])
    stats = _history_stats(hist)
    meta = _source_config_map(config).get(source_id, {})
    provenance = src.get("provenance") or {}
    changes = src.get("changes") or []
    feature_values = [x.get("feature_count") for x in hist]
    latency_values = [x.get("elapsed_ms") for x in hist]
    history_rows = "".join(
        f"<tr><td>{_format_time_pair(x.get('generated_at'))}</td><td>{_esc(x.get('status'))}</td><td>{_esc(f'{x.get("feature_count"):,}' if isinstance(x.get('feature_count'),int) else x.get('feature_count','—'))}</td><td>{_esc(len(x.get('changes') or []))}</td><td>{_esc(x.get('elapsed_ms','—'))} ms</td></tr>"
        for x in reversed(hist[-30:])
    )
    provider = meta.get("provider") or src.get("provider") or "—"
    category = meta.get("category") or src.get("category") or "—"
    source_count_text = _esc(f"{src.get('feature_count'):,}" if isinstance(src.get('feature_count'),int) else src.get('feature_count','—'))
    body = f"""<p><a href="/">← All data sources</a></p><div class="grid">
<div class="card"><div class="muted">Data source</div><h2>{_esc(src.get('name') or source_id)}</h2><code>{_esc(source_id)}</code></div>
<div class="card"><div class="muted">Health</div><div class="metric {_status_class(src.get('status','unknown'))}">{_esc(_health_status(src.get('status','unknown')))}</div><span class="subtext">{_esc('Reporting overdue' if src.get('reporting') == 'stale' else 'Reporting on time')} · {_esc(src.get('worker') or 'local/default')} worker</span></div>
<div class="card"><div class="muted">Record count</div><div class="metric">{source_count_text}</div><span class="subtext">Features or rows reported during the latest successful check.</span></div>
<div class="card"><div class="muted">Recent reliability</div><div class="metric">{_esc(stats.get('success_rate') if stats.get('success_rate') is not None else '—')}%</div><span class="subtext">{_esc(stats.get('consecutive_ok'))} successful checks in a row.</span></div>
<div class="card"><div class="muted">Days since data changed</div><div class="metric">{_esc(stats.get('change_age_days') if stats.get('change_age_days') is not None else '—')}</div><span class="subtext">Elapsed days since Watchtower last detected a meaningful observation change.</span></div></div>
<div class="grid"><div class="card"><h3>Record-count history</h3>{_svg_sparkline(feature_values)}</div><div class="card"><h3>Response-time history</h3>{_svg_sparkline(latency_values)}</div></div>

<div class="section-head"><div><h2>About this data</h2><p>Operational source facts first; low-level adapter and coordinate details remain expandable below.</p></div></div>
<div class="definition-grid">
<div class="definition-group"><h3>Source</h3><dl class="definition-list">
<dt>Provided by</dt><dd>{_esc(provider)}</dd><dt>Data type</dt><dd>{_esc(category)}</dd><dt>Checked by</dt><dd>{_esc(src.get('worker') or 'local/default')} worker</dd><dt>Reporting</dt><dd>{_esc(src.get('reporting') or 'current')}</dd><dt>Last successful check</dt><dd>{_format_time_pair(src.get('last_success_at') or src.get('checked_at'))}</dd><dt>Changes this check</dt><dd>{len(changes)}</dd><dt>Last change found</dt><dd>{_format_time_pair(stats.get('last_change')) if stats.get('last_change') else 'Not yet recorded'}</dd>
</dl></div>
<div class="definition-group"><h3>Parcel quality</h3><dl class="definition-list">
<dt>Records</dt><dd>{source_count_text}</dd><dt>Information fields</dt><dd>{_esc(src.get('field_count','—'))}</dd><dt>Parcel ID field</dt><dd>{_esc(src.get('parcel_id_field','Not identified'))} ({_esc(src.get('parcel_id_confidence','none'))} confidence)</dd><dt>Missing parcel IDs</dt><dd>{_esc(src.get('parcel_id_null_count','Not checked'))}</dd><dt>Duplicate-ID extra rows</dt><dd>{_esc(src.get('duplicate_id_extra_rows','Not checked'))}</dd><dt>Missing mapped shape</dt><dd>{_esc(src.get('null_geometry_count','Not checked'))}</dd>
</dl></div>
<div class="definition-group"><h3>Shape sample</h3><dl class="definition-list">
<dt>Shapes sampled</dt><dd>{_esc(src.get('geometry_sample_size','Not checked'))}</dd><dt>Multipart / holes</dt><dd>{_esc(src.get('geometry_sample_multipart_percent','Not checked'))}%</dd><dt>Average complexity</dt><dd>{_esc(src.get('geometry_sample_avg_vertices','Not checked'))}</dd><dt>Most complex shape</dt><dd>{_esc(src.get('geometry_sample_max_vertices','Not checked'))}</dd>
</dl></div>
</div><br>
<div class="card"><details class="technical"><summary>Technical details</summary><div class="technical-body"><dl class="definition-list">
<dt>Source connection</dt><dd>{_esc(provenance.get('adapter') or src.get('adapter') or src.get('kind'))}</dd>
<dt>Map shape type</dt><dd>{_esc(src.get('geometry_type','—'))}</dd>
<dt>Coordinate system code</dt><dd>{_esc(src.get('wkid','—'))}</dd>
<dt>Parcel map layer</dt><dd>{_esc(src.get('parcel_layer_name','Direct layer'))}</dd>
<dt>Mapped extent</dt><dd><code>{_esc(src.get('spatial_extent','Not reported'))}</code></dd>
<dt>Last checked</dt><dd>{_format_time_pair(provenance.get('observed_at') or src.get('checked_at'))}</dd>
<dt>Publisher modified</dt><dd>{_esc(provenance.get('publisher_modified') or 'Not reported')}</dd>
<dt>Source address</dt><dd><code>{_esc(provenance.get('source_url') or src.get('url'))}</code></dd>
<dt>Structure comparison ID</dt><dd><code>{_esc(src.get('schema_hash'))}</code></dd>
<dt>Observation comparison ID</dt><dd><code>{_esc(src.get('observation_fingerprint'))}</code></dd>
</dl></div></details></div><br>
<div class="card"><h2>Check history</h2><span class="subtext">Recent retained observations for this source.</span><table class="history-table"><thead><tr><th>Last checked</th><th>Status</th><th>Records</th><th>Changes found</th><th>Response time</th></tr></thead><tbody>{history_rows}</tbody></table></div>"""
    return _layout(f"{src.get('name') or source_id}", body, csrf_token=str(config.get("_csrf_token") or ""))

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
            f'<td>{_esc(src.get("feature_count","—"))}</td>'
            f'<td>{_esc(src.get("change_count", 0))}</td><td>{_esc(src.get("checked_at","—"))}</td></tr>'
        )
        detail = f'<p><a href="index.html">← All data sources</a></p><div class="grid">' \
            f'<div class="card"><div class="muted">Data source</div><h2>{_esc(src.get("name") or sid)}</h2></div>' \
            f'<div class="card"><div class="muted">Status</div><div class="metric {_status_class(src.get("status","unknown"))}">{_esc(_health_status(src.get("status","unknown")))}</div></div>' \
            f'<div class="card"><div class="muted">Record count</div><div class="metric">{_esc(src.get("feature_count","—"))}</div></div></div>' \
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

    def __init__(self, server_address, handler_cls, *, max_connections: int = 32):
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
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()


def serve(config: dict, host: str = "127.0.0.1", port: int = 8765) -> None:
    auth_password, auth_username = _dashboard_auth(config, host)
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
            check_sources(config, save=True)
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
            if parsed.path == "/snapshot.json":
                return self._send(200, json.dumps(_statewide_snapshot(config), indent=2), "application/json; charset=utf-8")
            if parsed.path == "/snapshot.csv":
                return self._send(200, _snapshot_csv(_statewide_snapshot(config)), "text/csv; charset=utf-8")
            if parsed.path == "/snapshot.xlsx":
                return self._send_bytes(200, _snapshot_xlsx(_statewide_snapshot(config)), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "watchtower-snapshot.xlsx")
            if parsed.path == "/county-snapshot.json":
                slug = urllib.parse.parse_qs(parsed.query).get("slug", [""])[0]
                snap = _county_snapshot(config, slug)
                return self._send(200 if snap else 404, json.dumps(snap or {"error":"county not found"}, indent=2), "application/json; charset=utf-8")
            if parsed.path == "/county-snapshot.csv":
                slug = urllib.parse.parse_qs(parsed.query).get("slug", [""])[0]
                snap = _county_snapshot(config, slug)
                return self._send(200 if snap else 404, _snapshot_csv(snap) if snap else "county not found", "text/csv; charset=utf-8")
            if parsed.path == "/county-snapshot.xlsx":
                slug = urllib.parse.parse_qs(parsed.query).get("slug", [""])[0]
                snap = _county_snapshot(config, slug)
                if not snap:
                    return self._send(404, "county not found", "text/plain; charset=utf-8")
                return self._send_bytes(200, _snapshot_xlsx(snap), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{slug}-watchtower.xlsx")
            if parsed.path == "/mngac":
                return self._send(200, render_mngac(config))
            if parsed.path == "/mngac.json":
                data = _mngac_data(_dashboard_state(config))
                return self._send(200 if data else 404, json.dumps(data or {"error":"MNGAC completeness data unavailable"}, indent=2), "application/json; charset=utf-8")
            if parsed.path == "/mngac.csv":
                data = _mngac_data(_dashboard_state(config))
                return self._send(200 if data else 404, _mngac_csv(data), "text/csv; charset=utf-8")
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

    server = _BoundedThreadingHTTPServer((host, port), Handler, max_connections=max_connections)
    print(f"GIS Data Watchtower dashboard: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
