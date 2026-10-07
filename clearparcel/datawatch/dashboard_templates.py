from __future__ import annotations

import base64
import html
from pathlib import Path

from clearparcel.datawatch.build_info import application_identity
from clearparcel.datawatch.analytics import posthog_html


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


_PUBLIC_V2_CSS = """
:root{color-scheme:dark;--bg:#080b12;--panel:#111722;--panel2:#151d2b;--panel3:#0d131e;--line:#263247;--line2:#34445e;--text:#eef4ff;--muted:#8e9bb0;--blue:#6ea8fe;--blue2:#4b8ee8;--green:#5bd49a;--amber:#f5c66a;--red:#ff7b86;--shadow:0 12px 30px #0004;--radius:14px}
*{box-sizing:border-box}
html{scroll-behavior:smooth;background:var(--bg)}
body{margin:0;background:radial-gradient(circle at 30% -10%,#152039 0,transparent 38%),var(--bg);color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible,.mngac-county:focus{outline:2px solid var(--blue);outline-offset:2px}
.public-header{height:88px;padding:18px max(22px,calc((100vw - 1400px)/2));display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:#090d15cc;position:sticky;top:0;backdrop-filter:blur(16px);z-index:30}
.brand-eyebrow{font-size:10px;letter-spacing:.18em;color:var(--blue);font-weight:800}
.public-header h1{font-size:24px;margin:3px 0 0;letter-spacing:-.25px}
.live-state{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--green);font-weight:800;white-space:nowrap}.live-dot{width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 14px currentColor}
.public-main{max-width:1400px;margin:auto;padding:0 22px 64px}
.public-tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:0 0 24px;position:sticky;top:88px;background:#080b12ed;backdrop-filter:blur(14px);z-index:20;overflow-x:auto;scrollbar-width:thin;scrollbar-color:var(--line2) transparent}
.public-tabs a{color:var(--muted);padding:14px 13px 11px;border-bottom:2px solid transparent;font-weight:700;white-space:nowrap}.public-tabs a:hover{text-decoration:none;color:var(--text)}.public-tabs a.active{color:var(--text);border-bottom-color:var(--blue)}
.skip-link{position:absolute;left:-10000px;top:auto}.skip-link:focus{left:12px;top:8px;z-index:100;background:var(--panel);padding:10px;border:1px solid var(--line);border-radius:8px}
.public-tools{margin-left:auto;display:flex;align-items:center;position:sticky;right:0;background:#080b12ed;padding-left:8px;box-shadow:-8px 0 12px #080b12ed}.public-export{position:relative}.public-export summary{list-style:none;cursor:pointer;border:1px solid var(--line);background:var(--panel);color:#c4d1e5;border-radius:8px;padding:8px 10px;font-weight:700}.public-export summary::-webkit-details-marker{display:none}.public-export[open] .export-pop{display:grid}
.export-pop{display:none;position:absolute;right:0;top:42px;min-width:160px;padding:6px;background:#0b1019;border:1px solid var(--line);border-radius:10px;box-shadow:0 16px 40px #0008;z-index:60}.export-pop a{padding:9px 10px;border-radius:7px}.export-pop a:hover{background:var(--panel2);text-decoration:none}
.page-kicker{padding:25px 0 16px}.page-kicker .eyebrow{font-size:10px;letter-spacing:.14em;color:var(--blue);font-weight:800;text-transform:uppercase}.page-kicker h2{font-size:27px;margin:4px 0 3px;letter-spacing:-.35px}.page-kicker p{margin:0;color:var(--muted);max-width:840px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:18px}.primary-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.worker-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.card{background:linear-gradient(145deg,var(--panel),#0d121c);border:1px solid var(--line);border-radius:var(--radius);padding:17px;box-shadow:var(--shadow);min-width:0}.card h2,.card h3{margin-top:0}.card h2{font-size:18px}.card h3{font-size:15px}
.metric{font-size:27px;font-weight:800;line-height:1.05;letter-spacing:-.5px;margin-top:4px}.muted{color:var(--muted)}.subtext{display:block;color:var(--muted);font-size:11px;line-height:1.45;margin-top:6px}.ok{color:var(--green)}.warn{color:var(--amber)}.error{color:var(--red)}.catalog{color:var(--blue)}.not-configured,.needs-source{color:var(--muted)}
.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:currentColor;margin-right:7px}.pill{display:inline-flex;align-items:center;height:24px;padding:4px 9px;border:1px solid var(--line);border-radius:999px;font-size:10px;text-transform:uppercase;font-weight:800}.pill.ok{border-color:#2d7155}.pill.warn,.pill.catalog{border-color:#705b2d}.pill.error{border-color:#773944}
.section-head{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:28px 2px 12px}.section-head h2{margin:0;font-size:18px}.section-head p,.section-head span{margin:3px 0 0;color:var(--muted);font-size:11px}.section-head>a{font-size:11px;font-weight:700}
.activity-strip{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}.worker-card{display:grid;grid-template-columns:1fr;gap:10px 18px}.worker-card h3{margin:0}.worker-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.worker-meta div{min-width:90px}.worker-meta .muted,.worker-meta span{display:block;font-size:9px}.worker-meta strong{display:block;margin-top:3px;font-size:13px;overflow-wrap:anywhere}
.summary-v2{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:30px}.summary-v2 .card{padding:16px 18px}.summary-v2 .metric{font-size:24px}.summary-v2 .muted{font-size:11px}
.hero-panel{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(300px,.75fr);gap:14px;margin-bottom:26px}.hero-copy{padding:22px}.hero-copy h2{font-size:24px;margin:0 0 8px}.hero-copy p{color:#c4cede;max-width:720px;margin:0 0 18px}.hero-actions{display:flex;gap:8px;flex-wrap:wrap}.hero-actions a{display:inline-flex;padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:#121a27;color:#c4d1e5;font-weight:700}.hero-actions a.primary{border-color:#315078;color:#dceaff;background:#101827}
.hero-stat{display:grid;grid-template-columns:1fr 1fr;gap:8px}.hero-stat>div{background:var(--panel2);border:1px solid #ffffff0d;border-radius:10px;padding:13px}.hero-stat small{display:block;color:var(--muted);font-size:9px;letter-spacing:.07em;text-transform:uppercase}.hero-stat b{display:block;font-size:19px;margin-top:4px}
table{width:100%;border-collapse:collapse;background:transparent}th,td{padding:11px 12px;border-bottom:1px solid #1b2535;text-align:left;vertical-align:top}th{font-size:9px;text-transform:uppercase;color:var(--muted);letter-spacing:.08em;background:#0d131e}td{color:#c4cede}td strong{color:var(--text)}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.filters input,.filters select,.mngac-controls select,.mngac-controls input{background:#0d131e;border:1px solid var(--line);color:var(--text);border-radius:9px;padding:9px 11px;font:inherit;min-height:38px}.filters input{flex:1;min-width:200px}.filters input::placeholder{color:#68768b}
.bar-row{min-width:0;display:grid;grid-template-columns:minmax(120px,1.35fr) minmax(100px,3fr) 64px;gap:9px;align-items:center;margin:9px 0;font-size:11px}.bar-row>span{min-width:0;overflow-wrap:anywhere}.bar-track{height:7px;background:#202a3b;border-radius:999px;overflow:hidden}.bar-track i{display:block;height:100%;background:var(--blue);border-radius:999px}.chart-range{font-size:10px;color:var(--muted)}
.definition-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.definition-group{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:14px}.definition-list{display:grid;grid-template-columns:minmax(120px,.8fr) 1.4fr;gap:7px 12px;margin:0}.definition-list dt{font-weight:700;color:var(--muted)}.definition-list dd{margin:0;overflow-wrap:anywhere;color:#c4cede}
.mngac-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:14px}.mngac-controls label{display:grid;gap:4px;font-size:10px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.mngac-layout{display:grid;grid-template-columns:minmax(360px,1.35fr) minmax(260px,.65fr);gap:14px;align-items:start}.mngac-map-panel{background:#0b111b;border:1px solid var(--line);border-radius:11px;padding:10px;min-width:0}.mngac-map{display:block;width:100%;height:auto;max-height:690px}.mngac-county{fill:#1b2636;stroke:#51647e;stroke-width:1.1;vector-effect:non-scaling-stroke;cursor:pointer;transition:fill .12s ease,stroke .12s ease,stroke-width .12s ease}.mngac-county:hover,.mngac-county:focus{stroke:#d7e8ff;stroke-width:2.2;outline:none}.mngac-county.selected{stroke:#fff;stroke-width:3}.mngac-detail{min-height:220px}.mngac-detail h3{margin-bottom:4px}.mngac-kpi{font-size:25px;font-weight:800}.mngac-legend{display:flex;flex-wrap:wrap;gap:7px 12px;margin:10px 0 0;font-size:10px;color:var(--muted)}.mngac-legend span{display:inline-flex;align-items:center;gap:5px}.mngac-swatch{width:13px;height:13px;border-radius:3px;border:1px solid #ffffff33;display:inline-block}.mngac-note{border-left:3px solid var(--blue);padding:10px 12px;background:#0e1622;border-radius:0 8px 8px 0;color:#aeb9ca;margin:12px 0}.mngac-table-wrap{overflow-x:auto}.mngac-field-select{background:none;color:var(--blue);padding:0;border:0;text-align:left;font:inherit;cursor:pointer}.mngac-field-select:hover{text-decoration:underline}
code{font-size:11px;color:#b9c6d8}.technical summary,.diagnostics summary{cursor:pointer;font-weight:700;color:var(--blue);padding:4px 0}.diagnostics{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow);margin:18px 0}.flat-note{padding:20px 4px;color:var(--muted);font-size:12px}
.public-footnote{margin:30px 2px 0;padding-top:16px;border-top:1px solid var(--line);color:#66778f;font-size:10px;display:flex;justify-content:space-between;gap:20px}.public-footnote strong{color:#8da4c4}.footer-brand{display:inline-flex;vertical-align:middle}.footer-brand img{width:120px;height:42px;object-fit:contain}.profile-evidence{margin:12px 0;padding:12px;border:1px solid var(--line);border-radius:8px}.profile-evidence summary{cursor:pointer;color:var(--blue);font-weight:600}.profile-evidence li{margin:12px 0;overflow-wrap:anywhere}.profile-evidence p{max-width:80ch}.county-complete-profile section{border-top:1px solid var(--line);padding-top:16px;margin-top:20px}.county-complete-profile dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:12px}.county-complete-profile dd{margin:4px 0}.county-complete-profile dt{color:var(--muted);font-size:12px}
@media(max-width:1050px){.summary-v2{grid-template-columns:repeat(3,minmax(0,1fr))}.primary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.hero-panel{grid-template-columns:1fr}.mngac-layout{grid-template-columns:1fr}.definition-grid{grid-template-columns:1fr}}
@media(max-width:760px){.public-header{height:74px;padding:13px 14px}.public-header h1{font-size:20px}.brand-eyebrow{font-size:8px}.live-state span:last-child{display:none}.public-main{padding:0 12px 76px}.public-tabs{top:74px;overflow-x:auto;margin:0 -12px 18px;padding:0 12px}.public-tabs a{padding:12px 10px 10px}.public-tools{margin-left:4px}.summary-v2{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.grid,.primary-grid,.worker-grid,.activity-strip{grid-template-columns:1fr;gap:9px}.card{padding:14px}.hero-copy{padding:16px}.hero-copy h2{font-size:21px}.hero-stat{grid-template-columns:1fr 1fr}.section-head{margin-top:22px}.section-head span{display:none}.filters{display:grid;grid-template-columns:1fr}.filters input,.filters select{width:100%;min-width:0}#counties thead,#datasets thead,.contacts-table thead,.history-table thead,#mngac-fields thead,#county-mngac-fields thead{display:none}#counties,#counties tbody,#counties tr,#counties td,#datasets,#datasets tbody,#datasets tr,#datasets td,.contacts-table,.contacts-table tbody,.contacts-table tr,.contacts-table td,.history-table,.history-table tbody,.history-table tr,.history-table td,#mngac-fields,#mngac-fields tbody,#mngac-fields tr,#mngac-fields td,#county-mngac-fields,#county-mngac-fields tbody,#county-mngac-fields tr,#county-mngac-fields td{display:block;width:100%}#counties tr,#datasets tr,.contacts-table tr,.history-table tr,#mngac-fields tr,#county-mngac-fields tr{padding:10px 0;border-bottom:1px solid #1b2535}#counties td,#datasets td,.contacts-table td,.history-table td,#mngac-fields td,#county-mngac-fields td{border:0;padding:4px 2px;white-space:normal;overflow-wrap:anywhere}.worker-card{grid-template-columns:1fr}.worker-meta{display:grid;grid-template-columns:1fr 1fr}.definition-list{grid-template-columns:1fr;gap:2px}.definition-list dd{margin-bottom:8px}.mngac-controls label,.mngac-controls select{width:100%}.public-footnote{flex-direction:column;gap:4px}}
@media(max-width:430px){.summary-v2{grid-template-columns:1fr 1fr}.summary-v2 .card{padding:12px}.summary-v2 .metric{font-size:21px}.hero-stat{grid-template-columns:1fr 1fr}.public-export summary{padding:7px 8px}.page-kicker{padding-top:18px}.page-kicker h2{font-size:23px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
"""

