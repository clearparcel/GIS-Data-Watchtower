from __future__ import annotations
from clearparcel.datawatch.csp import SCRIPT_TAG

from clearparcel.datawatch import dashboard as _dashboard
from clearparcel.datawatch.dashboard_summary import catalog_summary
from clearparcel.datawatch.county_profile_panel import profile_time
from clearparcel.datawatch.public_values import county_metadata_dates
from clearparcel.datawatch.product import page_title
from .dashboard_copy import statewide_copy_label, source_status_label
from .county_directory_view import render_published_directory, county_access_summary, RESEARCH_NOTICE


def render_counties(config: dict) -> str:
    state = _dashboard._dashboard_state(config)
    research = _dashboard.load_parcel_access()
    profiles = _dashboard._county_profiles(config, state, research)
    counties = [_dashboard._county_status(config, x, state, profiles=profiles, research=research) for x in _dashboard._load_counties()]
    active_count = sum(1 for x in counties if x["actively_monitored"])
    # Overdue is about check age, independent of health: a stale warning or
    # failure is overdue too, even though its status pill keeps the health.
    overdue_count = sum(1 for x in counties if x["actively_monitored"]
                        and (x.get("profile") or {}).get("monitoring", {}).get("reporting") == "overdue")
    direct_count = sum(1 for x in counties if "county-direct" in x["monitoring_paths"])
    mngeo_count = sum(1 for x in counties if "mngeo-open" in x["monitoring_paths"])
    status_counts = {}
    catalog = catalog_summary(state, [county["name"] for county in counties])
    age_buckets = catalog["buckets"]
    catalog_notice = ("Retained older catalog after failed check. " if catalog["retained"] else "")
    catalog_notice += "Catalog observation: " + profile_time(catalog["observed_at"])
    catalog_notice += " (inferred from last success)" if catalog["time_inferred"] else ""
    catalog_notice += "; latest attempt: " + profile_time(catalog["latest_attempt_at"])
    mngac = _dashboard._mngac_data(state)
    for x in counties:
        status_counts[x["status"]] = status_counts.get(x["status"], 0) + 1
    def access_summary(info):
        directory = profiles[info["slug"]].get("county_directory")
        return county_access_summary(directory) if directory is not None else _dashboard.access_label(info.get("parcel_access")).replace("County-direct parcel access not yet researched", "County access not yet confirmed").replace("Parcel-access research pending", "County access not yet confirmed")

    checked_count = sum(1 for x in counties if x["actively_monitored"]
                        and (x.get("profile") or {}).get("monitoring", {}).get("reporting") == "current")
    rows = []
    for info in counties:
        monitoring = info["profile"].get("monitoring") or {}
        checked = profile_time(monitoring.get("last_checked_at"))
        overdue = '<br><span class="subtext">Latest check overdue</span>' if monitoring.get("reporting") == "overdue" else ""
        statewide = statewide_copy_label(
            info.get("parcel_access"), (info.get("statewide_record") is not None) if mngac else None)
        rows.append(
            f'<tr data-name="{_dashboard._esc(info["name"].lower())}" data-status="{_dashboard._esc(info["status"])}">'
            f'<td><a href="/county?slug={_dashboard.urllib.parse.quote(info["slug"])}"><strong>{_dashboard._esc(info["name"])} County</strong></a></td>'
            f'<td>{_dashboard._esc(access_summary(info))}</td><td>{_dashboard._esc(statewide)}</td>'
            f'<td><span class="pill {_dashboard._esc(info["status"])}">{_dashboard._esc(_dashboard._friendly_status(info["status"]))}</span>'
            f'{overdue}<br><span class="subtext">Last checked: {_dashboard._esc(checked)}</span></td></tr>')
    coverage = mngac.get("covered_counties") if mngac else None
    coverage = coverage if isinstance(coverage, int) else "—"
    mngac_card = (
        f'<div class="card"><h2>Data completeness</h2><p><strong>{coverage} of {len(counties)} counties</strong> '
        'have parcel data in the latest statewide results. Completeness measures how often standard fields contain values.</p>'
        '<p><a href="/mngac">Explore county data completeness →</a></p></div>')
    body = f'''
<div class="grid">
  <div class="card"><div class="muted">Minnesota counties</div><div class="metric">{len(counties)}</div><span class="subtext">Find a county below to open its data links and contacts.</span></div>
  <div class="card"><div class="muted">Counties being checked</div><div class="metric">{checked_count}</div><span class="subtext">Counties with a source for checks: {active_count}. Checks overdue: {overdue_count}.</span></div>
  <div class="card"><div class="muted">Counties checked directly</div><div class="metric">{direct_count}</div><span class="subtext">Checks use the county’s own data source. Includes any overdue checks.</span></div>
  <div class="card"><div class="muted">Counties in the statewide parcel dataset</div><div class="metric">{mngeo_count}</div><span class="subtext">Included in the latest MnGeo statewide parcel results.</span></div>
</div>
<div class="card"><h2>Find a county</h2>
<p>County data may require payment even when a free statewide copy is available. Check status describes Watchtower’s checks, not data accuracy or access rights.</p>
<div class="filters"><input id="cq" type="search" aria-label="Search counties" placeholder="Search counties…"><select id="cs" aria-label="Filter by check status"><option value="">All check statuses</option><option value="ok">Actively checked</option><option value="overdue">Check overdue</option><option value="catalog">MnGeo listing only</option><option value="needs-source">Not currently checked</option><option value="not-configured">No source information yet</option><option value="warn">Needs attention</option><option value="error">Check failed</option><option value="paused">Paused</option><option value="awaiting-permission">Awaiting permission</option></select></div>
<table id="counties"><thead><tr><th>County</th><th>Data from the county</th><th>Free statewide copy</th><th>Check status</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
<p id="counties-no-results" hidden role="status">No counties match. Try another name or check status.</p></div>
{mngac_card}
<details class="card profile-evidence"><summary>County checks and data age</summary>
<div class="grid"><div class="card">{_dashboard._bar_chart([(_dashboard._friendly_status(k), v) for k, v in sorted(status_counts.items())], title="County check status")}<p class="subtext">A county is actively checked when its source check and monitoring report are recent. Older results show as overdue.</p></div>
<div class="card">{_dashboard._bar_chart(list(age_buckets.items()), title="Age of parcel data listed by MnGeo")}<p class="subtext">Age of the county data date listed by MnGeo, separate from the Watchtower check time. {_dashboard._esc(catalog_notice)}</p></div></div>
<h3>Parcel source research</h3>{_dashboard.research_summary(profiles)}</details>
{SCRIPT_TAG}function filterCounties(){{const q=document.getElementById('cq').value.toLowerCase(),s=document.getElementById('cs').value;let visible=0;document.querySelectorAll('#counties tbody tr').forEach(r=>{{const show=(!q||r.dataset.name.includes(q))&&(!s||r.dataset.status===s);r.style.display=show?'':'none';if(show)visible++}});document.getElementById('counties-no-results').hidden=visible>0}}document.getElementById('cq').addEventListener('input',filterCounties);document.getElementById('cs').addEventListener('change',filterCounties);</script>
'''
    return _dashboard._layout(page_title("Minnesota county parcel data"), '<p><a href="/">← Watchtower overview</a></p>'+body, static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))



