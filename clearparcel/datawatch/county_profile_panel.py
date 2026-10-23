"""Shared, offline county profile markup and accessible map dialog."""
from __future__ import annotations
from clearparcel.datawatch.csp import SCRIPT_TAG
import datetime as dt
import html
import json
import math
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from .public_values import safe_public_url

GROUPS = (("mngac_public_parcels", "MN GAC Public Parcels"), ("mngeo_public_repository", "MnGeo Public County Repository"), ("county_arcgis_rest", "County ArcGIS REST"), ("county_download", "County Website Download"))
# Sequential bins with about 2:1 luminance contrast between neighbours; "no data"
# is a hatch pattern so it never depends on telling two dark colours apart.
PERCENT_COLORS = ["#30506f", "#4583b3", "#7cbedf", "#c9edf5"]
NO_DATA_COLOR = "#151d2b"
NO_DATA_FILL = "url(#pct-no-data)"
# Fixed classes shared by map fills and legends. Exact 30 and 50 start the next class;
# exact 70 stays in 50-70. Rates outside 0-100 are unavailable, not low or high.
PERCENT_BINS = (("<30%", 30, False), ("30% - 50%", 50, False),
                ("50% - 70%", 70, True), (">70%", None, False))


def research_summary(profiles: dict[str, dict]) -> str:
    reviewed = sum(bool(p.get('research', {}).get('review_date')) for p in profiles.values())
    complete = sum(p.get('research', {}).get('complete') is True for p in profiles.values())
    statuses = [status for p in profiles.values() for status in p.get('research', {}).get('category_review_statuses', {}).values()]
    blocked = statuses.count('blocked')
    assessed = statuses.count('reviewed') + statuses.count('not-found')
    return (f'<p><strong>{reviewed}/{len(profiles)} counties researched.</strong> '
            f'{complete}/{len(profiles)} complete county profiles.</p>'
            f'<p>{assessed}/{len(statuses)} category slots reviewed; {blocked} blocked. Reviewed categories and complete profiles are separate measures.</p>'
            '<p class="subtext">A complete profile requires resolved evidence across all four parcel-source categories. '
            'Counties with blocked access, unclear terms, or unresolved products have been researched, '
            'but their profiles remain Research incomplete. Research does not authorize monitoring.</p>')


def _evidence_details(items: list[dict]) -> str:
    rows = []
    for item in items:
        url = safe_public_url(item.get('href') or item.get('url'))
        if url:
            rows.append(f'<li><a href="{_esc(url)}" target="_blank" rel="noopener">'
                        f'{_esc(urlsplit(url).hostname)}</a><p>{_esc(item.get("label") or "Official evidence")}</p></li>')
    return ('<details class="profile-evidence"><summary>Official evidence and findings ('
            + str(len(rows)) + ')</summary><ul>' + ''.join(rows) + '</ul></details>') if rows else '<p>Official evidence is not available.</p>'

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
    body += render_direct_schema_findings(profile.get('direct_gac_schema') or [])
    for key, heading in GROUPS:
        category = profile.get(key, {})
        availability = category.get("availability", "unknown")
        status = "Not included" if availability == "no" else "Available" if availability == "yes" else "Not available"
        body += f'<section><h3>{heading}</h3><p>{status} · {_esc(category.get("review_status"))}</p>'
        for source in category.get("sources", []):
            count = source.get("feature_count")
            file = source.get("file") or {}
            body += '<article class="profile-source"><h4>' + _esc(source.get("name")) + '</h4>'
            body += _rows([("Inventory ID", source.get("inventory_id")), ("Observed source ID", source.get("monitored_source_id")), ("Authority", source.get("authority")), ("Dataset type", source.get("dataset_type")), ("Layer ID", source.get("layer_id")), ("Geometry type", source.get("geometry_type")), ("Feature count", f"{count:,}" if isinstance(count, int) else count), ("Count basis", source.get("feature_count_basis")), ("Provider update", profile_time(source.get("provider_updated_at"))), ("MnGeo acquisition", profile_time(source.get("county_acquired_at"))), ("County metadata publication", profile_time(source.get("county_metadata_published_at"))), ("County metadata content date", profile_time(source.get("county_metadata_content_at"))), ("Catalog refresh", profile_time(source.get("catalog_refreshed_at"))), ("Watchtower check", profile_time(source.get("checked_at"))), ("Successful observation", profile_time(source.get("last_success_at"))), ("Health", source.get("health")), ("Reporting", source.get("reporting")), ("Execution profile", source.get("execution_profile")), ("Monitoring decision", source.get("monitoring_decision")), ("File type", file.get("type")), ("File size (bytes)", file.get("size_bytes")), ("ETag", file.get("etag")), ("File last modified", profile_time(file.get("last_modified")))])
            body += '<p>Official product links: ' + _links(source.get("approved_public_links") or []) + '</p></article>'
        body += '</section>'
    body += '<section><h3>Access and research evidence</h3>' + _rows([("County-direct classification", access.get("detailed_classification")), ("Dataset fee", access.get("dataset_fee")), ("Fee product", access.get("fee_product")), ("Monitoring decision", access.get("monitoring_decision")), ("Research status", "Complete" if research.get("complete") else "Research incomplete"), ("Research review", profile_time(research.get("review_date"))), ("Successful county observation", profile_time(monitoring.get("last_success_at"))), ("Aggregate generated", profile_time(monitoring.get("aggregate_generated_at")))])
    body += _evidence_details(research.get("evidence_links") or access.get("evidence_links") or []) + '</section>'
    if profile.get("comments"):
        body += '<section><h3>Research notes</h3><details class="profile-evidence"><summary>Read detailed research notes</summary><ul>' + ''.join('<li>' + _esc(note.strip()) + '</li>' for comment in profile['comments'] for note in comment.split(' · ') if note.strip()) + '</ul></details></section>'
    body += f'<p><a href="/county?slug={_esc(county.get("slug"))}">Open county dashboard →</a></p>'
    return '<div class="county-profile">' + body + '</div>'


