import copy
import unittest
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.public_projection import sanitize_public_render_state


class ObservationRetentionTests(unittest.TestCase):
    def config(self):
        return {"state_file": "unused.json", "history_file": "unused.jsonl",
                "retries": 0, "sources": [{"id": "mn-parcel-county-catalog",
                "name": "Catalog", "kind": "arcgis_layer", "url": "https://example.invalid/0"}]}

    def check(self, previous, details=None):
        with patch.object(watch, "load_state", return_value=previous), \
             patch.object(watch, "_source_check", **({"return_value": details} if details is not None
                                                       else {"side_effect": TimeoutError("forced")})):
            return watch.check_sources(self.config(), save=False)

    def test_catalog_success_timeout_recovery_preserves_observation(self):
        records = {"Aitkin": {"acqdate": "2025-01-01"}}
        good = self.check({}, {"county_records": records})
        source = good["sources"]["mn-parcel-county-catalog"]
        observed = source.get("catalog_observed_at")
        self.assertEqual(observed, source["checked_at"])
        self.assertFalse(source["catalog_retained"])
        before = copy.deepcopy(good)
        failed = self.check(good)
        source = failed["sources"]["mn-parcel-county-catalog"]
        self.assertEqual(source["status"], "error")
        self.assertEqual(source["county_records"], records)
        self.assertEqual(source["catalog_observed_at"], observed)
        self.assertTrue(source["catalog_retained"])
        self.assertEqual(good, before)
        recovered = self.check(failed, {"county_records": {"Aitkin": {"acqdate": "2026-01-01"}}})
        source = recovered["sources"]["mn-parcel-county-catalog"]
        self.assertEqual(source["county_records"]["Aitkin"]["acqdate"], "2026-01-01")
        self.assertFalse(source["catalog_retained"])

    def test_catalog_failure_without_prior_does_not_invent_observation(self):
        report = self.check({})
        self.assertIn("configuration_sha256", report.get("runtime_identity", {}))
        source = report["sources"]["mn-parcel-county-catalog"]
        self.assertFalse(source.get("catalog_retained", False))
        self.assertNotIn("catalog_observed_at", source)

    def test_legacy_catalog_time_uses_success_not_failed_attempt(self):
        old = {"sources": {"mn-parcel-county-catalog": {"status": "error",
            "checked_at": "2026-10-07T12:00:00+00:00", "last_success_at": "2026-10-06T12:00:00+00:00",
            "county_records": {"Aitkin": {"acqdate": "2025-01-01"}}}}}
        source = self.check(old)["sources"]["mn-parcel-county-catalog"]
        self.assertEqual(source["catalog_observed_at"], "2026-10-06T12:00:00+00:00")
        self.assertTrue(source["catalog_time_inferred"])

    def test_public_observation_metadata_survives_with_typed_boundaries(self):
        gac = {"observed_at": "2026-10-06T12:00:00+00:00", "observation_status": "complete",
               "fields": {"PIN": {"percent": 0}}, "counties": {"Aitkin": {}}}
        raw = {"sources": {"parcel": {"mngac_completeness": gac},
            "mn-parcel-county-catalog": {"catalog_observed_at": gac["observed_at"],
                                        "catalog_retained": True, "catalog_time_inferred": True}}}
        public = sanitize_public_render_state(raw)
        self.assertEqual(public["sources"]["parcel"]["mngac_completeness"]["observed_at"], gac["observed_at"])
        self.assertEqual(public["sources"]["parcel"]["mngac_completeness"]["observation_status"], "complete")
        self.assertTrue(public["sources"]["mn-parcel-county-catalog"]["catalog_retained"])
        raw["sources"]["mn-parcel-county-catalog"]["catalog_retained"] = "true"
        gac["observed_at"] = "private arbitrary data"
        public = sanitize_public_render_state(raw)
        self.assertNotIn("observed_at", public["sources"]["parcel"]["mngac_completeness"])
        self.assertNotIn("catalog_retained", public["sources"]["mn-parcel-county-catalog"])


