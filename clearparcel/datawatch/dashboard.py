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

COUNTIES_FILE = Path(__file__).with_name("minnesota_counties.json")
COUNTY_CONTACTS_FILE = Path(__file__).with_name("minnesota_county_contacts.json")


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

def _layout(title: str, body: str, *, refresh_seconds: int = 30, static: bool = False, csrf_token: str = "") -> str:
    refresh_form = "" if static else (
        '<form method="post" action="/refresh" class="refresh-form">'
        f'<input type="hidden" name="csrf_token" value="{_esc(csrf_token)}">'
        '<button>Check now</button></form>'
    )
    def icon(kind: str) -> str:
        paths = {
            "overview": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
            "counties": '<path d="M4 5h16v14H4z"/><path d="M8 5v14M16 5v14M4 10h16M4 15h16"/>',
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
<meta http-equiv="refresh" content="{refresh_seconds}">
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
@media(max-width:960px){{
  .primary-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
  .definition-grid{{grid-template-columns:1fr}}
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
  #counties thead,#datasets thead,.history-table thead{{display:none}}
  #counties,#counties tbody,#counties tr,#counties td,#datasets,#datasets tbody,#datasets tr,#datasets td,.history-table,.history-table tbody,.history-table tr,.history-table td{{display:block;width:100%}}
  #counties tr,#datasets tr,.history-table tr{{padding:11px 0;border-bottom:1px solid #e6eaee}}
  #counties td,#datasets td,.history-table td{{border:0;padding:4px 2px;white-space:normal;overflow-wrap:anywhere}}
  #counties td:nth-child(2)::before{{content:"Coverage: ";font-weight:700;color:var(--muted)}}
  #counties td:nth-child(3)::before{{content:"Direct sources: ";font-weight:700;color:var(--muted)}}
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
  .definition-list{{grid-template-columns:1fr;gap:2px}} .definition-list dd{{margin-bottom:8px}}
  .mobile-nav{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));width:100%;position:fixed;bottom:0;left:0;right:0;height:62px;background:var(--navy);border-top:1px solid #ffffff18;z-index:50;padding-bottom:env(safe-area-inset-bottom)}}
  .mobile-nav a{{color:#b9d1e2;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;font-size:10px;font-weight:600}}
  .mobile-nav a:hover{{text-decoration:none;color:#fff}} .mobile-nav .nav-icon{{width:18px;height:18px}}
}}
@media(max-width:480px){{
  .primary-grid{{grid-template-columns:1fr}}
  .bar-row{{grid-template-columns:100px minmax(60px,1fr) 40px}}
}}
</style></head><body>
<header><h1>GIS Data Watchtower</h1><div class="actions"><span>Refreshes every {refresh_seconds}s</span>{refresh_form}</div></header>
<div class="app-shell">
<aside class="sidebar"><div class="side-brand"><strong>ClearParcel</strong><small>GIS Data Watchtower</small></div><nav>
<a href="/">{icon("overview")}<span>Overview</span></a>
<a href="/counties">{icon("counties")}<span>Minnesota Counties</span></a>
<a href="/#datasets">{icon("sources")}<span>Data Sources</span></a>
<a href="/#changes">{icon("changes")}<span>Recent Changes</span></a>
<a href="/#alerts">{icon("alerts")}<span>Alerts</span></a>
<a href="/snapshot.xlsx">{icon("export")}<span>Export</span></a>
</nav><div class="side-note">Private dashboard<br><small>Central Time primary</small></div></aside>
<section class="content-shell">
<div class="pagebar"><div class="pagebar-title">{_esc(page_title)}</div><div class="page-actions"><details class="export-menu"><summary>Export</summary><div class="export-pop"><a href="/snapshot.xlsx">Excel (.xlsx)</a><a href="/snapshot.csv">CSV</a><a href="/snapshot.json">JSON</a></div></details></div></div>
<main>{body}</main>
</section></div>
<nav class="mobile-nav" aria-label="Mobile navigation">
<a href="/">{icon("overview")}<span>Overview</span></a><a href="/counties">{icon("counties")}<span>Counties</span></a><a href="/#datasets">{icon("sources")}<span>Sources</span></a><a href="/snapshot.xlsx">{icon("export")}<span>Export</span></a>
</nav>
</body></html>"""


def _load_counties() -> list[dict]:
    try:
        data = json.loads(COUNTIES_FILE.read_text(encoding="utf-8"))
        return data.get("counties", [])
    except (OSError, json.JSONDecodeError):
        return []


def _load_county_contacts() -> dict:
    try:
        data = json.loads(COUNTY_CONTACTS_FILE.read_text(encoding="utf-8"))
        return {str(x.get("county")): x.get("contacts", []) for x in data.get("counties", [])}
    except (OSError, json.JSONDecodeError):
        return {}


def _county_status(config: dict, county: dict, state: dict) -> dict:
    name = county["name"]
    needle = name.lower()
    matches = []
    for sid, src in (state.get("sources") or {}).items():
        if sid == "mn-parcel-county-catalog":
            continue
        source_slug = str(src.get("county_slug") or "").strip().lower()
        if source_slug and source_slug == county["slug"].lower():
            matches.append(src)
    catalog = ((state.get("sources") or {}).get("mn-parcel-county-catalog") or {})
    catalog_record = (catalog.get("county_records") or {}).get(name)
    open_approved = str((catalog_record or {}).get("gac_open_approval", "")).lower() == "true"
    has_data = bool((catalog_record or {}).get("data_url"))
    if matches:
        status = "error" if any(x.get("status") == "error" for x in matches) else "warn" if any(x.get("status") == "warn" for x in matches) else "ok"
    elif catalog_record and open_approved and has_data and catalog.get("status") == "ok":
        status = "catalog"
    elif catalog_record:
        status = "needs-source"
    else:
        status = "not-configured"
    return {"name": name, "slug": county["slug"], "status": status, "sources": matches, "catalog": catalog_record}


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


def render_counties(config: dict) -> str:
    state = _dashboard_state(config)
    counties = [_county_status(config, x, state) for x in _load_counties()]
    monitored = sum(1 for x in counties if x["sources"])
    status_counts = {}
    age_buckets = {"0–30 days": 0, "31–90 days": 0, "91–365 days": 0, "Over 1 year": 0, "No date": 0}
    public_count = 0
    for x in counties:
        status_counts[x["status"]] = status_counts.get(x["status"], 0) + 1
        record = x.get("catalog") or {}
        if str(record.get("gac_open_approval") or "").lower() == "true":
            public_count += 1
        d = _parse_time(_format_arcgis_date(record.get("acqdate")))
        if not d:
            age_buckets["No date"] += 1
        else:
            if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
            days = max(0, (dt.datetime.now(dt.timezone.utc) - d).days)
            bucket = "0–30 days" if days <= 30 else "31–90 days" if days <= 90 else "91–365 days" if days <= 365 else "Over 1 year"
            age_buckets[bucket] += 1
    rows = "".join(
        f'<tr data-name="{_esc(x["name"].lower())}" data-status="{_esc(x["status"])}"><td><a href="/county?slug={urllib.parse.quote(x["slug"])}"><strong>{_esc(x["name"])} County</strong></a></td><td><span class="pill {_esc(x["status"])}">{_esc(_friendly_status(x["status"]))}</span></td><td>{len(x["sources"])}</td></tr>'
        for x in counties
    )
    body = f'<div class="grid"><div class="card"><div class="muted">Minnesota counties</div><div class="metric">{len(counties)}</div><span class="subtext">Counties represented in the statewide county dashboard index.</span></div><div class="card"><div class="muted">Counties checked directly</div><div class="metric">{monitored}</div><span class="subtext">Counties with at least one county-specific source that Watchtower actively checks.</span></div><div class="card"><div class="muted">Counties with public parcel data</div><div class="metric">{public_count}</div><span class="subtext">Counties whose MnGeo catalog record indicates public parcel-data approval.</span></div></div>' \
        f'<div class="grid"><div class="card">{_bar_chart([( _friendly_status(k), v) for k,v in sorted(status_counts.items())], title="County parcel-data availability")}<span class="subtext">How Watchtower currently knows about each county.</span></div><div class="card">{_bar_chart(list(age_buckets.items()), title="MnGeo parcel update age")}<span class="subtext">Age of the county acquisition/update date reported in the MnGeo parcel catalog; this is not Watchtower check time.</span></div></div><div class="card"><h2>Minnesota county dashboards</h2><p class="muted">Coverage describes how Watchtower knows about each county: Directly monitored means a county-specific source is checked; MnGeo update data only means catalog information is available without a direct county check; Direct source not yet identified means more source research is needed.</p><p class="subtext">Use Export in the page toolbar for statewide Excel, CSV, or JSON.</p>' \
        '<div class="filters"><input id="cq" placeholder="Filter counties…" oninput="filterCounties()"><select id="cs" onchange="filterCounties()"><option value="">All coverage types</option><option value="ok">Directly monitored</option><option value="catalog">MnGeo update data only</option><option value="needs-source">Direct source not yet identified</option><option value="not-configured">No source information yet</option><option value="warn">Needs attention</option><option value="error">Check failed</option></select></div>' \
        f'<table id="counties"><thead><tr><th>County</th><th>Coverage<br><span class="subtext">How Watchtower currently knows about this county</span></th><th>Direct sources<br><span class="subtext">County-specific sources actively checked</span></th></tr></thead><tbody>{rows}</tbody></table></div>' \
        "<script>function filterCounties(){const q=document.getElementById('cq').value.toLowerCase(),s=document.getElementById('cs').value;document.querySelectorAll('#counties tbody tr').forEach(r=>r.style.display=(!q||r.dataset.name.includes(q))&&(!s||r.dataset.status===s)?'':'none')}</script>"
    return _layout("Minnesota Counties — GIS Data Watchtower", '<p><a href="/">← Watchtower overview</a></p>'+body, csrf_token=str(config.get("_csrf_token") or ""))


def render_county(config: dict, slug: str) -> str:
    state = _dashboard_state(config)
    county = next((x for x in _load_counties() if x.get("slug") == slug), None)
    if not county:
        return _layout("County not found", '<p><a href="/counties">← Minnesota counties</a></p><div class="card">County not found.</div>', csrf_token=str(config.get("_csrf_token") or ""))
    info = _county_status(config, county, state)
    source_cards = ""
    for src in info["sources"]:
        source_cards += f'<div class="card"><h3>{_esc(src.get("name"))}</h3><p><strong>Status:</strong> {_esc(src.get("status"))}<br><strong>Records:</strong> {_esc(src.get("feature_count","—"))}<br><strong>Provided by:</strong> {_esc(src.get("provider","—"))}<br><strong>Last checked:</strong> {_esc(src.get("checked_at","—"))}</p></div>'
    catalog = info.get("catalog") or {}
    if not source_cards and catalog:
        approval = str(catalog.get("gac_open_approval") or "—")
        data_url = _safe_url(catalog.get("data_url"))
        viewer_url = _safe_url(catalog.get("viewer_url"))
        source_links = (f'<a href="{_esc(data_url)}" target="_blank" rel="noopener">Open parcel data</a>' if data_url else "No open data URL supplied")
        if viewer_url:
            source_links += f' · <a href="{_esc(viewer_url)}" target="_blank" rel="noopener">Viewer</a>'
        source_cards = f'<div class="card"><h3>County parcel update information</h3><p><strong>Counties with public parcel data:</strong> {_esc(approval)}<br><strong>Last county update:</strong> {_esc(_format_arcgis_date(catalog.get("acqdate")))}<br><strong>MnGeo listing refreshed:</strong> {_esc(_format_arcgis_date(catalog.get("rundate")))}<br><strong>Parcel links:</strong> {source_links}</p></div>'
    elif not source_cards:
        source_cards = '<div class="card"><h3>A usable parcel-data source has not been found yet</h3><p>No direct county source or MnGeo parcel catalog record is currently available.</p></div>'
    contacts = _load_county_contacts().get(county["name"], [])
    contact_rows = ""
    for contact in contacts:
        email = str(contact.get("email") or "").strip().rstrip(".")
        phone = str(contact.get("phone") or "").strip()
        email_html = f'<a href="mailto:{_esc(email)}">{_esc(email)}</a>' if email else "—"
        phone_html = f'<a href="tel:{_esc(phone)}">{_esc(phone)}</a>' if phone else "—"
        contact_rows += f'<tr><td><strong>{_esc(contact.get("name") or "TBD")}</strong></td><td>{_esc(contact.get("title") or "—")}</td><td>{_esc(contact.get("department") or "—")}</td><td>{phone_html}</td><td>{email_html}</td></tr>'
    if not contact_rows:
        contact_rows = '<tr><td colspan="5">No contact is currently listed in the MnGeo county GIS directory.</td></tr>'
    contacts_html = f'<div class="card"><h2>County GIS contacts</h2><p class="muted">Source address: <a href="https://mn.gov/mngeo/community/gis-contacts/county-gis-contacts/" target="_blank" rel="noopener">Minnesota Geospatial Information Office (MnGeo)</a>. MnGeo describes this as a starting-point directory and notes that it depends on updates from associated jurisdictions.</p><table><thead><tr><th>Name</th><th>Title</th><th>Department</th><th>Phone</th><th>Email</th></tr></thead><tbody>{contact_rows}</tbody></table></div>'
    export_links = f'<p><a href="/county-snapshot.csv?slug={urllib.parse.quote(slug)}">Download county snapshot (CSV)</a> · <a href="/county-snapshot.xlsx?slug={urllib.parse.quote(slug)}">Download county snapshot (Excel)</a> · <a href="/county-snapshot.json?slug={urllib.parse.quote(slug)}">Download county snapshot (JSON)</a></p>'
    body = f'<p><a href="/counties">← Minnesota counties</a></p>{export_links}<div class="grid"><div class="card"><div class="muted">County</div><h2>{_esc(county["name"])} County</h2></div><div class="card"><div class="muted">Data availability</div><div class="metric {_esc(info["status"])}">{_esc(_friendly_status(info["status"]).upper())}</div></div><div class="card"><div class="muted">Direct data sources</div><div class="metric">{len(info["sources"])}</div></div></div><div class="grid">{source_cards}</div><br>{contacts_html}'
    return _layout(f'{county["name"]} County — Watchtower', body, csrf_token=str(config.get("_csrf_token") or ""))

def _county_snapshot(config: dict, slug: str) -> dict | None:
    state = _dashboard_state(config)
    county = next((x for x in _load_counties() if x.get("slug") == slug), None)
    if not county:
        return None
    info = _county_status(config, county, state)
    catalog = info.get("catalog") or {}
    return {
        "county": county["name"],
        "status": info["status"],
        "last_county_update": _format_arcgis_date(catalog.get("acqdate")),
        "catalog_refresh_date": _format_arcgis_date(catalog.get("rundate")),
        "public_data_approved": str(catalog.get("gac_open_approval") or "").lower() == "true",
        "parcel_data_url": _safe_url(catalog.get("data_url")) or "",
        "parcel_viewer_url": _safe_url(catalog.get("viewer_url")) or "",
        "direct_sources": [
            {
                "name": x.get("name"), "status": x.get("status"),
                "feature_count": x.get("feature_count"), "checked_at": x.get("checked_at"),
                "worker": x.get("worker"), "last_success_at": x.get("last_success_at"),
                "reporting": x.get("reporting"), "stale": x.get("stale"), "worker_stale": x.get("worker_stale"),
            } for x in info.get("sources", [])
        ],
        "contacts": _load_county_contacts().get(county["name"], []),
        **_snapshot_time_fields(dt.datetime.now(dt.timezone.utc).isoformat(), "snapshot_created"),
    }


def _statewide_snapshot(config: dict) -> dict:
    state = _dashboard_state(config)
    counties = []
    for county in _load_counties():
        item = _county_snapshot(config, county["slug"])
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
        "overall": state.get("overall"),
        "county_count": len(counties),
        "source_count": len(aggregate_sources),
        "sources": aggregate_sources,
        "workers": state.get("workers") or {},
        "counties": counties,
    }


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
    fields = ["county","status","last_county_update","catalog_refresh_date","public_data_approved","parcel_data_url","parcel_viewer_url","worker_provenance","stale_source_count","contact_names"]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in [snapshot]:
        writer.writerow({key: _csv_safe(value) for key, value in {
            "county": row.get("county"), "status": row.get("status"),
            "last_county_update": row.get("last_county_update"),
            "catalog_refresh_date": row.get("catalog_refresh_date"),
            "public_data_approved": row.get("public_data_approved"),
            "parcel_data_url": row.get("parcel_data_url"),
            "parcel_viewer_url": row.get("parcel_viewer_url"),
            "worker_provenance": "; ".join(sorted({str(x.get("worker")) for x in row.get("direct_sources",[]) if x.get("worker")})),
            "stale_source_count": sum(1 for x in row.get("direct_sources",[]) if x.get("stale") or x.get("worker_stale")),
            "contact_names": "; ".join(x.get("name","") for x in row.get("contacts",[]) if x.get("name")),
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

def _snapshot_xlsx(snapshot: dict) -> bytes:
    county_rows = [["County","Status","Last county update","Catalog refresh date","Public data approved","Parcel data URL","Parcel viewer URL","Contact names"]]
    source_rows = [["County","Source","Status","Record count","Worker","Reporting","Stale source","Stale worker","Last successful check","Last checked"]]
    contact_rows = [["County","Name","Title","Department","Phone","Email"]]
    rows = snapshot.get("counties") if "counties" in snapshot else [snapshot]
    for row in rows:
        county = row.get("county") or ""
        county_rows.append([county,row.get("status"),row.get("last_county_update"),row.get("catalog_refresh_date"),bool(row.get("public_data_approved")),row.get("parcel_data_url"),row.get("parcel_viewer_url"),"; ".join(x.get("name","") for x in row.get("contacts",[]) if x.get("name"))])
        for source in row.get("direct_sources", []):
            if "sources" not in snapshot:
                source_rows.append([county,source.get("name"),source.get("status"),source.get("feature_count"),source.get("worker"),source.get("reporting"),bool(source.get("stale")),bool(source.get("worker_stale")),source.get("last_success_at"),source.get("checked_at")])
        for contact in row.get("contacts", []):
            contact_rows.append([county,contact.get("name"),contact.get("title"),contact.get("department"),contact.get("phone"),contact.get("email")])
    if "sources" in snapshot:
        for source in snapshot.get("sources", []):
            source_rows.append([source.get("county"),source.get("name"),source.get("status"),source.get("feature_count"),source.get("worker"),source.get("reporting"),bool(source.get("stale")),bool(source.get("worker_stale")),source.get("last_success_at"),source.get("checked_at")])
    sheets=[("Counties",county_rows),("Sources",source_rows),("Contacts",contact_rows)]
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>')
        zf.writestr("_rels/.rels",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{html.escape(name,quote=True)}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+'</Relationships>')
        for i,(_,data) in enumerate(sheets,1): zf.writestr(f"xl/worksheets/sheet{i}.xml",_xlsx_sheet_xml(data))
    return out.getvalue()


def _friendly_status(value: str) -> str:
    return {
        "ok": "Directly monitored",
        "catalog": "MnGeo update data only",
        "needs-source": "Direct source not yet identified",
        "not-configured": "No source information yet",
        "warn": "Needs attention",
        "error": "Check failed",
    }.get(value, value.replace("-", " ").title())


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
        stale = bool(worker.get("stale"))
        worker_telemetry = worker.get("telemetry") or {}
        duration = worker_telemetry.get("wall_ms")
        duration_text = f"{duration / 1000.0:.1f}s" if isinstance(duration, (int, float)) else "—"
        source_count = worker.get("source_count")
        freshness_text = "Reporting overdue" if stale else "Reporting current"
        worker_cards.append(f"""<div class="card worker-card">
<div><h3><span class="status-dot {worker_status}"></span>{_esc(worker_name.title())} worker</h3><span class="subtext">{_esc(freshness_text)} · {_esc(worker_status.upper())}</span></div>
<div class="pill {_esc(worker_status)}">{_esc(worker_status)}</div>
<div class="worker-meta">
<div><span class="muted">Sources</span><strong>{_esc(source_count if source_count is not None else "—")}</strong></div>
<div><span class="muted">Run time</span><strong>{_esc(duration_text)}</strong></div>
<div><span class="muted">Last success</span><strong style="font-size:13px">{_format_time_pair(worker.get("last_success_at") or worker.get("checked_at"))}</strong></div>
</div></div>""")
    body = f"""<div class="grid primary-grid">
<div class="card"><div class="muted">Overall health</div><div class="metric {state.get('overall','')}">{_esc(state.get('overall','unknown').upper())}</div><span class="subtext">Combined health of all monitored sources in the latest saved aggregate.</span></div>
<div class="card"><div class="muted">Data sources</div><div class="metric">{len(sources)}</div><span class="subtext">Source observations represented in the unified Watchtower state.</span></div>
<div class="card"><div class="muted">Problems</div><div class="metric">{counts.get('warn',0) + counts.get('error',0)}</div><span class="subtext">Sources reporting a warning or failed check. Stale reporting is counted separately.</span></div>
<div class="card"><div class="muted">Overdue</div><div class="metric">{state.get('stale_sources',0)}</div><span class="subtext">{state.get('stale_workers',0)} worker(s) overdue · freshness threshold, not source failure.</span></div>
</div>
<div class="section-head"><div><h2>Workers</h2><p>Hybrid execution health and the most recent successful run from each worker.</p></div></div>
<div class="grid worker-grid">{''.join(worker_cards) or '<div class="card muted">Worker metadata has not been reported yet.</div>'}</div>
<div class="activity-strip">
<div class="card"><div class="muted">Recently changed</div><div class="metric">{changed_30}</div><span class="subtext">Sources where Watchtower detected a recorded data change within the last 30 days.</span></div>
<div class="card"><div class="muted">Aggregate updated</div><strong>{_format_time_pair(state.get('generated_at'))}</strong><span class="subtext">Time the unified aggregate was last generated from worker observations.</span><br><a href="/counties">View all 87 Minnesota county dashboards →</a></div>
</div>"""
    if alerts:
        body += '<div class="card"><h2>Needs attention</h2>' + "".join(
            f'<p class="{_esc(a.get("severity","warn"))}"><strong>{_esc(a.get("name") or a.get("source"))}</strong> — {_esc(a.get("message"))}</p>'
            for a in alerts
        ) + "</div><br>"
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
<td><span class="pill {_esc(src.get('status',''))}">{_esc(_friendly_status(src.get('status','unknown')))}</span><br><span class="muted">{_esc(src.get('reporting','current'))} reporting · {_esc(src.get('worker') or 'default')} worker</span></td>
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
    body += '<div class="section-head"><div><h2>Source overview</h2><p>Response behavior and source mix in the current aggregate.</p></div></div>'
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
<div class="card"><div class="muted">Status</div><div class="metric {_esc(src.get('status',''))}">{_esc(src.get('status','unknown').upper())}</div><span class="subtext">{_esc(src.get('reporting') or 'current')} reporting · {_esc(src.get('worker') or 'local/default')} worker</span></div>
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
    return _layout(f"Watchtower — {src.get('name') or source_id}", body, csrf_token=str(config.get("_csrf_token") or ""))

def _sanitize_public_state(state: dict) -> dict:
    """Return only user-facing monitoring facts safe for public/API use."""
    public = {
        "schema_version": state.get("schema_version"),
        "generated_at": state.get("generated_at"),
        "overall": state.get("overall"),
        "counts": state.get("counts", {}),
        "sources": {},
    }
    for sid, src in (state.get("sources") or {}).items():
        public["sources"][sid] = {
            key: src.get(key)
            for key in (
                "id", "name", "provider", "category", "status", "feature_count",
                "checked_at", "changes", "worker", "last_success_at", "last_report_at",
                "stale", "worker_stale", "health", "reporting",
            )
            if src.get(key) is not None
        }
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
            f'<td><span class="pill {_esc(src.get("status",""))}">{_esc(_friendly_status(src.get("status","unknown")))}</span></td>'
            f'<td>{_esc(src.get("provider") or "—")}</td>'
            f'<td>{_esc(src.get("category") or "—")}</td>'
            f'<td>{_esc(src.get("feature_count","—"))}</td>'
            f'<td>{_esc(len(src.get("changes") or []))}</td><td>{_esc(src.get("checked_at","—"))}</td></tr>'
        )
        detail = f'<p><a href="index.html">← All data sources</a></p><div class="grid">' \
            f'<div class="card"><div class="muted">Data source</div><h2>{_esc(src.get("name") or sid)}</h2></div>' \
            f'<div class="card"><div class="muted">Status</div><div class="metric {_esc(src.get("status",""))}">{_esc(_friendly_status(src.get("status","unknown")))}</div></div>' \
            f'<div class="card"><div class="muted">Record count</div><div class="metric">{_esc(src.get("feature_count","—"))}</div></div></div>' \
            f'<div class="card"><h2>About this data</h2><p><strong>Provided by:</strong> {_esc(src.get("provider") or "—")}<br>' \
            f'<strong>Data type:</strong> {_esc(src.get("category") or "—")}<br><strong>Last checked:</strong> {_esc(src.get("checked_at") or "—")}<br>' \
            f'<strong>Changes found this check:</strong> {_esc(len(src.get("changes") or []))}</p></div>'
        (output / filename).write_text(_layout(f'Watchtower — {src.get("name") or sid}', detail, refresh_seconds=300, static=True), encoding="utf-8")

    body = f'<div class="grid"><div class="card"><div class="muted">Overall status</div><div class="metric {public.get("overall","")}">{_esc(str(public.get("overall","unknown")).upper())}</div></div>' \
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


def serve(config: dict, host: str = "127.0.0.1", port: int = 8765) -> None:
    auth_password, auth_username = _dashboard_auth(config, host)
    csrf_token = secrets.token_urlsafe(32)
    config["_csrf_token"] = csrf_token
    refresh_lock = threading.Lock()
    refresh_state = {"last_started": 0.0}
    refresh_cooldown_seconds = int(config.get("dashboard_refresh_cooldown_seconds", 300))

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
            try:
                length = min(int(self.headers.get("Content-Length", "0")), 4096)
            except ValueError:
                length = 0
            form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
            token = (form.get("csrf_token") or [""])[0]
            if not _valid_refresh_request(token, csrf_token, self.headers.get("Sec-Fetch-Site")):
                return self._send(403, "Refresh request rejected.", "text/plain; charset=utf-8")
            threading.Thread(target=_guarded_refresh, daemon=True).start()
            self.send_response(303); self.send_header("Location", "/"); self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"GIS Data Watchtower dashboard: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