def render_direct_schema_findings(assessments: list[dict]) -> str:
    """Explain direct-feed schema evidence without grading county-wide compliance."""
    if not assessments:
        return ''
    rows = []
    for item in assessments:
        row = '<p><strong>' + _esc(item.get('label')) + '</strong></p>'
        if item.get('standard_fields_present') is not None:
            row += '<p>' + _esc(item.get('standard_fields_present')) + ' / ' + _esc(item.get('standard_field_count')) + ' standard field names; ' + _esc(item.get('mandatory_fields_present')) + ' / ' + _esc(item.get('mandatory_field_count')) + ' mandatory field names.</p>'
            if item.get('missing_mandatory_fields'):
                row += '<p>Missing mandatory names: <code>' + _esc(', '.join(item['missing_mandatory_fields'])) + '</code>.</p>'
        if item.get('reason'):
            row += '<p>' + _esc(item['reason']) + '</p>'
        if item.get('checked_at'):
            row += '<p class="subtext">Schema audit: ' + _esc(profile_time(item['checked_at'])) + '. '
            url = safe_public_url(item.get('evidence_url'))
            if url:
                row += '<a href="' + _esc(url) + '" target="_blank" rel="noopener">Checked direct layer</a>. '
            row += 'Feed: ' + _esc(item.get('name') or item.get('source_id')) + '.</p>'
        rows.append(row)
    return ('<div class="direct-gac-schema"><h3>County-direct MN GAC schema</h3>' + ''.join(rows)
            + '<p class="subtext">Field-name evidence applies to the checked direct feed. It is separate from MnGeo Open Parcels coverage and statewide field population. '
              'MN GAC is a transfer standard; counties may use another internal schema or offer a separate standardized export. '
              'Names alone do not establish full compliance.</p></div>')


def percentage_color(value: object) -> str:
    """Classify a measured 0-100 rate without turning missing values into zero."""
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        return NO_DATA_FILL
    for color, (_, upper, inclusive) in zip(PERCENT_COLORS, PERCENT_BINS):
        if upper is None or value < upper or (inclusive and value == upper):
            return color
    return NO_DATA_FILL


def percentage_color_js() -> str:
    """Use the same boundaries in browser maps and the server-rendered map."""
    classes = [{"upper": upper, "inclusive": inclusive, "color": color}
               for color, (_, upper, inclusive) in zip(PERCENT_COLORS, PERCENT_BINS)]
    return ("function percentageColor(value){if(typeof value!=='number'||!Number.isFinite(value)"
            "||value<0||value>100)return " + json.dumps(NO_DATA_FILL)
            + ";const classes=" + json.dumps(classes)
            + ";return classes.find(bin=>bin.upper===null||value<bin.upper||"
              "(bin.inclusive&&value===bin.upper)).color}")


def percentage_legend() -> str:
    """Use the same fixed breaks and colors as both maps."""
    values = [("pct-no-data-swatch", NO_DATA_COLOR, "No data"),
              *(("", color, label) for color, (label, _, _) in zip(PERCENT_COLORS, PERCENT_BINS))]
    return ('<div class="mngac-legend" role="group" aria-label="Map legend">' + ''.join(
        f'<span><i class="mngac-swatch {cls}" style="background-color:{color}" aria-hidden="true"></i>{html.escape(label)}</span>'
        for cls, color, label in values) + '</div>')


