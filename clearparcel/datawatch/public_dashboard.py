from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import threading
import time
import urllib.parse
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from clearparcel.datawatch.dashboard import (
    _BoundedThreadingHTTPServer,
    _county_snapshot,
    _county_monitoring_counts,
    _county_profiles,
    _dashboard_state,
    _health_status,
    _gac_data,
    _mngac_data,
    _mngac_map_svg,
    _statewide_snapshot,
    _status_class,
    render_counties,
    render_county,
    render_mngac,
)
from clearparcel.datawatch.dashboard_exports import _mngac_csv, _snapshot_csv, _snapshot_xlsx
from clearparcel.datawatch.dashboard_templates import _esc, _layout
from clearparcel.datawatch.dashboard_routes import dispatch_snapshot_exports
from clearparcel.datawatch.parcel_access import load_parcel_access
from clearparcel.datawatch.county_profile_exports import county_profiles_csv, parcel_sources_csv
from clearparcel.datawatch.county_profiles import county_profile_counts, _latest, _timestamp
from clearparcel.datawatch.county_profile_panel import render_county_profile_panel, percentage_legend, percentage_color_js, research_summary
from clearparcel.datawatch.storage import backend_from_env
from clearparcel.datawatch.public_values import sanitize_source_metadata
from clearparcel.datawatch.build_info import application_identity
from clearparcel.datawatch.gac_standards import normalize_standard_key
from clearparcel.datawatch.analytics import posthog_csp_sources
from clearparcel.datawatch.dashboard_summary import summary_for, render_diagnostics
from clearparcel.datawatch.public_details import dispatch_public_details, encode_response


from clearparcel.datawatch.public_projection import (
    _approval,
    _catalog_date,
    _project,
    _public_count,
    _public_date,
    _public_number,
    _public_status,
    _records,
    _sanitize_catalog_records,
    _sanitize_completeness,
    _sanitize_gac,
    _sanitize_mngac,
    sanitize_public_render_state,
)


def _publication_max_age_seconds() -> int:
    """Use one bounded publication threshold for the view and health endpoint."""
    return max(60, min(int(os.environ.get("WATCHTOWER_PUBLIC_MAX_PUBLICATION_AGE_SECONDS", "1800")), 86400))


def _publication_health(state: dict, *, max_age_seconds: int, now: dt.datetime | None = None) -> tuple[bool, dict]:
    stamp = str(state.get("public_published_at") or "").strip()
    if not stamp:
        return False, {"status": "stale", "reason": "publication_timestamp_missing"}
    try:
        published = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return False, {"status": "stale", "reason": "publication_timestamp_invalid"}
    now = now or dt.datetime.now(dt.timezone.utc)
    age_seconds = max(0, int((now - published.astimezone(dt.timezone.utc)).total_seconds()))
    payload = {"status": "ok", "public_published_at": stamp, "age_seconds": age_seconds}
    if age_seconds > max_age_seconds:
        payload["status"] = "stale"
        payload["reason"] = "publication_too_old"
        return False, payload
    return True, payload


def _public_time(value) -> str:
    if not value:
        return "—"
    try:
        if len(str(value)) == 10:
            return dt.date.fromisoformat(str(value)).isoformat()
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return str(value)
        local = parsed.astimezone(ZoneInfo("America/Chicago"))
        time_text = local.strftime("%I:%M %p").lstrip("0")
        return f"{local.strftime('%b')} {local.day}, {local.year} · {time_text} {local.tzname()}"
    except (ValueError, TypeError):
        return str(value)


def _public_age(value) -> str:
    if not value:
        return "Unavailable"
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        seconds = max(0, int((dt.datetime.now(dt.timezone.utc) - parsed.astimezone(dt.timezone.utc)).total_seconds()))
    except (ValueError, TypeError):
        return "Unavailable"
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hr ago"
    return f"{hours // 24} days ago"


