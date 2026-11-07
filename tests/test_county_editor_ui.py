"""County editor feedback, edit protection and public/private review boundaries."""
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from clearparcel.datawatch.county_admin_validation import editor_validation_errors


class CountyEditorUiTests(unittest.TestCase):
    def test_validation_hints_identify_fields_without_echoing_private_values(self):
        draft = {"contacts": [{"name": "Invented", "email": "PRIVATE_SENTINEL"}],
                 "access": {"parcel_polygons": {"classification": "open", "methods": [
                     {"kind": "direct_rest", "url": "https://example.org", "scope": "County data"}]}},
                 "policy": {"url": "javascript:PRIVATE_SENTINEL"}}
        errors = editor_validation_errors(draft)
        paths = {e.get("field") for e in errors}
        self.assertIn("contacts.0.email", paths)
        self.assertIn("access.parcel_polygons.methods.0.evidence_date", paths)
        self.assertIn("policy.url", paths)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(errors))

    def test_private_time_hint_points_to_the_corresponding_control(self):
        errors = editor_validation_errors({"correspondence": [{"sent_at": "2026-03-08T02:30-06:00"}]})
        self.assertEqual(errors[0]["field"], "correspondence.0.sent_at.time")

    def run_ui(self, scenario):
        if not shutil.which("node") and os.environ.get("WATCHTOWER_REQUIRE_NODE") != "1":
            self.skipTest("Node required for executable county-editor regression")
        source = (Path(__file__).resolve().parents[1] / "clearparcel/datawatch/county_admin.js").read_text()
        harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const nodes=new Map(),listeners=new Map(),calls=[];let confirmResult=false,failList=false,failSave=false;
function node(){return {key:'',disabled:false,hidden:false,value:'',textContent:'',children:[],dataset:{},files:[],scrollTop:0,
 append(c){this.children.push(c)},replaceChildren(){this.children=[]},querySelectorAll(){return[]},
 setAttribute(){},removeAttribute(){},focus(){},scrollIntoView(){},
 addEventListener(type,fn){listeners.set(this.key+':'+type,fn)}}}
for(const key of ['#editor','#fields','#counties','#county-search','#status','#save-status','#retry','#apply','#discard','#errors','.editor-scroll','#review','#change-summary','#county-results','#clear-search','#refresh-directory','.county-search']){const n=node();n.key=key;nodes.set(key,n)}
const sandbox={document:{querySelector:key=>nodes.get(key),querySelectorAll:()=>[],createElement:()=>node(),getElementById:()=>null},
 window:{addEventListener(){}},matchMedia:()=>({matches:false,addEventListener(){}}),Intl,Map,Set,URL,URLSearchParams,structuredClone,queueMicrotask,
 crypto:{randomUUID:()=>String(calls.length)},setTimeout(){},clearTimeout(){},confirm(){return confirmResult},
 fetch:async(path,options)=>{calls.push({path,method:options?.method||'GET',payload:options?.body&&JSON.parse(options.body)});
 if(options?.method==='POST'){if(failSave){failSave=false;throw Error('Ambiguous write')}return {status:200,json:async()=>({status:'published',revision:2})}}
 if(failList)throw Error('County list refresh failed');
 return {status:200,json:async()=>({counties:[],csrf_token:'synthetic-csrf'})};}};
vm.createContext(sandbox);vm.runInContext(SOURCE,sandbox);
(async()=>{await new Promise(resolve=>setImmediate(resolve));
vm.runInContext("selected='invented';draft={contacts:[],access:{},policy:{},correspondence:[]};baseline=structuredClone(draft);revision=1;dirty=true;",sandbox);
const submit=()=>listeners.get('#editor:submit')({preventDefault(){}});
'''
        ending = "\nconsole.log('OK');})().catch(error=>{console.error(error);process.exitCode=1});"
        result = subprocess.run(["node", "-e", "const SOURCE=" + json.dumps(source) + ";\n" + harness + scenario + ending], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "OK")

    def test_confirmed_save_is_not_replaced_by_directory_refresh_failure(self):
        self.run_ui(r'''
failList=true;await submit();
assert.match(nodes.get('#save-status').textContent,/saved and published/);
assert.match(nodes.get('#county-results').textContent,/list could not refresh/);
assert.equal(vm.runInContext('dirty',sandbox),false);
assert.equal(vm.runInContext('pendingRequest',sandbox),null);
''')

    def test_ambiguous_save_retries_the_identical_request(self):
        self.run_ui(r'''
failSave=true;await submit();assert.equal(nodes.get('#apply').textContent,'Retry save');
const first=calls.find(c=>c.method==='POST').payload;
assert.equal(vm.runInContext('dirty',sandbox),true);await submit();
const posts=calls.filter(c=>c.method==='POST');assert.equal(posts.length,2);
assert.deepEqual(posts[1].payload,first);assert.equal(vm.runInContext('pendingRequest',sandbox),null);
''')

    def test_discard_requires_confirmation_when_dirty(self):
        self.run_ui(r'''
vm.runInContext('loadCounty=async slug=>{selected="loaded:"+slug}',sandbox);
listeners.get('#discard:click')();assert.equal(vm.runInContext('selected',sandbox),'invented');
confirmResult=true;listeners.get('#discard:click')();assert.equal(vm.runInContext('selected',sandbox),'loaded:invented');
''')

    def test_review_excludes_unknown_fields_and_marks_private_values(self):
        self.run_ui(r'''
vm.runInContext(`draft={contacts:[{id:'contact-id',name:'Invented',secret:'NEVER_DISPLAY'}],policy:{text:'Public',attachment_id:'PRIVATE_FILE_ID'},
 correspondence:[{id:'event-id',notes:'PRIVATE_NOTE',crm_reference:'NEVER_DISPLAY'}],private_registry:'NEVER_DISPLAY'};`,sandbox);
const rows=JSON.parse(vm.runInContext('JSON.stringify([...reviewRows(draft).values()])',sandbox));
assert.ok(rows.some(r=>r.value==='PRIVATE_NOTE'&&r.private));
assert.ok(rows.some(r=>r.value==='Public'&&!r.private));
assert.ok(!JSON.stringify(rows.map(r=>({label:r.label,value:r.value}))).includes('PRIVATE_FILE_ID'));
assert.ok(!JSON.stringify(rows).includes('NEVER_DISPLAY'));
''')


if __name__ == "__main__":
    unittest.main()
