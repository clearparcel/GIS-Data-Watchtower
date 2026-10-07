from __future__ import annotations

import json
import urllib.parse

from clearparcel.datawatch import dashboard as _dashboard
from clearparcel.datawatch.county_profile_panel import (
    NO_DATA_COLOR,
    percentage_color_js,
    percentage_legend,
    profile_time,
    render_county_profile_panel,
)
from clearparcel.datawatch.gac_standards import (
    gac_defaults,
    load_gac_standard,
    normalize_standard_key,
    standard_keys,
)
from clearparcel.datawatch.parcel_access import load_parcel_access


def _gac_standard_selector(active: str) -> str:
    labels = {"parcel": "Parcels", "address": "Address Points", "road": "Road Centerlines"}
    links = []
    for key in standard_keys():
        cls = "primary" if key == active else ""
        links.append(
            f'<a class="{cls}" href="/mngac?standard={_dashboard._esc(key)}">{_dashboard._esc(labels[key])}</a>'
        )
    return (
        '<div class="card"><div class="muted">MN GAC standard</div>'
        '<div class="hero-actions" style="margin-top:8px">' + "".join(links) + '</div></div><br>'
    )

def _render_gac_standard(config: dict, standard_key: str) -> str:
    standard_key = normalize_standard_key(standard_key)
    state = _dashboard._dashboard_state(config)
    data = _dashboard._gac_data(state, standard_key)
    schema = load_gac_standard(standard_key)
    defaults = gac_defaults(standard_key)
    standard = schema.get("standard") or {}
    all_counties = _dashboard._load_counties()
    total_counties = len(all_counties)
    selector = _gac_standard_selector(standard_key)
    publication = f'<p>Public publication: {_dashboard._esc(profile_time(state.get("public_published_at")))}</p>'
    _, gac_source = _dashboard._gac_source(state, standard_key)
    failed_check = (gac_source or {}).get("gac_check_status") in {"error", "unsupported"}
    failure_notice = (
        f'<div class="mngac-note warn" role="status"><strong>Latest configured GAC check failed:</strong> '
        f'{_dashboard._esc((gac_source or {}).get("gac_check_error") or "The result may be from an earlier successful observation.")}</div>'
        if failed_check else ""
    )
    if not data:
        body = (
            selector
            + failure_notice
            + '<p><a href="/counties">← Minnesota counties</a></p>'
            + f'<div class="card"><h2>{_dashboard._esc(standard.get("short_name") or "MN GAC")} data is not available yet</h2>'
            + f'<p>The configured {_dashboard._esc(defaults["dataset_label"])} source has not published a stored '
              'GAC completeness observation. No 0% values are inferred from absence.</p></div>'
            + _dashboard._mngac_map_svg().replace(
                'class="mngac-county"',
                f'class="mngac-county" style="fill:{NO_DATA_COLOR}"'
            )
            + percentage_legend() + publication
        )
        return _dashboard._layout(
            f'{standard.get("short_name") or "MN GAC"} Completeness — GIS Data Watchtower',
            body, refresh_seconds=300, static=bool(config.get("_public_mode")),
            csrf_token=str(config.get("_csrf_token") or "")
        )

    covered = int(data.get("covered_counties") or 0)
    record_count = data.get("record_count")
    field_count = int(data.get("field_count") or len(schema.get("fields") or []))
    mandatory_count = int(data.get("mandatory_field_count") or 0)
    text_population_mode = str(data.get("text_population_mode") or "nonblank")
    overall_pct = data.get("field_population_percent")
    mandatory_pct = data.get("mandatory_population_percent")
    population_scope = str(
        data.get("population_scope") or ("all" if isinstance(overall_pct, (int, float)) else "mandatory")
    ).lower()
    scanned_field_count = int(
        data.get("scanned_field_count")
        or (field_count if population_scope == "all" else mandatory_count)
    )
    scan_note = (
        f"Population is scanned for all {field_count} standard fields."
        if population_scope == "all"
        else f"Provider-safe default: population is scanned for the {mandatory_count} Mandatory fields only; "
             f"all {field_count} standard fields are still schema-checked."
    )
    _, source = _dashboard._gac_source(state, standard_key)
    failure_notice = (
        f'<div class="mngac-note warn" role="status"><strong>Latest configured GAC check failed:</strong> '
        f'{_dashboard._esc((source or {}).get("gac_check_error") or "Showing the last successful observation.")}</div>'
        if (source or {}).get("gac_check_status") in {"error", "unsupported"} else ""
    )
    observed_at = data.get("observed_at") or (source or {}).get("last_success_at") or (source or {}).get("checked_at")
    metadata = data.get("county_metadata") or {}
    ng911_count = sum(1 for x in metadata.values() if isinstance(x, dict) and x.get("ng911_upload") is True)
    gac_open_count = sum(1 for x in metadata.values() if isinstance(x, dict) and x.get("gac_open") is True)
    standard_url = _dashboard._safe_url((data.get("standard") or {}).get("source_url") or standard.get("source_url"))
    standard_link = (
        f'<a href="{_dashboard._esc(standard_url)}" target="_blank" rel="noopener">'
        f'{_dashboard._esc(standard.get("short_name") or standard.get("name") or "official standard")}</a>'
        if standard_url else _dashboard._esc(standard.get("short_name") or "official MN GAC standard")
    )

    options = []
    if isinstance(overall_pct, (int, float)):
        options.append(f'<option value="__overall__">All {field_count} fields — row population rate</option>')
    options.append('<option value="__mandatory__" selected>Mandatory fields — row population rate</option>')
    if population_scope == "all":
        options.append('<option value="__fields_with_values__">Fields with any values — share of standard fields</option>')
    last_section = None
    summaries = data.get("fields") or {}
    field_rows = []
    for spec in schema.get("fields") or []:
        section_name = str(spec.get("section_name") or "Other")
        if section_name != last_section:
            if last_section is not None:
                options.append("</optgroup>")
            options.append(f'<optgroup label="{_dashboard._esc(section_name)}">')
            last_section = section_name
        field = str(spec.get("field") or "")
        stats = summaries.get(field) or {}
        scanned = stats.get("population_scanned") is not False and stats.get("record_count") is not None
        if scanned:
            options.append(
                f'<option value="{_dashboard._esc(field)}">{_dashboard._esc(spec.get("section"))}.{_dashboard._esc(spec.get("order"))} '
                f'{_dashboard._esc(spec.get("label"))} ({_dashboard._esc(field)}) — {_dashboard._esc(spec.get("inclusion"))}</option>'
            )
        populated = stats.get("populated")
        total = stats.get("record_count")
        pct = stats.get("percent")
        median = stats.get("county_median_percent")
        field_control = (
            f'<button type="button" class="mngac-field-select" data-field="{_dashboard._esc(field)}">'
            f'<strong>{_dashboard._esc(spec.get("label"))}</strong><br><code>{_dashboard._esc(field)}</code></button>'
            if scanned else
            f'<strong>{_dashboard._esc(spec.get("label"))}</strong><br><code>{_dashboard._esc(field)}</code>'
            '<br><span class="subtext">Schema checked · population not scanned in this routine observation</span>'
        )
        field_rows.append(
            f'<tr data-name="{_dashboard._esc((str(spec.get("label") or "")+" "+field).lower())}" '
            f'data-inclusion="{_dashboard._esc(spec.get("inclusion") or "")}">'
            f'<td>{field_control}</td>'
            f'<td>{_dashboard._esc(section_name)}</td><td>{_dashboard._esc(spec.get("inclusion"))}</td>'
            f'<td>{"Present" if stats.get("present_in_source_schema") is True else "Missing" if stats.get("present_in_source_schema") is False else "Unknown"}</td>'
            f'<td>{"Scanned" if scanned else "Not scanned"}</td>'
            f'<td>{_dashboard._esc(f"{populated:,}" if isinstance(populated,int) else "—")} / '
            f'{_dashboard._esc(f"{total:,}" if isinstance(total,int) else "—")}</td>'
            f'<td><strong>{_dashboard._esc(f"{pct:.2f}%" if isinstance(pct,(int,float)) else "—")}</strong></td>'
            f'<td>{_dashboard._esc(f"{median:.2f}%" if isinstance(median,(int,float)) else "—")}</td></tr>'
        )
    if last_section is not None:
        options.append("</optgroup>")

    counties_payload = {}
    slug_map = _dashboard._county_slug_map()
    for county in all_counties:
        name = str(county.get("name") or "")
        stats = (data.get("counties") or {}).get(name)
        meta = metadata.get(name) if isinstance(metadata, dict) else None
        entry = {"slug": slug_map.get(name), "metadata": meta if isinstance(meta, dict) else {}}
        if isinstance(stats, dict):
            entry.update({
                "record_count": stats.get("record_count"),
                "field_population_percent": stats.get("field_population_percent"),
                "mandatory_population_percent": stats.get("mandatory_population_percent"),
                "fields_with_values": stats.get("fields_with_values"),
                "field_count": stats.get("field_count"),
                "fields": stats.get("fields") or {},
            })
        else:
            entry["available"] = False
        counties_payload[name] = entry
    payload = {
        "standard_key": standard_key,
        "record_label": defaults["record_label"],
        "dataset_label": defaults["dataset_label"],
        "field_count": field_count,
        "scanned_field_count": scanned_field_count,
        "population_scope": population_scope,
        "counties": counties_payload,
        "fields": summaries,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    export_q = urllib.parse.urlencode({"standard": standard_key})
    record_label = defaults["record_label"]
    map_svg = _dashboard._mngac_map_svg()
    county_picker_options = "".join(
        f'<option value="{_dashboard._esc(row.get("name"))}">{_dashboard._esc(row.get("name"))} County</option>'
        for row in all_counties if row.get("name")
    )
    text_rule_note = (
        "Routine text population is non-null based; empty strings may count as populated in this lightweight observation."
        if text_population_mode == "non_null"
        else "Text population excludes both NULL and empty-string values."
    )
    body = f"""
{selector}
{failure_notice}
<p><a href="/counties">← Minnesota counties</a> ·
<a href="/mngac.csv?{export_q}" data-ph-event="export" data-ph-format="csv">Download field summary (CSV)</a> ·
<a href="/mngac.json?{export_q}" data-ph-event="export" data-ph-format="json">Download GAC data (JSON)</a></p>
<div class="grid primary-grid">
  <div class="card"><div class="muted">Standard fields</div><div class="metric">{field_count}</div><span class="subtext">{_dashboard._esc(standard.get("short_name") or standard.get("name"))} v{_dashboard._esc(standard.get("version") or "—")}. {_dashboard._esc(scan_note)}</span></div>
  <div class="card"><div class="muted">Counties represented</div><div class="metric">{covered}/{total_counties}</div><span class="subtext">{_dashboard._esc(defaults["dataset_label"])} public records in this snapshot.</span></div>
  <div class="card"><div class="muted">NG911 participants</div><div class="metric">{ng911_count if metadata else "—"}/{total_counties}</div><span class="subtext">Participation reported by MnGeo metadata; separate from public-data opt-in.</span></div>
  <div class="card"><div class="muted">GAC public opt-in</div><div class="metric">{gac_open_count if metadata else "—"}/{total_counties}</div><span class="subtext">Counties marked open in MnGeo metadata; separate from NG911 participation.</span></div>
</div>
<div class="activity-strip">
  <div class="card"><div class="muted">Open {_dashboard._esc(record_label)}</div><div class="metric">{_dashboard._esc(f"{record_count:,}" if isinstance(record_count,int) else "—")}</div><span class="subtext">Records used for the current population statistics.</span></div>
  <div class="card"><div class="muted">Mandatory-field fill rate</div><div class="metric">{_dashboard._esc(f"{mandatory_pct:.2f}%" if isinstance(mandatory_pct,(int,float)) else "—")}</div><span class="subtext">{mandatory_count} Mandatory fields; population is descriptive, not a compliance grade.</span></div>
</div>
<div class="mngac-note"><strong>Interpretation:</strong> this measures whether standardized fields contain values; it is <strong>not a standards-compliance score</strong>. Conditional and Optional fields can legitimately be blank. {_dashboard._esc(text_rule_note)} For public NG911-derived layers, NG911 participation and GAC public-data opt-in are separate facts. Source: {standard_link}. Observation: {_dashboard._format_time_pair(observed_at)}. {_dashboard._esc(defaults["grouping_note"])}</div>
<div class="card">
  <div class="section-head"><div><h2>Interactive Minnesota county map</h2><p>Select a field or summary statistic, then select a county.</p></div></div>
  <div class="mngac-controls"><label>Map statistic<select id="mngac-metric">{"".join(options)}</select></label><label>Choose county<select id="mngac-county-select"><option value="">Select a county</option>{county_picker_options}</select></label></div>
  <div class="mngac-layout">
    <div class="mngac-map-panel">{map_svg}{percentage_legend()}</div>
    <div class="card mngac-detail" id="mngac-detail" aria-live="polite">
      <div class="muted">Selected county</div><h3 id="mngac-county-name">Select a county</h3>
      <div class="muted" id="mngac-metric-label">Mandatory fields — row population rate</div>
      <div class="mngac-kpi" id="mngac-county-value">—</div>
      <div id="mngac-county-detail" class="subtext">Select a county from the list or map.</div>
      <p><a id="mngac-county-link" href="/counties" style="display:none">Open county dashboard →</a></p>
    </div>
  </div>
</div>
<div class="section-head"><div><h2>Statewide field completeness</h2><p>{_dashboard._esc(standard.get("short_name") or standard.get("name"))} population across represented {_dashboard._esc(record_label)}. Fields outside the current {_dashboard._esc(population_scope)} scan remain visible for schema coverage but are not assigned a population percentage.</p></div></div>
<div class="card">
  <div class="filters">
    <input id="mngac-q" placeholder="Filter standard fields…" aria-label="Filter MN GAC fields">
    <select id="mngac-inclusion" aria-label="Filter inclusion category"><option value="">All inclusion categories</option><option>Mandatory</option><option>Conditional</option><option>If Available</option><option>Optional</option></select>
  </div>
  <div class="mngac-table-wrap"><table id="mngac-fields"><thead><tr><th>Field</th><th>Section</th><th>Inclusion</th><th>Source schema</th><th>Population scan</th><th>Populated records</th><th>Statewide population</th><th>Median county populated %</th></tr></thead><tbody>{"".join(field_rows)}</tbody></table></div>
</div>
<script type="application/json" id="mngac-data">{payload_json}</script>
<script>
(function(){{
 const root=document,data=JSON.parse(root.getElementById('mngac-data').textContent),
 metric=root.getElementById('mngac-metric'),countySelect=root.getElementById('mngac-county-select'),paths=[...root.querySelectorAll('.mngac-county')],
 q=root.getElementById('mngac-q'),inc=root.getElementById('mngac-inclusion');let selected=null;
 function meta(k){{if(k==='__overall__')return {{label:'All '+data.field_count+' fields — row population rate'}};if(k==='__mandatory__')return {{label:'Mandatory fields — row population rate'}};if(k==='__fields_with_values__')return {{label:'Fields with any values — share of standard fields'}};return data.fields[k]||{{label:k}}}}
 function value(n,k){{const c=data.counties[n];if(!c||c.available===false)return null;if(k==='__overall__')return c.field_population_percent;if(k==='__mandatory__')return c.mandatory_population_percent;if(k==='__fields_with_values__')return typeof c.fields_with_values==='number'&&c.field_count?Math.round(c.fields_with_values/c.field_count*10000)/100:null;const f=(c.fields||{{}})[k];return f&&typeof f.percent==='number'?f.percent:null}}
 {percentage_color_js()}
 function explain(n,k){{const c=data.counties[n]||{{}},m=c.metadata||{{}},v=value(n,k),parts=[];if(c.available===false){{if(m.ng911_upload===true&&m.gac_open===false)parts.push('NG911 participant; not opted into this public GAC layer.');else if(m.gac_open===true)parts.push('GAC public opt-in is recorded, but no public records were observed in this snapshot.');else parts.push('No public records were observed in this snapshot.')}}else parts.push((c.record_count==null?'Unknown':Number(c.record_count).toLocaleString())+' '+data.record_label+' represented.');if(m.submitted_at)parts.push('Latest reported submission: '+new Date(m.submitted_at).toLocaleDateString()+'.');return parts.join(' ')}}
 function show(n){{selected=n;countySelect.value=n;paths.forEach(p=>{{const selectedPath=p.dataset.county===n;p.classList.toggle('selected',selectedPath);p.setAttribute('aria-pressed',String(selectedPath))}});const k=metric.value,v=value(n,k),c=data.counties[n]||{{}},mm=meta(k);root.getElementById('mngac-county-name').textContent=n+' County';root.getElementById('mngac-metric-label').textContent=mm.label||k;root.getElementById('mngac-county-value').textContent=typeof v==='number'?v.toFixed(2)+'%':'No data';root.getElementById('mngac-county-detail').textContent=explain(n,k);const a=root.getElementById('mngac-county-link');if(c.slug){{a.href='/county?slug='+encodeURIComponent(c.slug);a.style.display='inline'}}else a.style.display='none'}}
 function update(){{const k=metric.value,mm=meta(k);paths.forEach(p=>{{const v=value(p.dataset.county,k);p.style.fill=percentageColor(v);p.setAttribute('aria-label',p.dataset.county+' County, '+(mm.label||k)+', '+(typeof v==='number'?v.toFixed(2)+'%':'no data'))}});if(selected)show(selected)}}
 paths.forEach(p=>{{p.addEventListener('click',()=>show(p.dataset.county));p.addEventListener('keydown',e=>{{if(e.key==='Enter'||e.key===' '){{e.preventDefault();show(p.dataset.county)}}}})}});
 metric.addEventListener('change',update);countySelect.addEventListener('change',()=>{{if(countySelect.value)show(countySelect.value)}});root.querySelectorAll('.mngac-field-select').forEach(b=>b.addEventListener('click',()=>{{metric.value=b.dataset.field;update();root.getElementById('mngac-map').scrollIntoView({{behavior:'smooth',block:'center'}})}}));
 function filter(){{const t=(q.value||'').toLowerCase(),c=inc.value;root.querySelectorAll('#mngac-fields tbody tr').forEach(r=>r.style.display=(!t||r.dataset.name.includes(t))&&(!c||r.dataset.inclusion===c)?'':'none')}}q.addEventListener('input',filter);inc.addEventListener('change',filter);update();
}})();
</script>
{publication}
"""
    return _dashboard._layout(
        f'{standard.get("short_name") or "MN GAC"} Completeness — GIS Data Watchtower',
        body, refresh_seconds=0, static=bool(config.get("_public_mode")),
        csrf_token=str(config.get("_csrf_token") or "")
    )

def render_mngac(config: dict, standard_key: str = "parcel") -> str:
    standard_key = normalize_standard_key(standard_key)
    if standard_key != "parcel":
        return _render_gac_standard(config, standard_key)
    state = _dashboard._dashboard_state(config)
    data = _dashboard._mngac_data(state)
    profiles = _dashboard._county_profiles(config, state, _dashboard.load_parcel_access())
    profile_panel = _dashboard.render_county_profile_panel(profiles)
    publication = f'<p>Public publication: {_dashboard._esc(profile_time(state.get("public_published_at")))}</p>'
    schema = _dashboard._load_mngac_schema()
    standard = schema.get("standard") or {}
    all_counties = _dashboard._load_counties()
    total_counties = len(all_counties)
    selector = _gac_standard_selector("parcel")
    _, gac_source = _dashboard._mngac_source(state)
    failure_notice = (
        f'<div class="mngac-note warn" role="status"><strong>Latest configured GAC check failed:</strong> '
        f'{_dashboard._esc((gac_source or {}).get("gac_check_error") or "The result may be from an earlier successful observation.")}</div>'
        if (gac_source or {}).get("gac_check_status") in {"error", "unsupported"} else ""
    )
    if not data:
        body = selector + (
            failure_notice +
            '<p><a href="/counties">← Minnesota counties</a></p>'
            '<div class="card"><h2>MN GAC completeness data is not available yet</h2>'
            '<p>The statewide parcel source has not published a stored MNGAC completeness observation. '
            'Once the configured MnGeo statewide parcel check records it, this page will show county and field statistics.</p></div>'
            + _dashboard._mngac_map_svg().replace('class="mngac-county"', f'class="mngac-county" style="fill:{NO_DATA_COLOR}"') + percentage_legend() + publication + profile_panel
        )
        return _dashboard._layout("MN GAC Completeness — GIS Data Watchtower", body, refresh_seconds=300, static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))

    covered = int(data.get("covered_counties") or 0)
    uncovered = max(0, total_counties - covered)
    record_count = data.get("record_count")
    record_count_label = f"{record_count:,}" if isinstance(record_count, int) else "Not available"
    field_count = int(data.get("field_count") or len(schema.get("fields") or []))
    overall_pct = data.get("field_population_percent")
    mandatory_pct = data.get("mandatory_population_percent")
    source_id, source = _dashboard._mngac_source(state)
    observed_at = data.get("observed_at") or (source or {}).get("last_success_at") or (source or {}).get("checked_at")
    standard_url = _dashboard._safe_url((data.get("standard") or {}).get("source_url") or standard.get("source_url"))
    standard_link = (
        f'<a href="{_dashboard._esc(standard_url)}" target="_blank" rel="noopener">official MN GAC Parcel Data Standard</a>'
        if standard_url else "official MN GAC Parcel Data Standard"
    )

    options = [
        '<option value="__overall__">All 91 fields — row population rate</option>',
        '<option value="__mandatory__" selected>Mandatory fields — row population rate</option>',
        '<option value="__fields_with_values__">Fields with any values — share of standard fields</option>',
    ]
    last_section = None
    for spec in schema.get("fields") or []:
        section_name = str(spec.get("section_name") or "Other")
        if section_name != last_section:
            if last_section is not None:
                options.append("</optgroup>")
            options.append(f'<optgroup label="{_dashboard._esc(section_name)}">')
            last_section = section_name
        options.append(
            f'<option value="{_dashboard._esc(spec.get("field"))}">'
            f'{_dashboard._esc(spec.get("section"))}.{_dashboard._esc(spec.get("order"))} {_dashboard._esc(spec.get("label"))} '
            f'({_dashboard._esc(spec.get("field"))}) — {_dashboard._esc(spec.get("inclusion"))}</option>'
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
            f'<tr data-name="{_dashboard._esc((str(spec.get("label") or "") + " " + field).lower())}" '
            f'data-inclusion="{_dashboard._esc(spec.get("inclusion") or "")}">'
            f'<td><button type="button" class="mngac-field-select" data-field="{_dashboard._esc(field)}">'
            f'<strong>{_dashboard._esc(spec.get("label"))}</strong><br><code>{_dashboard._esc(field)}</code></button></td>'
            f'<td>{_dashboard._esc(spec.get("section_name"))}</td><td>{_dashboard._esc(spec.get("inclusion"))}</td>'
            f'<td>{county_values}/{total_counties}<br><span class="subtext">{county_values}/{covered} represented counties</span></td>'
            f'<td>{_dashboard._esc(f"{populated:,}" if isinstance(populated, int) else "—")} / '
            f'{_dashboard._esc(f"{total:,}" if isinstance(total, int) else "—")}</td>'
            f'<td><strong>{_dashboard._esc(f"{pct:.2f}%" if isinstance(pct, (int,float)) else "—")}</strong></td>'
            f'<td>{_dashboard._esc(f"{median:.2f}%" if isinstance(median, (int,float)) else "—")}</td></tr>'
        )

    counties_payload = {}
    slug_map = _dashboard._county_slug_map()
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
    map_svg = _dashboard._mngac_map_svg()
    body = selector + f"""
<p><a href="/counties">← Minnesota counties</a> · <a href="/mngac.csv?standard=parcel" data-ph-event="export" data-ph-format="csv">Download field summary (CSV)</a> · <a href="/mngac.json?standard=parcel" data-ph-event="export" data-ph-format="json">Download MN GAC data (JSON)</a> · <a href="/snapshot.xlsx" data-ph-event="export" data-ph-format="xlsx">Statewide Excel with MN GAC sheets</a></p>
<div class="grid primary-grid">
  <div class="card"><div class="muted">Standard fields</div><div class="metric">{field_count}</div><span class="subtext">{_dashboard._esc(standard.get("name") or "MN GAC Parcel Data Standard")} v{_dashboard._esc(standard.get("version") or "—")}.</span></div>
  <div class="card"><div class="muted">Counties represented</div><div class="metric">{covered}/{total_counties}</div><span class="subtext">Counties currently represented in MnGeo Plan Parcels Open.</span></div>
  <div class="card"><div class="muted">Not represented</div><div class="metric">{uncovered}</div><span class="subtext">Shown as No data on the map, not as 0% populated.</span></div>
  <div class="card"><div class="muted">Open parcel records</div><div class="metric">{record_count_label}</div><span class="subtext">Parcel records included in the current MnGeo statewide open layer.</span></div>
</div>
<div class="activity-strip">
  <div class="card"><div class="muted">All-field population</div><div class="metric">{_dashboard._esc(f"{overall_pct:.2f}%" if isinstance(overall_pct,(int,float)) else "—")}</div><span class="subtext">Record-weighted populated cells across all 91 standard fields for represented counties. Descriptive only.</span></div>
  <div class="card"><div class="muted">Mandatory-field fill rate</div><div class="metric">{_dashboard._esc(f"{mandatory_pct:.2f}%" if isinstance(mandatory_pct,(int,float)) else "—")}</div><span class="subtext">Record-weighted population across fields the standard classifies as Mandatory.</span></div>
</div>
<div class="mngac-note"><strong>How to read these percentages:</strong> this page measures whether standardized MNGAC fields contain values. It is <strong>not a compliance score</strong>. Conditional fields may be correctly blank when their condition does not apply; “If Available” fields are only required when the provider has the data; Optional fields may be blank. Mandatory-field population is shown separately. Source: {standard_link}. Observation: {_dashboard._format_time_pair(observed_at)}</div>
{failure_notice}
<div class="card">
  <div class="section-head"><div><h2>Interactive Minnesota county map</h2><p>Select an MN GAC field or summary statistic, then click or keyboard-select any county to inspect it.</p></div></div>
  <div class="mngac-controls">
    <label>Map statistic<select id="mngac-metric">{"".join(options)}</select></label>
    <label>Choose county<select id="mngac-county-select"><option value="">Select a county</option>{"".join(f'<option value="{_dashboard._esc(x.get("name"))}">{_dashboard._esc(x.get("name"))} County</option>' for x in all_counties if x.get("name"))}</select></label>
  </div>
  <div class="mngac-layout">
    <div class="mngac-map-panel">{map_svg}
      {percentage_legend()}
    </div>
    <div class="card mngac-detail" id="mngac-detail" aria-live="polite">
      <div class="muted">Selected county</div><h3 id="mngac-county-name">Select a county</h3>
      <div class="muted" id="mngac-metric-label">Mandatory fields — row population rate</div>
      <div class="mngac-kpi" id="mngac-county-value">—</div>
      <div id="mngac-county-detail" class="subtext">Select a county from the list or map.</div>
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
    <th>Field</th><th>Section</th><th>Inclusion</th><th>Source schema</th><th>Population scan</th><th>Counties with values</th>
    <th>Populated records</th><th>Statewide population</th><th>Median county populated %</th>
  </tr></thead><tbody>{"".join(field_rows)}</tbody></table></div>
</div>
<script type="application/json" id="mngac-data">{payload_json}</script>
<script>
(function(){{
  const root=document;
  const data=JSON.parse(root.getElementById('mngac-data').textContent);
  const metric=root.getElementById('mngac-metric');
  const countySelect=root.getElementById('mngac-county-select');
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
    selected=name; countySelect.value=name; paths.forEach(p=>{{const selectedPath=p.dataset.county===name;p.classList.toggle('selected',selectedPath);p.setAttribute('aria-pressed',String(selectedPath))}});
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
  countySelect.addEventListener('change',()=>{{if(countySelect.value)showCounty(countySelect.value)}});
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
    return _dashboard._layout("MN GAC Completeness — GIS Data Watchtower", body, refresh_seconds=0, static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))

def _render_county_mngac(state: dict, county: dict) -> str:
    data, stats = _dashboard._mngac_county_record(state, str(county.get("name") or ""))
    if not data:
        return (
            '<div class="card"><h2>MN GAC field completeness</h2>'
            '<p class="muted">A stored statewide MN GAC completeness observation is not available yet.</p>'
            '<p><a href="/mngac">Open statewide MN GAC page →</a></p></div>'
        )
    standard = data.get("standard") or _dashboard._load_mngac_schema().get("standard") or {}
    if not stats:
        return (
            '<div class="card"><h2>MN GAC field completeness</h2>'
            '<p>This county is not represented in the current MnGeo Plan Parcels Open layer. '
            'Watchtower reports this as <strong>No data</strong>, not 0% populated.</p>'
            f'<p class="subtext">The statewide open layer currently represents {_dashboard._esc(data.get("covered_counties") or 0)} of 87 Minnesota counties.</p>'
            '<p><a href="/mngac">Explore the statewide MN GAC map →</a></p></div>'
        )
    record_count = int(stats.get("record_count") or 0)
    field_count = int(stats.get("field_count") or 0)
    fields_with_values = int(stats.get("fields_with_values") or 0)
    population_pct = stats.get("field_population_percent")
    mandatory_pct = stats.get("mandatory_population_percent")
    mandatory_full = int(stats.get("mandatory_fields_full") or 0)
    mandatory_count = int(stats.get("mandatory_field_count") or 0)
    rows = _dashboard._mngac_field_rows(stats)
    return f"""
