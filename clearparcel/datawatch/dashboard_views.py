from __future__ import annotations

from clearparcel.datawatch import dashboard as _dashboard


def render_dashboard(config: dict) -> str:
    state = _dashboard._dashboard_state(config)
    sources = state.get("sources", {})
    counts = state.get("counts", {})
    alerts = state.get("active_alerts", [])
    config_map = _dashboard._source_config_map(config)
    enriched = []
    changed_30 = 0
    for sid, src in sources.items():
        hist = _dashboard.load_history(config, source_filter=sid, limit=60).get("entries", [])
        stats = _dashboard._history_stats(hist)
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
        worker_health = _dashboard._health_status(worker_status)
        stale = bool(worker.get("stale"))
        worker_telemetry = worker.get("telemetry") or {}
        duration = worker_telemetry.get("wall_ms")
        duration_text = f"{duration / 1000.0:.1f}s" if isinstance(duration, (int, float)) else "—"
        source_count = worker.get("source_count")
        freshness_text = "Reporting overdue" if stale else "Reporting on time"
        worker_cards.append(f"""<div class="card worker-card">
<div><h3><span class="status-dot {_dashboard._status_class(worker_status)}"></span>{_dashboard._esc(worker_name.title())} worker</h3><span class="subtext">{_dashboard._esc(worker_health)} · {_dashboard._esc(freshness_text)}</span></div>
<div class="worker-meta">
<div><span class="muted">Sources</span><strong>{_dashboard._esc(source_count if source_count is not None else "—")}</strong></div>
<div><span class="muted">Run time</span><strong>{_dashboard._esc(duration_text)}</strong></div>
<div><span class="muted">Last success</span><strong style="font-size:13px">{_dashboard._format_time_pair(worker.get("last_success_at"))}</strong></div>
</div></div>""")
    body = f"""<div class="grid primary-grid">
<div class="card"><div class="muted">Overall health</div><div class="metric {_dashboard._status_class(state.get('overall','unknown'))}">{_dashboard._esc(_dashboard._health_status(state.get('overall','unknown')))}</div><span class="subtext">Combined health of all cloud and local source checks.</span></div>
<div class="card"><div class="muted">Monitored sources</div><div class="metric">{len(sources)}</div><span class="subtext">Sources currently included across the cloud and local workers.</span></div>
<div class="card"><div class="muted">Source issues</div><div class="metric">{counts.get('warn',0) + counts.get('error',0)}</div><span class="subtext">Sources whose latest check reported a warning or error.</span></div>
<div class="card"><div class="muted">Reporting overdue</div><div class="metric">{state.get('stale_sources',0)}</div><span class="subtext">Sources that have not reported within the configured freshness window · {state.get('stale_workers',0)} worker(s) overdue.</span></div>
</div>
<div class="section-head"><div><h2>Workers</h2><p>Cloud and local worker health and their most recent successful runs.</p></div></div>
<div class="grid worker-grid">{''.join(worker_cards) or '<div class="card muted">Worker metadata has not been reported yet.</div>'}</div>
<div class="activity-strip">
<div class="card" id="changes"><div class="muted">Sources changed — 30 days</div><div class="metric">{changed_30}</div><span class="subtext">Sources where Watchtower detected a data change during the last 30 days.</span></div>
<div class="card"><div class="muted">Dashboard data updated</div><strong>{_dashboard._format_time_pair(state.get('generated_at'))}</strong><span class="subtext">When Watchtower last combined the cloud and local worker results.</span><br><a href="/counties">View all 87 Minnesota county dashboards →</a></div>
</div>"""
    if alerts:
        body += '<div class="card" id="alerts"><h2>Active alerts</h2>' + "".join(
            f'<p class="{_dashboard._status_class(a.get("severity","warn"))}"><strong>{_dashboard._esc(a.get("name") or a.get("source"))}</strong> — {_dashboard._esc(a.get("message"))}</p>'
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
        rows.append(f"""<tr data-name="{_dashboard._esc((src.get('name') or sid).lower())}" data-category="{_dashboard._esc(category)}" data-status="{_dashboard._esc(src.get('status','unknown'))}">
<td><a href="/source?{_dashboard.urllib.parse.urlencode({'id':sid})}"><strong>{_dashboard._esc(src.get('name') or sid)}</strong></a><br><span class="muted">{_dashboard._esc(sid)}</span></td>
<td>{_dashboard._esc(provider)}<br><span class="muted">{_dashboard._esc(category)}</span></td>
<td><span class="pill {_dashboard._status_class(src.get('status','unknown'))}">{_dashboard._esc(_dashboard._health_status(src.get('status','unknown')))}</span><br><span class="muted">{_dashboard._esc(src.get('reporting','current'))} reporting · {_dashboard._esc(src.get('worker') or 'default')} worker</span></td>
<td>{_dashboard._esc(f"{current_count:,}" if isinstance(current_count,int) else current_count or '—')}<br><span class="{delta_class}">{_dashboard._esc(delta_text)}</span></td>
<td>{_dashboard._esc(stats.get('change_age_days') if stats.get('change_age_days') is not None else '—')}</td>
<td>{_dashboard._esc(stats.get('success_rate') if stats.get('success_rate') is not None else '—')}%<br><span class="muted">{_dashboard._esc(stats.get('consecutive_ok'))} consecutive</span></td>
<td>{_dashboard._esc(src.get('elapsed_ms','—'))} ms</td><td>{_dashboard._format_time_pair(src.get('last_success_at'))}</td></tr>""")
    options = "".join(f'<option value="{_dashboard._esc(x)}">{_dashboard._esc(x)}</option>' for x in categories)
    run_history = _dashboard.load_history(config, limit=60).get("entries", [])
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
        f'<div class="card"><h3>How long Watchtower checks have taken</h3>{_dashboard._svg_sparkline(run_wall)}</div>'
        f'<div class="card"><h3>Computer processing time used</h3>{_dashboard._svg_sparkline(run_cpu)}</div>'
        f'<div class="card"><h3>Memory used by Watchtower</h3>{_dashboard._svg_sparkline(run_mem)}</div>'
        '</div><div class="grid">'
        f'<div class="card"><h3>Data sources checked per run</h3>{_dashboard._svg_sparkline(run_sources)}</div>'
        f'<div class="card"><h3>Checks that could not be completed</h3>{_dashboard._svg_sparkline(failure_rates)}</div>'
        '</div>'
    )
    body += '<details class="diagnostics"><summary>System diagnostics</summary><span class="subtext">Runtime telemetry from retained checks. These are operational diagnostics, not source-health scores.</span>' + telemetry_charts + '</details>'
    latency_chart = _dashboard._bar_chart(sorted([(src.get("name") or sid, src.get("elapsed_ms")) for sid,src in sources.items() if isinstance(src.get("elapsed_ms"),(int,float))], key=lambda x:x[1], reverse=True)[:8], title="Sources taking longest to respond", suffix=" ms")
    category_counts = {}
    for _,src,meta,_,_ in enriched:
        cat = meta.get("category") or src.get("category") or "Other"
        category_counts[cat] = category_counts.get(cat,0)+1
    category_chart = _dashboard._bar_chart(sorted(category_counts.items(), key=lambda x:x[1], reverse=True), title="Data sources by category")
    body += '<div class="section-head"><div><h2>Source overview</h2><p>Response behavior and source mix across the current cloud and local results.</p></div></div>'
    body += f'<div class="grid"><div class="card">{latency_chart}<span class="subtext">Latest source-check response time; longer does not necessarily mean unhealthy.</span></div><div class="card">{category_chart}<span class="subtext">Number of monitored source observations grouped by data category.</span></div></div>'
    county_direct = [(src.get("name") or sid, src.get("feature_count")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("feature_count"), (int,float))]
    county_fields = [(src.get("name") or sid, src.get("field_count")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("field_count"), (int,float))]
    county_counts_chart = _dashboard._bar_chart(sorted(county_direct, key=lambda x:x[1], reverse=True)[:10], title="Counties with the most parcel records")
    county_fields_chart = _dashboard._bar_chart(sorted(county_fields, key=lambda x:x[1], reverse=True)[:10], title="Number of information fields in county parcel data")
    null_ids = [(src.get("name") or sid, src.get("parcel_id_null_count")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("parcel_id_null_count"), (int,float))]
    duplicate_ids = [(src.get("name") or sid, src.get("duplicate_id_extra_rows")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("duplicate_id_extra_rows"), (int,float))]
    null_geometry = [(src.get("name") or sid, src.get("null_geometry_count")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("null_geometry_count"), (int,float))]
    quality_chart = _dashboard._bar_chart(sorted(null_ids, key=lambda x:x[1], reverse=True), title="Parcel records missing an ID")
    duplicate_chart = _dashboard._bar_chart(sorted(duplicate_ids, key=lambda x:x[1], reverse=True), title="Records that share the same parcel ID")
    geometry_chart = _dashboard._bar_chart(sorted(null_geometry, key=lambda x:x[1], reverse=True), title="Parcel records with no mapped shape")
    owner_complete=[]; site_address_complete=[]; mailing_address_complete=[]
    for sid,src in sources.items():
        if not sid.endswith("-parcels-direct"): continue
        profiles=src.get("completeness_profiles") or {}
        if isinstance((profiles.get("owner") or {}).get("complete_percent"), (int,float)): owner_complete.append((src.get("name") or sid, profiles["owner"]["complete_percent"]))
        if isinstance((profiles.get("site_address") or {}).get("complete_percent"), (int,float)): site_address_complete.append((src.get("name") or sid, profiles["site_address"]["complete_percent"]))
        if isinstance((profiles.get("mailing_address") or {}).get("complete_percent"), (int,float)): mailing_address_complete.append((src.get("name") or sid, profiles["mailing_address"]["complete_percent"]))
    owner_chart=_dashboard._bar_chart(sorted(owner_complete,key=lambda x:x[1]),title="Records with an owner name",suffix="%")
    site_address_chart=_dashboard._bar_chart(sorted(site_address_complete,key=lambda x:x[1]),title="Records with a property address",suffix="%")
    mailing_address_chart=_dashboard._bar_chart(sorted(mailing_address_complete,key=lambda x:x[1]),title="Records with an owner mailing address",suffix="%")
    multipart = [(src.get("name") or sid, src.get("geometry_sample_multipart_percent")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("geometry_sample_multipart_percent"),(int,float))]
    complexity = [(src.get("name") or sid, src.get("geometry_sample_avg_vertices")) for sid,src in sources.items() if sid.endswith("-parcels-direct") and isinstance(src.get("geometry_sample_avg_vertices"),(int,float))]
    multipart_chart=_dashboard._bar_chart(sorted(multipart,key=lambda x:x[1],reverse=True),title="Sampled parcel shapes with multiple parts or holes",suffix="%")
    complexity_chart=_dashboard._bar_chart(sorted(complexity,key=lambda x:x[1],reverse=True),title="Average parcel-shape complexity")
    body += '<div class="section-head"><div><h2>Parcel-source quality</h2><p>Comparative quality indicators for directly monitored county parcel layers.</p></div></div>'
    body += f'<div class="grid"><div class="card">{county_counts_chart}</div><div class="card">{county_fields_chart}</div></div><div class="grid"><div class="card">{quality_chart}</div><div class="card">{duplicate_chart}</div><div class="card">{geometry_chart}</div></div><div class="grid"><div class="card">{owner_chart}</div><div class="card">{site_address_chart}</div><div class="card">{mailing_address_chart}</div></div><div class="grid"><div class="card">{multipart_chart}</div><div class="card">{complexity_chart}</div></div>'
    body += f"""<div class="card"><h2>Data being watched</h2>
<div class="filters"><input id="q" aria-label="Filter data sources" placeholder="Filter datasets…" oninput="filterRows()"><select id="cat" aria-label="Filter by source category" onchange="filterRows()"><option value="">All categories</option>{options}</select><select id="health" aria-label="Filter by source health" onchange="filterRows()"><option value="">All statuses</option><option>ok</option><option>warn</option><option>error</option></select></div>
<table id="datasets"><thead><tr><th>Data source</th><th>Provided by / type</th><th>Status</th><th>Records / change<br><span class="subtext">Current count and change from the prior comparable check</span></th><th>Days since data changed<br><span class="subtext">Days since Watchtower last detected a source-data change</span></th><th>Recent reliability<br><span class="subtext">Successful checks across retained recent history</span></th><th>Response time<br><span class="subtext">Elapsed time for the source request/check</span></th><th>Last successful check<br><span class="subtext">Most recent successful observation, not merely last attempt</span></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<script>function filterRows(){{const q=document.getElementById('q').value.toLowerCase(),c=document.getElementById('cat').value,h=document.getElementById('health').value;document.querySelectorAll('#datasets tbody tr').forEach(r=>{{r.style.display=(!q||r.dataset.name.includes(q))&&(!c||r.dataset.category===c)&&(!h||r.dataset.status===h)?'':'none'}})}};</script>"""
    return _dashboard._layout("GIS Data Watchtower", body, csrf_token=str(config.get("_csrf_token") or ""))


