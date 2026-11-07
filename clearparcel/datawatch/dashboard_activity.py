"""Read-only operational attention and change history views."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

from . import dashboard
from .csp import SCRIPT_TAG
from .product import page_title
from .watch import _safe_diagnostic

CHANGE_LABELS = {"feature_count": "Record count", "schema": "Field structure",
                 "tracked_value": "Tracked value", "spatial_extent": "Mapped area",
                 "observation": "Source details"}
MAX_CHANGES = 500


def compact_time(value) -> str:
    instant = dashboard._parse_time(value)
    if instant is None:
        return "Unavailable"
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=dt.UTC)
    shown = instant.astimezone(ZoneInfo("America/Chicago")).strftime("%b %d, %Y · %I:%M %p %Z")
    utc = instant.astimezone(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f'<time datetime="{dashboard._esc(instant.isoformat())}" title="{dashboard._esc(utc)}">{shown}</time>'


def source_url(source_id: str) -> str:
    return "/source?" + urlencode({"id": source_id})


def render_attention(state: dict, alerts: list[dict] | None) -> str:
    if alerts is None:
        message = "Alert status unavailable. Check the source list and monitoring reports below."
    elif not alerts:
        message = "No active alerts. No recorded check result or overdue report currently needs attention."
    else:
        message = "Failures and overdue checks first. Source access permissions are tracked separately."
    groups = {}
    for alert in alerts or []:
        sid = str(alert.get("source") or "")
        group = groups.setdefault(sid, {"name": alert.get("name") or sid or "Monitoring system", "messages": [], "severity": "warn"})
        group["messages"].append(_safe_diagnostic(alert.get("message") or "Check needs attention"))
        if alert.get("severity") == "error":
            group["severity"] = "error"
    rows = []
    for sid, item in sorted(groups.items(), key=lambda pair: (pair[1]["severity"] != "error", str(pair[1]["name"]).casefold())):
        src = (state.get("sources") or {}).get(sid)
        worker = (state.get("workers") or {}).get(sid.removeprefix("worker:")) if sid.startswith("worker:") else None
        record = src or worker or {}
        href = source_url(sid) + "#source-status" if src is not None else "/#monitoring-systems" if worker is not None else "/sources"
        rows.append(f'<tr><th scope="row"><a href="{dashboard._esc(href)}"><strong>{dashboard._esc(item["name"])}</strong></a></th>'
                    f'<td data-label="Needs attention" class="{item["severity"]}">{dashboard._esc(" · ".join(dict.fromkeys(item["messages"])))}</td>'
                    f'<td data-label="Latest check or report">{compact_time(record.get("checked_at") or record.get("last_report_at"))}</td>'
                    f'<td data-label="Last successful check">{compact_time(record.get("last_success_at"))}</td></tr>')
    table = ('<table class="ops-table" id="attention-sources"><thead><tr><th>Source or system</th><th>Needs attention</th>'
             '<th>Latest check or report</th><th>Last successful check</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>') if rows else ''
    return f'<section class="card" id="alerts"><h2>Needs attention</h2><p role="status">{message}</p>{table}</section>'


def _stamp(value) -> dt.datetime:
    parsed = dashboard._parse_time(value)
    if parsed is None:
        return dt.datetime.min.replace(tzinfo=dt.UTC)
    return parsed.replace(tzinfo=dt.UTC) if parsed.tzinfo is None else parsed.astimezone(dt.UTC)


def change_events(config: dict, state: dict, source_id: str | None = None, *, history: list[dict] | None = None) -> list[dict]:
    """Bounded retained observations, deduplicated by actual source-check time."""
    if history is None:
        history = dashboard.load_history(config, limit=1000).get("entries") or []
    observations = [(sid, rec, run.get("generated_at"))
                    for run in history if isinstance(run, dict) and isinstance(run.get("sources"), dict)
                    for sid, rec in run["sources"].items()
                    if isinstance(rec, dict) and (source_id is None or sid == source_id)]
    observations += [(sid, rec, state.get("generated_at")) for sid, rec in (state.get("sources") or {}).items()
                     if isinstance(rec, dict) and (source_id is None or sid == source_id)]
    observations.sort(key=lambda row: _stamp(row[1].get("checked_at") or row[2]), reverse=True)
    events, seen = [], set()
    for sid, source, generated in observations:
        observed = source.get("checked_at") or generated
        for change in source.get("changes") or []:
            if not isinstance(change, dict):
                continue
            signature = json.dumps([sid, observed, change], sort_keys=True, default=str)
            fingerprint = hashlib.sha256(signature.encode()).hexdigest()[:20]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            instant = _stamp(observed)
            events.append({"source": sid, "name": source.get("name") or sid, "observed_at": observed,
                           "day": instant.astimezone(ZoneInfo("America/Chicago")).date().isoformat() if observed and instant.year > 1 else "",
                           "change": change, "anchor": "change-" + fingerprint,
                           "current_source": sid in (state.get("sources") or {})})
            if len(events) >= MAX_CHANGES:
                return events
    return events


def _change_value(value) -> str:
    if value is None:
        return "Not recorded"
    if type(value) is int:
        return f"{value:,}"
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return dashboard._esc(_safe_diagnostic(value, limit=1024))


def render_change_list(events: list[dict], *, preview: bool = False) -> str:
    rows = []
    for event in events[:5] if preview else events:
        change = event["change"]
        kind = str(change.get("type") or "other")
        label = CHANGE_LABELS.get(kind, kind.replace("_", " ").title())
        name = dashboard._esc(event["name"])
        href = source_url(event["source"]) + "#" + event["anchor"]
        source = f'<a href="{dashboard._esc(href)}">{name}</a>' if event["current_source"] else name + ' <small>No longer monitored</small>'
        previous = change.get("previous", change.get("old"))
        current = change.get("current", change.get("new"))
        key = change.get("key") or change.get("field")
        detail = f'<p>{dashboard._esc(_safe_diagnostic(change.get("message") or label))}</p>'
        if key:
            detail += f'<p>Field: <code>{dashboard._esc(_safe_diagnostic(key))}</code></p>'
        if kind == "spatial_extent" and "previous" not in change and "old" not in change:
            detail += f'<p>Recorded coordinate shifts: {_change_value(change.get("coordinate_deltas"))}</p>'
        detail += f'<dl class="change-values"><div><dt>Previous</dt><dd>{_change_value(previous)}</dd></div><div><dt>Current</dt><dd>{_change_value(current)}</dd></div></dl>'
        rows.append(f'<article class="change-entry" id="{event["anchor"]}" data-day="{event["day"]}" data-type="{dashboard._esc(kind)}" '
                    f'data-search="{dashboard._esc((str(event["name"]) + " " + event["source"] + " " + label).casefold())}">'
                    f'<h3>{source} — {dashboard._esc(label)}</h3><p class="subtext">{compact_time(event["observed_at"])}</p>{detail}</article>')
    return ''.join(rows) or '<p>No changes were found in the retained observations. This does not prove the provider’s data is unchanged.</p>'


def render_changes(config: dict) -> str:
    state = dashboard._dashboard_state(config)
    events = change_events(config, state)
    types = sorted({str(e["change"].get("type") or "other") for e in events})
    options = ''.join(f'<option value="{dashboard._esc(t)}">{dashboard._esc(CHANGE_LABELS.get(t, t.replace("_", " ").title()))}</option>' for t in types)
    body = f'''<p>Recorded changes to counts, fields and source details. Up to {MAX_CHANGES} events from retained history; observations are not a complete record of provider edits.</p>
<section class="card"><h2>Recent changes</h2><div class="filters">
<input id="activity-q" type="search" placeholder="Find a source or change type" aria-label="Search changes">
<select id="change-type" aria-label="Filter change type"><option value="">All change types</option>{options}</select>
<label>From <input id="change-start" type="date"></label><label>Through <input id="change-end" type="date"></label>
<button type="button" id="changes-clear">Clear filters</button></div><p id="changes-results" role="status"></p>
<div id="change-feed">{render_change_list(events)}</div><p id="changes-empty" hidden>No changes match these filters.</p></section>
{SCRIPT_TAG}(function(){{const ids=['activity-q','change-type','change-start','change-end'],controls=ids.map(id=>document.getElementById(id));function filter(){{const [q,type,start,end]=controls.map(c=>c.value.toLowerCase());let n=0;document.querySelectorAll('#change-feed .change-entry').forEach(r=>{{const show=(!q||r.dataset.search.includes(q))&&(!type||r.dataset.type===type)&&(!start||r.dataset.day&&r.dataset.day>=start)&&(!end||r.dataset.day&&r.dataset.day<=end);r.hidden=!show;if(show)n++}});document.getElementById('changes-results').textContent=n+' changes shown';document.getElementById('changes-empty').hidden=n>0||!document.querySelector('#change-feed .change-entry')}}controls.forEach(c=>c.addEventListener(c.tagName==='SELECT'?'change':'input',filter));document.getElementById('changes-clear').addEventListener('click',()=>{{controls.forEach(c=>c.value='');filter();controls[0].focus();window.watchtowerRefresh?.save()}});filter()}})();</script>'''
    return dashboard._layout(page_title("Recent changes"), body, active_section="changes", csrf_token=str(config.get("_csrf_token") or ""))


def render_alerts(config: dict) -> str:
    from .dashboard_views import derive_aggregate_alerts
    state = dashboard._dashboard_state(config)
    alerts = state.get("active_alerts")
    if not isinstance(alerts, list):
        alerts = derive_aggregate_alerts(state)
    return dashboard._layout(page_title("Alerts"), render_attention(state, alerts), active_section="alerts", csrf_token=str(config.get("_csrf_token") or ""))


def source_snapshot(config: dict, source_id: str) -> dict | None:
    state = dashboard._dashboard_state(config)
    source = (state.get("sources") or {}).get(source_id)
    if not isinstance(source, dict):
        return None
    # Deliberately match the existing source-summary export contract. No
    # registry URLs, credentials, diagnostics or private CRM content cross over.
    row = {key: source.get(key) for key in ("status", "feature_count", "worker", "reporting", "last_success_at", "checked_at")}
    row.update(id=source_id, name=source.get("name") or source_id, county=source.get("county_slug") or "",
               stale=bool(source.get("stale")), worker_stale=bool(source.get("worker_stale")))
    return {"title": "Watchtower source summary", "export_scope": "source", "sources": [row], "source_count": 1, "county_count": 0,
            "counties": [], "workers": {}, "mngac": None, "gac": {}, "overall": source.get("status"),
            **dashboard._snapshot_time_fields(dt.datetime.now(dt.UTC).isoformat(), "snapshot_created"),
            **dashboard._snapshot_time_fields(source.get("checked_at"), "watchtower_last_checked")}


def render_downloads(config: dict) -> str:
    body = ('<section class="card"><h2>All monitoring data</h2><p>These downloads contain saved summary observations, not raw parcel records. Observation and export times are included where supported.</p>'
            '<p><a href="/snapshot.xlsx">Excel spreadsheet (.xlsx)</a> · <a href="/snapshot.csv">Source checks (CSV)</a> · <a href="/snapshot.json">Summary data (JSON)</a></p>'
            '<p><a href="/county-profiles.csv">County profiles (CSV)</a> · <a href="/parcel-sources.csv">Parcel source research (CSV)</a></p></section>'
            '<section class="card"><h2>One county or source</h2><p>Open a county or source, then use its Download menu to export just that item.</p>'
            '<p><a href="/counties">Choose a county</a> · <a href="/sources">Choose a source</a> · <a href="/mngac">Data completeness downloads</a></p></section>')
    return dashboard._layout(page_title("Downloads"), body, active_section="export", csrf_token=str(config.get("_csrf_token") or ""))
