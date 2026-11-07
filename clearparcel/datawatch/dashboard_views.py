from __future__ import annotations
from clearparcel.datawatch.csp import SCRIPT_TAG

from clearparcel.datawatch import dashboard as _dashboard
from clearparcel.datawatch.data_freshness import HISTORY_LIMIT as FRESHNESS_HISTORY_LIMIT, data_freshness, summarize as summarize_data_freshness
from clearparcel.datawatch.product import PRODUCT_NAME, page_title
from .dashboard_activity import compact_time, render_attention, change_events, render_change_list
from .dashboard_source import measurement, duration, check_timing, RESULTS


def _county_direct_parcels(source_id: str, source: dict) -> bool:
    """County-specific parcel sources, identified by data rather than ID suffix.

    Some approved IDs (for example ``mn-wabasha-parcels``) do not end in
    ``-parcels-direct``; statewide parcel services carry no county slug.
    """
    if source.get("category") == "Parcels" and source.get("county_slug"):
        return True
    return source_id.endswith("-parcels-direct")


_DATA_STATE_LABELS = {"current": "Current", "stale": "Data stale", "unknown": "Data age unknown"}
_DATA_BASIS_LABELS = {"configured": "set in the source registry", "observed": "learned from this source's updates",
                      "default": "default until enough updates are seen"}

def derive_aggregate_alerts(state: dict) -> list[dict] | None:
    """Alert list for a hybrid aggregate, which carries none of its own.

    Worker alerts are derived from each source's current status, and the
    aggregate keeps those statuses, so the same rule applies here. Overdue
    reporting is added on top: an empty list (all clear) is returned only when
    every source is healthy and no worker or source is past its freshness
    window. Returns ``None`` (status unknown) when the state has no workers.
    ``state`` must already carry freshness flags (``_dashboard_state`` applies
    ``with_freshness``); unannotated state is annotated here so it is never
    mistaken for current.
    """
    if "stale_workers" not in state:
        from clearparcel.datawatch.aggregate import with_freshness
        state = with_freshness(state)
    workers = state.get("workers")
    if not isinstance(workers, dict) or not workers:
        return None
    from clearparcel.datawatch.watch import _build_alerts
    sources = state.get("sources") or {}
    alerts, _ = _build_alerts({}, sources, set(), str(state.get("generated_at") or ""))
    for name in sorted(workers):
        if (workers.get(name) or {}).get("stale"):
            alerts.append({"severity": "warn", "source": f"worker:{name}", "name": f"{str(name).title()} worker",
                           "type": "worker_overdue",
                           "message": "Worker has not reported within the freshness window"})
    for sid, src in sources.items():
        if src.get("stale") and not src.get("worker_stale") and src.get("status") not in ("warn", "error"):
            alerts.append({"severity": "warn", "source": sid, "name": src.get("name"), "type": "check_overdue",
                           "message": "Latest check is older than the freshness window"})
    return alerts