class SummaryTests(unittest.TestCase):
    def fixture(self):
        profiles = {str(i): {"county": {"slug": str(i), "name": str(i)},
            "monitoring": {"paths": paths}, "research": {"complete": i == 0,
            "category_review_statuses": {"rest": "blocked" if i else "reviewed"}}}
            for i, paths in enumerate([[], ["mngeo-open"], ["county-direct"], ["county-direct", "mngeo-open"]])}
        gac = {"standard_key": "parcel", "standard": {"key": "parcel", "version": "1.1.3"},
            "observed_at": "2026-10-06T12:00:00+00:00", "record_count": 100,
            "mandatory_field_count": 2, "field_count": 3, "scanned_field_count": 2,
            "population_scope": "Mandatory", "fields": {
                "A": {"inclusion": "Mandatory", "population_scanned": True, "populated": 100, "record_count": 100},
                "B": {"inclusion": "Mandatory", "population_scanned": True, "populated": 0, "record_count": 100},
                "C": {"inclusion": "Optional", "population_scanned": False}},
            "counties": {"Aitkin": {"mandatory_population_percent": 25},
                         "Anoka": {"mandatory_population_percent": 75}}}
        return {"generated_at": "2026-10-06T12:00:00+00:00", "sources": {
            "mn-state-parcels": {"mngac_completeness": gac, "status": "ok", "url": "private"}}}, profiles

    def test_summary_partitions_coverage_and_distinguishes_unscanned_values(self):
        from clearparcel.datawatch.dashboard_summary import build_summary
        state, profiles = self.fixture()
        summary = build_summary(state, profiles, identity={"version": "test"})
        self.assertEqual(summary["coverage"], {"total": 4, "statewide_only": 1,
            "direct_only": 1, "both": 1, "neither": 1})
        parcel = summary["standards"]["parcel"]
        self.assertEqual(parcel["mandatory_population_percent"], 50)
        self.assertEqual(parcel["county_median_percent"], 50)
        self.assertEqual([f["name"] for f in parcel["gaps"]], ["B", "A"])
        self.assertEqual(parcel["gaps"][0]["percent"], 0)
        self.assertIsNone(summary["standards"]["address"]["mandatory_population_percent"])
        self.assertNotIn("private", str(summary))
        self.assertEqual(summary["research"]["complete"], 1)
        self.assertEqual(summary["research"]["category_statuses"]["blocked"], 3)

    def test_revision_ignores_publication_and_private_details_but_tracks_observations(self):
        from clearparcel.datawatch.dashboard_summary import build_summary
        state, profiles = self.fixture()
        def revision():
            return build_summary(state, profiles, identity={"version": "test"})["content_revision"]
        before = revision()
        state["public_published_at"] = "2026-10-07T12:00:00+00:00"
        state["sources"]["mn-state-parcels"]["url"] = "other private"
        self.assertEqual(revision(), before)
        state["sources"]["mn-state-parcels"]["status"] = "error"
        self.assertNotEqual(revision(), before)

    def test_catalog_unknown_missing_date_and_retained_are_distinct(self):
        from clearparcel.datawatch.dashboard_summary import catalog_summary
        missing = catalog_summary({}, ["Aitkin", "Anoka"])
        self.assertEqual(missing["buckets"]["Catalog unavailable"], 2)
        state = {"sources": {"mn-parcel-county-catalog": {"status": "error",
            "catalog_retained": True, "catalog_observed_at": "2026-10-06T12:00:00+00:00",
            "county_records": {"Aitkin": {}}}}}
        summary = catalog_summary(state, ["Aitkin", "Anoka"])
        self.assertTrue(summary["retained"])
        self.assertEqual(summary["buckets"]["Provider supplied no date"], 1)
        self.assertEqual(summary["buckets"]["No catalog entry"], 1)