def render_public_dashboard(config: dict) -> str:
    state = _dashboard_state(config)
    sources = state.get("sources") or {}
    counts = state.get("counts") or {}
    workers = state.get("workers") or {}
    mngac = _mngac_data(state)
    healthy = int(counts.get("ok") or 0)
    issues = int(counts.get("warn") or 0) + int(counts.get("error") or 0)
    published_at = state.get("public_published_at")
    publication_healthy, publication_health = _publication_health(state, max_age_seconds=_publication_max_age_seconds())
    publication_reporting = "Current" if publication_healthy else "Overdue" if publication_health.get("reason") == "publication_too_old" else "Unknown"
    checked_at = _latest(source.get("checked_at") for source in sources.values())
    now = dt.datetime.now(dt.timezone.utc)
    stale_after = dt.timedelta(minutes=int(config.get("source_stale_minutes", 1560)))
    overdue = sum(bool((stamp := _timestamp(source.get("checked_at"))) and now - stamp > stale_after) for source in sources.values())
    unknown_checks = sum(_timestamp(source.get("checked_at")) is None for source in sources.values())
    research = load_parcel_access()
    profiles = _county_profiles(config, state, research)
    monitoring = county_profile_counts(profiles)
    all_field = (mngac or {}).get("field_population_percent")
    mandatory = (mngac or {}).get("mandatory_population_percent")
    parcel_records = (mngac or {}).get("record_count")
    parcel_records_label = f"{parcel_records:,}" if isinstance(parcel_records, int) else "Not available"

    rows = []
    for source_id, source in sorted(
        sources.items(),
        key=lambda item: str((item[1] or {}).get("name") or item[0]).lower(),
    ):
        name = source.get("name") or source_id
        status = source.get("status") or "unknown"
        rows.append(
            f'<tr data-name="{_esc(str(name).lower())}" data-status="{_esc(status)}">'
            f'<td><a href="/source?{urllib.parse.urlencode({"id": source_id})}"><strong>{_esc(name)}</strong></a>'
            f'<br><span class="subtext">{_esc(source.get("category") or "Other")}</span></td>'
            f'<td>{_esc(source.get("provider") or "—")}</td>'
            f'<td><span class="pill {_status_class(status)}">{_esc(_health_status(status))}</span></td>'
            f'<td>{_esc(f"{source.get("feature_count"):,}" if isinstance(source.get("feature_count"), int) else source.get("feature_count") or "—")}</td>'
            f'<td>{_esc(source.get("change_count") or 0)}</td>'
            f'<td>{_esc(_public_time(source.get("last_success_at")))}</td>'
            '</tr>'
        )

    worker_cards = []
    for name in sorted(workers):
        worker = workers[name] or {}
        status = str(worker.get("overall") or "unknown")
        reported = _timestamp(worker.get("last_report_at") or worker.get("checked_at"))
        reporting = "Reporting unknown" if reported is None else "Reporting overdue" if now - reported > dt.timedelta(minutes=int(config.get("worker_stale_minutes", 1560))) else "Reporting on time"
        worker_cards.append(
            '<div class="card worker-card">'
            f'<div><h3><span class="status-dot {_status_class(status)}"></span>{_esc(name.title())} monitoring path</h3>'
            f'<span class="subtext" data-worker-report="{_esc(name)}">{_esc(_health_status(status))} · {_esc(reporting)}</span></div>'
            '<div class="worker-meta">'
            f'<div><span class="muted">Sources</span><strong>{_esc(worker.get("source_count", "—"))}</strong></div>'
            f'<div><span class="muted">Last successful provider check</span><strong>{_esc(_public_time(worker.get("last_success_at")))}</strong></div>'
            f'<div><span class="muted">Last worker report</span><strong>{_esc(_public_time(worker.get("last_report_at") or worker.get("checked_at")))}</strong></div>'
            '</div></div>'
        )

    map_data = {}
    for county_name, county in ((mngac or {}).get("counties") or {}).items():
        map_data[county_name] = {
            "pct": county.get("mandatory_population_percent"),
            "records": county.get("record_count"),
            "fields": county.get("fields_with_values"),
            "field_count": county.get("field_count"),
            "slug": county.get("slug"),
        }
    map_json = json.dumps(map_data, ensure_ascii=False).replace("</", "<\\/")
    map_svg = _mngac_map_svg(width=620, height=560)
    summary = summary_for(config, state, profiles=profiles, research=research)
    profile_panel = render_county_profile_panel(profiles, revision=summary["content_revision"])
    diagnostics = render_diagnostics(summary)
    county_options = ''.join(f'<option value="{_esc(slug)}">{_esc(p["county"]["name"])} County</option>'
                             for slug, p in sorted(profiles.items(), key=lambda item: item[1]["county"]["name"]))
    monitoring_json = json.dumps({slug: p["monitoring"]["paths"] for slug, p in profiles.items()})

    body = f"""
<div class="summary-v2">
  <div class="card"><div class="muted">Dataset/service entries monitored</div><div class="metric">{len(sources)}</div><span class="subtext">All data types · entries, not counties or unique providers</span></div>
  <div class="card"><div class="muted">Entries healthy at last check</div><div class="metric ok">{healthy}</div><span class="subtext">{issues} had issues at their last check</span></div>
  <div class="card"><div class="muted">Minnesota counties</div><div class="metric">87</div><span class="subtext">Statewide county profile index</span></div>
  <div class="card"><div class="muted">Counties with parcel observations</div><div class="metric">{monitoring["active"]}/87</div><span class="subtext">{monitoring["mngeo_open"]} via MnGeo open parcels · {monitoring["county_direct"]} via county-direct sources · each county counted once</span></div>
  <div class="card"><div class="muted">Parcel all-field population</div><div class="metric">{_esc(f"{all_field:.2f}%" if isinstance(all_field,(int,float)) else "—")}</div><span class="subtext">Across all 91 standard fields</span></div>
  <div class="card"><div class="muted">Parcel mandatory-field population</div><div class="metric">{_esc(f"{mandatory:.2f}%" if isinstance(mandatory,(int,float)) else "—")}</div><span class="subtext">Record-weighted statewide rate</span></div>
</div>
<p class="mngac-note">A source is a monitored dataset or service entry across any data type. Parcel coverage counts unique counties observed through county-direct or statewide sources. One statewide source can cover many counties; overlapping paths count each county once.</p>

<div class="section-head"><div><h2>Explore Minnesota GIS data</h2><p>Select any county to inspect its complete parcel source profile.</p></div><a href="/counties">All 87 counties →</a></div>
<div class="hero-panel">
  <div class="card">
    <label>Map view<select id="overview-metric"><option value="monitoring">Monitoring paths</option><option value="completeness">MN GAC mandatory-field completeness</option></select></label>
    <label for="overview-county-select">Find a county</label><select id="overview-county-select"><option value="">Choose a county…</option>{county_options}</select>
    <div class="mngac-map-panel">{map_svg}<div id="overview-legend"></div></div>
  </div>
  <div class="card hero-copy">
    <div class="muted">Selected county</div>
    <h2 id="home-county-name">Choose a county</h2>
    <p id="home-county-detail">The map shows active parcel monitoring paths: county-direct, MnGeo open parcels, both, or no active parcel monitoring path. Select a county to inspect its complete source profile.</p>
    <div class="hero-stat">
      <div><small>Mandatory-field population</small><b id="home-county-rate">—</b></div>
      <div><small>Parcel records</small><b id="home-county-records">—</b></div>
      <div><small>Fields with values</small><b id="home-county-fields">—</b></div>
      <div><small>Statewide parcels</small><b>{parcel_records_label}</b></div>
    </div>
    <div class="hero-actions" style="margin-top:16px">
      <a id="home-county-link" class="primary" href="/counties">Open county profile</a>
      <a href="/mngac">Explore all 91 MN GAC fields</a>
    </div>
  </div>
</div>

<div class="card"><h3>Parcel source research</h3>{research_summary(profiles)}</div>
{diagnostics}
<div class="section-head"><div><h2>Latest Watchtower activity</h2><p>Public monitoring results, separated from internal provider diagnostics.</p></div></div>
<div class="activity-strip">
  <div class="card"><div class="muted">Latest public publication</div><div class="metric" data-age-kind="publication" data-age-time="{_esc(published_at or "")}">{_esc(_public_age(published_at))}</div><span id="public-publication-time" class="subtext">{_esc(_public_time(published_at))}</span><p>When the public snapshot was published. Publication copies existing results and does not check GIS providers again.</p><p id="public-publication-status">Public publication reporting: {_esc(publication_reporting)}</p></div>
  <div class="card"><div class="muted">Latest provider check in this snapshot</div><div class="metric" data-age-time="{_esc(checked_at or "")}">{_esc(_public_age(checked_at))}</div><span class="subtext">{_esc(_public_time(checked_at))}</span><p>The newest provider check included here, not the provider’s dataset update date. Other sources may have older checks.</p><p id="source-reporting-status" class="{"warn" if overdue or unknown_checks else "muted"}">Source reporting: {overdue} overdue · {unknown_checks} without a check time. Reporting becomes overdue after {_esc(config.get("source_stale_minutes", 1560))} minutes without a provider check (26 hours by default). Publication freshness is separate.</p></div>
</div>

<div class="section-head"><div><h2>Data sources</h2><p>Dataset and service checks across all data types. A statewide parcel service covers multiple counties; source entries and county coverage are different counts.</p></div><span>{len(sources)} dataset/service entries · {monitoring["active"]} counties with parcel observations</span></div>
<div class="card" id="datasets">
  <div class="filters"><input id="q" aria-label="Search data sources" placeholder="Search data sources…" oninput="filterRows()"><select id="health" aria-label="Source health" onchange="filterRows()"><option value="">All statuses</option><option>ok</option><option>warn</option><option>error</option></select></div>
  <table><thead><tr><th>Data source</th><th>Provided by</th><th>Status</th><th>Records</th><th>Changes</th><th>Last success</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
</div>

<div class="section-head"><div><h2>System status</h2><p>Worker reports show when monitoring results last arrived. Last success can remain old after a failed or missed run. A fresh public publication does not prove either worker ran recently.</p></div></div>
<div class="grid worker-grid">{"".join(worker_cards) or '<div class="card muted">System metadata is unavailable.</div>'}</div>
<div class="card" id="alerts"><h3>Public data boundary</h3><p class="subtext">This read-only site shares dataset availability, record counts, check times, county access research, and MN GAC field-population statistics. It does not distribute parcel datasets or provide live property records. Use the approved official product links in county profiles to obtain data under each provider’s terms.</p><p class="subtext">The public snapshot contains a selected summary of monitoring results. Private connection settings, credentials, internal change-tracking details, and controls for running checks are excluded. Refreshing this page reloads published results; it does not contact GIS providers. Publication time, provider check time, and dataset update time describe different events.</p></div>

<script>
(function(){{
  const countyData={map_json};
  const root=document;
  const monitoringPaths={monitoring_json};
  const selector=root.getElementById("overview-metric");
  let selectedPath=null;
  function monitoringLabel(paths){{
    return paths.length===2?'Both county-direct and MnGeo open parcel monitoring paths':paths.includes('county-direct')?'County-direct parcel monitoring path':paths.includes('mngeo-open')?'MnGeo open parcel monitoring path':'No active parcel monitoring path';
  }}
  function updateDescription(){{
    const detail=root.getElementById('home-county-detail');
    if(selector.value==='monitoring'){{
      detail.textContent=selectedPath?monitoringLabel(monitoringPaths[selectedPath.dataset.slug]||[])+'. Statewide completeness statistics below are separate from monitoring coverage.':'The map shows active parcel monitoring paths: county-direct, MnGeo open parcels, both, or no active parcel monitoring path. Select a county to inspect its complete source profile.';
    }}else{{
      const d=selectedPath&&countyData[selectedPath.dataset.county];
      detail.textContent=!selectedPath?'The map shows record-weighted population across mandatory Minnesota GAC parcel-transfer fields. Unavailable statewide completeness remains distinct from 0%.':!d||d.pct==null?'Statewide completeness is unavailable for this county. These statistics are separate from county-direct monitoring; no 0% value is inferred.':'Current record-weighted population across mandatory parcel-transfer fields for this county. These statistics are separate from county-direct monitoring.';
    }}
  }}
  function updateOverview(){{
    const monitoring=selector.value==="monitoring";
    root.querySelectorAll(".mngac-county").forEach(p=>{{
      const paths=monitoringPaths[p.dataset.slug]||[],d=countyData[p.dataset.county];
      p.style.fill=monitoring?(paths.length===2?"#4c9b7b":paths.includes("county-direct")?"#3c708f":paths.includes("mngeo-open")?"#315373":"#151d2b"):fill(d&&d.pct);
      const label=monitoring?monitoringLabel(paths):d&&d.pct!=null?Number(d.pct).toFixed(2)+'% MN GAC mandatory-field population':'Statewide completeness is unavailable';
      p.setAttribute('aria-label',p.dataset.county+' County, '+label);
    }});
    updateDescription();
    root.getElementById("overview-legend").innerHTML=monitoring?'<div class="mngac-legend"><span><i class="mngac-swatch" style="background:#4c9b7b"></i>Both paths</span><span><i class="mngac-swatch" style="background:#3c708f"></i>County-direct</span><span><i class="mngac-swatch" style="background:#315373"></i>MnGeo open</span><span><i class="mngac-swatch" style="background:#151d2b"></i>No active parcel path</span></div>':{json.dumps(percentage_legend())};
  }}
  selector.addEventListener("change",updateOverview);
  {percentage_color_js()}
  const fill=percentageColor;
  function show(name,path){{
    selectedPath=path;
    root.getElementById('overview-county-select').value=path.dataset.slug;
    window.watchtowerRefresh?.save();
    const d=countyData[name];
    root.querySelectorAll('.mngac-county').forEach(p=>p.classList.toggle('selected',p===path));
    root.getElementById('home-county-name').textContent=name+' County';
    const rate=root.getElementById('home-county-rate'), rec=root.getElementById('home-county-records'), fields=root.getElementById('home-county-fields'), link=root.getElementById('home-county-link');
    if(!d){{
      rate.textContent='No data';rec.textContent='—';fields.textContent='—';
    }}else{{
      rate.textContent=d.pct==null?'—':Number(d.pct).toFixed(2)+'%';
      rec.textContent=d.records==null?"Not available":Number(d.records).toLocaleString();
      fields.textContent=(d.fields==null?'—':d.fields)+' / '+(d.field_count||91);
    }}
    const slug=(d&&d.slug)||path.dataset.slug||'';
    link.href=slug?'/county?slug='+encodeURIComponent(slug):'/counties';
    updateDescription();
  }}
  root.querySelectorAll('.mngac-county').forEach(p=>{{
    p.addEventListener('click',()=>show(p.dataset.county,p));
    p.addEventListener('keydown',e=>{{if(e.key==='Enter'||e.key===' '){{e.preventDefault();show(p.dataset.county,p)}}}});
  }});
  updateOverview();
  root.getElementById('overview-county-select').addEventListener('change',event=>{{const path=[...root.querySelectorAll('.mngac-county')].find(p=>p.dataset.slug===event.target.value);if(path)show(path.dataset.county,path)}});
}})();
function filterRows(){{
  const q=document.getElementById('q').value.toLowerCase(),h=document.getElementById('health').value;
  document.querySelectorAll('#datasets tbody tr').forEach(r=>r.style.display=(!q||r.dataset.name.includes(q))&&(!h||r.dataset.status===h)?'':'none');
}}
</script>
{profile_panel}
"""
    return _layout("GIS Data Watchtower", body, refresh_seconds=30, static=True)