def render_county(config: dict, slug: str) -> str:
    state = _dashboard._dashboard_state(config)
    county = next((x for x in _dashboard._load_counties() if x.get("slug") == slug), None)
    if not county:
        return _dashboard._layout(page_title("County not found"), '<p><a href="/counties">← Minnesota counties</a></p><div class="card">County not found.</div>', static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))
    research = _dashboard.load_parcel_access()
    profiles = _dashboard._county_profiles(config, state, research)
    info = _dashboard._county_status(config, county, state, profiles=profiles, research=research)
    complete_profile = _dashboard.render_county_profile_body(profiles[slug], include_directory=False)
    mngac_html = _dashboard._render_county_mngac(state, county)
    gac_summary_html = _dashboard._render_county_gac_summaries(state, county)
    parcel_access = info.get("parcel_access")
    direct_access_label = _dashboard.access_label(parcel_access)
    live_mngac = _dashboard._mngac_data(state)
    statewide_live_available = (info.get("statewide_record") is not None) if live_mngac else None
    statewide_label = _dashboard.statewide_access_label(parcel_access, live_available=statewide_live_available)
    statewide_record_count = int((info.get("statewide_record") or {}).get("record_count") or 0)
    if parcel_access and parcel_access.get("research_complete"):
        evidence_links = []
        for item in parcel_access.get("evidence") or []:
            url = _dashboard._safe_url(item.get("url"))
            if url:
                evidence_links.append(
                    f'<a href="{_dashboard._esc(url)}" target="_blank" rel="noopener">{_dashboard._esc(item.get("authority") or "Source")}</a>'
                )
        details = [
            f'<strong>Reviewed:</strong> {_dashboard._esc(parcel_access.get("review_date") or "—")}',
            f'<strong>Evidence:</strong> {" · ".join(evidence_links) if evidence_links else "—"}',
        ]
        if parcel_access.get("parcel_dataset_fee"):
            details.append(f'<strong>County parcel dataset fee:</strong> {_dashboard._esc(parcel_access.get("parcel_dataset_fee"))}')
        if parcel_access.get("fee_product"):
            details.append(f'<strong>County fee applies to:</strong> {_dashboard._esc(parcel_access.get("fee_product"))}')
        service_url = _dashboard._safe_url(parcel_access.get("download_or_service_url"))
        if service_url:
            details.append(f'<strong>County data connection:</strong> <a href="{_dashboard._esc(service_url)}" target="_blank" rel="noopener">Connect in GIS software</a>')
        viewer_url = _dashboard._safe_url(parcel_access.get("viewer_url"))
        if viewer_url:
            details.append(f'<strong>County viewer:</strong> <a href="{_dashboard._esc(viewer_url)}" target="_blank" rel="noopener">Open viewer</a>')
        statewide = parcel_access.get("statewide_open_coverage") or {}
        statewide_url = _dashboard._safe_url(statewide.get("source_url"))
        if statewide_url:
            details.append(f'<strong>MnGeo source:</strong> <a href="{_dashboard._esc(statewide_url)}" target="_blank" rel="noopener">Plan Parcels Open</a>')
        if info.get("statewide_record"):
            details.append(f'<strong>MnGeo parcel records currently observed:</strong> {_dashboard._esc(f"{statewide_record_count:,}")}')
        parcel_access_detail = (
            '<div class="card"><h2>Parcel dataset access</h2>'
            f'<p><strong>County-direct access:</strong> {_dashboard._esc(direct_access_label)}</p>'
            f'<p><strong>Statewide open access:</strong> {_dashboard._esc(statewide_label)}</p>'
            f'<p>{_dashboard._esc(parcel_access.get("evidence_note") or "")}</p>'
            f'<p class="subtext">{"<br>".join(details)}</p></div>'
        )
    else:
        parcel_access_detail = (
            '<div class="card"><h2>Parcel dataset access</h2>'
            f'<p><strong>County-direct access:</strong> {_dashboard._esc(direct_access_label)}</p>'
            f'<p><strong>Statewide open access:</strong> {_dashboard._esc(statewide_label)}</p>'
            '<p class="muted">A completed county-direct parcel-access review is not stored for this county.</p></div>'
        )
    source_cards = ""
    if info.get("statewide_record") and info.get("statewide_source"):
        src = info["statewide_source"]
        checked_value = src.get("checked_at") or src.get("last_success_at")
        checked = _dashboard._format_public_time_compact(checked_value) if config.get("_public_mode") else _dashboard._esc(checked_value or "—")
        source_cards += (
            '<div class="card"><h3>MnGeo Plan Parcels Open</h3>'
            f'<p><strong>Status:</strong> {_dashboard._esc((source_status_label if config.get("_public_mode") else _dashboard._health_status)(src.get("status") or "unknown"))}'
            f'<br><strong>County records:</strong> {_dashboard._esc(f"{statewide_record_count:,}")}'
            f'<br><strong>Source used for checks:</strong> Statewide open parcel source'
            f'<br><strong>Last checked:</strong> {checked}</p></div>'
        )
    for src in info["sources"]:
        checked = _dashboard._format_public_time_compact(src.get("checked_at")) if config.get("_public_mode") else _dashboard._esc(src.get("checked_at", "—"))
        source_cards += f'<div class="card"><h3>{_dashboard._esc(src.get("name"))}</h3><p><strong>Status:</strong> {_dashboard._esc(_dashboard._friendly_status(src.get("status") or "unknown"))}<br><strong>Records:</strong> {_dashboard._esc(f"{src.get("feature_count"):,}" if isinstance(src.get("feature_count"), int) else "—")}<br><strong>Provided by:</strong> {_dashboard._esc(src.get("provider","—"))}<br><strong>Last checked:</strong> {checked}</p></div>'
    catalog = info.get("catalog") or {}
    if not source_cards and catalog:
        approval = str(catalog.get("gac_open_approval") or "—")
        data_url = _dashboard._safe_url(catalog.get("data_url"))
        viewer_url = _dashboard._safe_url(catalog.get("viewer_url"))
        county_dates = county_metadata_dates(catalog)
        metadata_lines = "".join(
            f'<br><strong>{label}:</strong> {_dashboard._esc(value)}'
            for label, value in (("County metadata publication date", county_dates["publication_date"]),
                                 ("County metadata content date", county_dates["content_date"])) if value)
        source_links = (f'<a href="{_dashboard._esc(data_url)}" target="_blank" rel="noopener">Open parcel data</a>' if data_url else "No open data URL supplied")
        if viewer_url:
            source_links += f' · <a href="{_dashboard._esc(viewer_url)}" target="_blank" rel="noopener">Viewer</a>'
        source_cards = f'<div class="card"><h3>County parcel update information</h3><p><strong>MnGeo public-data approval:</strong> {_dashboard._esc(approval)}<br><strong>MnGeo acquired county data:</strong> {_dashboard._esc(_dashboard._format_arcgis_date(catalog.get("acqdate")))}{metadata_lines}<br><strong>MnGeo listing refreshed:</strong> {_dashboard._esc(_dashboard._format_arcgis_date(catalog.get("rundate")))}<br><strong>Parcel links:</strong> {source_links}</p></div>'
    elif not source_cards:
        source_cards = '<div class="card"><h3>No direct county parcel source currently monitored</h3><p>Check status is separate from the parcel-data access research shown below.</p></div>'
    contact_record = _dashboard._load_county_contact_records().get(county["name"], {})
    contacts = contact_record.get("contacts", [])
    contact_rows = ""
    for contact in contacts:
        email = str(contact.get("email") or "").strip().rstrip(".")
        phone = str(contact.get("phone") or "").strip()
        email_html = f'<a href="mailto:{_dashboard._esc(email)}">{_dashboard._esc(email)}</a>' if email else "—"
        phone_html = f'<a href="tel:{_dashboard._esc(phone)}">{_dashboard._esc(phone)}</a>' if phone else "—"
        contact_rows += f'<tr><td><strong>{_dashboard._esc(contact.get("name") or "Department contact")}</strong></td><td>{_dashboard._esc(contact.get("title") or "—")}</td><td>{_dashboard._esc(contact.get("department") or "—")}</td><td>{phone_html}</td><td>{email_html}</td></tr>'
    if not contact_rows:
        contact_rows = '<tr><td colspan="5">No contact is currently listed in the MnGeo county GIS directory.</td></tr>'
    contact_source_url = _dashboard._safe_url(contact_record.get("source_url"))
    contact_source_name = contact_record.get("source_name") or "MnGeo County GIS Contacts"
    contact_source = f'<a href="{_dashboard._esc(contact_source_url)}" target="_blank" rel="noopener">{_dashboard._esc(contact_source_name)}</a>' if contact_source_url else _dashboard._esc(contact_source_name)
    if contact_record.get("authority") == "county":
        contact_source_note = "The official county website provides additional or changed GIS/land-records contact information, so the county website is authoritative."
    elif contact_record.get("verified"):
        contact_source_note = "The official county website was checked; because it did not provide additional or changed usable GIS contact information, the MnGeo county GIS directory is retained as the fallback."
    else:
        contact_source_note = "MnGeo is the current contact source; an official-county verification result is not recorded yet."
    verified_text = f' Verified {_dashboard._esc(contact_record.get("verified"))}.' if contact_record.get("verified") else ""
    contacts_html = f'<div class="card"><h2>County GIS contacts</h2><p class="muted"><strong>Contact source:</strong> {contact_source}. {contact_source_note}{verified_text}</p><table class="contacts-table"><thead><tr><th>Name</th><th>Title</th><th>Department</th><th>Phone</th><th>Email</th></tr></thead><tbody>{contact_rows}</tbody></table></div>'
    directory = (config.get("_county_directory") or {}).get(profiles[slug].get("county", {}).get("fips"))
    published_html = ""
    if directory is not None:
        published_html = render_published_directory(directory)
        contacts_html = ""
        parcel_access_detail = ('<details class="card"><summary>Earlier parcel-access research</summary>'
                                f'<p>{RESEARCH_NOTICE}</p>' + parcel_access_detail + '</details>')
    export_links = f'<p><a href="/county-snapshot.csv?slug={_dashboard.urllib.parse.quote(slug)}">Download county snapshot (CSV)</a> · <a href="/county-snapshot.xlsx?slug={_dashboard.urllib.parse.quote(slug)}">Download county snapshot (Excel)</a> · <a href="/county-snapshot.json?slug={_dashboard.urllib.parse.quote(slug)}">Download county snapshot (JSON)</a></p>'
    if config.get("_county_pdf_enabled"):
        export_links += f'<p><a href="/county-profile.pdf?slug={_dashboard.urllib.parse.quote(slug)}">Download county profile PDF</a></p>'
    body = f'<p><a href="/counties">← Minnesota counties</a></p>{export_links}<div class="grid"><div class="card"><div class="muted">County</div><h2>{_dashboard._esc(county["name"])} County</h2></div><div class="card"><div class="muted">Check status</div><div class="metric {_dashboard._esc(info["status"])}">{_dashboard._esc(_dashboard._friendly_status(info["status"]).upper())}</div></div><div class="card"><div class="muted">Source used for checks</div><div class="metric" style="font-size:20px">{_dashboard._esc(_dashboard._monitoring_path_label(info))}</div></div><div class="card"><div class="muted">County sources checked directly</div><div class="metric">{len(info["sources"])}</div><span class="subtext">Data sources checked directly by Watchtower, separate from the access links below.</span></div></div><div class="grid">{source_cards}</div><br>{published_html}{parcel_access_detail}<br>{mngac_html}<br>{gac_summary_html}<br><div class="card county-complete-profile">{complete_profile}</div><br>{contacts_html}'
    return _dashboard._layout(page_title(f'{county["name"]} County'), body,
                              refresh_seconds=10 if config.get("_directory_refresh") else 30,
                              static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))