class HybridReceiptTests(unittest.TestCase):
    def test_shared_source_receipt_uses_latest_accepted_worker(self):
        from clearparcel.datawatch.hybrid_validation import candidate_manifest, validation_receipt
        from clearparcel.datawatch.aggregate import merge_states
        manifest = candidate_manifest({'sources': [{'id': 'a', 'execution_profiles': ['any']}]}, {})
        reports = {p: {'generated_at': f'2026-10-07T{hour}:00:00+00:00',
                      'runtime_identity': manifest['runtime_identity'],
                      'sources': {'a': {'checked_at': f'2026-10-07T{hour}:00:00+00:00', 'status': 'ok'}}}
                   for p, hour in [('cloud', '12'), ('local', '13')]}
        aggregate = merge_states(merge_states({}, reports['cloud'], 'cloud'), reports['local'], 'local')
        public = sanitize_public_render_state(aggregate)
        self.assertTrue(validation_receipt(manifest, reports, aggregate, public)['passed'])
        aggregate['sources']['a']['worker'] = 'cloud'
        self.assertFalse(validation_receipt(manifest, reports, aggregate, public)['passed'])

    def test_package_identity_includes_normalized_runtime_json(self):
        from clearparcel.datawatch.hybrid_validation import runtime_identity
        from pathlib import Path
        original = Path.read_text
        before = runtime_identity({}, {})['package_sha256']
        def changed(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            return value + ' ' if path.name == 'mngac_parcel_fields.json' else value
        with patch.object(Path, 'read_text', changed):
            self.assertNotEqual(runtime_identity({}, {})['package_sha256'], before)
        def environment_changed(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            return value + ' ' if path.name == 'build_info.json' else value
        with patch.object(Path, 'read_text', environment_changed):
            self.assertEqual(runtime_identity({}, {})['package_sha256'], before)

    def test_receipt_requires_inventory_identity_and_public_arrival(self):
        from clearparcel.datawatch.hybrid_validation import candidate_manifest, validation_receipt
        config = {"sources": [{"id": "a", "execution_profiles": ["cloud"]},
                              {"id": "b", "execution_profiles": ["local"]}]}
        manifest = candidate_manifest(config, {"revision": "abc"})
        self.assertEqual(manifest["expected_sources"], {"cloud": ["a"], "local": ["b"]})
        stamp = "2026-10-07T12:00:00+00:00"
        reports = {profile: {"generated_at": stamp, "runtime_identity": manifest["runtime_identity"],
                    "sources": {sid: {"checked_at": stamp, "status": "ok"}}}
                   for profile, sid in [("cloud", "a"), ("local", "b")]}
        aggregate = {"sources": {sid: {"checked_at": stamp, "worker": profile, "status": "ok"}
                     for profile, sid in [("cloud", "a"), ("local", "b")]},
                     "workers": {p: {"last_report_at": stamp} for p in reports}}
        public = sanitize_public_render_state(aggregate)
        self.assertTrue(validation_receipt(manifest, reports, aggregate, public)["passed"])
        public["sources"]["a"]["checked_at"] = "2026-10-06T12:00:00+00:00"
        receipt = validation_receipt(manifest, reports, aggregate, public)
        self.assertFalse(receipt["passed"])
        self.assertIn("public observation mismatch: a", receipt["problems"])
        reports["local"]["runtime_identity"] = {"revision": "old"}
        self.assertIn("runtime identity mismatch: local", validation_receipt(manifest, reports, aggregate, public)["problems"])

    def test_receipt_rejects_malformed_time_and_public_worker_provenance(self):
        from clearparcel.datawatch.hybrid_validation import candidate_manifest, validation_receipt
        config = {"sources": [{"id": "a", "execution_profiles": ["cloud"]}]}
        manifest = candidate_manifest(config, {})
        reports = {"cloud": {"generated_at": "invalid", "runtime_identity": manifest["runtime_identity"],
                             "sources": {"a": {"checked_at": "invalid", "status": "ok"}}}}
        aggregate = {"workers": {"cloud": {"last_report_at": "invalid"}},
                     "sources": {"a": {"checked_at": "invalid", "worker": "cloud", "status": "ok"}}}
        public = {"workers": {"cloud": {"last_report_at": "invalid"}},
                  "sources": {"a": {"checked_at": "invalid", "worker": "other", "status": "ok"}}}
        result = validation_receipt(manifest, reports, aggregate, public)
        self.assertFalse(result["passed"])
        self.assertIn('worker report mismatch: cloud', result['problems'])
        self.assertIn('public worker provenance mismatch: a', result['problems'])

    def test_candidate_fails_closed_on_unassigned_or_invalid_profiles(self):
        from clearparcel.datawatch.hybrid_validation import candidate_manifest
        for assignment in [[], ["other"]]:
            with self.assertRaises(ValueError):
                candidate_manifest({"sources": [{"id": "a", "execution_profiles": assignment}]}, {})


class DashboardInteractionTests(unittest.TestCase):
    def test_public_home_is_lazy_and_small_with_all_three_graphics(self):
        from clearparcel.datawatch.public_dashboard import render_public_dashboard
        state, _ = SummaryTests().fixture()
        with patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=state):
            page = render_public_dashboard({'_public_mode': True})
        self.assertNotIn('id="county-profile-data"', page)
        self.assertNotIn('<template data-profile=', page)
        self.assertLess(len(page.encode()), 250 * 1024)
        self.assertIn('/api/county-profile?', page)
        for label in ('Parcel monitoring paths', 'Three-standard comparison', 'Field-gap standard'):
            self.assertIn(label, page)

    def test_refresh_script_preserves_manual_pause_and_publication_only_updates(self):
        from clearparcel.datawatch.dashboard_templates import _refresh_script
        script = _refresh_script(30, public=True)
        for expected in ('userPaused', 'overview-metric', 'overview-county-select', 'gap-standard',
                         'visibilitychange', '/api/summary', 'content_revision', 'suspend', 'release'):
            self.assertIn(expected, script)

    def test_public_export_is_outside_navigation_and_tables_keep_semantics(self):
        from clearparcel.datawatch.dashboard_templates import _layout
        import re
        page = _layout('Test', '<table id="datasets"><thead><tr><th>Count</th></tr></thead><tbody><tr><td>0</td></tr></tbody></table>', static=True)
        nav = re.search(r'<nav class="public-tabs".*?</nav>', page, re.S).group()
        self.assertNotIn('public-export', nav)
        self.assertIn('class="table-scroll"', page)
        self.assertIn('scope="col"', page)
        self.assertIn('<thead>', page)
        self.assertIn('display:table-header-group!important', page)


class PublicDetailTests(unittest.TestCase):
    def test_revision_bound_county_fragment_unknown_and_old_revision(self):
        from clearparcel.datawatch.public_details import dispatch_public_details
        sent = []
        class Handler:
            def _send(self, *args):
                sent.append(args)
        view = {"summary": {"schema_version": 1, "content_revision": "abc"},
                "profiles": {"aitkin": {"county": {"name": "Aitkin", "slug": "aitkin"}}}}
        self.assertTrue(dispatch_public_details(Handler(), "/api/county-profile", "slug=aitkin&revision=old", view))
        self.assertEqual(sent[-1][0], 409)
        dispatch_public_details(Handler(), "/api/county-profile", "slug=missing&revision=abc", view)
        self.assertEqual(sent[-1][0], 404)
        dispatch_public_details(Handler(), "/api/county-profile", "slug=aitkin&revision=abc", view)
        self.assertEqual(sent[-1][0], 200)
        self.assertIn('Aitkin County', sent[-1][1])
        self.assertNotIn('Anoka', sent[-1][1])
        dispatch_public_details(Handler(), "/api/summary", "", view)
        import json
        self.assertEqual(json.loads(sent[-1][1])["content_revision"], "abc")

    def test_conditional_response_and_gzip_negotiation(self):
        from clearparcel.datawatch.public_details import encode_response
        import gzip
        raw = ('<p>test</p>' * 500).encode()
        status, body, headers = encode_response(200, raw, 'text/html', 'gzip', None)
        self.assertEqual(gzip.decompress(body), raw)
        self.assertEqual(headers['Content-Encoding'], 'gzip')
        self.assertEqual(status, 200)
        status, body, _ = encode_response(200, raw, 'text/html', 'gzip', headers['ETag'])
        self.assertEqual((status, body), (304, b''))
        _, body, headers = encode_response(200, raw, 'text/html', 'gzip;q=0', None)
        self.assertEqual(body, raw)
        self.assertNotIn('Content-Encoding', headers)
        status, body, _ = encode_response(404, raw, 'text/html', '', '*')
        self.assertEqual(status, 404)


class RefreshBehaviorTests(unittest.TestCase):
    def test_manual_pause_dialog_release_and_pending_revision_after_304(self):
        import json
        import shutil
        import subprocess
        if not shutil.which('node'):
            self.skipTest('Node required for executable refresh-controller regression')
        from clearparcel.datawatch.dashboard_refresh import _SCRIPT
        controller = _SCRIPT.replace('__DELAY__', '30000').replace('__PUBLIC__', 'true')
        harness = r'''
const assert=require('assert');const timers=new Map(),events={},stored=new Map();let next=0,reloads=0,reading=false;
const publicationBadge={dataset:{ageTime:'2000-01-01T00:00:00Z'},textContent:''},publicationTime={textContent:'old'};
const button={textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v},addEventListener(){}};
global.window={scrollY:0,addEventListener(){},scrollTo(){}};global.location={pathname:'/',search:'',reload(){reloads++}};
global.sessionStorage={getItem(k){return stored.get(k)||null},setItem(k,v){stored.set(k,v)}};
global.document={hidden:false,activeElement:null,querySelectorAll(){return []},getElementById(id){return id==='refresh-pause'?button:id==='public-publication-time'?publicationTime:null},querySelector(q){return q==='[data-age-kind="publication"]'?publicationBadge:q==='[data-content-revision]'?{dataset:{contentRevision:'a'}}:q==='.profile-evidence[open]'&&reading?{}:null},addEventListener(name,fn){events[name]=fn}};
global.setTimeout=(fn,delay)=>{timers.set(++next,{fn,delay});return next};global.clearTimeout=id=>timers.delete(id);
let status=200,revision='a',pending=null;global.fetch=async()=>{if(pending)await pending;return {status,ok:status===200,headers:{get(){return 'etag'}},json:async()=>({schema_version:1,content_revision:revision,public_published_at:'2026-10-07T12:00:00Z'})}};
'''
        scenario = r'''
(async()=>{events.DOMContentLoaded();window.watchtowerRefresh.pause();window.watchtowerRefresh.suspend('county-dialog');window.watchtowerRefresh.release('county-dialog');assert.equal(button.attrs['aria-pressed'],'true');assert.equal(timers.size,0);window.watchtowerRefresh.resume();
async function tick(){const entry=[...timers].find(([id,v])=>v.delay===30000);assert.ok(entry);timers.delete(entry[0]);await entry[1].fn()}
await tick();assert.equal(reloads,0);assert.equal(publicationBadge.dataset.ageTime,'2026-10-07T12:00:00Z');assert.notEqual(publicationTime.textContent,'old');
let resolve;pending=new Promise(r=>resolve=r);revision='b';const inFlight=tick();window.watchtowerRefresh.pause();resolve();await inFlight;assert.equal(reloads,0);pending=null;window.watchtowerRefresh.resume();
reading=true;await tick();assert.equal(reloads,0);reading=false;status=304;pending=new Promise(r=>resolve=r);const conditional=tick();document.hidden=true;resolve();await conditional;assert.equal(reloads,0);pending=null;document.hidden=false;events.visibilitychange();await tick();assert.equal(reloads,1);console.log('OK')})().catch(e=>{console.error(e);process.exit(1)});
'''
        result = subprocess.run(['node', '-e', harness + controller + scenario], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'OK')
