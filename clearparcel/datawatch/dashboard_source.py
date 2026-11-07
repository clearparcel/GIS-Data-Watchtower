"""Private source facts, relevant measurements and retained change evidence."""
from __future__ import annotations

import math

from . import dashboard
from .dashboard_activity import change_events, compact_time, render_change_list
from .data_freshness import HISTORY_LIMIT, data_freshness
from .product import page_title
from .watch import _safe_diagnostic

RESULTS = {"ok": "Passed", "warn": "Needs attention", "error": "Failed", "unknown": "Unknown",
           "paused": "Paused", "awaiting-permission": "Awaiting permission"}


def measurement(value, unit: str = "", *, missing: str = "Not checked") -> str:
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        return missing
    text = f"{value:,}" if type(value) is int else f"{value:,.2f}".rstrip("0").rstrip(".")
    return text + unit


def duration(value) -> str:
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        return "Unavailable"
    return measurement(value / 1000, " s") if value >= 1000 else measurement(value, " ms")


def check_timing(source: dict) -> str:
    if source.get("stale") or source.get("worker_stale") or source.get("reporting") == "stale":
        return "Check or monitoring report overdue"
    if dashboard._parse_time(source.get("checked_at")) is None:
        return "Check time unavailable"
    return "Check is recent"


def trend(values: list, entries: list[dict], *, label: str, unit: str = "") -> str:
    chart = dashboard._svg_sparkline(values, label=label, unit=unit)
    dates = [x.get("checked_at") or x.get("generated_at") for x in entries]
    dates = [x for x in dates if dashboard._parse_time(x) is not None]
    if dates:
        chart += f'<p class="subtext">{compact_time(dates[0])} – {compact_time(dates[-1])}. Points represent retained observations; gaps stay unconnected.</p>'
    return chart


