import os
import unittest
import html
import json
import subprocess
import shutil
import re
from clearparcel.datawatch.county_profile_panel import render_county_profile_body, render_county_profile_panel, profile_time

# CI sets WATCHTOWER_REQUIRE_NODE=1 so these tests fail instead of silently skipping.
NODE_AVAILABLE = bool(shutil.which('node')) or os.environ.get('WATCHTOWER_REQUIRE_NODE') == '1'


class CountyProfilePanelTests(unittest.TestCase):
    @unittest.skipUnless(NODE_AVAILABLE, 'Inline async behavior requires Node.js')
    def test_inline_selection_races_cache_revision_retry_and_failure(self):
        from clearparcel.datawatch.county_profile_panel import render_inline_county_panel
        script = re.search(r'<script[^>]*>(.*?)</script[^>]*>', render_inline_county_panel(revision='old'), re.S | re.I).group(1)
        harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const content={nodes:[],attrs:{},replaceChildren(...nodes){this.nodes=nodes},setAttribute(k,v){this.attrs[k]=v}},status={textContent:''};
const graphics=new Map(),graphic=id=>{if(!graphics.has(id))graphics.set(id,{attrs:{},textContent:'',style:{values:{},setProperty(k,v){this.values[k]=v}},classList:{values:{},toggle(k,v){this.values[k]=v}},setAttribute(k,v){this.attrs[k]=v}});return graphics.get(id)};
let calls=[],pending=[];
const store=new Map(),sessionStorage={getItem:k=>store.has(k)?store.get(k):null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)};
const location={pathname:'/',search:'',reloads:0,reload(){this.reloads++}};
const context={AbortController,setTimeout,clearTimeout,Map,encodeURIComponent,window:{},location,sessionStorage,Date,Number,String,
 document:{getElementById:id=>id==='home-county-profile'?content:id==='home-county-profile-status'?status:graphic(id),querySelector:()=>({dataset:{contentRevision:'old'}})},
 DOMParser:class{parseFromString(id){const profile={id,children:[],cloneNode(){return{id,children:this.children}}};for(const tagName of ['H2','P','DIV','SECTION','SECTION','SECTION','SECTION','SECTION','SECTION','P']){const node={tagName,remove(){profile.children=profile.children.filter(n=>n!==this)}};profile.children.push(node)}return{querySelector:()=>profile}}},
 fetch:(url,options)=>{calls.push({url,options});return new Promise(resolve=>pending.push(resolve))}};