def _refresh_script(seconds: int) -> str:
    """Use a cancellable timer so reading a county dialog prevents page reload."""
    if not seconds:
        return ""
    return """<script>
(function(){let timer=null;const delay=""" + str(int(seconds)*1000) + """;
    const key='watchtower-view:'+location.pathname+location.search;
const ids=['q','cat','health','cq','cs','mngac-metric','mngac-county-select','mngac-q','mngac-inclusion','cmq','cmi'];
function save(){const values={};ids.forEach(id=>{const el=document.getElementById(id);if(el)values[id]=el.value});values.focus=document.activeElement?.id||'';try{sessionStorage.setItem(key,JSON.stringify(values))}catch(e){}}
function restore(){try{const values=JSON.parse(sessionStorage.getItem(key)||'{}');ids.forEach(id=>{const el=document.getElementById(id);if(el&&values[id]!==undefined){el.value=values[id];el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}))}});if(values.focus)document.getElementById(values.focus)?.focus();sessionStorage.removeItem(key)}catch(e){}}
function pause(){clearTimeout(timer);timer=null;const button=document.getElementById('refresh-pause');if(button){button.textContent='Resume automatic refresh';button.setAttribute('aria-pressed','true')}}
function resume(){clearTimeout(timer);timer=setTimeout(()=>{if(document.getElementById('county-profile-dialog')?.open||document.querySelector('.profile-evidence[open]')){resume();return}save();location.reload()},delay);const button=document.getElementById('refresh-pause');if(button){button.textContent='Pause automatic refresh';button.setAttribute('aria-pressed','false')}}
document.addEventListener('DOMContentLoaded',()=>{restore();const button=document.getElementById('refresh-pause');button?.addEventListener('click',()=>timer?pause():resume())});
window.watchtowerRefresh={pause,resume};resume();})();
</script>"""