def render_dashboard(config: dict, *, sources_only: bool = False) -> str:
    state = _dashboard._dashboard_state(config)
    sources = state.get("sources", {})
    counts = state.get("counts", {})
    # A worker state carries its own alert list. The hybrid aggregate does not,
    # so its alerts are derived from source status and freshness; without any
    # worker data the status stays unknown rather than all clear.
    alerts = state.get("active_alerts")
    if not isinstance(alerts, list):
        alerts = derive_aggregate_alerts(state)
    config_map = _dashboard._source_config_map(config)
    enriched = []
    freshness_rows = []
    changed_30 = 0
    # One history read per render: run telemetry plus exact-ID source histories.
    # Freshness learns from the longer window; the cards keep the recent 60.
    run_history, histories = _dashboard.load_history_index(config, sources.keys(), limit=FRESHNESS_HISTORY_LIMIT)
    retained_runs = run_history
    run_history = run_history[-60:]
    for sid, src in sources.items():
        full_hist = histories.get(sid, [])
        hist = full_hist[-60:]
        stats = _dashboard._history_stats(hist)
        if stats["change_age_days"] is not None and stats["change_age_days"] <= 30:
            changed_30 += 1
        meta = config_map.get(sid, {})
        freshness_rows.append(data_freshness(src, source_config=meta, history=full_hist))
        enriched.append((sid, src, meta, stats, hist))
    workers = state.get("workers") or {}
    worker_cards = []
    for worker_name in ("cloud", "local"):
        worker = workers.get(worker_name)
        if not worker:
            continue
        worker_status = str(worker.get("overall") or "unknown")
        worker_health = RESULTS.get(worker_status, "Unknown")
        stale = bool(worker.get("stale"))
        worker_telemetry = worker.get("telemetry") or {}
        wall_ms = worker_telemetry.get("wall_ms")
        duration_text = duration(wall_ms)
        source_count = worker.get("source_count")
        freshness_text = "Monitoring report overdue" if stale else "Monitoring report is recent" if worker.get("last_report_at") or worker.get("checked_at") else "Report time unavailable"
        worker_cards.append(f"""<div class="card worker-card">
<div><h3><span class="status-dot {_dashboard._status_class(worker_status)}"></span>{_dashboard._esc(worker_name.title())} monitoring</h3><span class="subtext">{_dashboard._esc(worker_health)} · {_dashboard._esc(freshness_text)}</span></div>
<div class="worker-meta">
<div><span class="muted">Sources</span><strong>{_dashboard._esc(source_count if source_count is not None else "—")}</strong></div>
<div><span class="muted">Run time</span><strong>{_dashboard._esc(duration_text)}</strong></div>
<div><span class="muted">Last success</span><strong style="font-size:13px">{compact_time(worker.get("last_success_at"))}</strong></div>
</div></div>""")
    data_counts = summarize_data_freshness(freshness_rows)
    source_issues = sum(s.get("status") in {"warn", "error"} for s in sources.values())
    freshness_label = "Unknown" if data_counts["unknown"] == len(freshness_rows) else str(data_counts["stale"]) + " may be old"
    body = f"""<div class="grid primary-grid">
<div class="card"><div class="muted">Latest check results</div><div class="metric {_dashboard._status_class(state.get('overall','unknown'))}">{_dashboard._esc(RESULTS.get(state.get('overall'), 'Unknown'))}</div><span class="subtext">Results of the last recorded checks; check timing is shown separately.</span></div>
<div class="card"><div class="muted">Monitored sources</div><div class="metric">{len(sources)}</div><span class="subtext">Sources currently included across the cloud and local workers.</span></div>
<div class="card"><div class="muted">Source issues</div><div class="metric">{source_issues}</div><span class="subtext">Sources whose latest check reported a warning or error.</span></div>
<div class="card"><div class="muted">Checks overdue</div><div class="metric">{state.get('stale_sources',0)}</div><span class="subtext">Sources that have not reported within the configured freshness window · {state.get('stale_workers',0)} worker(s) overdue.</span></div>
</div>
<div class="activity-strip">
<div class="card"><div class="muted">Sources changed — 30 days</div><div class="metric">{changed_30}</div><span class="subtext">Sources where Watchtower detected a data change during the last 30 days.</span></div>
<div class="card" id="data-freshness"><div class="muted">Data freshness</div><div class="metric">{freshness_label}</div><span class="subtext">{data_counts['current']} current · {data_counts['unknown']} with no publisher update time. Based on when each publisher last changed its data, not on Watchtower check time.</span></div>
<div class="card"><div class="muted">Dashboard data updated</div><strong>{compact_time(state.get('generated_at'))}</strong><span class="subtext">When Watchtower last combined the cloud and local worker results.</span><br><a href="/counties">View all 87 Minnesota county dashboards →</a></div>
</div>"""
    body = render_attention(state, alerts) + "<br>" + body
    rows = []
    categories = sorted({str(meta.get("category") or src.get("category") or "Other") for _,src,meta,_,_ in enriched})
    for sid, src, meta, stats, hist in sorted(enriched, key=lambda x: str(x[1].get("name", x[0])).lower()):
        provider = meta.get("provider") or src.get("provider") or "—"
        category = meta.get("category") or src.get("category") or "Other"
        prev_count = next((x.get("feature_count") for x in reversed(hist[:-1]) if x.get("feature_count") is not None), None) if len(hist) > 1 else None
        current_count = src.get("feature_count")
        delta = current_count - prev_count if isinstance(current_count,(int,float)) and isinstance(prev_count,(int,float)) else None
        delta_text = "—" if delta is None else f"{delta:+,}"
        delta_class = "delta-up" if isinstance(delta,(int,float)) and delta > 0 else "delta-down" if isinstance(delta,(int,float)) and delta < 0 else ""
        status = str(src.get("status") or "unknown")
        timing = "overdue" if src.get("stale") or src.get("worker_stale") else "recent" if _dashboard._parse_time(src.get("checked_at")) else "unknown"
        priority = 0 if status == "error" else 1 if status == "warn" else 2 if timing == "overdue" else 3 if timing == "unknown" else 4
        name = str(src.get("name") or sid)
        search = " ".join(str(x) for x in (name, sid, provider, category, src.get("worker") or "")).lower()
        successes = sum(x.get("status") == "ok" for x in hist)
        rows.append(f'''<tr data-name="{_dashboard._esc(name.lower())}" data-search="{_dashboard._esc(search)}" data-category="{_dashboard._esc(category)}" data-status="{_dashboard._esc(status)}" data-timing="{timing}" data-priority="{priority}" data-last="{_dashboard._esc(src.get("checked_at") or "")}" data-success="{_dashboard._esc(src.get("last_success_at") or "")}">
<th scope="row"><a href="/source?{_dashboard.urllib.parse.urlencode({'id':sid})}"><strong>{_dashboard._esc(name)}</strong></a><br><span class="subtext">{_dashboard._esc(sid)}</span></th>
<td data-label="Provider / type">{_dashboard._esc(provider)}<br><span class="subtext">{_dashboard._esc(category)}</span></td>
<td data-label="Latest check result"><span class="pill {_dashboard._status_class(status)}">{_dashboard._esc(RESULTS.get(status, "Unknown"))}</span><br><span class="subtext {'warn' if timing == 'overdue' else ''}">{_dashboard._esc(check_timing(src))}</span></td>
<td data-label="Last known records">{_dashboard._esc(measurement(current_count, missing="Unavailable"))}<br><span class="{delta_class}">{_dashboard._esc(delta_text)}</span></td>
<td data-label="Days since change detected">{_dashboard._esc(stats.get('change_age_days') if stats.get('change_age_days') is not None else 'Unavailable')}</td>
<td data-label="Recent observations passed">{_dashboard._esc(measurement(stats.get('success_rate'), '%', missing='No history'))}<br><span class="subtext">{successes} of {len(hist)} retained observations · {stats['consecutive_ok']} consecutive passed</span></td>
<td data-label="Response time">{_dashboard._esc(duration(src.get('elapsed_ms')))}</td><td data-label="Check times"><small>Latest attempt</small><br>{compact_time(src.get('checked_at'))}<br><small>Last success</small><br>{compact_time(src.get('last_success_at'))}</td></tr>''')
    options = "".join(f'<option value="{_dashboard._esc(x)}">{_dashboard._esc(x)}</option>' for x in categories)
    source_table = _source_table(rows, options)
    if sources_only:
        return _dashboard._layout(page_title("Data sources"), source_table, active_section="sources", csrf_token=str(config.get("_csrf_token") or ""))
    body += source_table
    body += '<section class="card" id="changes"><h2>Recent changes</h2><a href="/changes">View and filter all retained changes →</a>' + render_change_list(change_events(config, state, history=retained_runs), preview=True) + '</section>'
    run_wall = [((x.get("telemetry") or {}).get("wall_ms") or 0) / 1000.0 if (x.get("telemetry") or {}).get("wall_ms") is not None else None for x in run_history]
    run_cpu = [((x.get("telemetry") or {}).get("cpu_ms") or 0) / 1000.0 if (x.get("telemetry") or {}).get("cpu_ms") is not None else None for x in run_history]
    run_mem = [((x.get("telemetry") or {}).get("peak_python_memory_kb") or 0) / 1024.0 if (x.get("telemetry") or {}).get("peak_python_memory_kb") is not None else None for x in run_history]
    run_sources = [(x.get("telemetry") or {}).get("sources_checked") for x in run_history]
    failure_rates = []
    for x in run_history:
        counts = x.get("counts") or {}
        total = sum(int(counts.get(k) or 0) for k in ("ok","warn","error"))
        failure_rates.append(round(int(counts.get("error") or 0) / total * 100.0, 2) if total else None)
    telemetry_charts = (
        '<div class="grid">'
        f'<div class="card"><h3>How long Watchtower checks have taken</h3>{_dashboard._svg_sparkline(run_wall, label="Check run duration", unit="s")}</div>'
        f'<div class="card"><h3>Computer processing time used</h3>{_dashboard._svg_sparkline(run_cpu, label="CPU time", unit="s")}</div>'
        f'<div class="card"><h3>Memory used by Watchtower</h3>{_dashboard._svg_sparkline(run_mem, label="Python memory", unit="MiB")}</div>'
        '</div><div class="grid">'
        f'<div class="card"><h3>Data sources checked per run</h3>{_dashboard._svg_sparkline(run_sources, label="Sources checked", unit="sources")}</div>'
        f'<div class="card"><h3>Checks that could not be completed</h3>{_dashboard._svg_sparkline(failure_rates, label="Failed checks", unit="%")}</div>'
        '</div>'
    )
    body += '<details class="card diagnostics" id="monitoring-systems"><summary>Monitoring systems and diagnostics</summary><p>Last check results and reporting time are separate. The charts describe retained observations.</p><div class="grid worker-grid">' + (''.join(worker_cards) or '<p>Monitoring system reports are unavailable.</p>') + '</div>' + telemetry_charts
    if run_history:
        body += f'<p class="subtext">{len(run_history)} retained runs: {compact_time(run_history[0].get("generated_at"))} – {compact_time(run_history[-1].get("generated_at"))}. Missing measurements stay unconnected.</p>'
    latency_chart = _dashboard._bar_chart(sorted([(src.get("name") or sid, src.get("elapsed_ms")) for sid,src in sources.items() if isinstance(src.get("elapsed_ms"),(int,float))], key=lambda x:x[1], reverse=True)[:8], title="Sources taking longest to respond", suffix=" ms")
    category_counts = {}
    for _,src,meta,_,_ in enriched:
        cat = meta.get("category") or src.get("category") or "Other"
        category_counts[cat] = category_counts.get(cat,0)+1
    category_chart = _dashboard._bar_chart(sorted(category_counts.items(), key=lambda x:x[1], reverse=True), title="Data sources by category")
    body += '<div class="section-head"><div><h2>Source overview</h2><p>Response behavior and source mix across the current cloud and local results.</p></div></div>'
    body += f'<div class="grid"><div class="card">{latency_chart}<span class="subtext">Latest source-check response time; longer does not necessarily mean unhealthy.</span></div><div class="card">{category_chart}<span class="subtext">Number of monitored source observations grouped by data category.</span></div></div>'
    county_direct = [(src.get("name") or sid, src.get("feature_count")) for sid,src in sources.items() if _county_direct_parcels(sid, src) and isinstance(src.get("feature_count"), (int,float))]
    county_fields = [(src.get("name") or sid, src.get("field_count")) for sid,src in sources.items() if _county_direct_parcels(sid, src) and isinstance(src.get("field_count"), (int,float))]
    county_counts_chart = _dashboard._bar_chart(sorted(county_direct, key=lambda x:x[1], reverse=True)[:10], title="Counties with the most parcel records")
    county_fields_chart = _dashboard._bar_chart(sorted(county_fields, key=lambda x:x[1], reverse=True)[:10], title="Number of information fields in county parcel data")
    null_ids = [(src.get("name") or sid, src.get("parcel_id_null_count")) for sid,src in sources.items() if _county_direct_parcels(sid, src) and isinstance(src.get("parcel_id_null_count"), (int,float))]
    duplicate_ids = [(src.get("name") or sid, src.get("duplicate_id_extra_rows")) for sid,src in sources.items() if _county_direct_parcels(sid, src) and isinstance(src.get("duplicate_id_extra_rows"), (int,float))]
    null_geometry = [(src.get("name") or sid, src.get("null_geometry_count")) for sid,src in sources.items() if _county_direct_parcels(sid, src) and isinstance(src.get("null_geometry_count"), (int,float))]
    quality_chart = _dashboard._bar_chart(sorted(null_ids, key=lambda x:x[1], reverse=True), title="Parcel records missing an ID")
    duplicate_chart = _dashboard._bar_chart(sorted(duplicate_ids, key=lambda x:x[1], reverse=True), title="Records that share the same parcel ID")
    geometry_chart = _dashboard._bar_chart(sorted(null_geometry, key=lambda x:x[1], reverse=True), title="Parcel records with no mapped shape")
    owner_complete=[]; site_address_complete=[]; mailing_address_complete=[]
    for sid,src in sources.items():
        if not _county_direct_parcels(sid, src): continue
        profiles=src.get("completeness_profiles") or {}
        if isinstance((profiles.get("owner") or {}).get("complete_percent"), (int,float)): owner_complete.append((src.get("name") or sid, profiles["owner"]["complete_percent"]))
        if isinstance((profiles.get("site_address") or {}).get("complete_percent"), (int,float)): site_address_complete.append((src.get("name") or sid, profiles["site_address"]["complete_percent"]))
        if isinstance((profiles.get("mailing_address") or {}).get("complete_percent"), (int,float)): mailing_address_complete.append((src.get("name") or sid, profiles["mailing_address"]["complete_percent"]))
    owner_chart=_dashboard._bar_chart(sorted(owner_complete,key=lambda x:x[1]),title="Records with an owner name",suffix="%")
    site_address_chart=_dashboard._bar_chart(sorted(site_address_complete,key=lambda x:x[1]),title="Records with a property address",suffix="%")
    mailing_address_chart=_dashboard._bar_chart(sorted(mailing_address_complete,key=lambda x:x[1]),title="Records with an owner mailing address",suffix="%")
    multipart = [(src.get("name") or sid, src.get("geometry_sample_multipart_percent")) for sid,src in sources.items() if _county_direct_parcels(sid, src) and isinstance(src.get("geometry_sample_multipart_percent"),(int,float))]
    complexity = [(src.get("name") or sid, src.get("geometry_sample_avg_vertices")) for sid,src in sources.items() if _county_direct_parcels(sid, src) and isinstance(src.get("geometry_sample_avg_vertices"),(int,float))]
    multipart_chart=_dashboard._bar_chart(sorted(multipart,key=lambda x:x[1],reverse=True),title="Sampled parcel shapes with multiple parts or holes",suffix="%")
    complexity_chart=_dashboard._bar_chart(sorted(complexity,key=lambda x:x[1],reverse=True),title="Average parcel-shape complexity")
    body += '<div class="section-head"><div><h2>Parcel-source quality</h2><p>Comparative quality indicators for directly monitored county parcel layers.</p></div></div>'
    body += f'<div class="grid"><div class="card">{county_counts_chart}</div><div class="card">{county_fields_chart}</div></div><div class="grid"><div class="card">{quality_chart}</div><div class="card">{duplicate_chart}</div><div class="card">{geometry_chart}</div></div><div class="grid"><div class="card">{owner_chart}</div><div class="card">{site_address_chart}</div><div class="card">{mailing_address_chart}</div></div><div class="grid"><div class="card">{multipart_chart}</div><div class="card">{complexity_chart}</div></div>'
    body += "</details>"
    return _dashboard._layout(PRODUCT_NAME, body, csrf_token=str(config.get("_csrf_token") or ""))