def percentage_patterns() -> str:
    """SVG pattern for counties without a measured rate (shared by every map)."""
    return ('<defs><pattern id="pct-no-data" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            '<rect width="7" height="7" fill="#151d2b"/><line x1="0" y1="0" x2="0" y2="7" stroke="#8593a6" stroke-width="1.4"/>'
            '</pattern></defs>')


# Shared by both public county loaders. A 409 means the page's map and chart
# data belong to an older publication: never show a newer fragment beside
# them. Reload once (keeping selection and refresh-pause state) or ask the
# reader to reload; never combine two revisions.
_FRAGMENT_JS = r'''
  function countyRevision(){return window.watchtowerContentRevision||document.querySelector('[data-content-revision]')?.dataset.contentRevision||''}
  function newerRevision(reopen){
    const page=location.pathname+location.search,key='watchtower-revision-reload:'+page;
    let last=0;try{last=Number(sessionStorage.getItem(key))||0}catch(e){}
    if(window.watchtowerRefresh?.paused?.()||Date.now()-last<60000)return false;
    try{sessionStorage.setItem(key,String(Date.now()));if(reopen)sessionStorage.setItem('watchtower-reopen-county:'+page,reopen)}catch(e){return false}
    window.watchtowerRefresh?.save();location.reload();return true;
  }
  async function countyFragment(slug,signal){
    const response=await fetch('/api/county-profile?slug='+encodeURIComponent(slug)+'&revision='+encodeURIComponent(countyRevision()),{signal});
    if(response.status===409){const error=new Error('newer revision');error.newerRevision=true;throw error}
    if(!response.ok)throw new Error();
    return response.text();
  }
  const NEWER_REVISION='Newer observations were published after this page loaded. Reload the page to see current county details.';
'''