def render_public_source(config: dict, source_id: str) -> str:
    source = (_dashboard_state(config).get("sources") or {}).get(source_id)
    if not source:
        return _layout(
            "Source not found",
            '<div class="card"><h2>Source not found</h2><p><a href="/">Return to dashboard</a></p></div>',
            refresh_seconds=30,
            static=True,
        )

    body = (
        '<p><a href="/">← Watchtower overview</a></p>'
        '<div class="grid">'
        f'<div class="card"><div class="muted">Data source</div><h2>{_esc(source.get("name") or source_id)}</h2></div>'
        f'<div class="card"><div class="muted">Status</div><div class="metric {_status_class(source.get("status") or "unknown")}">{_esc(_health_status(source.get("status") or "unknown"))}</div></div>'
        f'<div class="card"><div class="muted">Records</div><div class="metric">{_esc(source.get("feature_count") if source.get("feature_count") is not None else "—")}</div></div>'
        '</div>'
        '<div class="card"><h2>Public monitoring summary</h2><dl class="definition-list">'
        f'<dt>Provided by</dt><dd>{_esc(source.get("provider") or "—")}</dd>'
        f'<dt>Data type</dt><dd>{_esc(source.get("category") or "—")}</dd>'
        f'<dt>Latest successful check</dt><dd>{_esc(_public_time(source.get("last_success_at")))}</dd>'
        f'<dt>Reporting</dt><dd>{_esc(source.get("reporting") or "current")}</dd>'
        f'<dt>Changes found</dt><dd>{_esc(source.get("change_count") or 0)}</dd>'
        f'<dt>Information fields</dt><dd>{_esc(source.get("field_count") if source.get("field_count") is not None else "—")}</dd>'
        f'<dt>Missing parcel IDs</dt><dd>{_esc(source.get("parcel_id_null_count") if source.get("parcel_id_null_count") is not None else "Not checked")}</dd>'
        f'<dt>Duplicate-ID extra rows</dt><dd>{_esc(source.get("duplicate_id_extra_rows") if source.get("duplicate_id_extra_rows") is not None else "Not checked")}</dd>'
        f'<dt>Missing mapped shape</dt><dd>{_esc(source.get("null_geometry_count") if source.get("null_geometry_count") is not None else "Not checked")}</dd>'
        '</dl></div>'
    )
    return _layout(
        f'Data Source — {source.get("name") or source_id} — GIS Data Watchtower',
        body,
        refresh_seconds=30,
        static=True,
    )