def render_source(config: dict, source_id: str) -> str:
    esc = dashboard._esc
    state = dashboard._dashboard_state(config)
    src = (state.get("sources") or {}).get(source_id)
    if not isinstance(src, dict):
        return dashboard._layout(page_title("Source not found"), '<div class="card"><h2>Source not found</h2><a href="/sources">Return to sources</a></div>', active_section="sources", csrf_token=str(config.get("_csrf_token") or ""))
    runs, histories = dashboard.load_history_index(config, [source_id], limit=HISTORY_LIMIT)
    entries = histories.get(source_id, [])
    hist = entries[-60:]
    stats = dashboard._history_stats(hist)
    meta = dashboard._source_config_map(config).get(source_id, {})
    fresh = data_freshness(src, source_config=meta, history=entries)
    category = meta.get("category") or src.get("category") or "Other"
    provenance = src.get("provenance") or {}
    result = str(src.get("status") or "unknown")
    result_label = RESULTS.get(result, "Unknown")
    issue = ""
    if result in {"error", "warn", "paused", "awaiting-permission"}:
        reason = src.get("error") or src.get("last_error") or "; ".join(str(x) for x in src.get("problems") or [])
        if not reason:
            reason = {"error": "The latest check failed; no further reason was recorded.",
                      "warn": "The source reported a warning. Review its recorded changes and checks below.",
                      "paused": "This source is paused. It is not a failed provider check.",
                      "awaiting-permission": "A check is awaiting permission. Access links do not grant monitoring approval."}[result]
        issue = f'<section class="card source-issue {dashboard._status_class(result)}" id="source-status"><h2>{esc(result_label)}</h2><p>{esc(_safe_diagnostic(reason))}</p><a href="/alerts">View the attention list</a></section>'
    count = measurement(src.get("feature_count"), missing="Unavailable")
    success_count = sum(x.get("status") == "ok" for x in hist)
    reliability = measurement(stats.get("success_rate"), "%", missing="Not enough history")
    data_age = {"current": "Within expected update interval", "stale": "Publisher data may be old", "unknown": "Publisher update time unavailable"}[fresh["state"]]
    record_card = f'<div class="card"><div class="muted">Last known record count</div><div class="metric">{esc(count)}</div><span class="subtext">Retained count; its observation time is shown below. The latest attempt may be newer.</span></div>' if type(src.get("feature_count")) in (int, float) or category in {"Parcels", "Roads", "Addresses", "Flood", "Wetlands"} else ''
    count_observed = f'<dt>Record count observed</dt><dd>{compact_time(src.get("last_success_at") if result == "error" else src.get("checked_at"))}</dd>' if record_card else ''
    body = f'''<nav class="breadcrumb" aria-label="Breadcrumb"><a href="/">Overview</a> / <a href="/sources">Data sources</a> / {esc(src.get("name") or source_id)}</nav>
<h2>{esc(src.get("name") or source_id)}</h2>{issue}
<div class="grid primary-grid"><div class="card"><div class="muted">Latest check result</div><div class="metric {dashboard._status_class(result)}">{esc(result_label)}</div><p class="subtext">{esc(check_timing(src))}</p></div>
{record_card}<div class="card"><div class="muted">Recent observations passed</div><div class="metric">{esc(reliability)}</div><span class="subtext">{success_count} of {len(hist)} retained observations passed. This is not a service guarantee.</span></div>
<div class="card"><div class="muted">Last change detected</div><strong>{compact_time(stats.get("last_change"))}</strong><p class="subtext">Detected by Watchtower; separate from the provider’s update date.</p></div></div>
<section class="card"><h2>Source and timing</h2><dl class="definition-list">
<dt>Provided by</dt><dd>{esc(meta.get("provider") or src.get("provider") or "Unavailable")}</dd><dt>Data type</dt><dd>{esc(category)}</dd>
{count_observed}<dt>Latest check attempt</dt><dd>{compact_time(src.get("checked_at"))}</dd><dt>Last successful check</dt><dd>{compact_time(src.get("last_success_at"))}</dd>
<dt>Publisher last updated data</dt><dd>{compact_time(fresh.get("data_updated_at"))}</dd><dt>Publisher data age</dt><dd>{esc(data_age)}{f' · {fresh["age_days"]} days old · expected within {fresh["expected_days"]} days' if fresh["age_days"] is not None else ''}</dd>
<dt>Checked by</dt><dd>{esc(src.get("worker") or "Not recorded")} monitoring</dd></dl></section>'''
    if category == "Parcels":
        parcel_fields = [("Data fields available", measurement(src.get("field_count"))),
                         ("Parcel number field", src.get("parcel_id_field") or "Not identified"),
                         ("Records missing a parcel number", measurement(src.get("parcel_id_null_count"))),
                         ("Extra records with repeated parcel numbers", measurement(src.get("duplicate_id_extra_rows"))),
                         ("Records missing map shapes", measurement(src.get("null_geometry_count")))]
        body += '<section class="card"><h2>Parcel checks</h2><p>Not checked means no measurement was recorded; it is separate from a measured zero.</p><dl class="definition-list">' + ''.join(f'<dt>{esc(k)}</dt><dd>{esc(v)}</dd>' for k, v in parcel_fields) + '</dl></section>'
    sample = src.get("geometry_sample_size")
    if type(sample) is int and sample > 0:
        values = [("Shapes sampled", measurement(sample)), ("Shapes with multiple parts or holes", measurement(src.get("geometry_sample_multipart_percent"), "%")),
                  ("Average vertices per shape", measurement(src.get("geometry_sample_avg_vertices"))), ("Most vertices in one shape", measurement(src.get("geometry_sample_max_vertices")))]
        body += '<details class="card technical" id="source-shape-sample"><summary>Sampled map shapes</summary><p>These measurements describe a bounded sample, not every shape.</p><dl class="definition-list">' + ''.join(f'<dt>{esc(k)}</dt><dd>{esc(v)}</dd>' for k, v in values) + '</dl></details>'
    if category == "Parcels":
        profiles = src.get("completeness_profiles") or {}
        labels = {"owner": "Records with an owner name", "site_address": "Records with a property address", "mailing_address": "Records with an owner mailing address"}
        body += '<section class="card"><h2>Parcel information completeness</h2><dl class="definition-list">' + ''.join(f'<dt>{label}</dt><dd>{esc(measurement((profiles.get(key) or {}).get("complete_percent"), "%"))}</dd>' for key, label in labels.items()) + '</dl><p class="subtext">A populated value does not establish that the value is accurate.</p></section>'
    count_history = '<section class="card"><h3>Record-count history</h3>' + trend([x.get("feature_count") for x in hist], hist, label="Record count", unit="records") + '</section>' if record_card or any(type(x.get("feature_count")) in (int, float) for x in hist) else ''
    body += '<div class="grid">' + count_history + '<section class="card"><h3>Response-time history</h3>' + trend([x.get("elapsed_ms") / 1000 if type(x.get("elapsed_ms")) in (int, float) else None for x in hist], hist, label="Response time", unit="s") + '</section></div>'
    events = change_events(config, state, source_id, history=runs)
    changes = render_change_list(events)
    if events:
        changes = '<details class="technical" id="source-change-details"><summary>View change details and previous/current values</summary>' + changes + '</details>'
    body += '<section class="card" id="source-changes"><h2>Recorded changes</h2>' + changes + '</section>'
    technical = [("Source ID", source_id), ("Source connection", provenance.get("adapter") or src.get("adapter") or src.get("kind") or "Not recorded"),
                 ("Map shape type", src.get("geometry_type") or "Not applicable or not recorded"), ("Coordinate system code", src.get("wkid") or "Not recorded"),
                 ("Source address", provenance.get("source_url") or src.get("url") or "Not recorded"),
                 ("Field structure comparison ID", src.get("schema_hash") or "Not recorded"), ("Observation comparison ID", src.get("observation_fingerprint") or "Not recorded"),
                 ("Expected publisher update interval", f'{fresh["expected_days"]} days; ' + {"configured": "set for this source", "observed": "estimated from previous updates", "default": "default while updates are unknown"}[fresh["basis"]])]
    body += '<details class="card technical" id="source-technical"><summary>Technical details</summary><dl class="definition-list">' + ''.join(f'<dt>{esc(k)}</dt><dd>{esc(v)}</dd>' for k, v in technical) + '</dl></details>'
    rows = ''.join(f'<tr><td>{compact_time(x.get("checked_at") or x.get("generated_at"))}</td><td>{esc(RESULTS.get(x.get("status"), "Unknown"))}</td><td>{esc(measurement(x.get("feature_count"), missing="Unavailable"))}</td><td>{len(x.get("changes") or [])}</td><td>{esc(duration(x.get("elapsed_ms")))}</td></tr>' for x in reversed(hist[-30:]))
    body += '<details class="card technical" id="source-check-history"><summary>Check history</summary><p>Up to 30 retained observations. Timestamps are Central time; UTC is available on hover.</p><table class="history-table"><thead><tr><th>Latest check attempt</th><th>Check result</th><th>Last known records</th><th>Changes</th><th>Response time</th></tr></thead><tbody>' + rows + '</tbody></table></details>'
    return dashboard._layout(page_title(src.get("name") or source_id), body, active_section="sources", download_scope=("source", source_id), csrf_token=str(config.get("_csrf_token") or ""))