vm.createContext(context);vm.runInContext(SCRIPT,context);
const response=(id,status=200)=>({status,ok:status===200,text:async()=>id,json:async()=>({content_revision:'new'})});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const first=context.window.watchtowerCountyPane.load('dakota',{pct:0,all_pct:100,fields:37,field_count:91});
 assert.equal(graphic('county-coverage-mandatory-value').textContent,'0.00%');
 assert.equal(graphic('county-coverage-mandatory').classList.values.unavailable,false);
 assert.equal(graphic('county-coverage-all').style.values['--coverage'],'100%');
 assert.equal(graphic('county-field-coverage-value').textContent,'37 / 91');
 assert.equal(graphic('county-field-coverage-fill').style.values['--coverage'],(37/91*100)+'%');
 const second=context.window.watchtowerCountyPane.load('rice');
 assert.equal(graphic('county-coverage-mandatory-value').textContent,'Unavailable');
 assert.equal(graphic('county-coverage-mandatory').classList.values.unavailable,true);
 assert.equal(graphic('county-field-coverage-value').textContent,'Unavailable');
 assert.equal(calls[0].options.signal.aborted,true);
 pending[1](response('rice'));await second;
 pending[0](response('dakota'));await first;
 assert.equal(content.nodes[0].id,'rice');assert.equal(content.attrs['aria-busy'],'false');
 assert.deepEqual(content.nodes[0].children.map(n=>n.tagName),['DIV']);
 const count=calls.length;await context.window.watchtowerCountyPane.load('rice');assert.equal(calls.length,count);
 // The page's charts belong to revision old; a 409 means the county changed
 // in a newer publication. Never show that fragment beside the old charts.
 let saved=0;context.window.watchtowerRefresh={paused:()=>false,save(){saved++}};
 const retry=context.window.watchtowerCountyPane.load('douglas',{pct:20,all_pct:20,fields:10,field_count:91});
 pending[2](response('',409));await retry;
 assert.equal(calls.length,3);assert.equal(location.reloads,1);assert.equal(saved,1);
 assert.equal(content.nodes.length,0);assert.match(status.textContent,/Loading newer observations/);
 assert.equal(graphic('county-coverage-all-value').textContent,'20.00%');
 // A second 409 soon after cannot loop reloads; the reader is asked instead.
 const again=context.window.watchtowerCountyPane.load('douglas',{pct:20,all_pct:20,fields:10,field_count:91});
 pending[3](response('',409));await again;
 assert.equal(location.reloads,1);assert.equal(content.nodes.length,0);
 assert.match(status.textContent,/Newer observations were published/);
 // Paused refresh is respected: no automatic reload.
 store.clear();context.window.watchtowerRefresh={paused:()=>true,save(){saved++}};
 const paused=context.window.watchtowerCountyPane.load('wright');pending[4](response('',409));await paused;
 assert.equal(location.reloads,1);assert.match(status.textContent,/Reload the page/);
 const failure=context.window.watchtowerCountyPane.load('aitkin');assert.equal(content.nodes.length,0);
 pending[5](response('',503));await failure;assert.match(status.textContent,/temporarily unavailable/);
 assert.equal(content.nodes.length,0);assert.equal(content.attrs['aria-busy'],'false');
 const clearing=context.window.watchtowerCountyPane.load('sibley');
 assert.equal(typeof context.window.watchtowerCountyPane.clear,'function');
 context.window.watchtowerCountyPane.clear();
 assert.equal(calls[6].options.signal.aborted,true);
 assert.equal(content.nodes.length,0);assert.equal(status.textContent,'');
 assert.equal(content.attrs['aria-busy'],'false');
 assert.equal(graphic('home-county-infographics').hidden,true);
 pending[6](response('sibley'));await clearing;
 assert.equal(content.nodes.length,0);assert.equal(status.textContent,'');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run(['node', '-e', harness.replace('SCRIPT', json.dumps(script))],
                                capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(NODE_AVAILABLE, 'Dialog async behavior requires Node.js')
    def test_dialog_fetch_is_bounded_cancelled_and_single_revision(self):
        script = re.search(r'<script[^>]*>(.*?)</script[^>]*>', render_county_profile_panel({}, revision='old'), re.S | re.I).group(1)
        harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const listeners=(target)=>{target.handlers={};target.addEventListener=(type,fn)=>{(target.handlers[type]||=[]).push(fn)};target.fire=(type,event={})=>(target.handlers[type]||[]).forEach(fn=>fn(event));return target};
const dialog=listeners({open:false,scrollTop:0,showModal(){this.open=true},close(){this.open=false;this.fire('close')},querySelectorAll:()=>[]});
const content={nodes:[],textContent:'',replaceChildren(...nodes){this.nodes=nodes;this.textContent=''},append(...nodes){this.nodes.push(...nodes)}};
Object.defineProperty(content,'text',{get(){return this.textContent}});
const close=listeners({focus(){}});
const counties=['dakota','rice'].map(slug=>listeners({dataset:{slug},focus(){}}));
const timers=[];let calls=[],pending=[];
const store=new Map(),sessionStorage={getItem:k=>store.has(k)?store.get(k):null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)};
const location={pathname:'/mngac',search:'',reloads:0,reload(){this.reloads++}};
let holds=[];
const context={AbortController,Map,encodeURIComponent,Date,Number,String,location,sessionStorage,
 setTimeout:(fn,ms)=>{timers.push({fn,ms,live:true});return timers.length-1},clearTimeout:id=>{if(timers[id])timers[id].live=false},
 window:{scrollY:0,scrollTo(){},watchtowerRefresh:{suspend:r=>holds.push(r),release:r=>{holds=holds.filter(x=>x!==r)},paused:()=>false,save(){}}},
 document:{getElementById:id=>id==='county-profile-dialog'?dialog:id==='county-profile-content'?content:close,
  querySelectorAll:sel=>sel==='.mngac-county'?counties:[],querySelector:()=>({dataset:{contentRevision:'old'}}),
  createElement:()=>({href:'',textContent:''})},
 DOMParser:class{parseFromString(id){return{querySelector:()=>({}),body:{childNodes:[{id,cloneNode(){return{id}}}]}}}},
 fetch:(url,options)=>{calls.push({url,options});return new Promise((resolve,reject)=>{pending.push(resolve);options?.signal?.addEventListener('abort',()=>reject(new Error('aborted')))})}};
