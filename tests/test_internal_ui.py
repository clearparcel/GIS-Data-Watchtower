"""Synthetic internal UI, saved-evidence and private-route regressions."""
import contextlib
import copy
import csv
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.aggregate import merge_states
from clearparcel.datawatch.dashboard_activity import change_events, render_change_list, source_snapshot, MAX_CHANGES
from clearparcel.datawatch.dashboard_source import measurement
from clearparcel.datawatch.dashboard_terms import render_terms_body


class InternalUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        self.source = {"name": "Invented source", "status": "error", "category": "Imagery", "provider": "Invented provider",
                       "worker": "cloud", "checked_at": self.stamp, "last_success_at": "2026-01-01T12:00:00Z",
                       "error": '<script>failure</script>', "feature_count": 0,
                       "url": "https://example.org/private?token=synthetic-secret",
                       "changes": [{"type": "feature_count", "previous": 2, "current": 0}]}
        self.state = {"generated_at": self.stamp, "overall": "error", "counts": {"error": 1},
                      "workers": {"cloud": {"last_report_at": self.stamp, "overall": "error"}},
                      "sources": {"sample": self.source}}
        self.config = {"_render_state": self.state, "state_file": str(Path(self.tmp.name) / "unused.json"),
                       "history_file": str(Path(self.tmp.name) / "history.jsonl"), "sources": []}

    def test_change_evidence_deduplicates_the_same_source_check(self):
        run = {"generated_at": self.stamp, "sources": {"sample": copy.deepcopy(self.source)}}
        later = {**run, "generated_at": "2099-01-01T00:00:00Z"}
        events = change_events(self.config, self.state, history=[run, later, {"sources": []}])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["observed_at"], self.stamp)
        html = render_change_list(events)
        self.assertIn('<dt>Previous</dt><dd>2</dd>', html)
        self.assertIn('<dt>Current</dt><dd>0</dd>', html)
        self.assertIn('/source?id=sample#change-', html)
        self.assertNotIn('synthetic-secret', html)

    def test_retired_sources_are_not_broken_links_and_changes_are_bounded(self):
        source = {**self.source, "changes": [{"type": "tracked_value", "key": str(i), "current": i} for i in range(MAX_CHANGES + 2)]}
        events = change_events(self.config, {"sources": {}}, history=[{"generated_at": self.stamp, "sources": {"old": source}}])
        self.assertEqual(len(events), MAX_CHANGES)
        html = render_change_list(events[:1])
        self.assertIn('No longer monitored', html)
        self.assertNotIn('/source?id=old', html)

    def test_failure_is_readable_and_irrelevant_parcel_measurements_are_absent(self):
        before = copy.deepcopy(self.state)
        page = dashboard.render_source(self.config, "sample")
        self.assertIn('&lt;script&gt;failure&lt;/script&gt;', page)
        self.assertNotIn('<script>failure</script>', page)
        self.assertIn('Latest check attempt', page)
        self.assertIn('Last successful check', page)
        self.assertIn('id="source-technical"', page)
        self.assertNotIn('<h2>Parcel checks</h2>', page)
        self.assertNotIn('Not checked%', page)
        self.assertIn('This source', page)
        self.assertIn('/source-snapshot.csv?id=sample', page)
        self.assertEqual(before, self.state)

    def test_measurements_preserve_zero_and_do_not_append_units_to_missing_values(self):
        for value in (None, True, '0', float('nan'), float('inf')):
            self.assertEqual(measurement(value, '%'), 'Not checked')
        self.assertEqual(measurement(0, '%'), '0%')
        self.assertEqual(measurement(15.25, '%'), '15.25%')

    def test_record_count_observation_time_survives_a_quality_failure(self):
        first = '2026-11-05T12:00:00Z'
        latest = '2026-11-06T12:00:00Z'
        state = {}
        for stamp, count, status, problems in ((first, 100, 'ok', []),
                                               (latest, 90, 'error', ['Required field missing'])):
            source = {'name': 'Invented source', 'status': status, 'feature_count': count,
                      'checked_at': stamp, 'problems': problems}
            report = {'generated_at': stamp, 'overall': status, 'sources': {'sample': source}}
            state = merge_states(state, report, 'cloud')
        self.assertEqual(state['sources']['sample']['last_success_at'], first)
        page = dashboard.render_source({**self.config, '_render_state': state}, 'sample')
        observed = page.split('<dt>Record count observed</dt><dd>', 1)[1].split('</dd>', 1)[0]
        self.assertIn(latest.replace('Z', '+00:00'), observed)
        self.assertNotIn(first.replace('Z', '+00:00'), observed)
        self.assertIn('>90</div>', page)

    def test_retained_or_unmeasured_counts_have_no_invented_observation_time(self):
        cases = [
            {'status': 'error', 'error': 'Request failed'},
            {'status': 'error', 'rate_limited': True},
            {'status': 'ok', 'deferred': {'reason': 'provider-rate-limit'}},
            {'status': 'unknown'},
            {'status': 'ok', 'feature_count': None},
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                src = {**self.source, 'error': None, 'category': 'Parcels', **extra}
                state = {**self.state, 'sources': {'sample': src}}
                page = dashboard.render_source({**self.config, '_render_state': state}, 'sample')
                observed = page.split('<dt>Record count observed</dt><dd>', 1)[1].split('</dd>', 1)[0]
                self.assertEqual(observed, 'Unavailable')

    def test_attention_precedes_sources_and_navigation_has_all_destinations(self):
        page = dashboard.render_dashboard(self.config)
        main = page.split('<main ', 1)[1]
        self.assertLess(main.index('id="alerts"'), main.index('id="datasets"'))
        self.assertIn('/source?id=sample#source-status', main)
        self.assertIn('id="refresh-status" role="status"', main)
        mobile = page.split('aria-label="Mobile navigation"', 1)[1]
        for path in ('/terms', '/changes', '/alerts', '/downloads', '/sources'):
            self.assertIn(f'href="{path}"', mobile)
        self.assertIn('id="mobile-more"', mobile)
        self.assertIn('Internal · view only', page)
        self.assertIn('provider checks run separately', page)
        self.assertIn('Build ', page)
        self.assertIn('data-search="invented source sample invented provider imagery cloud"', page)

    def test_scoped_exports_use_exact_identity_and_an_allowlist(self):
        self.state['sources']['sample-extra'] = {**self.source, 'name': 'Must not appear'}
        snapshot = source_snapshot(self.config, 'sample')
        self.assertEqual(len(snapshot['sources']), 1)
        self.assertEqual(snapshot['sources'][0]['id'], 'sample')
        self.assertEqual(snapshot['sources'][0]['feature_count'], 0)
        raw = json.dumps(snapshot)
        for private in ('synthetic-secret', '<script>', 'Must not appear', 'https://example.org'):
            self.assertNotIn(private, raw)
        self.assertIsNone(source_snapshot(self.config, 'sam'))
        self.source['name'] = '=SYNTHETIC()'
        snapshot = source_snapshot(self.config, 'sample')
        row = next(csv.DictReader(io.StringIO(dashboard._snapshot_csv(snapshot))))
        self.assertEqual(row['source_name'], "'=SYNTHETIC()")
        self.assertEqual(row['feature_count'], '0')
        self.assertTrue(row['snapshot_created_utc'])
        self.assertEqual(row['watchtower_last_checked_utc'], self.stamp)
        with zipfile.ZipFile(io.BytesIO(dashboard._snapshot_xlsx(snapshot))) as workbook:
            self.assertIn('Export details', workbook.read('xl/workbook.xml').decode())

    def handler(self):
        captured = {}
        class Server:
            def __init__(self, address, handler, **kwargs): captured['handler'] = handler
            def serve_forever(self): pass
            def server_close(self): pass
        with patch.object(dashboard, '_BoundedThreadingHTTPServer', Server), \
             patch.object(dashboard, '_dashboard_auth', return_value=('synthetic-password', 'user')), \
             contextlib.redirect_stdout(io.StringIO()):
            dashboard.serve(self.config, read_only=True)
        handler = object.__new__(captured['handler'])
        statuses, headers = [], {}
        handler.headers, handler.wfile = {}, io.BytesIO()
        handler.send_response = statuses.append
        handler.send_header = lambda k, v: headers.__setitem__(k, v)
        handler.end_headers = lambda: None
        return handler, statuses, headers

    def test_new_routes_preserve_authentication_and_read_only_hosting(self):
        handler, statuses, headers = self.handler()
        paths = ['/sources', '/changes', '/alerts', '/downloads',
                 '/source-snapshot.json?id=sample', '/source-snapshot.csv?id=sample', '/source-snapshot.xlsx?id=sample']
        for path in paths:
            with self.subTest(path=path):
                handler.path, handler.wfile = path, io.BytesIO()
                handler.do_GET()
                self.assertEqual(statuses[-1], 401)
                with patch.object(type(handler), '_authorized', return_value=True), \
                     patch.object(dashboard, 'check_sources', side_effect=AssertionError('No polling')):
                    handler.do_GET()
                    self.assertEqual(statuses[-1], 200)
                    handler.do_POST()
                    self.assertEqual(statuses[-1], 405)
                    self.assertEqual(headers['Allow'], 'GET')
        with patch.object(type(handler), '_authorized', return_value=True):
            handler.path = '/source-snapshot.json?id=sam'
            handler.do_GET()
            self.assertEqual(statuses[-1], 404)

    def test_terms_filters_cover_actions_without_changing_monitoring_decisions(self):
        provider = {'name': 'Invented County', 'terms_stopped': True, 'latest_outcome': 'full',
                    'crm_url': 'https://crm.example.test/organizations/invented',
                    'open_inquiry': {'stage': 'awaiting-reply', 'purposes': ['watchtower-monitoring']},
                    'watchtower_gate_url': 'https://github.com/clearparcel/GIS-Data-Watchtower/issues/1'}
        page = render_terms_body({'status': {'providers': [provider]}, 'fetched_at': self.stamp})
        for text in ('terms-q', 'terms-status', 'terms-clear', 'data-actions="no-date stopped open"',
                     'Review monitoring decision', 'Recorded scope: full', 'do not change Watchtower monitoring permission'):
            self.assertIn(text, page)
        self.assertIn('https://crm.example.test/organizations/invented', page)
        disconnected = render_terms_body(None)
        self.assertLess(disconnected.index('Administrator setup details'), disconnected.index('WATCHTOWER_CRM_TERMS_URL'))
        cached = render_terms_body({'status': {'providers': []}, 'fetched_at': self.stamp, 'last_error': '<bad>'})
        self.assertIn('Showing a saved CRM copy', cached)
        self.assertIn('&lt;bad&gt;', cached)

    def test_refresh_holds_reading_and_restores_details_filters_and_focus(self):
        if not shutil.which('node') and os.environ.get('WATCHTOWER_REQUIRE_NODE') != '1':
            self.skipTest('Node required for executable refresh-controller regression')
        from clearparcel.datawatch.dashboard_refresh import _SCRIPT
        harness = r"""
const assert=require('node:assert/strict');const nodes={},events={},timers=new Map(),store=new Map();let id=0,reloads=0;
function node(tag,id=''){const n={tagName:tag,id,dataset:{},open:false,value:'',children:[],listeners:{},textContent:'',
 addEventListener(k,f){this.listeners[k]=f},dispatchEvent(e){this.listeners[e.type]?.(e)},
 append(child){this.children.push(child);if(child&&typeof child==='object'){child.parent=this;if(child.id)nodes[child.id]=child}},
 focus(){document.activeElement=this},matches(s){return this.tagName==='INPUT'},closest(s){return s==='#reading-update'&&this.parent?.id==='reading-update'?this.parent:null},getAttribute(){return null}};if(id)nodes[id]=n;return n}
const q=node('INPUT','q'),detail=node('DETAILS','source-technical'),summary=node('SUMMARY','technical-summary'),status=node('DIV','refresh-status');
global.window={scrollY:123,scrollTo(){},addEventListener(){}};global.location={pathname:'/sources',search:'',reload(){reloads++}};
global.sessionStorage={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)};
global.document={hidden:false,activeElement:q,getElementById:id=>nodes[id]||null,createElement:tag=>node(tag.toUpperCase()),
 querySelector:q=>q==='details[open]'&&detail.open?detail:null,
 querySelectorAll:selector=>selector.startsWith('details')?[detail]:selector==='[data-refresh-key]'?[q,summary]:[],addEventListener:(k,f)=>events[k]=f};
global.setTimeout=(fn,delay)=>{timers.set(++id,{fn,delay});return id};global.clearTimeout=id=>timers.delete(id);
"""
        scenario = r"""
(async()=>{events.DOMContentLoaded();q.value='invented';detail.open=true;window.watchtowerRefresh.save();
async function tick(){const [id,t]=[...timers].find(([id,t])=>t.delay===30000);timers.delete(id);await t.fn()}
await tick();assert.equal(reloads,0);const notice=nodes['reading-update'];assert.ok(notice);
const button=notice.children.find(n=>n.tagName==='BUTTON');document.activeElement=button;button.listeners.click();assert.equal(reloads,1);
let saved=JSON.parse(store.get('watchtower-view:/sources'));assert.deepEqual(saved.details,['source-technical']);assert.equal(saved.q,'invented');assert.equal(saved.focus,'q');
q.value='';detail.open=false;document.activeElement=null;events.DOMContentLoaded();assert.equal(q.value,'invented');assert.equal(detail.open,true);assert.equal(document.activeElement,q);
window.watchtowerRefresh.pause();assert.equal(timers.size,0);console.log('OK')})().catch(e=>{console.error(e);process.exit(1)});
"""
        controller = _SCRIPT.replace('__DELAY__', '30000').replace('__PUBLIC__', 'false')
        result = subprocess.run(['node', '-e', harness + controller + scenario], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'OK')

    def test_trends_do_not_connect_across_missing_observations(self):
        page = dashboard._svg_sparkline([1, None, 3], label='Response time', unit='s')
        self.assertEqual(page.count('<circle'), 2)
        self.assertNotIn('<polyline', page)
        self.assertIn('1.0 – 3.0 s', page)
        self.assertNotIn('nan', dashboard._svg_sparkline([1, float('nan'), 3, float('inf')]))
        self.assertIn('10.0 s', dashboard._svg_sparkline([10, 10], unit='s'))

    def test_refresh_initialization_does_not_overwrite_saved_pause_and_sections(self):
        if not shutil.which('node') and os.environ.get('WATCHTOWER_REQUIRE_NODE') != '1':
            self.skipTest('Node required for executable refresh-controller regression')
        from clearparcel.datawatch.dashboard_refresh import _SCRIPT
        harness = r"""
const assert=require('node:assert/strict'),events={},store=new Map(),timers=new Map();let nextTimer=0;
const key='watchtower-view:/source?id=sample';
const saved={userPaused:true,q:'invented',details:['source-technical'],scroll:120};
store.set(key,JSON.stringify(saved));
function dispatch(type){for(const listener of events[type]||[])listener({type})}
const detail={id:'source-technical',tagName:'DETAILS',open:false};
const change={id:'source-change-details',tagName:'DETAILS',open:false};
const pause={id:'refresh-pause',dataset:{},addEventListener(){}};
const input={id:'q',tagName:'INPUT',value:'',dataset:{},addEventListener(){},
 dispatchEvent(){dispatch('toggle')}}; // A disclosure changes while controls are restored.
const nodes={'source-technical':detail,'source-change-details':change,'refresh-pause':pause,q:input};
global.location={pathname:'/source',search:'?id=sample',hash:'#change-example'};
global.window={scrollY:0,scrollTo(){},addEventListener(){}};
global.sessionStorage={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)};
global.document={hidden:false,activeElement:null,getElementById:id=>nodes[id]||null,
 querySelectorAll:s=>s.startsWith('details')?[detail,change]:[],
 querySelector:()=>null,addEventListener:(type,fn)=>(events[type]??=[]).push(fn)};
global.setTimeout=(fn,delay)=>{timers.set(++nextTimer,{fn,delay});return nextTimer};
global.clearTimeout=id=>timers.delete(id);
"""
        scenario = r"""
// A deep link opens a disclosure while the page is still being parsed.
change.open=true;dispatch('toggle');
assert.deepEqual(JSON.parse(store.get(key)),saved);
dispatch('DOMContentLoaded');
assert.equal(window.watchtowerRefresh.paused(),true);
assert.equal(pause.textContent,'Resume refresh');assert.equal(timers.size,0);
assert.equal(input.value,'invented');assert.equal(detail.open,true);assert.equal(change.open,true);
dispatch('toggle');
const restored=JSON.parse(store.get(key));assert.equal(restored.userPaused,true);
assert.deepEqual(restored.details,['source-technical','source-change-details']);
console.log('OK');
"""
        controller = _SCRIPT.replace('__DELAY__', '30000').replace('__PUBLIC__', 'false')
        result = subprocess.run(['node', '-e', harness + controller + scenario], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'OK')


if __name__ == '__main__':
    unittest.main()
