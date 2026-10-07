import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch.dashboard import _layout, render_counties, render_county, render_mngac
from clearparcel.datawatch.public_dashboard import (
    _PublicStateCache,
    _publication_health,
    render_public_dashboard,
    render_public_source,
    sanitize_public_render_state,
)


class PublicDashboardTests(unittest.TestCase):
    def test_feedback_uses_check_times_and_keeps_missing_success_unknown(self):
        from unittest.mock import patch
        now = dt.datetime.now(dt.timezone.utc)
        old = (now - dt.timedelta(days=2)).isoformat()
        recent = (now - dt.timedelta(minutes=10)).isoformat()
        state = sanitize_public_render_state(self._state())
        state['generated_at'] = now.isoformat()
        for source in state['sources'].values():
            source['checked_at'] = old
        state['workers'] = {'local': {'checked_at': recent, 'last_report_at': recent, 'source_count': 2, 'overall': 'error'}}
        with patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=state):
            page = render_public_dashboard({'_public_mode': True})
        self.assertIn('Latest provider check in this snapshot', page)
        self.assertIn('2 days ago', page)
        self.assertIn('Source reporting: 2 overdue', page)
        self.assertIn('Reporting on time', page)
        self.assertIn('Last successful provider check</span><strong>—', page)
        self.assertIn('does not check GIS providers again', page)
        state['sources'] = {'missing': {'checked_at': None}, 'invalid': {'checked_at': 'invalid'}}
        with patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=state):
            page = render_public_dashboard({'_public_mode': True})
        self.assertIn('Source reporting: 0 overdue · 2 without a check time', page)

    def test_feedback_mandatory_map_research_brand_and_record_format(self):
        from unittest.mock import patch
        state = sanitize_public_render_state(self._state())
        county = state['sources']['mn-state-parcels']['mngac_completeness']['counties']['Olmsted']
        county.update(field_population_percent=10, mandatory_population_percent=80)
        state['sources']['county-parcels-direct']['feature_count'] = 42996
        with patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=state), patch('clearparcel.datawatch.dashboard._dashboard_state', return_value=state):
            page = render_public_dashboard({'_public_mode': True})
            county_page = render_county({'_public_mode': True}, 'olmsted')
            index = render_counties({'_public_mode': True})
        self.assertIn('"pct": 80', page)
        self.assertIn('Mandatory-field population', page)
        self.assertIn('87/87 counties researched', page)
        self.assertIn('87/87 counties researched', index)
        self.assertIn('Open parcel data', index)
        self.assertNotIn('Free parcel data', index)
        self.assertIn('href="https://clear-parcel.com"', page)
        self.assertIn('src="data:image/webp;base64,', page)
        self.assertIn('<strong>Records:</strong> 42,996', county_page)
        self.assertIn('Official evidence and findings', county_page)
        self.assertIn('Read detailed research notes', county_page)

    def test_public_source_distinguishes_zero_counts_from_unknown(self):
        from unittest.mock import patch
        for value, expected in ((0, '0'), (None, '—')):
            with self.subTest(value=value), patch('clearparcel.datawatch.public_dashboard._dashboard_state',
                    return_value={'sources': {'x': {'name': 'X', 'feature_count': value, 'field_count': value}}}):
                page = render_public_source({}, 'x')
                self.assertIn('Records</div><div class="metric">' + expected + '</div>', page)
                self.assertIn('Information fields</dt><dd>' + expected + '</dd>', page)

    def test_overview_labels_publication_reporting_separately_from_source_health(self):
        from unittest.mock import patch
        state = sanitize_public_render_state(self._state())
        state['public_published_at'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
        with patch.dict('os.environ', {'WATCHTOWER_PUBLIC_MAX_PUBLICATION_AGE_SECONDS': '1800'}), patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=state):
            page = render_public_dashboard({'_public_mode': True})
        self.assertIn('Public publication reporting: Overdue', page)
        self.assertIn('complete county profiles', page)
        self.assertIn('Healthy', page)
        self.assertIn('/api/county-profile?', page)
        with patch('clearparcel.datawatch.dashboard._dashboard_state', return_value=state):
            self.assertIn('complete county profiles', render_counties({'_public_mode': True}))
        with patch.dict('os.environ', {'WATCHTOWER_PUBLIC_MAX_PUBLICATION_AGE_SECONDS': '86400'}), patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=state):
            self.assertIn('Public publication reporting: Current', render_public_dashboard({'_public_mode': True}))
        state['public_published_at'] = None
        with patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=state):
            self.assertIn('Public publication reporting: Unknown', render_public_dashboard({'_public_mode': True}))

    def test_overview_labels_follow_selected_map_view(self):
        from unittest.mock import patch
        import re
        state = sanitize_public_render_state(self._state())
        with patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=state):
            page = render_public_dashboard({'_public_mode': True})
        initial = re.search(r'<p id="home-county-detail">(.*?)</p>', page).group(1)
        self.assertIn('monitoring paths', initial)
        self.assertNotIn('population across', initial)
        self.assertIn('function monitoringLabel(paths)', page)
        self.assertIn('function updateDescription()', page)
        self.assertIn("p.setAttribute('aria-label',p.dataset.county+' County, '+label)", page)
        self.assertIn('selectedPath=path', page)
        self.assertIn('updateDescription();', page)
        self.assertIn('const monitoring=selector.value==="monitoring"', page)
        self.assertIn('No active parcel monitoring path', page)
        self.assertIn('Statewide completeness is unavailable', page)
        self.assertIn('These statistics are separate from county-direct monitoring', page)

    def test_both_public_maps_lazy_load_all_87_county_targets(self):
        import re
        from unittest.mock import patch
        from clearparcel.datawatch.dashboard import render_mngac, _county_profiles
        from clearparcel.datawatch.parcel_access import load_parcel_access
        from clearparcel.datawatch.county_profile_panel import GROUPS
        state = sanitize_public_render_state(self._state())
        expected = _county_profiles({}, state, load_parcel_access())
        for renderer in (render_public_dashboard, render_mngac):
            with patch('clearparcel.datawatch.dashboard._dashboard_state', return_value=state), patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=state):
                page = renderer({'_public_mode': True})
            self.assertNotIn('id="county-profile-data"', page)
            self.assertNotIn('<template data-profile=', page)
            self.assertIn('/api/county-profile?', page)
            slugs = re.findall(r'<path class="mngac-county"[^>]*data-slug="([^"]+)"', page)
            self.assertEqual(set(slugs), set(expected))
            self.assertEqual(len(slugs), 87)
            self.assertIn('dialog.showModal()', page)
            self.assertIn("event.key==='Enter'||event.key===' '", page)
            self.assertNotIn('http-equiv="refresh"', page)
            self.assertTrue("public publication" in page.lower())

    def test_no_statewide_observation_still_has_all_county_targets(self):
        import re
        from unittest.mock import patch
        from clearparcel.datawatch.dashboard import render_mngac
        with patch('clearparcel.datawatch.dashboard._dashboard_state', return_value={}):
            page=render_mngac({'_public_mode':True})
        self.assertEqual(len(re.findall(r'<path class="mngac-county"',page)),87)
        self.assertIn('/api/county-profile?',page)
        self.assertIn('style="fill:#151d2b"',page)

    def test_county_detail_uses_complete_composed_profile(self):
        from unittest.mock import patch
        state = sanitize_public_render_state(self._state())
        with patch('clearparcel.datawatch.dashboard._dashboard_state', return_value=state):
            page = render_county({'_public_mode':True}, 'winona')
        self.assertIn('County Website Download', page)
        self.assertIn('Research incomplete', page)

    def test_shared_profile_coverage_kpi_and_public_metadata(self):
        from test_county_profiles import coverage_state, NOW
        from clearparcel.datawatch.county_profiles import compose_county_profiles, county_profile_counts, FreshnessPolicy
        from clearparcel.datawatch.parcel_access import load_parcel_access
        from clearparcel.datawatch.dashboard import _county_monitoring_counts
        public = sanitize_public_render_state(coverage_state())
        profiles = compose_county_profiles(public, load_parcel_access(), now=NOW, freshness_policy=FreshnessPolicy())
        self.assertEqual(county_profile_counts(profiles)['active'], 70)
        self.assertEqual(_county_monitoring_counts({}, public)['active'], 70)
        observed = next(source for source in profiles['aitkin']['mngac_public_parcels']['sources'] if source['monitored_source_id'] == 'statewide')
        self.assertEqual(observed['feature_count'], 1000)
        self.assertEqual(public, sanitize_public_render_state(public))

    def test_safe_metadata_is_typed_and_idempotent(self):
        state = self._state()
        state['sources']['file'] = {'adapter': 'http_file', 'content_type': 'application/zip', 'tracked_values': {'content_length': '0', 'etag': '"abc"', 'last_modified': 'Wed, 01 Jan 2025 00:00:00 GMT'}}
        state['sources']['arcgis'] = {'adapter': 'arcgis_layer', 'geometry_type': 'esriGeometryPolygon', 'editing_info': {'lastEditDate': 1735689600000, 'secret': 'PRIVATE'}}
        public = sanitize_public_render_state(state)
        self.assertEqual(public['sources']['file']['public_metadata']['file'], {'type': 'application/zip', 'size_bytes': 0, 'etag': '"abc"', 'last_modified': '2025-01-01T00:00:00+00:00'})
        self.assertEqual(public['sources']['arcgis']['public_metadata']['provider_updated_at'], '2025-01-01T00:00:00+00:00')
        self.assertEqual(sanitize_public_render_state(public), public)

    def test_nested_private_values_never_reach_public_metadata(self):
        from clearparcel.datawatch.public_dashboard import sanitize_source_metadata
        source = {'adapter': {'secret': 'PRIVATE'}, 'geometry_type': 'PRIVATE', 'editing_info': {'lastEditDate': True}, 'content_type': 'x\nPRIVATE', 'tracked_values': {'content_length': '-1', 'etag': 'x' * 513, 'last_modified': 'invalid'}, 'public_metadata': {'file': {'etag': {'secret': 'PRIVATE'}, 'size_bytes': True}, 'provider_updated_at': 'invalid', 'secret': 'PRIVATE'}}
        self.assertEqual(sanitize_source_metadata(source), {})

    def test_nested_mngac_private_fields_and_links_are_removed(self):
        state = self._state()
        mngac = state['sources']['mn-state-parcels']['mngac_completeness']
        mngac['standard']['source_url'] = 'https://example.com/?token=PRIVATE'
        mngac['fields']['PIN']['provenance'] = {'secret': 'PRIVATE'}
        mngac['counties']['Olmsted']['tracked_values'] = {'secret': 'PRIVATE'}
        public = sanitize_public_render_state(state)
        self.assertNotIn('PRIVATE', json.dumps(public))

    def test_unsafe_evidence_links_and_formula_cells(self):
        from clearparcel.datawatch.public_values import spreadsheet_cell
        state = {'sources': {'mn-parcel-county-catalog': {'county_records': {'A': {'data_url': 'https://example.com/?token=secret', 'viewer_url': 'https://example.com/view'}}}}}
        record = sanitize_public_render_state(state)['sources']['mn-parcel-county-catalog']['county_records']['A']
        self.assertNotIn('data_url', record)
        self.assertEqual(record['viewer_url'], 'https://example.com/view')
        for value in ('=1', '+1', '-1', '@SUM(A1)', ' \t=1', '\r+1', '\u2003=1'):
            self.assertEqual(spreadsheet_cell(value), "'" + value)
        self.assertEqual(spreadsheet_cell('ordinary'), 'ordinary')

    def _state(self):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        return {
            "schema_version": 2,
            "generated_at": now,
            "overall": "ok",
            "counts": {"ok": 2, "warn": 0, "error": 0},
            "workers": {
                "cloud": {
                    "overall": "ok",
                    "source_count": 2,
                    "last_success_at": now,
                    "telemetry": {"private_runtime_detail": "hidden"},
                }
            },
            "sources": {
                "county-parcels-direct": {
                    "id": "county-parcels-direct",
                    "name": "County Parcels",
                    "provider": "Example County",
                    "category": "Parcels",
                    "county_slug": "olmsted",
                    "status": "ok",
                    "feature_count": 10,
                    "checked_at": now,
                    "worker": "cloud",
                    "changes": [{"type": "tracked_value", "previous": "PRIVATE-OLD", "current": "PRIVATE-NEW"}],
                    "tracked_values": {"secret": "PRIVATE-VALUE"},
                    "url": "https://secret.invalid/private",
                    "schema_hash": "PRIVATE-SCHEMA",
                    "observation_fingerprint": "PRIVATE-FINGERPRINT",
                    "field_count": 12,
                    "parcel_id_null_count": 0,
                },
                "mn-state-parcels": {
                    "id": "mn-state-parcels",
                    "name": "Minnesota State Parcels",
                    "provider": "MnGeo",
                    "category": "Parcels",
                    "status": "ok",
                    "checked_at": now,
                    "worker": "cloud",
                    "mngac_completeness": {
                        "standard": {"name": "MN GAC", "version": "1", "source_url": "https://example.invalid/standard"},
                        "method": "grouped statistics",
                        "record_count": 20,
                        "field_count": 1,
                        "covered_counties": 2,
                        "field_population_percent": 80.0,
                        "mandatory_field_count": 1,
                        "mandatory_population_percent": 100.0,
                        "source_schema_missing_fields": [],
                        "statistics_queries": [{"url": "https://secret.invalid/query"}],
                        "fields": {"PIN": {"percent": 100.0}},
                        "counties": {
                            "Olmsted": {"record_count": 10, "fields": {"PIN": {"percent": 100.0}}},
                            "Winona": {"record_count": 10, "fields": {"PIN": {"percent": 100.0}}},
                        },
                    },
                },
            },
        }

    def test_public_state_removes_operational_details_and_keeps_public_metrics(self):
        public = sanitize_public_render_state(self._state())
        source = public["sources"]["county-parcels-direct"]
        self.assertEqual(source["change_count"], 1)
        self.assertNotIn("url", source)
        self.assertNotIn("changes", source)
        self.assertNotIn("tracked_values", source)
        self.assertNotIn("schema_hash", source)
        self.assertNotIn("observation_fingerprint", source)
        self.assertNotIn("telemetry", public["workers"]["cloud"])

        mngac = public["sources"]["mn-state-parcels"]["mngac_completeness"]
        self.assertEqual(mngac["field_population_percent"], 80.0)
        self.assertNotIn("statistics_queries", mngac)

    def test_publication_health_accepts_fresh_snapshot(self):
        now = dt.datetime(2026, 10, 5, 23, 0, tzinfo=dt.timezone.utc)
        healthy, payload = _publication_health(
            {"public_published_at": "2026-10-05T22:50:00+00:00"},
            max_age_seconds=1800,
            now=now,
        )
        self.assertTrue(healthy)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["age_seconds"], 600)

    def test_publication_health_rejects_stale_or_missing_snapshot(self):
        now = dt.datetime(2026, 10, 5, 23, 30, tzinfo=dt.timezone.utc)
        healthy, payload = _publication_health(
            {"public_published_at": "2026-10-05T22:50:00+00:00"},
            max_age_seconds=1800,
            now=now,
        )
        self.assertFalse(healthy)
        self.assertEqual(payload["reason"], "publication_too_old")
        healthy, payload = _publication_health({}, max_age_seconds=1800, now=now)
        self.assertFalse(healthy)
        self.assertEqual(payload["reason"], "publication_timestamp_missing")

    def test_public_overview_does_not_emit_private_values(self):
        public = sanitize_public_render_state(self._state())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state.json"
            history = root / "history.jsonl"
            state.write_text(json.dumps(public), encoding="utf-8")
            history.write_text("", encoding="utf-8")
            config = {
                "state_file": str(state),
                "aggregate_state_file": str(state),
                "history_file": str(history),
                "sources": [],
                "_public_mode": True,
            }
            page = render_public_dashboard(config)
            self.assertIn("County Parcels", page)
            self.assertNotIn("secret.invalid/private", page)
            self.assertNotIn("PRIVATE-SCHEMA", page)
            self.assertNotIn("PRIVATE-FINGERPRINT", page)
            self.assertNotIn('<form method="post" action="/refresh"', page)
            self.assertIn("CLEARPARCEL GIS DATA WATCHTOWER", page)
            self.assertIn("<h1>Minnesota Open Data Watchtower</h1>", page)
            self.assertIn("summary-v2", page)
            self.assertIn("Explore Minnesota GIS data", page)
            self.assertIn("Counties with parcel observations", page)
            self.assertIn("Dataset/service entries monitored", page)
            self.assertIn("All data types · entries, not counties or unique providers", page)
            self.assertIn("One statewide source can cover many counties", page)
            self.assertIn("2/87", page)
            self.assertIn("2 via MnGeo open parcels", page)
            self.assertIn("1 via county-direct sources", page)
            self.assertIn('id="mngac-map"', page)
            self.assertIn("PUBLIC · READ ONLY", page)
            self.assertNotIn('class="sidebar"', page)

    def test_public_source_marks_data_sources_tab_active(self):
        public = sanitize_public_render_state(self._state())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state.json"
            history = root / "history.jsonl"
            state.write_text(json.dumps(public), encoding="utf-8")
            history.write_text("", encoding="utf-8")
            config = {
                "state_file": str(state),
                "aggregate_state_file": str(state),
                "history_file": str(history),
                "sources": [],
                "_public_mode": True,
            }
            page = render_public_source(config, "county-parcels-direct")
            self.assertIn('class="active" aria-current="page">Data Sources</a>', page)
            self.assertIn("Data Source — County Parcels", page)

    def test_public_overview_uses_v2_shell_and_interactive_map(self):
        public = sanitize_public_render_state(self._state())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state.json"
            history = root / "history.jsonl"
            state.write_text(json.dumps(public), encoding="utf-8")
            history.write_text("", encoding="utf-8")
            config = {
                "state_file": str(state),
                "aggregate_state_file": str(state),
                "history_file": str(history),
                "sources": [],
                "_public_mode": True,
            }
            page = render_public_dashboard(config)
            self.assertIn("CLEARPARCEL GIS DATA WATCHTOWER", page)
            self.assertIn("<h1>Minnesota Open Data Watchtower</h1>", page)
            self.assertIn("Explore Minnesota GIS data", page)
            self.assertIn('class="summary-v2"', page)
            self.assertIn('id="mngac-map"', page)
            self.assertNotIn('class="sidebar"', page)

    def test_public_map_exposes_county_buttons_and_a_labeled_list_alternative(self):
        from clearparcel.datawatch.dashboard import _mngac_map_svg
        svg = _mngac_map_svg()
        self.assertIn('role="group" aria-label="Interactive Minnesota county map"', svg)
        self.assertIn('role="button"', svg)
        state = sanitize_public_render_state(self._state())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_file = root / "state.json"
            history = root / "history.jsonl"
            state_file.write_text(json.dumps(state), encoding="utf-8")
            history.write_text("", encoding="utf-8")
            page = render_mngac({"state_file": str(state_file), "history_file": str(history),
                                 "sources": [], "_public_mode": True})
        self.assertIn('id="mngac-county-select"', page)
        self.assertIn("Choose county", page)

    def test_public_cache_serves_last_snapshot_and_caches_rendered_export(self):
        class Storage:
            def __init__(self):
                self.fail = False
            def download(self, name, destination):
                if self.fail:
                    return False
                Path(destination).write_text(json.dumps(PublicDashboardTests()._state()), encoding="utf-8")
                return True
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            storage = Storage()
            with patch.dict("os.environ", {"WATCHTOWER_PUBLIC_WORKDIR": str(root),
                                            "WATCHTOWER_PUBLIC_REFRESH_SECONDS": "5"}):
                with patch("clearparcel.datawatch.public_dashboard.backend_from_env", return_value=storage):
                    cache = _PublicStateCache()
            cache.refresh(force=True)
            saved = cache.public_path.read_bytes()
            storage.fail = True
            cache.refresh(force=True)
            self.assertTrue(cache.stale)
            self.assertEqual(cache.public_path.read_bytes(), saved)
            with patch("clearparcel.datawatch.public_dashboard._statewide_snapshot", return_value={"sources": []}) as snapshot, \
                 patch("clearparcel.datawatch.public_dashboard._snapshot_xlsx", return_value=b"xlsx") as export:
                self.assertEqual(cache.snapshot_xlsx(), b"xlsx")
                self.assertEqual(cache.snapshot_xlsx(), b"xlsx")
            self.assertEqual(snapshot.call_count, 1)
            self.assertEqual(export.call_count, 1)

    def test_public_source_uses_sources_tab_and_readable_timestamp(self):
        raw = self._state()
        public = sanitize_public_render_state(raw)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state.json"
            history = root / "history.jsonl"
            state.write_text(json.dumps(public), encoding="utf-8")
            history.write_text("", encoding="utf-8")
            config = {
                "state_file": str(state),
                "aggregate_state_file": str(state),
                "history_file": str(history),
                "sources": [],
                "_public_mode": True,
            }
            page = render_public_source(config, "county-parcels-direct")
            self.assertIn('<a href="/#datasets" class="active" aria-current="page">Data Sources</a>', page)
            self.assertNotIn(raw["sources"]["county-parcels-direct"]["checked_at"], page)

    def test_private_layout_does_not_use_public_v2_shell(self):
        page = _layout("Private dashboard", "<p>private</p>", static=False)
        self.assertIn('class="sidebar"', page)
        self.assertNotIn("CLEARPARCEL GIS DATA WATCHTOWER", page)
        self.assertNotIn('class="summary-v2"', page)

    def test_public_county_index_hides_refresh_control(self):
        public = sanitize_public_render_state(self._state())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state.json"
            history = root / "history.jsonl"
            state.write_text(json.dumps(public), encoding="utf-8")
            history.write_text("", encoding="utf-8")
            config = {
                "state_file": str(state),
                "aggregate_state_file": str(state),
                "history_file": str(history),
                "sources": [],
                "_public_mode": True,
            }
            page = render_counties(config)
            self.assertIn("Minnesota county dashboards", page)
            self.assertIn("Monitoring coverage", page)
            self.assertIn("County-direct access", page)
            self.assertIn("Statewide open access", page)
            self.assertIn("Fee-based parcel data", page)
            self.assertIn("Available free through MnGeo Plan Parcels Open", page)
            self.assertNotIn('<form method="post" action="/refresh"', page)

    def test_county_detail_separates_monitoring_from_parcel_access_research(self):
        public = sanitize_public_render_state(self._state())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state.json"
            history = root / "history.jsonl"
            state.write_text(json.dumps(public), encoding="utf-8")
            history.write_text("", encoding="utf-8")
            config = {
                "state_file": str(state),
                "aggregate_state_file": str(state),
                "history_file": str(history),
                "sources": [],
                "_public_mode": True,
            }
            page = render_county(config, "winona")
            self.assertIn("Monitoring coverage", page)
            self.assertIn("Monitoring path", page)
            self.assertIn("MnGeo Plan Parcels Open", page)
            self.assertIn("Parcel dataset access", page)
            self.assertIn("County-direct access:", page)
            self.assertIn("Fee-based parcel data", page)
            self.assertIn("Statewide open access:", page)
            self.assertIn("Available free through MnGeo Plan Parcels Open", page)
            self.assertIn("County parcel dataset fee:", page)
            self.assertIn("GIS Data Set - Parcels", page)

    def test_feedback_maps_share_classifier_and_entries_count_all_data_types(self):
        from unittest.mock import patch
        from clearparcel.datawatch.dashboard import render_mngac
        from clearparcel.datawatch.county_profile_panel import percentage_color_js, percentage_legend
        state = self._state()
        state["sources"]["imagery"] = {"id": "imagery", "name": "Imagery", "category": "Imagery", "status": "ok"}
        public = sanitize_public_render_state(state)
        with patch("clearparcel.datawatch.public_dashboard._dashboard_state", return_value=public):
            overview = render_public_dashboard({"_public_mode": True})
        with patch("clearparcel.datawatch.dashboard._dashboard_state", return_value=public):
            mngac = render_mngac({"_public_mode": True})
        # Two parcel entries cover two counties, including overlap; imagery adds an entry only.
        self.assertIn('Dataset/service entries monitored</div><div class="metric">3</div>', overview)
        self.assertIn('Counties with parcel observations</div><div class="metric">2/87</div>', overview)
        self.assertIn("2 via MnGeo open parcels · 1 via county-direct sources · each county counted once", overview)
        for page in (overview, mngac):
            self.assertIn("<h1>Minnesota Open Data Watchtower</h1>", page)
            self.assertIn(percentage_color_js(), page)
        self.assertIn(json.dumps(percentage_legend()), overview)
        self.assertIn(percentage_legend(), mngac)
        self.assertIn("const fill=percentageColor", overview)
        self.assertIn("const color=percentageColor", mngac)
        self.assertIn(":fill(d&&d.pct)", overview)
        self.assertIn("const v=valueFor(p.dataset.county,key); p.style.fill=color(v)", mngac)
        for key in ("__overall__", "__mandatory__", "__fields_with_values__"):
            self.assertIn("if(key==='" + key + "')", mngac)
        self.assertIn("const f=(c.fields||{})[key]", mngac)


if __name__ == "__main__":
    unittest.main()