def render_inline_county_panel(*, revision: str) -> str:
    """Load the existing escaped public fragment into the overview's county pane."""
    return '<span hidden data-content-revision="' + _esc(revision) + '"></span>' + r'''
<style>
.overview-county-explorer{align-items:stretch;grid-auto-rows:1fr}.overview-county-explorer>.card{min-width:0}#home-county-pane{display:flex;flex-direction:column;min-width:0}#home-county-profile{overflow-wrap:anywhere}
#overview-map-pane{display:flex;flex-direction:column;padding:17px;background:#0b111b}#overview-map-pane .overview-map-content{display:flex;flex-direction:column;flex:1;min-height:0}#overview-map-pane .mngac-map{flex:1;height:0;min-height:520px;max-height:none}#overview-map-pane .overview-map-note{font-size:11px;margin:12px 0 0}.status-different{background-image:repeating-linear-gradient(135deg,transparent 0 4px,#654900 4px 5px)}.status-closed{background-image:repeating-linear-gradient(45deg,transparent 0 4px,#26303d 4px 5px),repeating-linear-gradient(135deg,transparent 0 4px,#26303d 4px 5px)}.status-unresolved{background-image:radial-gradient(#8593a6 1px,transparent 1px);background-size:5px 5px}@media(max-width:600px){#overview-map-pane .mngac-map{min-height:320px}}
#home-county-profile dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
#home-county-profile dl>div{min-width:0}#home-county-profile dt{font-size:12px;color:#a9b9ce}
#home-county-profile dd{margin:4px 0;font-size:14px}
#home-county-profile-status:empty{display:none}
#home-county-infographics{margin-top:auto;padding-top:18px;border-top:1px solid #33445a}
#home-county-infographics h3{font-size:16px;margin:0 0 14px}.county-coverage-rings{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;text-align:center}
.county-coverage-ring{--coverage:0%;width:92px;height:92px;border-radius:50%;margin:0 auto 8px;display:grid;place-items:center;background:conic-gradient(#55b68f var(--coverage),#26364a 0);position:relative}
.county-coverage-ring::before{content:'';position:absolute;inset:8px;border-radius:50%;background:#101824}.county-coverage-ring b{position:relative;font-size:17px}
.county-coverage-ring.unavailable{background:#26364a}.county-coverage-ring.unavailable b{font-size:13px}.county-coverage-rings small{color:#a9b9ce}
.county-field-coverage{margin-top:16px;font-size:12px}.county-field-coverage>div:first-child{display:flex;justify-content:space-between;gap:8px;margin-bottom:6px}
.county-field-track{height:9px;background:#26364a;border-radius:5px;overflow:hidden}.county-field-track i{display:block;height:100%;width:var(--coverage,0%);background:#6da6d4}
#home-county-infographics .subtext{font-size:11px;margin:9px 0 0;color:#a9b9ce}
#home-county-profile .direct-gac-schema{margin-top:16px;border-top:1px solid #33445a;padding-top:10px}#home-county-profile .direct-gac-schema h3{font-size:16px}#home-county-profile .direct-gac-schema p{font-size:13px;margin:8px 0}
</style>
''' + SCRIPT_TAG + '\n(function(){' + _FRAGMENT_JS + r'''
  const content=document.getElementById('home-county-profile'),status=document.getElementById('home-county-profile-status');
  const fragments=new Map();let request=0,controller=null;
  function updateInfographics(data){
    document.getElementById('home-county-infographics').hidden=false;
    for(const [key,id,label] of [['pct','mandatory','Mandatory-field population'],['all_pct','all','All-field population']]){
      const value=data?.[key],known=typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100;
      const chart=document.getElementById('county-coverage-'+id),text=known?value.toFixed(2)+'%':'Unavailable';
      chart.style.setProperty('--coverage',known?value+'%':'0%');chart.classList.toggle('unavailable',!known);
      chart.setAttribute('aria-label',label+': '+text);document.getElementById('county-coverage-'+id+'-value').textContent=text;
    }
    const count=data?.fields,total=data?.field_count,known=Number.isInteger(count)&&Number.isInteger(total)&&total>0&&count>=0&&count<=total;
    const text=known?count+' / '+total:'Unavailable',chart=document.getElementById('county-field-coverage');
    chart.setAttribute('aria-label','Fields with values: '+text);
    document.getElementById('county-field-coverage-value').textContent=text;
    document.getElementById('county-field-coverage-fill').style.setProperty('--coverage',known?(count/total*100)+'%':'0%');
  }
  async function load(slug,data){
    updateInfographics(data);
    const current=++request;controller?.abort();controller=new AbortController();
    const signal=controller.signal;
    content.replaceChildren();content.setAttribute('aria-busy','true');status.textContent='Loading county details…';
    const deadline=setTimeout(()=>controller?.signal===signal&&controller.abort(),15000);
    try{
      const cacheKey=slug+':'+countyRevision();
      if(!fragments.has(cacheKey)){
        const text=await countyFragment(slug,signal);
        // Only escaped server-rendered same-origin public fragments enter this parser.
        const parsed=new DOMParser().parseFromString(text,'text/html');
        const profile=parsed.querySelector('.county-profile');if(!profile)throw new Error();
        // Keep only the compact monitoring summary; full evidence stays on the county page.
        [...profile.children].filter(node=>['H2','P','SECTION'].includes(node.tagName)).forEach(node=>node.remove());
        fragments.set(cacheKey,profile);
      }
      if(current!==request)return;
      content.replaceChildren(fragments.get(cacheKey).cloneNode(true));status.textContent='';
    }catch(error){
      if(current!==request)return;
      if(error?.newerRevision){status.textContent=newerRevision()?'Loading newer observations…':NEWER_REVISION;return}
      status.textContent='County details are temporarily unavailable. Use Open county profile to view the county page.';
    }finally{clearTimeout(deadline);if(current===request)content.setAttribute('aria-busy','false')}
  }
  function clear(){
    ++request;controller?.abort();controller=null;
    content.replaceChildren();content.setAttribute('aria-busy','false');status.textContent='';
    updateInfographics();document.getElementById('home-county-infographics').hidden=true;
  }
  window.watchtowerCountyPane={load,clear};
})();
</script>
'''


