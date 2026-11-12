"""An open public page reloads when county reporting expires, though observations are unchanged."""
import contextlib
import copy
import io
import os
import shutil
import subprocess
import unittest

from unittest.mock import patch

from clearparcel.datawatch import public_dashboard
from clearparcel.datawatch.dashboard_refresh import _SCRIPT
from clearparcel.datawatch.dashboard_summary import build_summary

NODE_AVAILABLE = bool(shutil.which("node")) or os.environ.get("WATCHTOWER_REQUIRE_NODE") == "1"


def profiles(reporting):
    return {"aitkin": {"county": {"name": "Aitkin"}, "monitoring": {"paths": ["county-direct"], "reporting": reporting,
                                                                     "health": "ok"}, "research": {}}}


class PresentationRevisionTests(unittest.TestCase):
    def test_reporting_change_moves_presentation_but_not_content_revision(self):
        state = {"generated_at": "2026-11-12T00:00:00Z", "sources": {}}
        current = build_summary(state, profiles("current"), identity={})
        overdue = build_summary(copy.deepcopy(state), profiles("overdue"), identity={})
        self.assertEqual(current["content_revision"], overdue["content_revision"])
        self.assertNotEqual(current["presentation_revision"], overdue["presentation_revision"])
        again = build_summary(copy.deepcopy(state), profiles("current"), identity={})
        self.assertEqual(again["presentation_revision"], current["presentation_revision"])

    def test_public_pages_carry_the_presentation_revision(self):
        captured = {}

        class Server:
            def __init__(self, addr, handler, **kwargs):
                captured["handler"] = handler

            def serve_forever(self):
                pass

            def server_close(self):
                pass

        class Cache:
            stale = False

            def refresh(self, **kwargs):
                pass

        with patch.object(public_dashboard, "_BoundedThreadingHTTPServer", Server), \
                patch.object(public_dashboard, "_PublicStateCache", Cache), contextlib.redirect_stdout(io.StringIO()):
            public_dashboard.serve_public()
        handler = object.__new__(captured["handler"])
        handler.headers, handler.command, handler.wfile = {}, "GET", io.BytesIO()
        handler.send_response = handler.end_headers = lambda *args: None
        handler.send_header = lambda *args: None
        handler._render_revision, handler._presentation_revision = "content1", "present1"
        handler._send(200, "<html><head></head><body></body></html>")
        page = handler.wfile.getvalue().decode()
        self.assertIn('data-content-revision="content1"', page)
        self.assertIn('data-presentation-revision="present1"', page)


@unittest.skipUnless(NODE_AVAILABLE, "Node required for executable refresh-controller regression")
class PresentationRefreshControllerTests(unittest.TestCase):
    HARNESS = r'''
const assert=require('assert');const timers=new Map(),events={},stored=new Map();let next=0,reloads=0,reading=false;
const button={textContent:'',setAttribute(){},addEventListener(){}};
const status={textContent:'',append(){}};
global.window={scrollY:0,addEventListener(){},scrollTo(){}};global.location={pathname:'/',search:'',reload(){reloads++}};
global.sessionStorage={getItem(k){return stored.get(k)||null},setItem(k,v){stored.set(k,v)}};
global.document={hidden:false,activeElement:null,createElement(){return {append(){},addEventListener(){}}},querySelectorAll(){return []},
 getElementById(id){return id==='refresh-pause'?button:id==='refresh-status'?status:null},
 querySelector(q){return q==='[data-content-revision]'?{dataset:{contentRevision:'a'}}:q==='[data-presentation-revision]'?{dataset:{presentationRevision:'p1'}}:q==='.profile-evidence[open]'&&reading?{}:null},
 addEventListener(name,fn){events[name]=fn}};
global.setTimeout=(fn,delay)=>{timers.set(++next,{fn,delay});return next};global.clearTimeout=id=>timers.delete(id);
let presentation='p1';global.fetch=async()=>({status:200,ok:true,headers:{get(){return 'etag-'+presentation}},
 json:async()=>({schema_version:1,content_revision:'a',presentation_revision:presentation,public_published_at:'2026-11-12T12:00:00Z'})});
async function tick(){const entry=[...timers].find(([id,v])=>v.delay===30000);assert.ok(entry);timers.delete(entry[0]);await entry[1].fn()}
'''

    def run_scenario(self, scenario):
        controller = _SCRIPT.replace("__DELAY__", "30000").replace("__PUBLIC__", "true")
        result = subprocess.run(["node", "-e", self.HARNESS + controller + "(async()=>{events.DOMContentLoaded();"
                                 + scenario + ";console.log('OK')})().catch(e=>{console.error(e);process.exit(1)});"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "OK")

    def test_unchanged_observations_with_expired_reporting_reload(self):
        self.run_scenario("await tick();assert.equal(reloads,0);presentation='p2';await tick();assert.equal(reloads,1)")

    def test_reading_and_pause_still_hold_the_reload(self):
        self.run_scenario("presentation='p2';reading=true;await tick();assert.equal(reloads,0);reading=false;"
                          "window.watchtowerRefresh.pause();assert.equal(timers.size,0);assert.equal(reloads,0);"
                          "window.watchtowerRefresh.resume();await tick();assert.equal(reloads,1)")


if __name__ == "__main__":
    unittest.main()