def render_source(config: dict, source_id: str) -> str:
    state = _dashboard._dashboard_state(config)
    src = (state.get("sources") or {}).get(source_id)
    if not src:
        return _dashboard._layout("Source not found", '<div class="card"><h2>Source not found</h2><p><a href="/">Return to dashboard</a></p></div>', csrf_token=str(config.get("_csrf_token") or ""))
    hist = _dashboard.load_history(config, source_filter=source_id, limit=60).get("entries", [])
    stats = _dashboard._history_stats(hist)
    meta = _dashboard._source_config_map(config).get(source_id, {})
    provenance = src.get("provenance") or {}
    changes = src.get("changes") or []
    feature_values = [x.get("feature_count") for x in hist]
    latency_values = [x.get("elapsed_ms") for x in hist]
    history_rows = "".join(
        f"<tr><td>{_dashboard._format_time_pair(x.get('generated_at'))}</td><td>{_dashboard._esc(x.get('status'))}</td><td>{_dashboard._esc(f'{x.get("feature_count"):,}' if isinstance(x.get('feature_count'),int) else x.get('feature_count','—'))}</td><td>{_dashboard._esc(len(x.get('changes') or []))}</td><td>{_dashboard._esc(x.get('elapsed_ms','—'))} ms</td></tr>"
        for x in reversed(hist[-30:])
    )
    provider = meta.get("provider") or src.get("provider") or "—"
    category = meta.get("category") or src.get("category") or "—"
    source_count_text = _dashboard._esc(f"{src.get('feature_count'):,}" if isinstance(src.get('feature_count'),int) else src.get('feature_count','—'))
    body = f"""<p><a href="/">← All data sources</a></p><div class="grid">
<div class="card"><div class="muted">Data source</div><h2>{_dashboard._esc(src.get('name') or source_id)}</h2><code>{_dashboard._esc(source_id)}</code></div>
<div class="card"><div class="muted">Health</div><div class="metric {_dashboard._status_class(src.get('status','unknown'))}">{_dashboard._esc(_dashboard._health_status(src.get('status','unknown')))}</div><span class="subtext">{_dashboard._esc('Reporting overdue' if src.get('reporting') == 'stale' else 'Reporting on time')} · {_dashboard._esc(src.get('worker') or 'local/default')} worker</span></div>
<div class="card"><div class="muted">Record count</div><div class="metric">{source_count_text}</div><span class="subtext">Features or rows reported during the latest successful check.</span></div>
<div class="card"><div class="muted">Recent reliability</div><div class="metric">{_dashboard._esc(stats.get('success_rate') if stats.get('success_rate') is not None else '—')}%</div><span class="subtext">{_dashboard._esc(stats.get('consecutive_ok'))} successful checks in a row.</span></div>
<div class="card"><div class="muted">Days since data changed</div><div class="metric">{_dashboard._esc(stats.get('change_age_days') if stats.get('change_age_days') is not None else '—')}</div><span class="subtext">Elapsed days since Watchtower last detected a meaningful observation change.</span></div></div>
<div class="grid"><div class="card"><h3>Record-count history</h3>{_dashboard._svg_sparkline(feature_values)}</div><div class="card"><h3>Response-time history</h3>{_dashboard._svg_sparkline(latency_values)}</div></div>

<div class="section-head"><div><h2>About this data</h2><p>Operational source facts first; low-level adapter and coordinate details remain expandable below.</p></div></div>
<div class="definition-grid">
<div class="definition-group"><h3>Source</h3><dl class="definition-list">
<dt>Provided by</dt><dd>{_dashboard._esc(provider)}</dd><dt>Data type</dt><dd>{_dashboard._esc(category)}</dd><dt>Checked by</dt><dd>{_dashboard._esc(src.get('worker') or 'local/default')} worker</dd><dt>Reporting</dt><dd>{_dashboard._esc(src.get('reporting') or 'current')}</dd><dt>Last successful check</dt><dd>{_dashboard._format_time_pair(src.get('last_success_at'))}</dd><dt>Changes this check</dt><dd>{len(changes)}</dd><dt>Last change found</dt><dd>{_dashboard._format_time_pair(stats.get('last_change')) if stats.get('last_change') else 'Not yet recorded'}</dd>
</dl></div>
<div class="definition-group"><h3>Parcel quality</h3><dl class="definition-list">
<dt>Records</dt><dd>{source_count_text}</dd><dt>Information fields</dt><dd>{_dashboard._esc(src.get('field_count','—'))}</dd><dt>Parcel ID field</dt><dd>{_dashboard._esc(src.get('parcel_id_field','Not identified'))} ({_dashboard._esc(src.get('parcel_id_confidence','none'))} confidence)</dd><dt>Missing parcel IDs</dt><dd>{_dashboard._esc(src.get('parcel_id_null_count','Not checked'))}</dd><dt>Duplicate-ID extra rows</dt><dd>{_dashboard._esc(src.get('duplicate_id_extra_rows','Not checked'))}</dd><dt>Missing mapped shape</dt><dd>{_dashboard._esc(src.get('null_geometry_count','Not checked'))}</dd>
</dl></div>
<div class="definition-group"><h3>Shape sample</h3><dl class="definition-list">
<dt>Shapes sampled</dt><dd>{_dashboard._esc(src.get('geometry_sample_size','Not checked'))}</dd><dt>Multipart / holes</dt><dd>{_dashboard._esc(src.get('geometry_sample_multipart_percent','Not checked'))}%</dd><dt>Average complexity</dt><dd>{_dashboard._esc(src.get('geometry_sample_avg_vertices','Not checked'))}</dd><dt>Most complex shape</dt><dd>{_dashboard._esc(src.get('geometry_sample_max_vertices','Not checked'))}</dd>
</dl></div>
</div><br>
<div class="card"><details class="technical"><summary>Technical details</summary><div class="technical-body"><dl class="definition-list">
<dt>Source connection</dt><dd>{_dashboard._esc(provenance.get('adapter') or src.get('adapter') or src.get('kind'))}</dd>
<dt>Map shape type</dt><dd>{_dashboard._esc(src.get('geometry_type','—'))}</dd>
<dt>Coordinate system code</dt><dd>{_dashboard._esc(src.get('wkid','—'))}</dd>
<dt>Parcel map layer</dt><dd>{_dashboard._esc(src.get('parcel_layer_name','Direct layer'))}</dd>
<dt>Mapped extent</dt><dd><code>{_dashboard._esc(src.get('spatial_extent','Not reported'))}</code></dd>
<dt>Last checked</dt><dd>{_dashboard._format_time_pair(provenance.get('observed_at') or src.get('checked_at'))}</dd>
<dt>Publisher modified</dt><dd>{_dashboard._esc(provenance.get('publisher_modified') or 'Not reported')}</dd>
<dt>Source address</dt><dd><code>{_dashboard._esc(provenance.get('source_url') or src.get('url'))}</code></dd>
<dt>Structure comparison ID</dt><dd><code>{_dashboard._esc(src.get('schema_hash'))}</code></dd>
<dt>Observation comparison ID</dt><dd><code>{_dashboard._esc(src.get('observation_fingerprint'))}</code></dd>
</dl></div></details></div><br>
<div class="card"><h2>Check history</h2><span class="subtext">Recent retained observations for this source.</span><table class="history-table"><thead><tr><th>Last checked</th><th>Status</th><th>Records</th><th>Changes found</th><th>Response time</th></tr></thead><tbody>{history_rows}</tbody></table></div>"""
    return _dashboard._layout(f"{src.get('name') or source_id}", body, csrf_token=str(config.get("_csrf_token") or ""))