class _PublicStateCache:
    def __init__(self) -> None:
        self.root = Path(os.environ.get("WATCHTOWER_PUBLIC_WORKDIR", "/tmp/watchtower-public"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.raw_path = self.root / "aggregate-raw.json"
        self.public_path = self.root / "aggregate-public.json"
        self.history_path = self.root / "history-empty.jsonl"
        self.history_path.touch(exist_ok=True)
        self.storage = backend_from_env(self.root)
        self.object_name = os.environ.get("WATCHTOWER_AGGREGATE_OBJECT", "aggregate-state.json")
        self.refresh_seconds = max(5, min(int(os.environ.get("WATCHTOWER_PUBLIC_REFRESH_SECONDS", "30")), 300))
        self._last_refresh = 0.0
        self._last_attempt = 0.0
        self._refresh_lock = threading.Lock()
        self._export_lock = threading.Lock()
        self._snapshot_key = None
        self._snapshot_value = None
        self._xlsx_value = None
        self._view_key = None
        self._view_value = None
        self.last_refresh_error = False

    @property
    def stale(self) -> bool:
        return self.last_refresh_error

    @property
    def config(self) -> dict:
        return {
            "state_file": str(self.public_path),
            "aggregate_state_file": str(self.public_path),
            "history_file": str(self.history_path),
            "sources": [],
            "_public_mode": True,
            "worker_stale_minutes": int(os.environ.get("WATCHTOWER_WORKER_STALE_MINUTES", "1560")),
            "source_stale_minutes": int(os.environ.get("WATCHTOWER_SOURCE_STALE_MINUTES", "1560")),
            "publication_max_age_seconds": _publication_max_age_seconds(),
        }

    def refresh(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and self.public_path.is_file() and now - self._last_refresh < self.refresh_seconds:
            return
        # Back off after storage errors and let concurrent requests use the
        # last-known snapshot while one refresh is in flight.
        if not force and self.public_path.is_file() and now - self._last_attempt < self.refresh_seconds:
            return
        if not self._refresh_lock.acquire(blocking=False):
            if self.public_path.is_file():
                return
            self._refresh_lock.acquire()
        try:
            now = time.monotonic()
            self._last_attempt = now
            if not self.storage.download(self.object_name, self.raw_path):
                raise FileNotFoundError(f"aggregate object not found: {self.object_name}")
            raw = json.loads(self.raw_path.read_text(encoding="utf-8"))
            public = sanitize_public_render_state(raw)
            tmp = self.public_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.public_path)
            self._last_refresh = now
            self.last_refresh_error = False
        except Exception:
            self.last_refresh_error = True
            if not self.public_path.is_file():
                raise
        finally:
            self._refresh_lock.release()

    def _ensure_snapshot(self) -> dict:
        state_bytes = self.public_path.read_bytes()
        identity = application_identity()
        key = hashlib.sha256(
            state_bytes + str(identity.get("revision")).encode() + str(identity.get("version")).encode()
        ).hexdigest()
        if key != self._snapshot_key:
            self._snapshot_value = _statewide_snapshot(self.config)
            self._xlsx_value = None
            self._snapshot_key = key
        return self._snapshot_value

    def snapshot(self) -> dict:
        with self._export_lock:
            return self._ensure_snapshot()

    def view(self) -> dict:
        """Capture an immutable state/profile/summary bundle for one request."""
        with self._export_lock:
            state_bytes = self.public_path.read_bytes()
            research = load_parcel_access()
            key = hashlib.sha256(state_bytes + json.dumps(research, sort_keys=True).encode()
                                 + json.dumps(application_identity(), sort_keys=True).encode()
                                 + json.dumps(self.config, sort_keys=True).encode()).hexdigest()
            if key != self._view_key:
                state = sanitize_public_render_state(json.loads(state_bytes))
                profiles = _county_profiles(self.config, state, research)
                summary = summary_for(self.config, state, profiles=profiles, research=research)
                self._view_value = {"state": state, "profiles": profiles, "summary": summary}
                self._view_key = key
            return {**self._view_value, "summary": {**self._view_value["summary"], "refresh_failed": self.stale}}

    def snapshot_xlsx(self) -> bytes:
        with self._export_lock:
            snapshot = self._ensure_snapshot()
            if self._xlsx_value is None:
                rendered = _snapshot_xlsx(snapshot)
                if len(rendered) > 32 * 1024 * 1024:
                    raise RuntimeError("rendered public export exceeds cache size limit")
                self._xlsx_value = rendered
            return self._xlsx_value


def _public_request_timeout_seconds() -> int:
    try:
        value = int(os.environ.get("WATCHTOWER_PUBLIC_REQUEST_TIMEOUT_SECONDS", "10"))
    except (TypeError, ValueError):
        value = 10
    return max(2, min(value, 60))


def serve_public(host: str = "0.0.0.0", port: int = 8080) -> None:
    cache = _PublicStateCache()
    cache.refresh(force=True)
    max_connections = max(1, min(int(os.environ.get("WATCHTOWER_PUBLIC_MAX_CONNECTIONS", "64")), 256))
    max_publication_age_seconds = _publication_max_age_seconds()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content: str, content_type: str = "text/html; charset=utf-8"):
            if cache.stale and content_type.startswith("text/html"):
                content = content.replace(
                    "<main class=\"public-main\">",
                    '<main class="public-main"><div class="mngac-note warn" role="status">'
                    'Showing a cached public snapshot because the latest storage refresh failed.</div>',
                    1,
                )
            if status == 200 and content_type.startswith("text/html") and "</head>" in content:
                revision = getattr(self, "_render_revision", None)
                if revision:
                    content = content.replace("</head>", '<meta data-content-revision="' + revision + '"></head>', 1)
            raw = content.encode("utf-8")
            status, raw, headers = encode_response(status, raw, content_type,
                self.headers.get("Accept-Encoding", ""), self.headers.get("If-None-Match"))
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if status != 304:
                self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-cache" if status in {200, 304} else "no-store")
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            analytics_sources = posthog_csp_sources()
            script_src = "script-src 'self' 'unsafe-inline'"
            connect_src = "connect-src 'self'"
            if analytics_sources:
                script_origin, api_origin = analytics_sources
                script_src += f" {script_origin}"
                connect_src += f" {api_origin}"
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                + script_src + "; " + connect_src
                + "; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(raw)

        def _send_bytes(self, status: int, raw: bytes, content_type: str, filename: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "public, max-age=30")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/healthz":
                try:
                    cache.refresh()
                    state = json.loads(cache.public_path.read_text(encoding="utf-8"))
                    healthy, payload = _publication_health(state, max_age_seconds=max_publication_age_seconds)
                    if cache.stale:
                        healthy = False
                        payload = {**payload, "status": "stale", "refresh_failed": True}
                    return self._send(200 if healthy else 503, json.dumps(payload, separators=(",", ":")), "application/json; charset=utf-8")
                except Exception:
                    return self._send(503, '{"status":"unavailable"}', "application/json; charset=utf-8")

            try:
                cache.refresh()
            except Exception:
                return self._send(503, "Dashboard data is temporarily unavailable.", "text/plain; charset=utf-8")

            config = cache.config
            if parsed.path in {"/api/summary", "/api/county-profile", "/", "/counties", "/county", "/mngac", "/source"}:
                view = cache.view()
                self._render_revision = view["summary"]["content_revision"]
                config = {**config, "_render_state": view["state"]}
                if dispatch_public_details(self, parsed.path, parsed.query, view):
                    return
            if dispatch_snapshot_exports(
                self,
                parsed.path,
                parsed.query,
                statewide_snapshot=cache.snapshot,
                county_snapshot=lambda slug: _county_snapshot(config, slug),
                statewide_xlsx=cache.snapshot_xlsx,
            ):
                return
            if parsed.path == "/":
                return self._send(200, render_public_dashboard(config))
            if parsed.path == "/counties":
                return self._send(200, render_counties(config))
            if parsed.path == "/county":
                slug = urllib.parse.parse_qs(parsed.query).get("slug", [""])[0]
                return self._send(200, render_county(config, slug))
            if parsed.path == "/mngac":
                try:
                    standard_key = normalize_standard_key(
                        urllib.parse.parse_qs(parsed.query).get("standard", ["parcel"])[0]
                    )
                except ValueError:
                    return self._send(400, "Unsupported GAC standard", "text/plain; charset=utf-8")
                return self._send(200, render_mngac(config, standard_key))
            if parsed.path == "/source":
                source_id = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
                return self._send(200, render_public_source(config, source_id))
            if parsed.path == "/api/state":
                return self._send(200, cache.public_path.read_text(encoding="utf-8"), "application/json; charset=utf-8")
            if parsed.path in ("/county-profiles.csv", "/parcel-sources.csv"):
                snap = cache.snapshot()
                profiles = {row["parcel_source_profile"]["county"]["slug"]: row["parcel_source_profile"] for row in snap["counties"]}
                export = county_profiles_csv if parsed.path == "/county-profiles.csv" else parcel_sources_csv
                return self._send(200, export(profiles), "text/csv; charset=utf-8")
            if parsed.path in ("/mngac.json", "/mngac.csv"):
                try:
                    standard_key = normalize_standard_key(
                        urllib.parse.parse_qs(parsed.query).get("standard", ["parcel"])[0]
                    )
                except ValueError:
                    return self._send(400, "Unsupported GAC standard", "text/plain; charset=utf-8")
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
            return self._send(404, "Not found", "text/plain; charset=utf-8")

        def do_POST(self):
            return self._send(405, "Method not allowed", "text/plain; charset=utf-8")

        def log_message(self, format, *args):
            return

    server = _BoundedThreadingHTTPServer((host, port), Handler, max_connections=max_connections, request_timeout=_public_request_timeout_seconds())
    print(f"GIS Data Watchtower public dashboard: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
