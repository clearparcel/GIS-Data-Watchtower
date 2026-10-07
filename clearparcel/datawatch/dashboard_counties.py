from __future__ import annotations

from clearparcel.datawatch import dashboard as _dashboard
from clearparcel.datawatch.dashboard_summary import catalog_summary
from clearparcel.datawatch.county_profile_panel import profile_time


def render_counties(config: dict) -> str:
    state = _dashboard._dashboard_state(config)
    research = _dashboard.load_parcel_access()
    profiles = _dashboard._county_profiles(config, state, research)
    counties = [_dashboard._county_status(config, x, state, profiles=profiles, research=research) for x in _dashboard._load_counties()]
    active_count = sum(1 for x in counties if x["actively_monitored"])
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
    rows = "".join(
        f'<tr data-name="{_dashboard._esc(x["name"].lower())}" data-status="{_dashboard._esc(x["status"])}">'
        f'<td><a href="/county?slug={_dashboard.urllib.parse.quote(x["slug"])}"><strong>{_dashboard._esc(x["name"])} County</strong></a></td>'
        f'<td><span class="pill {_dashboard._esc(x["status"])}">{_dashboard._esc(_dashboard._friendly_status(x["status"]))}</span>'
        f'<br><span class="subtext">{_dashboard._esc(_dashboard._monitoring_path_label(x))}</span></td>'
        f'<td><strong>{_dashboard._esc(_dashboard.access_label(x.get("parcel_access")))}</strong></td>'
        f'<td><strong>{_dashboard._esc(_dashboard.statewide_access_label(x.get("parcel_access"), live_available=(x.get("statewide_record") is not None) if mngac else None))}</strong></td>'
        f'<td>{len(x["sources"])}</td></tr>'
        for x in counties
    )
    if mngac:
        mngac_card = (
            f'<div class="card"><h2>MN GAC field completeness</h2><p><strong>{_dashboard._esc(mngac.get("covered_counties") or 0)} of {len(counties)} counties</strong> are represented in MnGeo Plan Parcels Open for standardized field-population statistics.</p>'
            f'<p><a href="/mngac">Explore the interactive county map and all 91 fields →</a></p></div><br>'
        )
    else:
        mngac_card = '<div class="card"><h2>MN GAC field completeness</h2><p class="muted">A statewide completeness observation has not been stored yet.</p><p><a href="/mngac">Open MN GAC completeness →</a></p></div><br>'
    body = f'<div class="grid"><div class="card"><div class="muted">Minnesota counties</div><div class="metric">{len(counties)}</div><span class="subtext">Counties represented in the statewide county dashboard index.</span></div><div class="card"><div class="muted">Counties actively checked</div><div class="metric">{active_count}</div><span class="subtext">Actively monitored through a county-direct source, MnGeo Plan Parcels Open, or both.</span></div><div class="card"><div class="muted">County-direct checks</div><div class="metric">{direct_count}</div><span class="subtext">Counties with at least one county-specific source actively checked.</span></div><div class="card"><div class="muted">MnGeo open coverage</div><div class="metric">{mngeo_count}</div><span class="subtext">Counties represented in the current Plan Parcels Open observation.</span></div></div>' + mngac_card + \
        f'<div class="grid"><div class="card">{_dashboard._bar_chart([( _dashboard._friendly_status(k), v) for k,v in sorted(status_counts.items())], title="County monitoring coverage")}<span class="subtext">A county is actively checked when Watchtower observes it through a county-specific source, the statewide MnGeo open-parcels source, or both.</span></div><div class="card">{_dashboard._bar_chart(list(age_buckets.items()), title="MnGeo parcel update age")}<span class="subtext">Age of the county acquisition/update date reported in the MnGeo parcel catalog; this is not Watchtower check time. {_dashboard._esc(catalog_notice)}</span></div></div><div class="card"><h2>Minnesota county dashboards</h2><p class="muted">Monitoring coverage, county-direct parcel access, and statewide open access are separate. A county can require payment for its county-supplied dataset while also being freely available through MnGeo Plan Parcels Open.</p><p class="subtext">Use Export in the page toolbar for statewide Excel, CSV, or JSON.</p>' \
        '<div class="filters"><input id="cq" aria-label="Filter counties" placeholder="Filter counties…" oninput="filterCounties()"><select id="cs" aria-label="Filter by county monitoring coverage" onchange="filterCounties()"><option value="">All coverage types</option><option value="ok">Actively checked</option><option value="catalog">MnGeo catalog only</option><option value="needs-source">No active parcel monitoring</option><option value="not-configured">No source information yet</option><option value="warn">Needs attention</option><option value="error">Check failed</option></select></div>' \
        f'<table id="counties"><thead><tr><th>County</th><th>Monitoring coverage<br><span class="subtext">Health and active monitoring path</span></th><th>County-direct access<br><span class="subtext">Evidence-backed county access</span></th><th>Statewide open access<br><span class="subtext">Current MnGeo Plan Parcels Open coverage</span></th><th>County-direct sources<br><span class="subtext">County-specific sources actively checked</span></th></tr></thead><tbody>{rows}</tbody></table></div>' \
        "<script>function filterCounties(){const q=document.getElementById('cq').value.toLowerCase(),s=document.getElementById('cs').value;document.querySelectorAll('#counties tbody tr').forEach(r=>r.style.display=(!q||r.dataset.name.includes(q))&&(!s||r.dataset.status===s)?'':'none')}</script>"
    body += f'<div class="card"><h2>Parcel source research</h2>{_dashboard.research_summary(profiles)}</div>'
    return _dashboard._layout("Minnesota Counties — GIS Data Watchtower", '<p><a href="/">← Watchtower overview</a></p>'+body, static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))


