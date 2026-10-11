"""County-first MN GAC navigation over saved observations only."""
from __future__ import annotations

import html
import re
from urllib.parse import urlencode

from . import dashboard as dashboard
from .county_profile_panel import NO_DATA_COLOR, PERCENT_BINS, PERCENT_COLORS, percentage_legend, profile_time, render_direct_schema_findings
from .direct_gac_schema import direct_schema_assessment
from .gac_standards import gac_defaults, load_gac_standard, standard_keys

LABELS = {'parcel': 'Parcels', 'address': 'Address Points', 'road': 'Road Centerlines'}


def resolve_county(value: str) -> dict | None:
    name = str(value or '').strip().casefold()
    if not name:
        return None
    for county in dashboard._load_counties():
        if name in {county['slug'].casefold(), county['name'].casefold(), (county['name'] + ' County').casefold()}:
            return county
    raise ValueError('Choose a Minnesota county from the list.')


def gac_url(standard: str, view: str = 'county', county: str = '') -> str:
    values = {'standard': standard, 'view': view}
    if county:
        values['county'] = county
    return '/mngac?' + urlencode(values)


def navigation(standard: str, view: str, county: dict | None) -> str:
    esc = dashboard._esc
    slug = (county or {}).get('slug', '')
    links = ''.join(
        f'<a href="{esc(gac_url(key, view, slug))}"'
        + (' class="primary" aria-current="page"' if key == standard else '')
        + f'>{LABELS[key]}</a>' for key in standard_keys()
    )
    scopes = ''.join(
        f'<a href="{esc(gac_url(standard, key, slug))}"'
        + (' class="primary" aria-current="page"' if key == view else '')
        + f'>{label}</a>' for key, label in (('county', 'County results'), ('statewide', 'Statewide overview'))
    )
    options = ''.join(f'<option value="{esc(c["name"])}"></option>'
                      for c in dashboard._load_counties())
    return f'''<style>
.gac-navigation{{margin-bottom:20px}}.gac-navigation nav{{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px}}
.gac-navigation nav a,.gac-county-form button{{padding:10px 14px;border:1px solid #33465e;border-radius:8px;background:#101925;color:#dce9fa;font:inherit;text-decoration:none;cursor:pointer}}
.gac-navigation nav a[aria-current="page"],.gac-county-form button{{background:#1c4065;border-color:#69a6ff;color:#fff}}
.gac-navigation a:focus-visible,.gac-county-form input:focus-visible,.gac-county-form button:focus-visible{{outline:2px solid #91bcff;outline-offset:3px}}
.gac-county-form{{display:flex;align-items:end;flex-wrap:wrap;gap:12px}}.gac-county-form label{{display:grid;gap:6px;flex:1;min-width:180px;max-width:420px}}
.gac-county-form input{{width:100%;box-sizing:border-box;min-height:42px;padding:10px 12px;border:1px solid #33465e;border-radius:8px;background:#0c121d;color:#edf5ff;font:inherit}}.gac-county-form button{{min-height:42px}}
.gac-county-heading{{margin:20px 0 12px}}.gac-county-heading h2{{margin-bottom:6px}}
.gac-map-link:focus .mngac-county,.gac-map-link:hover .mngac-county{{stroke:#fff;stroke-width:3}}
.gac-map-link[aria-current="page"] .mngac-county{{stroke:#fff;stroke-width:3}}
.gac-field-table tr[hidden]{{display:none!important}}
.gac-county-map{{max-width:620px;margin:16px auto}}.gac-field-table td,.gac-field-table th{{white-space:normal}}
@media(max-width:760px){{.gac-county-form label{{max-width:none}}.gac-county-form button{{width:100%}}}}
</style>
<section class="card gac-navigation" aria-label="MN GAC results navigation">
<div class="muted">MN GAC standard</div><nav aria-label="MN GAC standard">{links}</nav>
<nav aria-label="Results scope">{scopes}</nav>
<form action="/mngac" method="get" class="gac-county-form">
<input type="hidden" name="standard" value="{esc(standard)}"><input type="hidden" name="view" value="county">
<label for="gac-county-search">Choose county<input id="gac-county-search" name="county" type="search" list="gac-county-options" required autocomplete="off" placeholder="Type or choose a county" value="{esc((county or {}).get('name', ''))}"></label>
<datalist id="gac-county-options">{options}</datalist><button type="submit" class="primary">View county results</button>
</form></section>'''