def render_county_profile_panel(profiles: dict[str, dict], *, revision: str | None = None) -> str:
    """Public dialogs load one escaped fragment; offline/private views use templates."""
    templates = (''.join(f'<template data-profile="{_esc(slug)}">{render_county_profile_body(profile)}</template>'
                         for slug, profile in profiles.items()) if revision is None else '')
    return templates + ('<span hidden data-content-revision="' + _esc(revision) + '"></span>' if revision else '') + r'''
<style>
#county-profile-dialog{color:#e0e7f2;background:#0d1522;border:1px solid #52647c;border-radius:14px;width:min(940px,calc(100vw - 24px));max-width:calc(100vw - 24px);max-height:90dvh;overflow-y:auto;padding:0;box-sizing:border-box}#county-profile-dialog::backdrop{background:#020710bb}#county-profile-dialog .profile-toolbar{position:sticky;top:0;z-index:2;display:flex;justify-content:flex-end;background:#0d1522;padding:10px;border-bottom:1px solid #33445a}#county-profile-dialog button{color:#fff;background:#263d59;border:1px solid #74869b;border-radius:6px;padding:8px 14px}#county-profile-content{padding:18px;overflow-wrap:anywhere}#county-profile-dialog section{border-top:1px solid #33445a;margin-top:18px;padding-top:12px}#county-profile-dialog dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}#county-profile-dialog dl>div{min-width:0}#county-profile-dialog dt{font-size:12px;color:#a9b9ce}#county-profile-dialog dd{margin:4px 0;font-size:14px}#county-profile-dialog .profile-source{padding:12px;background:#131e2e;border:1px solid #33445a;border-radius:8px;margin:12px 0}#county-profile-dialog a{color:#8bbdff}#county-profile-dialog h4{margin:0 0 12px}@media(max-width:600px){#county-profile-dialog dl{grid-template-columns:minmax(0,1fr)}#county-profile-content{padding:12px}}
</style>
<dialog id="county-profile-dialog" aria-label="County parcel source profile"><div class="profile-toolbar"><button type="button" id="county-profile-close" autofocus>Close ×</button></div><div id="county-profile-content"></div></dialog>
''' + SCRIPT_TAG + '\n(function(){' + _FRAGMENT_JS + r'''
  const dialog=document.getElementById('county-profile-dialog'),content=document.getElementById('county-profile-content');
  let opener=null,scroll=0,request=0,controller=null;
  const fragments=new Map();
  function unavailable(slug,text){content.textContent=text;const link=document.createElement('a');link.href='/county?slug='+encodeURIComponent(slug);link.textContent='Open county page';content.append(' ',link)}
  async function openCounty(target){
    const template=[...document.querySelectorAll('template[data-profile]')].find(t=>t.dataset.profile===target.dataset.slug);
    const slug=target.dataset.slug;if(!slug)return;
    opener=target;scroll=window.scrollY;const current=++request;
    controller?.abort();controller=null;
    window.watchtowerRefresh?.suspend('county-dialog');
    if(!dialog.open)dialog.showModal();dialog.scrollTop=0;document.getElementById('county-profile-close').focus();
    if(template){content.replaceChildren(template.content.cloneNode(true));return}
    content.textContent='Loading county profile…';
    // One bounded lifecycle per open: closing, reopening or the deadline aborts it.
    const own=controller=new AbortController(),signal=own.signal;
    const deadline=setTimeout(()=>own.abort(),15000);
    try{
      const cacheKey=slug+':'+countyRevision();
      if(!fragments.has(cacheKey)){
        const html=await countyFragment(slug,signal);
        // Only server-rendered, escaped same-origin fragments enter this parser.
        const parsed=new DOMParser().parseFromString(html,'text/html');
        if(!parsed.querySelector('.county-profile'))throw new Error();
        fragments.set(cacheKey,parsed.body);
      }
      if(current===request&&dialog.open)content.replaceChildren(...[...fragments.get(cacheKey).childNodes].map(node=>node.cloneNode(true)));
    }catch(e){
      if(current!==request||!dialog.open)return;
      if(e?.newerRevision){if(newerRevision(slug)){content.textContent='Loading newer observations…';return}unavailable(slug,NEWER_REVISION);return}
      unavailable(slug,'County details are temporarily unavailable.');
    }finally{clearTimeout(deadline);if(controller===own)controller=null}
  }
  document.querySelectorAll('.mngac-county').forEach(target=>{
    target.addEventListener('click',()=>openCounty(target));
    target.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openCounty(target)}});
  });
  document.getElementById('county-profile-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{request++;controller?.abort();controller=null;opener?.focus({preventScroll:true});window.scrollTo(0,scroll);window.watchtowerRefresh?.release('county-dialog')});
  try{const key='watchtower-reopen-county:'+location.pathname+location.search,slug=sessionStorage.getItem(key);
    if(slug){sessionStorage.removeItem(key);const target=[...document.querySelectorAll('.mngac-county')].find(t=>t.dataset.slug===slug);if(target)openCounty(target)}}catch(e){}
  dialog.addEventListener('keydown',event=>{
    if(event.key!=='Tab')return;
    const targets=[...dialog.querySelectorAll('button,a[href],summary,input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter(el=>!el.disabled&&(el.checkVisibility?el.checkVisibility():el.getClientRects().length>0)),first=targets[0],last=targets[targets.length-1];if(!targets.length)return;
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
  });
})();
</script>
'''


def __getattr__(name: str):
    """Resolve names that v0.2.3 exposed here (see clearparcel.datawatch._compat)."""
    from clearparcel.datawatch import _compat
    return _compat.resolve(__name__, name)