def _public_layout_v2(title: str, body: str, *, refresh_seconds: int = 30) -> str:
    refresh_meta = _refresh_script(refresh_seconds)
    identity = application_identity()
    build_label = identity["revision"][:7] or "unknown"
    release_label = f'v{identity["version"]} · build {build_label} · {identity["environment"].title()}'
    logo_src = "data:image/webp;base64," + base64.b64encode(Path(__file__).with_name("clearparcel-logo.webp").read_bytes()).decode("ascii")
    lower = title.lower()
    active = "mngac" if "gac" in lower else "sources" if "source" in lower else "counties" if "county" in lower or "counties" in lower else "overview"
    tabs = [
        ("overview", "/", "Overview"),
        ("counties", "/counties", "Minnesota Counties"),
        ("mngac", "/mngac", "MN GAC"),
        ("sources", "/#datasets", "Data Sources"),
    ]
    nav = "".join(
        f'<a href="{href}" class="{"active" if key == active else ""}"'
        + (' aria-current="page"' if key == active else "")
        + f'>{label}</a>'
        for key, href, label in tabs
    )
    page_name = (
        title.replace(" — GIS Data Watchtower", "")
        .replace(" — Watchtower", "")
        .replace("GIS Data Watchtower", "Overview")
    )
    subtitle = {
        "overview": "Availability, freshness, and structure of Minnesota public GIS data.",
        "counties": "County profiles, parcel availability, monitoring coverage, and GIS contact references.",
        "mngac": "Field population across Minnesota GAC parcel, address-point, and road-centerline standards.",
        "sources": "Public source health and high-level structural observations.",
    }.get(active, "Minnesota public GIS data, summarized for practical exploration.")
    analytics_script = posthog_html(
        page=page_name,
        version=identity["version"],
        build=build_label,
        environment=identity["environment"],
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{refresh_meta}{analytics_script}<title>{_esc(title)}</title><style>{_PUBLIC_V2_CSS}</style></head><body>
<header class="public-header">
  <div><div class="brand-eyebrow">CLEARPARCEL GIS DATA WATCHTOWER</div><h1>Minnesota Open Data Watchtower</h1></div>
  <div class="live-state"><span class="live-dot"></span><span>PUBLIC · READ ONLY</span>{'<button type="button" id="refresh-pause" aria-pressed="false">Pause refresh</button>' if refresh_seconds else ''}</div>
</header>
<main class="public-main">
  <a class="skip-link" href="#main-content">Skip to content</a><nav class="public-tabs" aria-label="Watchtower views">{nav}
    <div class="public-tools"><details class="public-export"><summary>Export</summary><div class="export-pop"><a href="/snapshot.xlsx">Excel (.xlsx)</a><a href="/county-profiles.csv">County profiles (CSV)</a><a href="/parcel-sources.csv">Parcel sources (CSV)</a><a href="/snapshot.csv">Monitored sources (CSV)</a><a href="/snapshot.json">JSON</a></div></details></div>
  </nav>
  <div class="page-kicker"><div class="eyebrow">PUBLIC DATA INTELLIGENCE</div><h2>{_esc(page_name)}</h2><p>{_esc(subtitle)}</p></div>
  <div id="main-content">{body}</div>
  <footer class="public-footnote"><span><a class="footer-brand" href="https://clear-parcel.com" aria-label="ClearParcel home"><img src="{logo_src}" alt="ClearParcel" width="120" height="42"></a> · Public read-only view</span><span><strong class="application-version" title="Source revision: {_esc(identity['revision'] or 'unknown')}">{_esc(release_label)}</strong><br>Monitoring results are informational and source-dependent.</span></footer>
</main></body></html>"""

def _layout(title: str, body: str, *, refresh_seconds: int = 30, static: bool = False, csrf_token: str = "") -> str:
    if static:
        return _public_layout_v2(title, body, refresh_seconds=refresh_seconds)
    auto_refresh = int(refresh_seconds or 0) > 0
    refresh_meta = _refresh_script(refresh_seconds)
    refresh_label = f"Dashboard view refreshes every {int(refresh_seconds)}s" if auto_refresh else "Interactive view · reload for latest saved data"
    refresh_form = "" if static else (
        '<form method="post" action="/refresh" class="refresh-form">'
        f'<input type="hidden" name="csrf_token" value="{_esc(csrf_token)}">'
        '<button>Check now</button></form>'
    )
    side_context = "Public read-only view" if static else "Private dashboard"
    def icon(kind: str) -> str:
        paths = {
            "overview": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
            "counties": '<path d="M4 5h16v14H4z"/><path d="M8 5v14M16 5v14M4 10h16M4 15h16"/>',
            "mngac": '<path d="M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2z"/><path d="M9 4v14M15 6v14"/>',
            "sources": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
            "changes": '<path d="M4 16l5-5 4 4 7-8"/><path d="M15 7h5v5"/>',
            "alerts": '<path d="M12 3l9 17H3L12 3z"/><path d="M12 9v5M12 17h.01"/>',
            "export": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>',
            "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
        }
        return f'<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">{paths.get(kind, paths["overview"])}</svg>'
    page_title = title.replace(" — GIS Data Watchtower", "").replace("GIS Data Watchtower", "Overview")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{refresh_meta}
<title>{_esc(title)}</title>
<style>
:root{{--navy:#10263b;--navy-2:#17324d;--green:#2d6a4f;--bg:#edf2f6;--card:#fff;--text:#17212b;--muted:#64727e;--accent:#0b6fa4;--soft:#f6f8fa;--line:#d9e1e7;--warn:#8a4600;--err:#a3342f;--shadow:0 3px 14px rgb(23 50 77 / 9%);--radius:13px}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);max-width:100%}}
a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}} a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible{{outline:3px solid #5bb6e8;outline-offset:2px}}
button{{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:9px 13px;font-weight:650;cursor:pointer}}
header{{height:64px;background:var(--navy);color:#fff;padding:0 24px;display:flex;align-items:center;justify-content:space-between;border-bottom:2px solid var(--accent);position:sticky;top:0;z-index:30}}
header h1{{margin:0;font-size:20px;letter-spacing:-.2px}}
.actions{{display:flex;gap:12px;align-items:center;font-size:12px}}
.skip-link{{position:absolute;left:-10000px;top:auto}} .skip-link:focus{{left:12px;top:70px;z-index:100;background:#fff;padding:10px;border:1px solid var(--line);border-radius:8px}}
.app-shell{{display:flex;min-height:calc(100vh - 64px)}}
.sidebar{{width:216px;flex:0 0 216px;background:var(--navy);color:#b9d1e2;padding:18px 12px;position:sticky;top:64px;height:calc(100vh - 64px)}}
.side-brand{{padding:3px 10px 18px;border-bottom:1px solid #ffffff18}}
.side-brand strong{{display:block;color:#fff;font-size:16px}} .side-brand small{{color:#7f9bb0}}
.sidebar nav{{margin-top:15px}}
.sidebar nav a{{display:flex;align-items:center;gap:10px;color:#b8cbd9;padding:10px 11px;border-radius:8px;margin:3px 0;font-weight:550}}
.sidebar nav a:hover{{background:#ffffff0d;color:#fff;text-decoration:none}}
.nav-icon{{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}}
.side-note{{position:absolute;bottom:18px;left:22px;color:#6f8da4;font-size:11px}}
.content-shell{{flex:1;min-width:0;max-width:100%}}
.pagebar{{width:100%;min-width:0;min-height:52px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:8px 24px;position:sticky;top:64px;z-index:20}}
.pagebar-title{{font-size:15px;font-weight:700;color:var(--navy-2)}}
.page-actions{{display:flex;align-items:center;gap:10px;min-width:0;flex:none}}
.export-menu{{position:relative}} .export-menu summary{{list-style:none;cursor:pointer;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--soft);font-weight:650;color:var(--navy-2)}}
.export-menu summary::-webkit-details-marker{{display:none}}
.export-menu[open] .export-pop{{display:grid}}
.export-pop{{display:none;position:absolute;right:0;top:38px;min-width:150px;padding:6px;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);z-index:40}}
.export-pop a{{padding:8px 9px;border-radius:6px}} .export-pop a:hover{{background:var(--soft);text-decoration:none}}
main{{max-width:1280px;margin:22px auto;padding:0 20px 40px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-bottom:18px}}
.primary-grid{{grid-template-columns:repeat(4,minmax(0,1fr))}}
.worker-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:16px;box-shadow:var(--shadow);min-width:0}}
.card h2,.card h3{{margin-top:0}}
.metric{{font-size:28px;font-weight:750;line-height:1.05;letter-spacing:-.4px}}
.muted{{color:var(--muted)}} .subtext{{display:block;color:var(--muted);font-size:12.5px;line-height:1.4;margin-top:6px}}
.ok{{color:var(--green)}} .warn{{color:var(--warn)}} .error{{color:var(--err)}}
.status-dot{{display:inline-block;width:9px;height:9px;border-radius:50%;background:currentColor;margin-right:6px}}
.section-head{{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:26px 0 10px}}
.section-head h2{{margin:0;font-size:19px}} .section-head p{{margin:3px 0 0;color:var(--muted);font-size:12.5px}}
.worker-card{{display:grid;grid-template-columns:1fr auto;gap:10px 20px;align-items:start}}
.worker-card h3{{margin:0;font-size:16px}} .worker-meta{{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px}}
.worker-meta div{{min-width:0;flex:1 1 110px}} .worker-meta strong{{display:block;font-size:17px}}
.activity-strip{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px}}
table{{width:100%;border-collapse:collapse;background:#fff}}
th,td{{padding:11px 12px;border-bottom:1px solid #e6eaee;text-align:left;vertical-align:top}}
th{{background:#f8fafb;font-size:11px;text-transform:uppercase;color:var(--muted);letter-spacing:.2px}}
.pill{{font-weight:750;text-transform:uppercase;font-size:11px}}
code{{font-size:12px;overflow-wrap:anywhere}}
.filters{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px}}
.filters input,.filters select{{padding:9px 10px;border:1px solid #ccd4db;border-radius:8px;background:#fff;min-height:38px}}
.spark{{width:100%;height:78px;color:var(--accent);display:block}}
.bar-row{{min-width:0;display:grid;grid-template-columns:minmax(120px,1.35fr) minmax(100px,3fr) 64px;gap:9px;align-items:center;margin:9px 0;font-size:12px}}
.bar-row > span{{min-width:0;overflow-wrap:anywhere}} .bar-track{{height:9px;background:#e5ebf0;border-radius:999px;overflow:hidden}} .bar-track i{{display:block;height:100%;background:var(--accent);border-radius:999px}}
.not-configured,.needs-source{{color:var(--muted)}} .catalog{{color:var(--accent)}}
.chart-range{{font-size:11px;color:var(--muted);margin-top:2px}}
.delta-up{{color:var(--green)}} .delta-down{{color:var(--warn)}}
.technical summary,.diagnostics summary{{cursor:pointer;font-weight:700;color:var(--accent);padding:4px 0}}
.technical-body{{padding-top:10px}}
.diagnostics{{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow);margin:18px 0}}
.diagnostics > summary{{font-size:15px;color:var(--navy-2)}}
.definition-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}
.definition-group{{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:14px}}
.definition-group h3{{font-size:14px;margin:0 0 10px}}
.definition-list{{display:grid;grid-template-columns:minmax(120px,.8fr) 1.4fr;gap:6px 12px;margin:0}}
.definition-list dt{{font-weight:700;color:var(--muted)}} .definition-list dd{{margin:0;overflow-wrap:anywhere}}
.mobile-nav{{display:none}}
.history-table{{width:100%}}
.flat-note{{padding:20px 4px;color:var(--muted);font-size:13px}}
.mngac-controls{{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:14px}}
.mngac-controls label{{display:grid;gap:4px;font-size:12px;font-weight:700;color:var(--muted)}}
.mngac-controls select,.mngac-controls input{{min-height:40px;padding:8px 10px;border:1px solid #ccd4db;border-radius:8px;background:#fff;font:inherit;color:var(--text)}}
.mngac-layout{{display:grid;grid-template-columns:minmax(360px,1.35fr) minmax(260px,.65fr);gap:16px;align-items:start}}
.mngac-map-panel{{background:var(--soft);border:1px solid var(--line);border-radius:11px;padding:10px;min-width:0}}
.mngac-map{{display:block;width:100%;height:auto;max-height:690px}}
.mngac-county{{fill:#dfe5ea;stroke:#fff;stroke-width:1.2;vector-effect:non-scaling-stroke;cursor:pointer;transition:fill .12s ease,stroke .12s ease,stroke-width .12s ease}}
.mngac-county:hover,.mngac-county:focus{{stroke:#10263b;stroke-width:2.2;outline:none}}
.mngac-county.selected{{stroke:#10263b;stroke-width:3}}
.mngac-detail{{min-height:220px}}
.mngac-detail h3{{margin-bottom:4px}}
.mngac-kpi{{font-size:25px;font-weight:760;letter-spacing:-.3px}}
.mngac-legend{{display:flex;flex-wrap:wrap;gap:7px 12px;margin:10px 0 0;font-size:11px;color:var(--muted)}}
.mngac-legend span{{display:inline-flex;align-items:center;gap:5px}}
.mngac-swatch{{width:13px;height:13px;border-radius:3px;border:1px solid #0002;display:inline-block}}
.mngac-note{{border-left:3px solid var(--accent);padding:10px 12px;background:var(--soft);border-radius:0 8px 8px 0;color:var(--muted);margin:12px 0}}
.mngac-table-wrap{{overflow-x:auto}}
#mngac-fields code{{white-space:nowrap}} .mngac-field-select{{background:none;color:var(--accent);padding:0;border:0;text-align:left;font:inherit;cursor:pointer}} .mngac-field-select:hover{{text-decoration:underline}}
@media(max-width:960px){{
  .primary-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
  .definition-grid{{grid-template-columns:1fr}}
  .mngac-layout{{grid-template-columns:1fr}}
}}
@media(max-width:700px){{
  body{{padding-bottom:68px}}
  header{{height:58px;padding:0 14px;position:sticky;top:0;flex-direction:row}}
  header h1{{font-size:18px}}
  .actions{{font-size:11px;gap:7px}} .actions > span{{display:none}} .refresh-form button{{padding:7px 9px;font-size:11px}}
  .app-shell{{display:block;min-height:auto}}
  .sidebar{{display:none}}
  .pagebar{{top:58px;min-height:46px;padding:7px 12px}}
  .pagebar-title{{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;max-width:calc(100vw - 104px)}}
  .export-menu summary{{padding:6px 8px;font-size:12px}}
  main{{margin:12px auto;padding:0 10px 24px;max-width:100%}}
  .grid,.primary-grid,.worker-grid,.activity-strip{{grid-template-columns:1fr;gap:9px}}
  .card{{padding:13px;border-radius:11px;overflow:visible}}
  .metric{{font-size:24px}}
  .subtext{{font-size:13px}}
  .section-head{{margin:20px 2px 9px;align-items:start}}
  .section-head h2{{font-size:18px}}
  .worker-card{{grid-template-columns:minmax(0,1fr)}} .worker-meta{{gap:10px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}} .worker-meta div:last-child{{grid-column:1/-1}}
  .bar-row{{grid-template-columns:minmax(105px,1.3fr) minmax(80px,2fr) 46px;gap:6px;font-size:11.5px}}
  .spark{{height:82px}}
  .filters{{display:grid;grid-template-columns:1fr;gap:8px}} .filters input,.filters select{{width:100%;min-width:0}}
  #counties thead,#datasets thead,.history-table thead,.contacts-table thead{{display:none}}
  #counties,#counties tbody,#counties tr,#counties td,#datasets,#datasets tbody,#datasets tr,#datasets td,.history-table,.history-table tbody,.history-table tr,.history-table td,.contacts-table,.contacts-table tbody,.contacts-table tr,.contacts-table td{{display:block;width:100%}}
  #counties tr,#datasets tr,.history-table tr,.contacts-table tr{{padding:11px 0;border-bottom:1px solid #e6eaee}}
  #counties td,#datasets td,.history-table td,.contacts-table td{{border:0;padding:4px 2px;white-space:normal;overflow-wrap:anywhere}}
  #counties td:nth-child(2)::before{{content:"Monitoring coverage: ";font-weight:700;color:var(--muted)}}
  #counties td:nth-child(3)::before{{content:"County-direct access: ";font-weight:700;color:var(--muted)}}
  #counties td:nth-child(4)::before{{content:"Statewide open access: ";font-weight:700;color:var(--muted)}}
  #counties td:nth-child(5)::before{{content:"County-direct sources: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(2)::before{{content:"Provider / type: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(3)::before{{content:"Status: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(4)::before{{content:"Records / change: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(5)::before{{content:"Days since change: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(6)::before{{content:"Reliability: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(7)::before{{content:"Response: ";font-weight:700;color:var(--muted)}}
  #datasets td:nth-child(8)::before{{content:"Last success: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(1)::before{{content:"Checked: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(2)::before{{content:"Status: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(3)::before{{content:"Records: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(4)::before{{content:"Changes: ";font-weight:700;color:var(--muted)}}
  .history-table td:nth-child(5)::before{{content:"Response: ";font-weight:700;color:var(--muted)}}
  .contacts-table td:nth-child(2)::before{{content:"Title: ";font-weight:700;color:var(--muted)}}
  .contacts-table td:nth-child(3)::before{{content:"Department: ";font-weight:700;color:var(--muted)}}
  .contacts-table td:nth-child(4)::before{{content:"Phone: ";font-weight:700;color:var(--muted)}}
  .contacts-table td:nth-child(5)::before{{content:"Email: ";font-weight:700;color:var(--muted)}}
  #mngac-fields thead,#county-mngac-fields thead{{display:none}}
  #mngac-fields,#mngac-fields tbody,#mngac-fields tr,#mngac-fields td,#county-mngac-fields,#county-mngac-fields tbody,#county-mngac-fields tr,#county-mngac-fields td{{display:block;width:100%}}
  #mngac-fields tr,#county-mngac-fields tr{{padding:11px 0;border-bottom:1px solid #e6eaee}}
  #mngac-fields td,#county-mngac-fields td{{border:0;padding:4px 2px;white-space:normal;overflow-wrap:anywhere}}
  #mngac-fields td:nth-child(2)::before,#county-mngac-fields td:nth-child(2)::before{{content:"Section: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(3)::before,#county-mngac-fields td:nth-child(3)::before{{content:"Inclusion: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(4)::before{{content:"Source schema: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(5)::before{{content:"Population scan: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(6)::before{{content:"Counties with values: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(7)::before{{content:"Populated records: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(8)::before{{content:"Statewide population: ";font-weight:700;color:var(--muted)}}
  #mngac-fields td:nth-child(9)::before{{content:"County median: ";font-weight:700;color:var(--muted)}}
  #county-mngac-fields td:nth-child(4)::before{{content:"Source schema: ";font-weight:700;color:var(--muted)}}
  #county-mngac-fields td:nth-child(5)::before{{content:"Population scan: ";font-weight:700;color:var(--muted)}}
  #county-mngac-fields td:nth-child(6)::before{{content:"Populated: ";font-weight:700;color:var(--muted)}}
  #county-mngac-fields td:nth-child(7)::before{{content:"Records: ";font-weight:700;color:var(--muted)}}
  #county-mngac-fields td:nth-child(8)::before{{content:"Population: ";font-weight:700;color:var(--muted)}}
  .mngac-controls label,.mngac-controls select{{width:100%}}
  .mngac-map-panel{{padding:6px}}
  .definition-list{{grid-template-columns:1fr;gap:2px}} .definition-list dd{{margin-bottom:8px}}
  .mobile-nav{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));width:100%;position:fixed;bottom:0;left:0;right:0;height:62px;background:var(--navy);border-top:1px solid #ffffff18;z-index:50;padding-bottom:env(safe-area-inset-bottom)}}
  .mobile-nav a{{color:#b9d1e2;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;font-size:10px;font-weight:600}}
  .mobile-nav a:hover{{text-decoration:none;color:#fff}} .mobile-nav .nav-icon{{width:18px;height:18px}}
}}
@media(max-width:480px){{
  .primary-grid{{grid-template-columns:1fr}}
  .bar-row{{grid-template-columns:100px minmax(60px,1fr) 40px}}
}}
</style></head><body>
<a class="skip-link" href="#main-content">Skip to content</a><header><h1>GIS Data Watchtower</h1><div class="actions"><span>{_esc(refresh_label)}</span>{refresh_form}{'<button type="button" id="refresh-pause" aria-pressed="false">Pause automatic refresh</button>' if auto_refresh else ''}</div></header>
<div class="app-shell">
<aside class="sidebar"><div class="side-brand"><strong>ClearParcel</strong><small>GIS Data Watchtower</small></div><nav>
<a href="/">{icon("overview")}<span>Overview</span></a>
<a href="/counties">{icon("counties")}<span>Minnesota Counties</span></a>
<a href="/mngac">{icon("mngac")}<span>MN GAC Completeness</span></a>
<a href="/#datasets">{icon("sources")}<span>Data Sources</span></a>
<a href="/#changes">{icon("changes")}<span>Recent Changes</span></a>
<a href="/#alerts">{icon("alerts")}<span>Alerts</span></a>
<a href="/snapshot.xlsx">{icon("export")}<span>Export</span></a>
</nav><div class="side-note">{side_context}<br><small>Central Time primary</small></div></aside>
<section class="content-shell">
<div class="pagebar"><div class="pagebar-title">{_esc(page_title)}</div><div class="page-actions"><details class="export-menu"><summary>Export</summary><div class="export-pop"><a href="/snapshot.xlsx">Excel (.xlsx)</a><a href="/county-profiles.csv">County profiles (CSV)</a><a href="/parcel-sources.csv">Parcel sources (CSV)</a><a href="/snapshot.csv">Monitored sources (CSV)</a><a href="/snapshot.json">JSON</a></div></details></div></div>
<main id="main-content">{body}</main>
</section></div>
<nav class="mobile-nav" aria-label="Mobile navigation">
<a href="/">{icon("overview")}<span>Overview</span></a><a href="/counties">{icon("counties")}<span>Counties</span></a><a href="/mngac">{icon("mngac")}<span>MN GAC</span></a><a href="/#datasets">{icon("sources")}<span>Sources</span></a><a href="/snapshot.xlsx">{icon("export")}<span>Export</span></a>
</nav>
</body></html>"""