def county_map(standard: str, data: dict | None = None, selected: str = '') -> str:
    """Native SVG links give map and search the same keyboard-friendly destination."""
    counties = (data or {}).get('counties') or {}

    def link(match):
        path = match.group(0)
        slug = html.unescape(re.search(r'data-slug="([^"]*)"', path).group(1))
        name = html.unescape(re.search(r'data-county="([^"]*)"', path).group(1))
        value = (counties.get(name) or {}).get('mandatory_population_percent')
        color = NO_DATA_COLOR
        if type(value) in (int, float):
            for index, (_, bound, inclusive) in enumerate(PERCENT_BINS):
                if bound is None or value < bound or inclusive and value == bound:
                    color = PERCENT_COLORS[index]
                    break
        path = path.replace('tabindex="0" role="button" aria-pressed="false" ', '')
        path = path.replace('class="mngac-county"', f'class="mngac-county" style="fill:{color}"')
        current = ' aria-current="page"' if slug == selected else ''
        return (f'<a class="gac-map-link" href="{dashboard._esc(gac_url(standard, county=slug))}"'
                f' aria-label="{dashboard._esc(name)} County MN GAC results"{current}>{path}</a>')

    return re.sub(r'<path\b[^>]*>.*?</path>', link, dashboard._mngac_map_svg(), flags=re.S)


def _percent(value, missing='No data') -> str:
    return f'{value:.2f}%' if type(value) in (int, float) else missing


def _count(value) -> str:
    return f'{value:,}' if type(value) is int and value >= 0 else '—'