def render_county(config: dict, slug: str) -> str:
    state = _dashboard._dashboard_state(config)
    county = next((x for x in _dashboard._load_counties() if x.get("slug") == slug), None)
    if not county:
        return _dashboard._layout("County not found", '<p><a href="/counties">← Minnesota counties</a></p><div class="card">County not found.</div>', static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))
    research = _dashboard.load_parcel_access()
    profiles = _dashboard._county_profiles(config, state, research)
    info = _dashboard._county_status(config, county, state, profiles=profiles, research=research)
    complete_profile = _dashboard.render_county_profile_body(profiles[slug])
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
            details.append(f'<strong>County-direct machine-readable source:</strong> <a href="{_dashboard._esc(service_url)}" target="_blank" rel="noopener">Open source</a>')
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
            f'<p><strong>Status:</strong> {_dashboard._esc(_dashboard._health_status(src.get("status") or "unknown"))}'
            f'<br><strong>County records:</strong> {_dashboard._esc(f"{statewide_record_count:,}")}'
            f'<br><strong>Monitoring path:</strong> Statewide open parcel source'
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
        source_links = (f'<a href="{_dashboard._esc(data_url)}" target="_blank" rel="noopener">Open parcel data</a>' if data_url else "No open data URL supplied")
        if viewer_url:
            source_links += f' · <a href="{_dashboard._esc(viewer_url)}" target="_blank" rel="noopener">Viewer</a>'
        source_cards = f'<div class="card"><h3>County parcel update information</h3><p><strong>MnGeo public-data approval:</strong> {_dashboard._esc(approval)}<br><strong>Last county update:</strong> {_dashboard._esc(_dashboard._format_arcgis_date(catalog.get("acqdate")))}<br><strong>MnGeo listing refreshed:</strong> {_dashboard._esc(_dashboard._format_arcgis_date(catalog.get("rundate")))}<br><strong>Parcel links:</strong> {source_links}</p></div>'
    elif not source_cards:
        source_cards = '<div class="card"><h3>No direct county parcel source currently monitored</h3><p>Monitoring coverage is separate from the parcel-data access research shown below.</p></div>'
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
    export_links = f'<p><a href="/county-snapshot.csv?slug={_dashboard.urllib.parse.quote(slug)}">Download county snapshot (CSV)</a> · <a href="/county-snapshot.xlsx?slug={_dashboard.urllib.parse.quote(slug)}">Download county snapshot (Excel)</a> · <a href="/county-snapshot.json?slug={_dashboard.urllib.parse.quote(slug)}">Download county snapshot (JSON)</a></p>'
    body = f'<p><a href="/counties">← Minnesota counties</a></p>{export_links}<div class="grid"><div class="card"><div class="muted">County</div><h2>{_dashboard._esc(county["name"])} County</h2></div><div class="card"><div class="muted">Monitoring coverage</div><div class="metric {_dashboard._esc(info["status"])}">{_dashboard._esc(_dashboard._friendly_status(info["status"]).upper())}</div></div><div class="card"><div class="muted">Monitoring path</div><div class="metric" style="font-size:20px">{_dashboard._esc(_dashboard._monitoring_path_label(info))}</div></div><div class="card"><div class="muted">County-direct sources</div><div class="metric">{len(info["sources"])}</div></div></div><div class="grid">{source_cards}</div><br>{parcel_access_detail}<br>{mngac_html}<br>{gac_summary_html}<br><div class="card county-complete-profile">{complete_profile}</div><br>{contacts_html}'
    return _dashboard._layout(f'{county["name"]} County — Watchtower', body, static=bool(config.get("_public_mode")), csrf_token=str(config.get("_csrf_token") or ""))
