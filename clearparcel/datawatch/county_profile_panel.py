"""Shared, offline county profile markup and accessible map dialog."""
from __future__ import annotations
import datetime as dt
import html
import json
from zoneinfo import ZoneInfo
from .public_values import safe_public_url

GROUPS = (("mngac_public_parcels", "MN GAC Public Parcels"), ("mngeo_public_repository", "MnGeo Public County Repository"), ("county_arcgis_rest", "County ArcGIS REST"), ("county_download", "County Website Download"))
PERCENT_COLORS = ["#1b2b40", "#263d59", "#315373", "#3c708f", "#4c9b7b"]
NO_DATA_COLOR = "#151d2b"

def profile_time(value: object) -> str:
    """Preserve calendar dates and convert only aware instants to Central."""
    if not value:
        return "Not available"
    text = str(value)
    try:
        if len(text) == 10:
            return dt.date.fromisoformat(text).isoformat()
        instant = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if instant.tzinfo is not None:
            return instant.astimezone(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M %Z")
    except ValueError:
        pass
    return text

def _esc(value: object) -> str:
    return html.escape(str(value if value is not None and value != "" else "Not available"), quote=True)

def _rows(values: list[tuple[str, object]]) -> str:
    return "<dl>" + "".join(f"<div><dt>{_esc(label)}</dt><dd>{_esc(value)}</dd></div>" for label, value in values) + "</dl>"

def _links(items: list[dict]) -> str:
    links = []
    for item in items:
        url = safe_public_url(item.get("href") or item.get("url"))
        if url:
            links.append(f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(item.get("label") or item.get("authority") or url)}</a>')
    return " · ".join(links) or "Not available"

def render_county_profile_body(profile: dict) -> str:
    """Render one complete composed profile using escaped scalar values."""
    county, monitoring = profile.get("county", {}), profile.get("monitoring", {})
    access, research = profile.get("access", {}), profile.get("research", {})
    body = f'<h2 id="county-profile-title">{_esc(county.get("name"))} County</h2>'
    body += '<p>' + _esc(" · ".join(monitoring.get("paths") or []) or "No active parcel monitoring") + ' · ' + _esc(monitoring.get("health")) + ' · ' + _esc(monitoring.get("reporting")) + '</p>'
    body += '<div class="profile-summary">' + _rows([("Active monitoring", "Yes" if monitoring.get("active") else "No"), ("County-direct access", access.get("public_classification")), ("Active parcel sources", monitoring.get("active_parcel_source_count")), ("Latest county Watchtower check", profile_time(monitoring.get("last_checked_at")))]) + '</div>'
    for key, heading in GROUPS:
        category = profile.get(key, {})
        availability = category.get("availability", "unknown")
        status = "Not included" if availability == "no" else "Available" if availability == "yes" else "Not available"
        body += f'<section><h3>{heading}</h3><p>{status} · {_esc(category.get("review_status"))}</p>'
        for source in category.get("sources", []):
            count = source.get("feature_count")
            file = source.get("file") or {}
            body += '<article class="profile-source"><h4>' + _esc(source.get("name")) + '</h4>'
            body += _rows([("Inventory ID", source.get("inventory_id")), ("Observed source ID", source.get("monitored_source_id")), ("Authority", source.get("authority")), ("Dataset type", source.get("dataset_type")), ("Layer ID", source.get("layer_id")), ("Geometry type", source.get("geometry_type")), ("Feature count", f"{count:,}" if isinstance(count, int) else count), ("Count basis", source.get("feature_count_basis")), ("Provider update", profile_time(source.get("provider_updated_at"))), ("County acquisition", profile_time(source.get("county_acquired_at"))), ("Catalog refresh", profile_time(source.get("catalog_refreshed_at"))), ("Watchtower check", profile_time(source.get("checked_at"))), ("Successful observation", profile_time(source.get("last_success_at"))), ("Health", source.get("health")), ("Reporting", source.get("reporting")), ("Execution profile", source.get("execution_profile")), ("Monitoring decision", source.get("monitoring_decision")), ("File type", file.get("type")), ("File size (bytes)", file.get("size_bytes")), ("ETag", file.get("etag")), ("File last modified", profile_time(file.get("last_modified")))])
            body += '<p>Official product links: ' + _links(source.get("approved_public_links") or []) + '</p></article>'
        body += '</section>'
    body += '<section><h3>Access and research evidence</h3>' + _rows([("County-direct classification", access.get("detailed_classification")), ("Dataset fee", access.get("dataset_fee")), ("Fee product", access.get("fee_product")), ("Monitoring decision", access.get("monitoring_decision")), ("Research status", "Complete" if research.get("complete") else "Research incomplete"), ("Research review", profile_time(research.get("review_date"))), ("Successful county observation", profile_time(monitoring.get("last_success_at"))), ("Aggregate generated", profile_time(monitoring.get("aggregate_generated_at")))])
    body += '<p>' + _links(research.get("evidence_links") or access.get("evidence_links") or []) + '</p></section>'
    if profile.get("comments"):
        body += '<section><h3>Comments</h3>' + ''.join('<p>' + _esc(comment) + '</p>' for comment in profile['comments']) + '</section>'
    body += f'<p><a href="/county?slug={_esc(county.get("slug"))}">Open county dashboard →</a></p>'
    return body

def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

def percentage_color_js() -> str:
    """Shared percentage classifier; null is distinct from observed zero."""
    return "function percentageColor(value){if(typeof value!=='number')return " + json.dumps(NO_DATA_COLOR) + ";const colors=" + json.dumps(PERCENT_COLORS) + ";const breaks=[25,50,75,90];return colors[breaks.filter(edge=>value>=edge).length]}"


def percentage_legend() -> str:
    """Use the same fixed breaks and colors as both maps."""
    values = [(NO_DATA_COLOR, "No data"), *zip(PERCENT_COLORS, ["0–<25%", "25–<50%", "50–<75%", "75–<90%", "90–100%"])]
    return '<div class="mngac-legend" aria-label="Map legend">' + ''.join(f'<span><i class="mngac-swatch" style="background:{color}"></i>{label}</span>' for color, label in values) + '</div>'

def render_county_profile_panel(profiles: dict[str, dict]) -> str:
    """Return exact JSON profiles, trusted escaped templates and a native dialog."""
    templates = ''.join(f'<template data-profile="{_esc(slug)}">{render_county_profile_body(profile)}</template>' for slug, profile in profiles.items())
    return '<script type="application/json" id="county-profile-data">' + _json(profiles) + '</script>' + templates + r'''
<style>
#county-profile-dialog{color:#e0e7f2;background:#0d1522;border:1px solid #52647c;border-radius:14px;width:min(940px,calc(100vw - 24px));max-width:calc(100vw - 24px);max-height:90dvh;overflow-y:auto;padding:0;box-sizing:border-box}#county-profile-dialog::backdrop{background:#020710bb}#county-profile-dialog .profile-toolbar{position:sticky;top:0;z-index:2;display:flex;justify-content:flex-end;background:#0d1522;padding:10px;border-bottom:1px solid #33445a}#county-profile-dialog button{color:#fff;background:#263d59;border:1px solid #74869b;border-radius:6px;padding:8px 14px}#county-profile-content{padding:18px;overflow-wrap:anywhere}#county-profile-dialog section{border-top:1px solid #33445a;margin-top:18px;padding-top:12px}#county-profile-dialog dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}#county-profile-dialog dl>div{min-width:0}#county-profile-dialog dt{font-size:12px;color:#a9b9ce}#county-profile-dialog dd{margin:4px 0;font-size:14px}#county-profile-dialog .profile-source{padding:12px;background:#131e2e;border:1px solid #33445a;border-radius:8px;margin:12px 0}#county-profile-dialog a{color:#8bbdff}#county-profile-dialog h4{margin:0 0 12px}@media(max-width:600px){#county-profile-dialog dl{grid-template-columns:minmax(0,1fr)}#county-profile-content{padding:12px}}
</style>
<dialog id="county-profile-dialog" aria-labelledby="county-profile-title"><div class="profile-toolbar"><button type="button" id="county-profile-close" autofocus>Close ×</button></div><div id="county-profile-content"></div></dialog>
<script>
(function(){
  const dialog=document.getElementById('county-profile-dialog'),content=document.getElementById('county-profile-content');
  let opener=null,scroll=0;
  function openCounty(target){
    const template=[...document.querySelectorAll('template[data-profile]')].find(t=>t.dataset.profile===target.dataset.slug);
    if(!template)return;
    opener=target;scroll=window.scrollY;content.replaceChildren(template.content.cloneNode(true));
    window.watchtowerRefresh?.pause();dialog.showModal();dialog.scrollTop=0;document.getElementById('county-profile-close').focus();
  }
  document.querySelectorAll('.mngac-county').forEach(target=>{
    target.addEventListener('click',()=>openCounty(target));
    target.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openCounty(target)}});
  });
  document.getElementById('county-profile-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{opener?.focus({preventScroll:true});window.scrollTo(0,scroll);window.watchtowerRefresh?.resume()});
  dialog.addEventListener('keydown',event=>{
    if(event.key!=='Tab')return;
    const targets=[...dialog.querySelectorAll('button,a[href]')],first=targets[0],last=targets[targets.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
  });
})();
</script>
'''