vm.createContext(context);vm.runInContext(SCRIPT,context);
const response=(id,status=200)=>({status,ok:status===200,text:async()=>id});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const open=i=>{counties[i].fire('click');return flush()};
(async()=>{
 // A request that never resolves hits the deadline and shows the unavailable state.
 await open(0);assert.equal(dialog.open,true);assert.deepEqual(holds,['county-dialog']);
 assert.match(calls[0].url,/revision=old/);assert.equal(content.textContent,'Loading county profile…');
 timers.filter(t=>t.live&&t.ms===15000).forEach(t=>t.fn());await flush();await flush();
 assert.equal(calls[0].options.signal.aborted,true);
 assert.match(content.textContent,/temporarily unavailable/);
 // Closing while loading aborts the request and releases refresh.
 await open(1);dialog.close();await flush();
 assert.equal(calls[1].options.signal.aborted,true);assert.deepEqual(holds,[]);
 // Rapid reopen aborts the earlier request; its late answer is ignored.
 await open(0);await open(1);
 assert.equal(calls[2].options.signal.aborted,true);
 pending[3](response('rice'));await flush();await flush();
 assert.equal(content.nodes[0].id,'rice');
 pending[2](response('dakota'));await flush();assert.equal(content.nodes[0].id,'rice');
 // A 409 never fetches or shows a newer revision beside the old page; it reloads once
 // and reopens this county afterwards.
 dialog.close();await open(0);pending[4](response('',409));await flush();await flush();
 assert.equal(calls.length,5);assert.equal(location.reloads,1);
 assert.equal(store.get('watchtower-reopen-county:/mngac'),'dakota');
 assert.equal(content.textContent,'Loading newer observations…');
 dialog.close();await open(0);pending[5](response('',409));await flush();await flush();
 assert.equal(location.reloads,1);assert.match(content.textContent,/Newer observations were published/);
 // After the reload the stored county reopens once.
 dialog.close();calls=[];vm.runInContext(SCRIPT,context);await flush();
 assert.equal(dialog.open,true);assert.match(calls[0].url,/slug=dakota/);
 assert.equal(store.has('watchtower-reopen-county:/mngac'),false);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run(['node', '-e', harness.replace('SCRIPT', json.dumps(script))],
                                capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dates_preserve_calendar_and_central_dst(self):
        self.assertEqual(profile_time('2026-10-06'), '2026-10-06')
        self.assertEqual(profile_time('2026-01-06T12:00:00+00:00'), '2026-01-06 06:00 CST')
        self.assertEqual(profile_time('2026-07-06T12:00:00+00:00'), '2026-07-06 07:00 CDT')
    def test_panel_escapes_payload_and_links(self):
        profile={'county': {'name': '</script><img src=x>', 'slug':'test'}, 'monitoring':{}, 'access':{}, 'research':{}, 'comments':[]}
        body=render_county_profile_body(profile)
        self.assertNotIn('<img', body)
        self.assertIn('Not available', body)
        self.assertNotIn('Comments', body)
        page=render_county_profile_panel({'test':profile})
        self.assertNotIn('id="county-profile-data"', page)
        self.assertNotIn('</script><img', page)
        for name in ('MN GAC Public Parcels','MnGeo Public County Repository','County ArcGIS REST','County Website Download'):
            self.assertIn(name, body)

    def test_labels_keep_dates_and_counts_source_specific(self):
        source={'name':'Two products', 'feature_count':0, 'provider_updated_at':'2026-01-02', 'county_acquired_at':'2026-02-03', 'catalog_refreshed_at':'2026-03-04', 'checked_at':'2026-04-05', 'last_success_at':'2026-05-06', 'approved_public_links':[{'href':'https://example.com/product','label':'Product'}, {'href':'javascript:alert(1)','label':'Unsafe'}]}
        profile={'county':{'name':'Test','slug':'test'}, 'county_download':{'sources':[source]}, 'research':{'review_date':'2026-06-07'}, 'comments':['A supported comment']}
        body=render_county_profile_body(profile)
        for label in ('Provider update', 'MnGeo acquisition','County metadata publication','Catalog refresh','Watchtower check','Successful observation','Research review','Feature count','Research notes'):
            self.assertIn(label, body)
        self.assertIn('<dd>0</dd>',body)
        self.assertIn('target="_blank" rel="noopener"',body)
        self.assertNotIn('javascript:',body)
        self.assertIn('2026-01-02',body)
    def test_county_panel_sections_are_metric_independent(self):
        from clearparcel.datawatch.dashboard import _county_profiles
        from clearparcel.datawatch.parcel_access import load_parcel_access
        profiles=_county_profiles({}, {}, load_parcel_access())
        page=render_county_profile_panel(profiles)
        self.assertIn('opener?.focus({preventScroll:true})',page)
        self.assertIn("dialog.addEventListener('close'",page)
        self.assertIn("event.key!=='Tab'",page)
        self.assertIn('max-height:90dvh',page)
        self.assertIn('overflow-wrap:anywhere',page)
        self.assertIn("window.watchtowerRefresh?.suspend('county-dialog')",page)
        self.assertNotIn('innerHTML',page)
        self.assertEqual(page.count('<template data-profile='),87)

    @unittest.skipUnless(NODE_AVAILABLE, "JavaScript boundary execution requires Node.js")
    def test_percentage_class_boundaries_and_legend_match_emitted_javascript(self):
        from clearparcel.datawatch.county_profile_panel import percentage_color_js, PERCENT_COLORS, NO_DATA_FILL
        values = [0, 0.001, 29.999, 30, 30.001, 49.999, 50, 50.001,
                  69.999, 70, 70.001, 100, None, "", "30", -1, 101]
        expected = [PERCENT_COLORS[i] for i in [0, 0, 0, 1, 1, 1, 2, 2,
                    2, 2, 3, 3]] + [NO_DATA_FILL] * 5
        script = percentage_color_js() + "\nconsole.log(JSON.stringify(" + json.dumps(values) + ".map(percentageColor).concat([percentageColor(undefined),percentageColor(NaN),percentageColor(Infinity),percentageColor(-Infinity)])))"
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), expected + [NO_DATA_FILL] * 4)
        self.assertEqual(result.stderr, "")
    def test_percentage_legend_classes_and_palette(self):
        from clearparcel.datawatch.county_profile_panel import percentage_legend, PERCENT_COLORS
        legend = html.unescape(percentage_legend())
        self.assertEqual(PERCENT_COLORS, ["#30506f", "#4583b3", "#7cbedf", "#c9edf5"])
        self.assertEqual(legend.count('class="mngac-swatch'), 5)
        self.assertIn('role="group"', legend)
        self.assertIn('class="mngac-swatch pct-no-data-swatch" style="background-color:#151d2b" aria-hidden="true"></i>No data</span>', legend)
        for color, label in zip(PERCENT_COLORS, ["<30%", "30% - 50%", "50% - 70%", ">70%"]):
            self.assertIn(f'background-color:{color}" aria-hidden="true"></i>{label}</span>', legend)

    def test_adjacent_percentage_classes_have_usable_contrast(self):
        from clearparcel.datawatch.county_profile_panel import PERCENT_COLORS

        def luminance(color):
            channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        for darker, lighter in zip(PERCENT_COLORS, PERCENT_COLORS[1:]):
            ratio = (luminance(lighter) + 0.05) / (luminance(darker) + 0.05)
            self.assertGreaterEqual(ratio, 1.6, (darker, lighter))