<div class="section-head"><div><h2>MN GAC field completeness</h2><p>Population of the official Minnesota GAC parcel-transfer fields for this county in MnGeo Plan Parcels Open.</p></div><a href="/mngac">Statewide map →</a></div>
<div class="grid primary-grid">
  <div class="card"><div class="muted">MnGeo parcel records</div><div class="metric">{record_count:,}</div><span class="subtext">Records used as the denominator for county field-population percentages.</span></div>
  <div class="card"><div class="muted">Fields with values</div><div class="metric">{fields_with_values}/{field_count}</div><span class="subtext">Standard fields containing at least one populated value in this county.</span></div>
  <div class="card"><div class="muted">All-field fill rate</div><div class="metric">{_dashboard._esc(f"{population_pct:.2f}%" if isinstance(population_pct,(int,float)) else "—")}</div><span class="subtext">Populated cells across all standard fields. This is descriptive, not a compliance score.</span></div>
  <div class="card"><div class="muted">Mandatory-field fill rate</div><div class="metric">{_dashboard._esc(f"{mandatory_pct:.2f}%" if isinstance(mandatory_pct,(int,float)) else "—")}</div><span class="subtext">{mandatory_full}/{mandatory_count} Mandatory fields are populated for 100% of records.</span></div>
</div>
<div class="mngac-note">The GAC standard uses four inclusion categories: Mandatory, Conditional, If Available, and Optional. A blank Conditional, If Available, or Optional field can be valid, so these percentages should not be interpreted as a pass/fail compliance grade. Standard: {_dashboard._esc(standard.get("short_name") or "MN GAC Parcel Data Standard")} v{_dashboard._esc(standard.get("version") or "—")}.</div>
<div class="card">
  <div class="filters"><input id="cmq" placeholder="Filter MNGAC fields…" aria-label="Filter county MNGAC fields"><select id="cmi" aria-label="Filter county inclusion category"><option value="">All inclusion categories</option><option>Mandatory</option><option>Conditional</option><option>If Available</option><option>Optional</option></select></div>
  <div class="mngac-table-wrap"><table id="county-mngac-fields"><thead><tr><th>Field</th><th>Section</th><th>Inclusion</th><th>Source schema</th><th>Population scan</th><th>Populated</th><th>Records</th><th>Population</th></tr></thead><tbody>{rows}</tbody></table></div>