def render_source(config: dict, source_id: str) -> str:
    from .dashboard_source import render_source as render
    return render(config, source_id)


def _source_table(rows: list[str], options: str) -> str:
    return f'''<section class="card" id="datasets"><h2>Data sources</h2><p>Last recorded results, with check timing shown separately. Access permissions do not follow from a successful check.</p>
<div class="filters"><input id="q" type="search" aria-label="Search source names, providers and IDs" placeholder="Search sources, providers or IDs…"><select id="cat" aria-label="Filter source category"><option value="">All categories</option>{options}</select>
<select id="health" aria-label="Filter check result"><option value="">All check results</option><option value="ok">Passed</option><option value="warn">Needs attention</option><option value="error">Failed</option><option value="unknown">Unknown</option><option value="paused">Paused</option><option value="awaiting-permission">Awaiting permission</option></select>
<select id="check-timing" aria-label="Filter check timing"><option value="">All check times</option><option value="recent">Recent</option><option value="overdue">Overdue</option><option value="unknown">Time unavailable</option></select>
<select id="source-sort" aria-label="Sort sources"><option value="priority">Needs attention first</option><option value="name">Source name</option><option value="oldest">Oldest check first</option><option value="success">Oldest success first</option></select><button type="button" id="source-clear">Clear filters</button></div>
<p id="source-results" role="status"></p><table class="ops-table" id="source-list"><thead><tr><th>Data source</th><th>Provided by / type</th><th>Latest check result</th><th>Last known records / change</th><th>Days since change detected</th><th>Recent observations passed</th><th>Response time</th><th>Check times</th></tr></thead><tbody>{"".join(rows)}</tbody></table><p id="source-empty" hidden>No sources match these filters.</p></section>
{SCRIPT_TAG}(function(){{const ids=['q','cat','health','check-timing'],controls=ids.map(id=>document.getElementById(id)),sort=document.getElementById('source-sort'),body=document.querySelector('#source-list tbody');function filterRows(){{const[q,c,h,t]=controls.map(e=>e.value.toLowerCase());const rows=[...body.rows];rows.sort((a,b)=>sort.value==='name'?a.dataset.name.localeCompare(b.dataset.name):['oldest','success'].includes(sort.value)?(Date.parse(a.dataset[sort.value==='success'?'success':'last'])||0)-(Date.parse(b.dataset[sort.value==='success'?'success':'last'])||0):Number(a.dataset.priority)-Number(b.dataset.priority)||a.dataset.name.localeCompare(b.dataset.name));let n=0;rows.forEach(r=>{{body.append(r);const show=(!q||r.dataset.search.includes(q))&&(!c||r.dataset.category.toLowerCase()===c)&&(!h||r.dataset.status===h)&&(!t||r.dataset.timing===t);r.hidden=!show;if(show)n++}});document.getElementById('source-results').textContent=n+' of '+rows.length+' sources shown';document.getElementById('source-empty').hidden=n>0}}controls.forEach(e=>e.addEventListener(e.tagName==='SELECT'?'change':'input',filterRows));sort.addEventListener('change',filterRows);document.getElementById('source-clear').addEventListener('click',()=>{{controls.forEach(e=>e.value='');sort.value='priority';filterRows();controls[0].focus();window.watchtowerRefresh?.save()}});filterRows()}})();</script>'''
