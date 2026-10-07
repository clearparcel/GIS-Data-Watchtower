"""Shared refresh controller: user intent is separate from reading suppression."""


def refresh_script(seconds: int, *, public: bool = False) -> str:
    if not seconds:
        return ""
    return '<script>\n' + _SCRIPT.replace('__DELAY__', str(int(seconds) * 1000)).replace('__PUBLIC__', 'true' if public else 'false') + '\n</script>'


_SCRIPT = r"""
(function(){
const delay=__DELAY__,isPublic=__PUBLIC__,key='watchtower-view:'+location.pathname+location.search;
const ids=['q','cat','health','cq','cs','mngac-metric','mngac-county-select','mngac-q','mngac-inclusion','cmq','cmi','overview-metric','overview-county-select','gap-standard'];
let timer=null,userPaused=false,revision=null,etag=null,busy=false,lastSummary=null;
const holds=new Set();
function save(){const values={userPaused,scroll:window.scrollY};ids.forEach(id=>{const el=document.getElementById(id);if(el)values[id]=el.value});values.focus=document.activeElement?.id||'';values.focusCounty=document.activeElement?.dataset?.slug||'';try{sessionStorage.setItem(key,JSON.stringify(values))}catch(e){}}
function restore(){try{const values=JSON.parse(sessionStorage.getItem(key)||'{}');userPaused=values.userPaused===true;ids.forEach(id=>{const el=document.getElementById(id);if(el&&values[id]!==undefined){el.value=values[id];el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}))}});if(values.focus)document.getElementById(values.focus)?.focus({preventScroll:true});else if(values.focusCounty)[...document.querySelectorAll('.mngac-county')].find(p=>p.dataset.slug===values.focusCounty)?.focus({preventScroll:true});if(Number.isFinite(values.scroll))window.scrollTo(0,values.scroll)}catch(e){}}
function reading(){return holds.size>0||document.getElementById('county-profile-dialog')?.open||!!document.querySelector('.profile-evidence[open]')||!!document.querySelector('.public-export[open]')}
function label(){const button=document.getElementById('refresh-pause');if(button){button.textContent=userPaused?'Resume automatic refresh':'Pause automatic refresh';button.setAttribute('aria-pressed',String(userPaused))}}
function schedule(){clearTimeout(timer);timer=null;label();if(!userPaused&&!document.hidden&&!holds.size)timer=setTimeout(tick,delay)}
function relative(value){const stamp=Date.parse(value);if(!Number.isFinite(stamp))return 'Unavailable';const seconds=Math.max(0,Math.floor((Date.now()-stamp)/1000));if(seconds<60)return 'Just now';const minutes=Math.floor(seconds/60);if(minutes<60)return minutes+' min ago';const hours=Math.floor(minutes/60);return hours<48?hours+' hr ago':Math.floor(hours/24)+' days ago'}
function publication(summary){const badge=document.querySelector('[data-age-kind="publication"]');if(badge)badge.dataset.ageTime=summary.public_published_at||'';const publicationTime=document.getElementById('public-publication-time');if(publicationTime)publicationTime.textContent=summary.public_published_at?new Date(summary.public_published_at).toLocaleString('en-US',{timeZone:'America/Chicago',timeZoneName:'short'}):'Unavailable';document.querySelectorAll('[data-age-time]').forEach(node=>node.textContent=relative(node.dataset.ageTime));document.querySelectorAll('[data-worker-report]').forEach(node=>{const worker=summary.workers?.[node.dataset.workerReport];if(!worker)return;const stamp=Date.parse(worker.last_report_at||worker.checked_at);const limit=(summary.thresholds?.worker_stale_minutes||1560)*60000;const reporting=!Number.isFinite(stamp)?'Report time unavailable':Date.now()-stamp>limit?'Reporting overdue':'Reporting on time';const health={ok:'Healthy',warn:'Warning',error:'Error'}[worker.overall]||'Unknown';node.textContent=health+' · '+reporting});const target=document.getElementById('public-publication-status');if(target){const time=summary.public_published_at;const parsed=Date.parse(time);const age=Number.isFinite(parsed)?Math.max(0,Math.floor((Date.now()-parsed)/1000)):null;const limit=summary.thresholds?.publication_max_age_seconds||1800;target.textContent='Public publication reporting: '+(age===null?'Unknown':age>limit?'Overdue':'Current')+' · '+(time?new Date(time).toLocaleString():'Unavailable');target.title=time||''}const sourceTarget=document.getElementById('source-reporting-status');if(sourceTarget){const limit=(summary.thresholds?.source_stale_minutes||1560)*60*1000;let overdue=0,missing=0;Object.values(summary.source_observations||{}).forEach(source=>{const t=Date.parse(source.checked_at);if(!Number.isFinite(t))missing++;else if(Date.now()-t>limit)overdue++});sourceTarget.textContent='Source reporting: '+overdue+' overdue · '+missing+' without a check time. Provider check age is separate from publication age.'}}
async function tick(){timer=null;if(userPaused||document.hidden||busy){schedule();return}busy=true;try{
 if(!isPublic){if(!reading()){save();location.reload()}return}
 const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),10000);
 let response;try{response=await fetch('/api/summary',{headers:etag?{'If-None-Match':etag}:{},cache:'no-cache',signal:controller.signal})}finally{clearTimeout(deadline)}
 if(response.status===304){if(lastSummary){publication(lastSummary);if(lastSummary.content_revision!==revision&&!userPaused&&!document.hidden&&!reading()){save();location.reload()}}return;}if(!response.ok)throw new Error('summary unavailable');
 const summary=await response.json();if(summary.schema_version!==1||typeof summary.content_revision!=='string')throw new Error('invalid summary');
 etag=response.headers.get('ETag');lastSummary=summary;publication(summary);
 if(revision===null){revision=summary.content_revision;window.watchtowerContentRevision=revision}
 else if(summary.content_revision!==revision&&!userPaused&&!document.hidden&&!reading()){save();location.reload()}
 const status=document.getElementById('refresh-status');if(status)status.textContent=summary.refresh_failed?'Storage refresh unavailable; showing cached observations.':'';
 }catch(e){const status=document.getElementById('refresh-status');if(status)status.textContent='Refresh unavailable; showing the last loaded observations.';etag=null}
 finally{busy=false;schedule()}}
function pause(){userPaused=true;save();schedule()}
function resume(){userPaused=false;save();schedule()}
function suspend(reason='dialog'){holds.add(reason);schedule()}
function release(reason='dialog'){holds.delete(reason);schedule()}
window.watchtowerRefresh={pause,resume,suspend,release,save};
document.addEventListener('DOMContentLoaded',()=>{revision=document.querySelector('[data-content-revision]')?.dataset.contentRevision||null;window.watchtowerContentRevision=revision;restore();document.getElementById('refresh-pause')?.addEventListener('click',()=>userPaused?resume():pause());ids.forEach(id=>{const el=document.getElementById(id);el?.addEventListener(el.tagName==='SELECT'?'change':'input',save)});schedule()});
document.addEventListener('visibilitychange',schedule);window.addEventListener('pagehide',save);
})();
"""