</div>
<script>(function(){{const q=document.getElementById('cmq'),i=document.getElementById('cmi');function f(){{const t=(q.value||'').toLowerCase(),c=i.value;document.querySelectorAll('#county-mngac-fields tbody tr').forEach(r=>r.style.display=(!t||r.dataset.name.includes(t))&&(!c||r.dataset.inclusion===c)?'':'none')}}q.addEventListener('input',f);i.addEventListener('change',f)}})();</script>
"""

def _county_mngac_summary(state: dict, county: dict) -> dict:
    data, county_stats = _dashboard._mngac_county_record(state, county["name"])
    source_id, source = _dashboard._mngac_source(state)
    return {
        "data": data,
        "county": county_stats,
        "source_id": source_id,
        "source": source,
        "checked_at": (source or {}).get("checked_at") or (source or {}).get("last_success_at"),
    }

def _render_county_gac_summaries(state: dict, county: dict) -> str:
    name = str(county.get("name") or "")
    cards = []
    for standard_key in ("address", "road"):
        schema = load_gac_standard(standard_key)
        defaults = gac_defaults(standard_key)
        data = _dashboard._gac_data(state, standard_key)
        label = schema.get("standard", {}).get("short_name") or standard_key.title()
        if not data:
            cards.append(
                f'<div class="card"><h3>{_dashboard._esc(label)}</h3>'
                '<p class="muted">A stored statewide completeness observation is not available yet.</p>'
                f'<p><a href="/mngac?standard={_dashboard._esc(standard_key)}">Open statewide standard →</a></p></div>'
            )
            continue
        stats = (data.get("counties") or {}).get(name)
        meta = (data.get("county_metadata") or {}).get(name) or {}
        if isinstance(stats, dict):
            record_count = stats.get("record_count")
            mandatory = stats.get("mandatory_population_percent")
            availability = (
                f'{record_count:,} {defaults["record_label"]}' if isinstance(record_count, int)
                else f'Public {defaults["record_label"]} represented'
            )
            fill = f'{mandatory:.2f}%' if isinstance(mandatory, (int, float)) else "—"
        elif meta.get("ng911_upload") is True and meta.get("gac_open") is False:
            availability = "NG911 participant · not opted into public GAC data"
            fill = "No public data"
        elif meta.get("gac_open") is True:
            availability = "GAC public opt-in recorded · no records observed"
            fill = "No data"
        else:
            availability = "Not represented in the public statewide layer"
            fill = "No data"
        submitted = profile_time(meta.get("submitted_at")) if meta.get("submitted_at") else "Not available"
        cards.append(
            f'<div class="card"><h3>{_dashboard._esc(label)}</h3>'
            f'<p><strong>Public representation:</strong> {_dashboard._esc(availability)}'
            f'<br><strong>Mandatory-field fill:</strong> {_dashboard._esc(fill)}'
            f'<br><strong>Latest reported submission:</strong> {_dashboard._esc(submitted)}</p>'
            f'<p><a href="/mngac?standard={_dashboard._esc(standard_key)}">Open statewide standard →</a></p></div>'
        )
    return (
        '<div class="section-head"><div><h2>Address and road GAC status</h2>'
        '<p>NG911 participation, public-data opt-in and field population are reported separately.</p>'
        '</div></div><div class="grid">' + "".join(cards) + '</div>'
    )

def _gac_county_payload(state: dict, standard_key: str, county_name: str) -> dict | None:
    data = _dashboard._gac_data(state, standard_key)
    if not isinstance(data, dict):
        return None
    metadata = (data.get("county_metadata") or {}).get(county_name)
    county = (data.get("counties") or {}).get(county_name)
    county = county if isinstance(county, dict) else None
    return {
        "standard_key": standard_key,
        "standard": data.get("standard") or {},
        "method": data.get("method"),
        "population_scope": data.get("population_scope"),
        "text_population_mode": data.get("text_population_mode"),
        "covered_counties": data.get("covered_counties"),
        "record_count": (county or {}).get("record_count"),
        "field_count": data.get("field_count"),
        "mandatory_field_count": data.get("mandatory_field_count"),
        "field_population_percent": (county or {}).get("field_population_percent"),
        "mandatory_population_percent": (county or {}).get("mandatory_population_percent"),
        "fields": data.get("fields") or {},
        "county": county,
        "metadata": metadata if isinstance(metadata, dict) else {},
    }