def render_county_results(config: dict, standard_key: str, county: dict | None) -> str:
    esc = dashboard._esc
    state = dashboard._dashboard_state(config)
    data = dashboard._gac_data(state, standard_key)
    _, source = dashboard._gac_source(state, standard_key)
    source = source or {}
    data = data or {}
    schema = load_gac_standard(standard_key)
    defaults = gac_defaults(standard_key)
    name = (county or {}).get('name', '')
    slug = (county or {}).get('slug', '')
    stats = (data.get('counties') or {}).get(name)
    observed = data.get('observed_at') or source.get('last_success_at') or (source.get('checked_at') if source.get('status') == 'ok' else None)
    body = navigation(standard_key, 'county', county)
    standard = schema.get('standard') or {}
    if source.get('gac_check_status') in {'error', 'unsupported'}:
        body += '<p class="mngac-note warn" role="status">Latest configured GAC check failed. Results may be from an earlier successful observation.</p>'
    if not county:
        body += '<div class="gac-county-heading"><h2>Explore county results</h2><p>Choose a county above or on the map to see its record counts, field population and individual field results.</p></div>'
    else:
        body += f'<div class="gac-county-heading"><h2>{esc(name)} County — {LABELS[standard_key]}</h2><p>County results from {esc(defaults["dataset_label"])}. Observation: {esc(profile_time(observed))}.</p></div>'
        body += f'<p class="subtext">{esc(standard.get("short_name") or standard.get("name"))} v{esc(standard.get("version") or "—")}. {esc(defaults["grouping_note"])}</p>'
        if not isinstance(stats, dict):
            reason = ('This county is not represented in the current saved observation.' if data else
                      'A saved observation for this MN GAC standard is not available yet.')
            heading = 'Not in MnGeo Open Parcels' if standard_key == 'parcel' and data else 'Statewide results unavailable'
            qualification = 'Absence is not reported as 0%.'
            if standard_key == 'parcel':
                qualification += ' It does not establish direct-feed noncompliance.'
            body += f'<div class="card"><h3>{heading}</h3><p>{reason} {qualification}</p></div>'
        else:
            all_rate = _percent(stats.get('field_population_percent'), 'Not scanned' if data.get('population_scope') == 'mandatory' else 'No data')
            body += f'''<div class="grid primary-grid" aria-label="Selected county summary">
<div class="card"><div class="muted">County {esc(defaults['record_label'])}</div><div class="metric">{_count(stats.get('record_count'))}</div></div>
<div class="card"><div class="muted">Mandatory-field population</div><div class="metric">{_percent(stats.get('mandatory_population_percent'))}</div></div>
<div class="card"><div class="muted">All-field population</div><div class="metric">{all_rate}</div></div>
<div class="card"><div class="muted">Standard fields</div><div class="metric">{len(schema['fields'])}</div></div></div>
<p class="mngac-note">These percentages describe fields containing values in this county's records, not a compliance score. Conditional, If Available and Optional fields may legitimately be blank. Source schema describes the shared statewide layer; population figures below are county-specific.</p>'''
            if data.get('text_population_mode') == 'non_null':
                body += '<p class="subtext">Text population is non-null based; empty strings may count as populated in this observation.</p>'
            rows = []
            for spec in schema['fields']:
                field = spec['field']
                meta = (data.get('fields') or {}).get(field) or {}
                values = (stats.get('fields') or {}).get(field) or {}
                not_scanned = meta.get('population_scanned') is False
                scanned = not not_scanned and type(values.get('record_count')) is int
                scan = 'Scanned' if scanned else 'Not scanned' if not_scanned else 'No data'
                present = meta.get('present_in_source_schema')
                shape = 'Present' if present is True else 'Missing' if present is False else 'Unknown'
                populated = _count(values.get('populated')) if scanned else '—'
                records = _count(values.get('record_count')) if scanned else '—'
                percent = _percent(values.get('percent')) if scanned else scan
                rows.append(f'<tr data-name="{esc((spec["label"] + " " + field).lower())}" data-inclusion="{esc(spec["inclusion"])}">'
                            f'<td><strong>{esc(spec["label"])}</strong><br><code>{esc(field)}</code></td>'
                            f'<td>{esc(spec["section_name"])}</td><td>{esc(spec["inclusion"])}</td><td>{shape}</td><td>{scan}</td>'
                            f'<td>{populated}</td><td>{records}</td><td>{percent}</td></tr>')
            body += f'''<section class="card"><h2>County field results</h2>
<div class="filters"><input id="gac-field-search" type="search" placeholder="Find a field" aria-label="Find a county field"><select id="gac-field-inclusion" aria-label="Filter field inclusion"><option value="">All inclusion categories</option><option>Mandatory</option><option>Conditional</option><option>If Available</option><option>Optional</option></select></div>
<div class="table-scroll"><table class="gac-field-table" id="gac-county-fields"><caption>{esc(name)} County — {LABELS[standard_key]} field population</caption><thead><tr><th>Field</th><th>Section</th><th>Inclusion</th><th>Source schema</th><th>Population scan</th><th>Populated</th><th>County records</th><th>Population</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p id="gac-no-fields" hidden role="status">No fields match these filters.</p></section>
<script>(function(){{const q=document.getElementById('gac-field-search'),i=document.getElementById('gac-field-inclusion');function filter(){{let visible=0;document.querySelectorAll('#gac-county-fields tbody tr').forEach(r=>{{const show=r.dataset.name.includes(q.value.toLowerCase())&&(!i.value||r.dataset.inclusion===i.value);r.hidden=!show;if(show)visible++}});document.getElementById('gac-no-fields').hidden=visible>0}}q.addEventListener('input',filter);i.addEventListener('change',filter)}})();</script>'''
        if standard_key == 'parcel':
            assessments = [direct_schema_assessment(sid, item) for sid, item in sorted((state.get('sources') or {}).items())
                           if item.get('category') == 'Parcels' and item.get('county_slug') == slug]
            body += render_direct_schema_findings(assessments)
        body += f'<p><a href="/county?slug={esc(slug)}">Open full {esc(name)} County profile</a> · <a href="{esc(gac_url(standard_key, county=slug))}">Link to these county results</a></p>'
    map_content = (f'<div class="gac-county-map"><h2>Interactive Minnesota county map</h2><p>Mandatory-field population. Select a county to open its results.</p>'
                   + county_map(standard_key, data, slug) + percentage_legend() + '</div>')
    body += f'<details><summary>Choose another county on the map</summary>{map_content}</details>' if county else map_content
    body += f'<p class="subtext">Public publication: {esc(profile_time(state.get("public_published_at")))}</p>'
    return dashboard._layout(f'MN GAC {name + " County — " if name else ""}{LABELS[standard_key]} — Watchtower', body,
                             refresh_seconds=30 if config.get('_public_mode') else 0,
                             static=bool(config.get('_public_mode')), csrf_token=str(config.get('_csrf_token') or ''))
