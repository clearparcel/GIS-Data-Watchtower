import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_ROOT))

import clearparcel.datawatch.watch as datawatch
import clearparcel.datawatch.dashboard as datawatch_dashboard
from clearparcel.datawatch.watch import _compare, load_config as load_data_config, load_history as load_data_history

class DataWatchTests(unittest.TestCase):

    def test_data_source_registry_loads(self):
        config = load_data_config(TOOLS_ROOT / 'config' / 'example_sources.json')
        self.assertGreaterEqual(len(config['sources']), 2)
        self.assertEqual(len({x['id'] for x in config['sources']}), len(config['sources']))
        ids = {x['id'] for x in config['sources']}
        self.assertIn('example-arcgis-layer', ids)
        self.assertIn('example-wms', ids)

    def test_schema_change_is_warning(self):
        changes = _compare({'schema_hash': 'old', 'feature_count': 10}, {'schema_hash': 'new', 'feature_count': 12})
        self.assertTrue(any((x['severity'] == 'warn' and x['type'] == 'schema' for x in changes)))
        self.assertTrue(any((x['severity'] == 'info' and x['type'] == 'feature_count' for x in changes)))

    def test_wfs_and_sda_parsers(self):
        from unittest.mock import patch
        wfs_xml = b"<?xml version='1.0'?><wfs:WFS_Capabilities xmlns:wfs='http://www.opengis.net/wfs'><FeatureTypeList><FeatureType><Name>mapunitpoly</Name></FeatureType><FeatureType><Name>surveyareapoly</Name></FeatureType></FeatureTypeList></wfs:WFS_Capabilities>"
        with patch.object(datawatch, '_request', return_value=(wfs_xml, {'status': 200, 'transport': 'test'})):
            wfs = datawatch._wfs({'url': 'https://example.invalid/wfs', 'expected_feature_types': ['mapunitpoly', 'surveyareapoly']}, 1)
        self.assertFalse(wfs['problems'])
        self.assertEqual(wfs['feature_type_count'], 2)
        with patch.object(datawatch, '_post_json', return_value=({'Table': [['survey_count', 'latest_saverest'], ['92', '2026-05-05']]}, {'status': 200, 'transport': 'test'})):
            sda = datawatch._sda_query({'url': 'https://example.invalid/post', 'query': 'select 1', 'expected_columns': ['survey_count', 'latest_saverest'], 'tracked_values': ['survey_count', 'latest_saverest']}, 1)
        self.assertEqual(sda['tracked_values']['survey_count'], 92)
        self.assertEqual(sda['tracked_values']['latest_saverest'], '2026-05-05')

    def test_alerts_separate_active_from_recovery_events(self):
        previous = {'a': {'status': 'error'}, 'b': {'status': 'ok'}}
        current = {'a': {'status': 'ok', 'name': 'A', 'changes': []}, 'b': {'status': 'error', 'name': 'B', 'error': 'down', 'changes': []}}
        active, events = datawatch._build_alerts(previous, current, {'a', 'b'}, 'now')
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['source'], 'b')
        self.assertTrue(any((x['type'] == 'recovered' and x['source'] == 'a' for x in events)))

    def test_history_reads_rotated_files_and_filters_source(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            history = root / 'history.jsonl'
            rotated = root / 'history.jsonl.1'
            rotated.write_text(json.dumps({'generated_at': '2026-09-24T00:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'sources': {'soil': {'name': 'Soils', 'status': 'ok', 'feature_count': 90, 'tracked_values': {'latest': '2026-05-01'}, 'schema_hash': 'a', 'changes': []}}}) + '\n', encoding='utf-8')
            history.write_text(json.dumps({'generated_at': '2026-09-25T00:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'sources': {'soil': {'name': 'Soils', 'status': 'ok', 'feature_count': 92, 'tracked_values': {'latest': '2026-05-05'}, 'schema_hash': 'a', 'changes': [{'severity': 'info', 'type': 'feature_count'}]}}}) + '\n', encoding='utf-8')
            result = load_data_history({'history_file': str(history)}, source_filter='soil', limit=10)
            self.assertEqual(result['entry_count'], 2)
            self.assertEqual(result['entries'][0]['feature_count'], 90)
            self.assertEqual(result['entries'][1]['feature_count'], 92)
            self.assertEqual(result['entries'][1]['tracked_values']['latest'], '2026-05-05')

    def test_filtered_check_preserves_other_saved_sources(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            history = root / 'history.jsonl'
            state.write_text(json.dumps({'schema_version': 1, 'generated_at': '2026-09-25T00:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 2, 'warn': 0, 'error': 0}, 'sources': {'a': {'id': 'a', 'name': 'A', 'status': 'ok', 'schema_hash': 'old-a'}, 'b': {'id': 'b', 'name': 'B', 'status': 'ok', 'schema_hash': 'old-b'}}}), encoding='utf-8')
            config = {'state_file': str(state), 'history_file': str(history), 'timeout_seconds': 1, 'retries': 0, 'sources': [{'id': 'a', 'name': 'A', 'kind': 'arcgis_service', 'url': 'https://example.invalid'}]}
            original = datawatch._source_check
            try:
                datawatch._source_check = lambda source, timeout: {'schema_hash': 'new-a', 'problems': []}
                datawatch.check_sources(config, source_filter='a', save=True)
            finally:
                datawatch._source_check = original
            saved = json.loads(state.read_text(encoding='utf-8'))
            self.assertIn('a', saved['sources'])
            self.assertIn('b', saved['sources'])

    def test_adapter_aliases_support_public_style_names(self):
        self.assertEqual(datawatch._adapter_name({'adapter': 'arcgis-feature-service'}), 'arcgis_layer')
        self.assertEqual(datawatch._adapter_name({'kind': 'arcgis_service'}), 'arcgis_service')

    def test_observation_fingerprint_ignores_transport_noise(self):
        first = {'schema_hash': 'abc', 'feature_count': 100, 'http_status': 200, 'transport': 'urllib', 'problems': []}
        second = {'schema_hash': 'abc', 'feature_count': 100, 'http_status': 200, 'transport': 'curl-fallback', 'problems': []}
        self.assertEqual(datawatch._observation_fingerprint(first), datawatch._observation_fingerprint(second))

    def test_feature_count_threshold_promotes_material_change_to_warning(self):
        changes = _compare({'schema_hash': 'same', 'feature_count': 100}, {'schema_hash': 'same', 'feature_count': 112}, {'thresholds': {'feature_count_change_percent': 10}})
        count_change = next((x for x in changes if x['type'] == 'feature_count'))
        self.assertEqual(count_change['severity'], 'warn')
        self.assertEqual(count_change['delta'], 12)
        self.assertAlmostEqual(count_change['delta_percent'], 12.0)

    def test_dashboard_renders_saved_state_and_source_detail(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            history = root / 'history.jsonl'
            state.write_text(json.dumps({'schema_version': 2, 'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'active_alerts': [], 'sources': {'sample': {'id': 'sample', 'name': 'Sample Parcels', 'status': 'ok', 'adapter': 'arcgis_layer', 'feature_count': 123, 'elapsed_ms': 45, 'checked_at': '2026-10-04T12:00:00+00:00', 'schema_hash': 'schema', 'observation_fingerprint': 'obs', 'provenance': {'source_url': 'https://example.invalid', 'observed_at': '2026-10-04T12:00:00+00:00'}, 'changes': []}}}), encoding='utf-8')
            history.write_text(json.dumps({'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'sources': {'sample': {'name': 'Sample Parcels', 'status': 'ok', 'feature_count': 123, 'elapsed_ms': 45, 'changes': []}}}) + '\n', encoding='utf-8')
            config = {'state_file': str(state), 'history_file': str(history)}
            overview = datawatch_dashboard.render_dashboard(config)
            detail = datawatch_dashboard.render_source(config, 'sample')
            self.assertIn('GIS Data Watchtower', overview)
            self.assertIn('Sample Parcels', overview)
            self.assertIn('123', overview)
            self.assertIn('Technical details', detail)
            self.assertIn('Check history', detail)

    def test_static_dashboard_sanitizes_operational_metadata(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            history = root / 'history.jsonl'
            state.write_text(json.dumps({'schema_version': 2, 'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'active_alerts': [{'message': 'internal detail'}], 'sources': {'sample': {'id': 'sample', 'name': 'Sample Parcels', 'status': 'ok', 'adapter': 'arcgis_layer', 'url': 'https://secret.example.invalid/internal', 'feature_count': 123, 'checked_at': '2026-10-04T12:00:00+00:00', 'schema_hash': 'schema', 'observation_fingerprint': 'obs', 'transport': 'curl', 'elapsed_ms': 99, 'provenance': {'source_url': 'https://secret.example.invalid/internal'}, 'changes': []}}}), encoding='utf-8')
            history.write_text('', encoding='utf-8')
            output = root / 'site'
            result = datawatch_dashboard.build_static_site({'state_file': str(state), 'history_file': str(history)}, output)
            self.assertEqual(result['source_count'], 1)
            page = (output / 'index.html').read_text(encoding='utf-8')
            payload = json.loads((output / 'state.json').read_text(encoding='utf-8'))
            self.assertIn('Sample Parcels', page)
            self.assertNotIn('Run source check', page)
            all_html = '\n'.join((p.read_text(encoding='utf-8') for p in output.glob('*.html')))
            self.assertNotIn('Run source check', all_html)
            self.assertNotIn('secret.example.invalid', all_html)
            self.assertNotIn('secret.example.invalid', json.dumps(payload))
            self.assertNotIn('provenance', json.dumps(payload))
            self.assertNotIn('elapsed_ms', json.dumps(payload))

    def test_dashboard_v03_renders_metadata_stats_filters_and_charts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            history = root / 'history.jsonl'
            state.write_text(json.dumps({'schema_version': 2, 'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'active_alerts': [], 'sources': {'sample': {'id': 'sample', 'name': 'Sample Parcels', 'status': 'ok', 'adapter': 'arcgis_layer', 'provider': 'Sample County', 'category': 'Parcels', 'feature_count': 105, 'elapsed_ms': 40, 'checked_at': '2026-10-04T12:00:00+00:00', 'geometry_type': 'esriGeometryPolygon', 'wkid': 26915, 'field_count': 20, 'schema_hash': 'schema', 'observation_fingerprint': 'obs', 'provenance': {'source_url': 'https://example.invalid', 'observed_at': '2026-10-04T12:00:00+00:00'}, 'changes': [{'type': 'feature_count', 'severity': 'info'}]}}}), encoding='utf-8')
            rows = [{'generated_at': '2026-10-01T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'sources': {'sample': {'name': 'Sample Parcels', 'status': 'ok', 'feature_count': 100, 'elapsed_ms': 55, 'changes': []}}}, {'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'sources': {'sample': {'name': 'Sample Parcels', 'status': 'ok', 'feature_count': 105, 'elapsed_ms': 40, 'changes': [{'type': 'feature_count'}]}}}]
            history.write_text('\n'.join((json.dumps(x) for x in rows)) + '\n', encoding='utf-8')
            config = {'state_file': str(state), 'history_file': str(history), 'sources': [{'id': 'sample', 'provider': 'Sample County', 'category': 'Parcels'}]}
            overview = datawatch_dashboard.render_dashboard(config)
            detail = datawatch_dashboard.render_source(config, 'sample')
            self.assertIn('Sample County', overview)
            self.assertIn('Days since data changed', overview)
            self.assertIn('filterRows()', overview)
            self.assertIn('+5', overview)
            self.assertIn('Record-count history', detail)
            self.assertIn('Response-time history', detail)
            self.assertIn('<svg', detail)
            self.assertIn('Recent reliability', detail)

    def test_dashboard_v04_municipal_theme_charts_and_all_counties(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            history = root / 'history.jsonl'
            state.write_text(json.dumps({'schema_version': 2, 'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'active_alerts': [], 'sources': {'mn-wabasha-parcels': {'id': 'mn-wabasha-parcels', 'name': 'Wabasha County Parcels', 'provider': 'Wabasha County / MnGeo', 'category': 'Parcels', 'county_slug': 'wabasha', 'status': 'ok', 'feature_count': 10, 'elapsed_ms': 25, 'checked_at': '2026-10-04T12:00:00+00:00', 'changes': []}}}), encoding='utf-8')
            history.write_text('', encoding='utf-8')
            config = {'state_file': str(state), 'history_file': str(history), 'sources': [{'id': 'mn-wabasha-parcels', 'provider': 'Wabasha County / MnGeo', 'category': 'Parcels'}]}
            overview = datawatch_dashboard.render_dashboard(config)
            counties = datawatch_dashboard.render_counties(config)
            wabasha = datawatch_dashboard.render_county(config, 'wabasha')
            aitkin = datawatch_dashboard.render_county(config, 'aitkin')
            self.assertIn('--navy:#17324d', overview)
            self.assertIn('--accent:#0b6fa4', overview)
            self.assertIn('Sources taking longest to respond', overview)
            self.assertIn('Data sources by category', overview)
            self.assertEqual(len(datawatch_dashboard._load_counties()), 87)
            self.assertIn('Wabasha County', counties)
            self.assertIn('Yellow Medicine County', counties)
            self.assertIn('Wabasha County Parcels', wabasha)
            self.assertIn('A usable parcel-data source has not been found yet', aitkin)

    def test_all_minnesota_counties_have_mngeo_contact_records(self):
        contacts = datawatch_dashboard._load_county_contacts()
        counties = datawatch_dashboard._load_counties()
        self.assertEqual(len(counties), 87)
        self.assertEqual(len(contacts), 87)
        wabasha = datawatch_dashboard.render_county({'state_file': str(TOOLS_ROOT / 'datawatch' / 'state.json'), 'history_file': str(TOOLS_ROOT / 'datawatch' / 'history.jsonl'), 'sources': []}, 'wabasha')
        self.assertIn('County GIS contacts', wabasha)
        self.assertIn('Minnesota Geospatial Information Office', wabasha)

    def test_arcgis_county_catalog_and_county_status(self):
        from unittest.mock import patch
        payload = {'features': [{'attributes': {'countyname': 'Aitkin', 'acqdate': 1780617600000, 'rundate': 1783296000000, 'data_url': 'https://example.invalid/a.zip', 'viewer_url': 'https://example.invalid/a', 'gac_open_approval': 'true'}}, {'attributes': {'countyname': 'Roseau', 'acqdate': None, 'rundate': 1783296000000, 'data_url': None, 'viewer_url': None, 'gac_open_approval': 'false'}}]}
        with patch.object(datawatch, '_json_request', return_value=(payload, {'status': 200, 'transport': 'test'})):
            result = datawatch._arcgis_county_catalog({'url': 'https://example.invalid/0', 'expected_count': 2}, 1)
        self.assertEqual(result['county_record_count'], 2)
        state = {'sources': {'mn-parcel-county-catalog': {'status': 'ok', 'county_records': result['county_records']}}}
        aitkin = datawatch_dashboard._county_status({}, {'name': 'Aitkin', 'slug': 'aitkin'}, state)
        roseau = datawatch_dashboard._county_status({}, {'name': 'Roseau', 'slug': 'roseau'}, state)
        self.assertEqual(aitkin['status'], 'catalog')
        self.assertEqual(roseau['status'], 'needs-source')

    def test_dashboard_v05_friendly_county_charts_and_snapshots(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            history = root / 'history.jsonl'
            state.write_text(json.dumps({'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'active_alerts': [], 'sources': {'mn-parcel-county-catalog': {'status': 'ok', 'county_records': {'Aitkin': {'countyname': 'Aitkin', 'acqdate': 1780617600000, 'rundate': 1783296000000, 'data_url': 'https://example.invalid/a.zip', 'viewer_url': 'https://example.invalid/a', 'gac_open_approval': 'true'}}}}}), encoding='utf-8')
            history.write_text('', encoding='utf-8')
            config = {'state_file': str(state), 'history_file': str(history), 'sources': []}
            page = datawatch_dashboard.render_counties(config)
            county = datawatch_dashboard.render_county(config, 'aitkin')
            snap = datawatch_dashboard._county_snapshot(config, 'aitkin')
            csv_text = datawatch_dashboard._snapshot_csv(snap)
            self.assertIn('County parcel-data availability', page)
            self.assertIn('How recently county parcel data was updated', page)
            self.assertIn('Download statewide snapshot', page)
            self.assertIn('County parcel update information', county)
            self.assertIn('Last county update', county)
            self.assertIn('Download county snapshot', county)
            self.assertNotIn('MnGeo parcel metadata', county)
            self.assertEqual(snap['county'], 'Aitkin')
            self.assertIn('last_county_update', csv_text)

    def test_dashboard_central_time_primary_utc_secondary_and_direct_counties(self):
        value = '2026-10-04T12:00:00+00:00'
        rendered = datawatch_dashboard._format_time_pair(value)
        self.assertIn('CDT', rendered)
        self.assertIn('UTC', rendered)
        fields = datawatch_dashboard._snapshot_time_fields(value, 'checked')
        self.assertTrue(fields['checked_central'].endswith('-05:00'))
        self.assertTrue(fields['checked_utc'].endswith('+00:00'))
        cfg = load_data_config(TOOLS_ROOT / 'config' / 'example_sources.json')
        ids = {x['id'] for x in cfg['sources']}
        self.assertEqual(ids, {'example-arcgis-layer', 'example-wms'})

    def test_dashboard_v06_admin_shell_central_time_and_direct_counties(self):
        value = '2026-10-04T12:00:00+00:00'
        rendered = datawatch_dashboard._format_time_pair(value)
        self.assertIn('CDT', rendered)
        self.assertIn('UTC', rendered)
        fields = datawatch_dashboard._snapshot_time_fields(value, 'checked')
        self.assertTrue(fields['checked_central'].endswith('-05:00'))
        self.assertTrue(fields['checked_utc'].endswith('+00:00'))
        cfg = load_data_config(TOOLS_ROOT / 'config' / 'example_sources.json')
        self.assertEqual(len(cfg['sources']), 2)
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            hist = root / 'history.jsonl'
            state.write_text(json.dumps({'generated_at': value, 'overall': 'ok', 'counts': {'ok': 0, 'warn': 0, 'error': 0}, 'active_alerts': [], 'sources': {}}), encoding='utf-8')
            hist.write_text('', encoding='utf-8')
            page = datawatch_dashboard.render_dashboard({'state_file': str(state), 'history_file': str(hist), 'sources': []})
            self.assertIn('class="sidebar"', page)
            self.assertIn('Minnesota Counties', page)
            self.assertIn('Snapshots', page)
            self.assertIn('#10263b', page)

    def test_arcgis_service_discovers_parcel_layer_for_qa(self):
        from unittest.mock import patch
        service = {'name': 'County Data', 'layers': [{'id': 0, 'name': 'Roads'}, {'id': 3, 'name': 'Tax Parcels'}]}
        layer = {'name': 'Tax Parcels', 'type': 'Feature Layer', 'geometryType': 'esriGeometryPolygon', 'objectIdField': 'OBJECTID', 'fields': [{'name': 'OBJECTID', 'type': 'esriFieldTypeOID', 'nullable': False}, {'name': 'PIN', 'type': 'esriFieldTypeString', 'nullable': True}], 'extent': {'spatialReference': {'wkid': 26915}}}
        count = {'count': 1234}

        def fake(url, timeout, prefer_curl=False):
            if 'returnCountOnly' in url:
                return (count, {'status': 200, 'transport': 'test'})
            if '/3?f=json' in url:
                return (layer, {'status': 200, 'transport': 'test'})
            return (service, {'status': 200, 'transport': 'test'})
        with patch.object(datawatch, '_json_request', side_effect=fake):
            result = datawatch._arcgis_service({'url': 'https://example.invalid/FeatureServer', 'discover_parcel_layer': True}, 1)
        self.assertEqual(result['parcel_layer_id'], 3)
        self.assertEqual(result['parcel_layer_name'], 'Tax Parcels')
        self.assertEqual(result['feature_count'], 1234)
        self.assertEqual(result['field_count'], 2)

    def test_parcel_id_candidate_is_conservative(self):
        self.assertEqual(datawatch._parcel_id_candidate(['OBJECTID', 'PIN', 'OWNER']), ('PIN', 'high'))
        self.assertEqual(datawatch._parcel_id_candidate(['OBJECTID', 'ParcelLabel']), ('ParcelLabel', 'medium'))
        self.assertEqual(datawatch._parcel_id_candidate(['OBJECTID', 'OWNER']), (None, 'none'))

    def test_extent_change_and_field_candidates(self):
        previous = {'xmin': 0.0, 'ymin': 0.0, 'xmax': 100.0, 'ymax': 100.0, 'wkid': 26915}
        current = {'xmin': -1.0, 'ymin': 0.0, 'xmax': 100.0, 'ymax': 101.0, 'wkid': 26915}
        change = datawatch._extent_change(previous, current)
        self.assertAlmostEqual(change['max_extent_shift_percent'], 1.0)
        self.assertEqual(datawatch._field_candidate(['OWNER_NAME', 'SITE_ADDRESS'], ['owner_name'], ['owner']), 'OWNER_NAME')
        self.assertEqual(datawatch._field_candidate(['OWNER_NAME', 'SITE_ADDRESS'], ['site_address'], ['address']), 'SITE_ADDRESS')

    def test_geometry_sample_metrics_are_bounded_and_descriptive(self):
        from unittest.mock import patch
        payload = {'features': [{'geometry': {'rings': [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}, {'geometry': {'rings': [[[0, 0], [2, 0], [2, 2], [0, 0]], [[0.5, 0.5], [0.6, 0.5], [0.5, 0.5]]]}}, {'geometry': None}]}
        with patch.object(datawatch, '_json_request', return_value=(payload, {'status': 200, 'transport': 'test'})):
            result = datawatch._arcgis_geometry_sample('https://example.invalid/0', 1, sample_size=250)
        self.assertEqual(result['geometry_sample_size'], 3)
        self.assertEqual(result['geometry_sample_empty'], 1)
        self.assertEqual(result['geometry_sample_multipart'], 1)
        self.assertEqual(result['geometry_sample_multipart_percent'], 33.33)
        self.assertEqual(result['geometry_sample_max_vertices'], 7)

    def test_dashboard_v11_mobile_css_and_processing_telemetry(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            hist = root / 'history.jsonl'
            state.write_text(json.dumps({'generated_at': '2026-10-04T13:30:00+00:00', 'overall': 'ok', 'counts': {'ok': 0, 'warn': 0, 'error': 0}, 'active_alerts': [], 'sources': {}, 'telemetry': {'wall_ms': 1234, 'cpu_ms': 321, 'peak_python_memory_kb': 4096, 'sources_checked': 0}}), encoding='utf-8')
            hist.write_text('', encoding='utf-8')
            page = datawatch_dashboard.render_dashboard({'state_file': str(state), 'history_file': str(hist), 'sources': []})
            self.assertIn('Last check duration', page)
            self.assertIn('Memory used during check', page)
            self.assertIn('grid-template-columns:1fr', page)
            self.assertIn('grid-template-columns:repeat(3,minmax(0,1fr))', page)
            self.assertIn('overflow-x:hidden', page)

    def test_telemetry_history_is_persisted_and_rendered(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            hist = root / 'history.jsonl'
            rows = [{'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 2, 'warn': 0, 'error': 0}, 'telemetry': {'wall_ms': 1000, 'cpu_ms': 100, 'peak_python_memory_kb': 2048, 'sources_checked': 2}, 'sources': {}}, {'generated_at': '2026-10-04T13:00:00+00:00', 'overall': 'warn', 'counts': {'ok': 1, 'warn': 0, 'error': 1}, 'telemetry': {'wall_ms': 1500, 'cpu_ms': 120, 'peak_python_memory_kb': 3072, 'sources_checked': 2}, 'sources': {}}]
            hist.write_text('\n'.join((json.dumps(x) for x in rows)) + '\n', encoding='utf-8')
            state.write_text(json.dumps({'generated_at': rows[-1]['generated_at'], 'overall': 'warn', 'counts': rows[-1]['counts'], 'active_alerts': [], 'sources': {}, 'telemetry': rows[-1]['telemetry']}), encoding='utf-8')
            page = datawatch_dashboard.render_dashboard({'state_file': str(state), 'history_file': str(hist), 'sources': []})
            self.assertIn('How long Watchtower checks have taken', page)
            self.assertIn('Computer processing time used', page)
            self.assertIn('Memory used by Watchtower', page)
            self.assertIn('Checks that could not be completed', page)
            self.assertIn('<svg', page)

    def test_dashboard_v13_uses_plain_language_and_collapses_technical_details(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            hist = root / 'history.jsonl'
            state.write_text(json.dumps({'generated_at': '2026-10-04T13:30:00+00:00', 'overall': 'ok', 'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'active_alerts': [], 'sources': {'sample': {'id': 'sample', 'name': 'Sample Parcels', 'status': 'ok', 'feature_count': 100, 'elapsed_ms': 25, 'checked_at': '2026-10-04T13:30:00+00:00', 'schema_hash': 'abc', 'observation_fingerprint': 'def', 'changes': []}}}), encoding='utf-8')
            hist.write_text('', encoding='utf-8')
            config = {'state_file': str(state), 'history_file': str(hist), 'sources': []}
            overview = datawatch_dashboard.render_dashboard(config)
            detail = datawatch_dashboard.render_source(config, 'sample')
            self.assertIn('Overall status', overview)
            self.assertIn('Working normally', overview)
            self.assertIn('Data being watched', overview)
            self.assertIn('Records / change', overview)
            self.assertIn('Recent reliability', overview)
            self.assertIn('<details class="technical">', detail)
            self.assertIn('<summary>Technical details</summary>', detail)
            self.assertIn('About this data', detail)
            self.assertNotIn('>Provenance<', detail)

    def test_watchtower_user_agent_identifies_project_and_429_does_not_fallback(self):
        self.assertIn('GIS-Data-Watchtower', datawatch.USER_AGENT)
        self.assertIn('github.com/clearparcel/GIS-Data-Watchtower', datawatch.USER_AGENT)
        import urllib.error
        from unittest.mock import patch
        err = urllib.error.HTTPError('https://example.invalid', 429, 'Too Many Requests', {'Retry-After': '60'}, None)
        with patch('urllib.request.urlopen', side_effect=err), patch.object(datawatch, '_curl_request') as fallback:
            with self.assertRaisesRegex(RuntimeError, 'HTTP 429'):
                datawatch._request('https://example.invalid', 1)
            fallback.assert_not_called()
        err.close()

    def test_post_429_stops_without_curl_fallback(self):
        import urllib.error
        from unittest.mock import patch
        err = urllib.error.HTTPError('https://example.invalid', 429, 'Too Many Requests', {'Retry-After': '120'}, None)
        with patch('urllib.request.urlopen', side_effect=err), patch('subprocess.run') as curl:
            with self.assertRaises(datawatch.ProviderRateLimitError):
                datawatch._post_json('https://example.invalid', {'x': 1}, 1)
            curl.assert_not_called()
        err.close()

    def test_rate_limit_stops_source_retry_loop(self):
        from unittest.mock import patch
        config = {'state_file': str(TOOLS_ROOT / 'datawatch' / 'test-rate-state.json'), 'history_file': str(TOOLS_ROOT / 'datawatch' / 'test-rate-history.jsonl'), 'retries': 3, 'sources': [{'id': 'rate', 'name': 'Rate', 'kind': 'arcgis_layer', 'url': 'https://example.invalid/0'}]}
        with patch.object(datawatch, 'load_state', return_value={'sources': {}}), patch.object(datawatch, '_source_check', side_effect=datawatch.ProviderRateLimitError('60')) as check:
            report = datawatch.check_sources(config, save=False)
        self.assertEqual(check.call_count, 1)
        self.assertEqual(report['sources']['rate']['attempts'], 1)
        self.assertEqual(report['sources']['rate']['status'], 'error')

    def test_state_backup_recovers_corrupt_primary(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'state.json'
            datawatch._save_json(p, {'schema_version': 2, 'sources': {'a': {'status': 'ok'}}})
            datawatch._save_json(p, {'schema_version': 2, 'sources': {'b': {'status': 'ok'}}})
            p.write_text('{broken', encoding='utf-8')
            recovered = datawatch.load_state(p)
            self.assertTrue(recovered['_state_recovered_from_backup'])
            self.assertIn('a', recovered['sources'])

    def test_watchtower_run_lock_blocks_overlap_and_recovers_stale_lock(self):
        import tempfile, time
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / 'state.json'
            lock = datawatch._acquire_run_lock(state, stale_seconds=60)
            with self.assertRaises(datawatch.WatchtowerRunLockedError):
                datawatch._acquire_run_lock(state, stale_seconds=60)
            datawatch._release_run_lock(lock)
            stale = state.with_suffix('.json.lock')
            stale.write_text('stale', encoding='utf-8')
            old = time.time() - 120
            import os
            os.utime(stale, (old, old))
            lock2 = datawatch._acquire_run_lock(state, stale_seconds=60)
            self.assertTrue(lock2.exists())
            datawatch._release_run_lock(lock2)

    def test_watchtower_run_lock_releases_after_unexpected_failure(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / 'state.json'
            config = {'state_file': str(state), 'history_file': str(Path(td) / 'history.jsonl'), 'sources': []}
            with patch.object(datawatch, '_check_sources_unlocked', side_effect=RuntimeError('boom')):
                with self.assertRaisesRegex(RuntimeError, 'boom'):
                    datawatch.check_sources(config, save=False)
            self.assertFalse(state.with_suffix('.json.lock').exists())

    def test_watchtower_runtime_paths_can_be_overridden_for_cloud_runtime(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / 'config.json'
            cfg_path.write_text(json.dumps({'state_file': 'C:/old/state.json', 'history_file': 'C:/old/history.jsonl', 'sources': []}), encoding='utf-8')
            with patch.dict('os.environ', {'CLEARPARCEL_WATCHTOWER_STATE_FILE': '/tmp/state.json', 'CLEARPARCEL_WATCHTOWER_HISTORY_FILE': '/tmp/history.jsonl'}):
                cfg = datawatch.load_config(cfg_path)
            self.assertEqual(cfg['state_file'], '/tmp/state.json')
            self.assertEqual(cfg['history_file'], '/tmp/history.jsonl')

    def test_dashboard_time_helpers_are_defined_once(self):
        source = (TOOLS_ROOT / 'clearparcel' / 'datawatch' / 'dashboard.py').read_text(encoding='utf-8')
        self.assertEqual(source.count('CENTRAL_TZ = ZoneInfo("America/Chicago")'), 1)
        self.assertEqual(source.count('def _format_time_pair('), 1)
        self.assertEqual(source.count('def _snapshot_time_fields('), 1)

    def test_snapshot_csv_neutralizes_formula_cells(self):
        self.assertEqual(datawatch_dashboard._csv_safe('=HYPERLINK("x")'), '\'=HYPERLINK("x")')
        self.assertEqual(datawatch_dashboard._csv_safe('+cmd'), "'+cmd")

    def test_provider_http_refusals_do_not_use_fallback_transport(self):
        import urllib.error
        from unittest.mock import patch
        for code in (403, 429):
            err = urllib.error.HTTPError('https://example.invalid', code, 'Denied', {'Retry-After': '60'}, None)
            with patch('urllib.request.urlopen', side_effect=err), patch.object(datawatch, '_curl_request') as fallback:
                with self.assertRaisesRegex(RuntimeError, f'HTTP {code}'):
                    datawatch._request('https://example.invalid', 1)
                fallback.assert_not_called()
            err.close()

    def test_curl_fallback_resolves_portable_executable(self):
        from unittest.mock import patch

        class CP:
            returncode = 0
            stderr = b''
            stdout = b'{}\n__CP_HTTP__200'
        with patch.object(datawatch.shutil, 'which', side_effect=lambda name: '/usr/bin/curl' if name == 'curl' else None), patch.object(datawatch.subprocess, 'run', return_value=CP()) as run:
            body, meta = datawatch._curl_request('https://example.invalid', 1)
        self.assertEqual(body, b'{}')
        self.assertEqual(meta['status'], 200)
        self.assertEqual(run.call_args.args[0][0], '/usr/bin/curl')

    def test_watchtower_config_paths_are_relative_and_portable(self):
        import tempfile, os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            (root / 'config').mkdir()
            p = root / 'config' / 'example_sources.json'
            p.write_text(json.dumps({'state_file': 'datawatch/state.json', 'history_file': 'datawatch/history.jsonl', 'sources': []}), encoding='utf-8')
            cfg = datawatch.load_config(p)
            self.assertEqual(Path(cfg['state_file']), root / 'datawatch' / 'state.json')
            self.assertEqual(Path(cfg['history_file']), root / 'datawatch' / 'history.jsonl')
            with patch.dict(os.environ, {'CLEARPARCEL_WATCHTOWER_ROOT': str(root / 'alt')}, clear=False):
                cfg2 = datawatch.load_config(p)
            self.assertEqual(Path(cfg2['state_file']), root / 'alt' / 'datawatch' / 'state.json')

    def test_public_state_api_removes_internal_watchtower_details(self):
        state = {'schema_version': 2, 'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1}, 'sources': {'x': {'id': 'x', 'name': 'X', 'provider': 'P', 'category': 'Parcels', 'status': 'ok', 'feature_count': 10, 'checked_at': 'now', 'changes': [], 'url': 'https://secret.invalid', 'schema_hash': 'abc', 'observation_fingerprint': 'def', 'wkid': 26915, 'field_names': ['A'], 'telemetry': {'x': 1}}}}
        public = datawatch_dashboard._sanitize_public_state(state)
        row = public['sources']['x']
        self.assertEqual(row['feature_count'], 10)
        for key in ('url', 'schema_hash', 'observation_fingerprint', 'wkid', 'field_names', 'telemetry', 'adapter', 'kind'):
            self.assertNotIn(key, row)

    def test_public_dashboard_requires_password_when_internet_exposure_enabled(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD', None)
            with self.assertRaisesRegex(RuntimeError, 'requires CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD'):
                datawatch_dashboard._dashboard_auth({'public_dashboard': {'internet_exposure': True}})
        with patch.dict(os.environ, {'CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD': 'test-secret'}, clear=False):
            password, user = datawatch_dashboard._dashboard_auth({'public_dashboard': {'internet_exposure': True}})
            self.assertEqual(password, 'test-secret')
            self.assertEqual(user, 'watchtower')

    def test_get_429_raises_provider_rate_limit_error(self):
        import urllib.error
        from unittest.mock import patch
        err = urllib.error.HTTPError('https://example.invalid', 429, 'Too Many Requests', {'Retry-After': '60'}, None)
        with patch('urllib.request.urlopen', side_effect=err):
            with self.assertRaises(datawatch.ProviderRateLimitError):
                datawatch._request('https://example.invalid', 1)
        err.close()

    def test_safe_url_allows_only_http_https(self):
        self.assertEqual(datawatch_dashboard._safe_url('https://example.com/x'), 'https://example.com/x')
        self.assertEqual(datawatch_dashboard._safe_url('http://example.com/x'), 'http://example.com/x')
        self.assertIsNone(datawatch_dashboard._safe_url('javascript:alert(1)'))
        self.assertIsNone(datawatch_dashboard._safe_url('data:text/html,x'))

    def test_non_loopback_dashboard_requires_password(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD', None)
            with self.assertRaisesRegex(RuntimeError, 'CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD'):
                datawatch_dashboard._dashboard_auth({'public_dashboard': {'internet_exposure': False}}, '0.0.0.0')

    def test_county_status_uses_explicit_slug_not_substring(self):
        state = {'sources': {'lake-source': {'name': 'Lake of the Woods County Parcels', 'provider': 'County', 'status': 'ok', 'county_slug': 'lake-of-the-woods'}}}
        lake = datawatch_dashboard._county_status({}, {'name': 'Lake', 'slug': 'lake'}, state)
        woods = datawatch_dashboard._county_status({}, {'name': 'Lake of the Woods', 'slug': 'lake-of-the-woods'}, state)
        self.assertEqual(lake['sources'], [])
        self.assertEqual(len(woods['sources']), 1)

    def test_arcgis_service_rejects_ambiguous_parcel_layers(self):
        from unittest.mock import patch
        service = {'name': 'County', 'layers': [{'id': 0, 'name': 'Parcels Current'}, {'id': 1, 'name': 'Tax Parcels Archive'}]}
        with patch.object(datawatch, '_json_request', return_value=(service, {'status': 200, 'transport': 'test'})):
            result = datawatch._arcgis_service({'url': 'https://example.invalid/FeatureServer', 'discover_parcel_layer': True}, 1)
        self.assertIn('multiple parcel-like layers', result['problems'][0])
        self.assertNotIn('parcel_layer_id', result)

    def test_get_429_stops_outer_retry_loop(self):
        import urllib.error
        from unittest.mock import patch
        err = urllib.error.HTTPError('https://example.invalid', 429, 'Too Many Requests', {'Retry-After': '60'}, None)
        config = {'state_file': str(TOOLS_ROOT / 'datawatch' / 'test-get-rate-state.json'), 'history_file': str(TOOLS_ROOT / 'datawatch' / 'test-get-rate-history.jsonl'), 'retries': 3, 'sources': [{'id': 'rate', 'name': 'Rate', 'kind': 'arcgis_layer', 'url': 'https://example.invalid/0'}]}
        with patch.object(datawatch, 'load_state', return_value={'sources': {}}), patch('urllib.request.urlopen', side_effect=err) as request:
            report = datawatch.check_sources(config, save=False)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(report['sources']['rate']['attempts'], 1)
        err.close()

    def test_private_lan_bind_is_allowed_without_password_but_wildcard_is_not(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD', None)
            password, user = datawatch_dashboard._dashboard_auth({'public_dashboard': {'internet_exposure': False}}, '192.168.8.236')
            self.assertIsNone(password)
            self.assertEqual(user, 'watchtower')
            with self.assertRaisesRegex(RuntimeError, 'DASHBOARD_PASSWORD'):
                datawatch_dashboard._dashboard_auth({'public_dashboard': {'internet_exposure': False}}, '0.0.0.0')

    def test_county_catalog_forwards_prefer_curl(self):
        from unittest.mock import patch
        payload = {'features': []}
        with patch.object(datawatch, '_json_request', return_value=(payload, {'status': 200, 'transport': 'test'})) as req:
            datawatch._arcgis_county_catalog({'url': 'https://example.invalid/0', 'prefer_curl': True}, 1)
        self.assertTrue(req.call_args.kwargs['prefer_curl'])

    def test_filtered_check_reports_source_scope(self):
        from unittest.mock import patch
        config = {'state_file': str(TOOLS_ROOT / 'datawatch' / 'scope-state.json'), 'history_file': str(TOOLS_ROOT / 'datawatch' / 'scope-history.jsonl'), 'sources': [{'id': 'one', 'name': 'One', 'kind': 'arcgis_layer', 'url': 'https://example.invalid/0'}]}
        with patch.object(datawatch, 'load_state', return_value={'sources': {}}), patch.object(datawatch, '_source_check', return_value={'field_names': [], 'schema_hash': 'x', 'problems': []}):
            report = datawatch.check_sources(config, source_filter='one', save=False)
        self.assertEqual(report['scope'], {'type': 'source', 'source_id': 'one'})

    def test_example_registry_is_safe_and_provider_neutral(self):
        cfg = datawatch.load_config(TOOLS_ROOT / 'config' / 'example_sources.json')
        self.assertEqual(len(cfg['sources']), 2)
        self.assertTrue(all('example.com' in x['url'] for x in cfg['sources']))
        self.assertTrue(all(not x.get('county_slug') for x in cfg['sources']))

    def test_excel_snapshot_export_is_valid_xlsx_package(self):
        import io, zipfile
        snapshot={"county":"Example","status":"ok","last_county_update":"2026-10-04","catalog_refresh_date":"2026-10-04","public_data_approved":True,"parcel_data_url":"https://example.com/data","parcel_viewer_url":"https://example.com/view","direct_sources":[{"name":"Parcels","status":"ok","feature_count":123,"checked_at":"2026-10-04T12:00:00+00:00"}],"contacts":[{"name":"GIS Contact","title":"GIS Manager","department":"GIS","phone":"555-0100","email":"gis@example.com"}]}
        raw=datawatch_dashboard._snapshot_xlsx(snapshot)
        self.assertTrue(raw.startswith(b"PK"))
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names=set(zf.namelist())
            self.assertIn("xl/workbook.xml",names)
            self.assertIn("xl/worksheets/sheet1.xml",names)
            workbook=zf.read("xl/workbook.xml").decode()
            self.assertIn('name="Counties"',workbook)
            self.assertIn('name="Sources"',workbook)
            self.assertIn('name="Contacts"',workbook)
            sheet=zf.read("xl/worksheets/sheet1.xml").decode()
            self.assertIn("Example",sheet)
            self.assertIn("https://example.com/data",sheet)

    def test_local_storage_round_trip(self):
        import tempfile
        from clearparcel.datawatch.storage import LocalStorage
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            source=root/"source.json"; source.write_text('{"ok":true}',encoding="utf-8")
            backend=LocalStorage(root/"objects")
            backend.upload("state.json",source)
            destination=root/"downloaded.json"
            self.assertTrue(backend.download("state.json",destination))
            self.assertEqual(destination.read_text(encoding="utf-8"),'{"ok":true}')
            self.assertFalse(backend.download("missing.json",root/"missing.json"))

    def test_storage_backend_env_validation(self):
        import os, tempfile
        from clearparcel.datawatch.storage import LocalStorage, backend_from_env
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ,{"WATCHTOWER_STORAGE":"local","WATCHTOWER_STORAGE_ROOT":td},clear=False):
                self.assertIsInstance(backend_from_env(td),LocalStorage)
            with patch.dict(os.environ,{"WATCHTOWER_STORAGE":"gcs"},clear=True):
                with self.assertRaisesRegex(RuntimeError,"WATCHTOWER_GCS_BUCKET"):
                    backend_from_env(td)

    def test_public_cli_defaults_to_example_config(self):
        import inspect
        from clearparcel.datawatch import cli
        self.assertIn("example_sources.json",str(cli._default_config()))

    def test_execution_profiles_filter_sources(self):
        from unittest.mock import patch
        config={"state_file":str(TOOLS_ROOT/"datawatch"/"profile-state.json"),"history_file":str(TOOLS_ROOT/"datawatch"/"profile-history.jsonl"),"sources":[
            {"id":"cloud","name":"Cloud","kind":"arcgis_layer","url":"https://example.invalid/0","execution_profiles":["cloud"]},
            {"id":"local","name":"Local","kind":"arcgis_layer","url":"https://example.invalid/1","execution_profiles":["local"]},
            {"id":"any","name":"Any","kind":"arcgis_layer","url":"https://example.invalid/2","execution_profiles":["any"]},
            {"id":"default","name":"Default","kind":"arcgis_layer","url":"https://example.invalid/3"},
        ]}
        details={"http_status":200,"transport":"test","layer_name":"X","geometry_type":"esriGeometryPolygon","wkid":26915,"object_id_field":"OBJECTID","field_count":1,"field_names":["OBJECTID"],"schema_hash":"x","spatial_extent":None,"problems":[]}
        with patch.object(datawatch,"load_state",return_value={"sources":{}}), patch.object(datawatch,"_source_check",return_value=details):
            result=datawatch.check_sources(config,save=False,execution_profile="cloud")
        self.assertEqual(set(result["sources"]),{"cloud","any"})

    def test_hybrid_aggregation_preserves_other_workers(self):
        from clearparcel.datawatch.aggregate import merge_states
        base={"schema_version":2,"generated_at":"old","sources":{"local":{"id":"local","status":"ok","feature_count":4,"worker":"local"}},"workers":{"local":{"checked_at":"old","source_count":1}}}
        partial={"schema_version":2,"generated_at":"new","overall":"ok","counts":{"ok":1,"warn":0,"error":0},"telemetry":{"wall_ms":10},"sources":{"cloud":{"id":"cloud","status":"ok","feature_count":8}}}
        merged=merge_states(base,partial,"cloud")
        self.assertEqual(set(merged["sources"]),{"local","cloud"})
        self.assertEqual(merged["sources"]["local"]["worker"],"local")
        self.assertEqual(merged["sources"]["cloud"]["worker"],"cloud")
        self.assertEqual(merged["counts"],{"ok":2,"warn":0,"error":0})
        self.assertEqual(merged["workers"]["cloud"]["source_count"],1)

    def test_hybrid_aggregation_replaces_only_worker_observations(self):
        from clearparcel.datawatch.aggregate import merge_states
        base={"sources":{"a":{"id":"a","status":"error","worker":"cloud"},"b":{"id":"b","status":"ok","worker":"local"}}}
        partial={"generated_at":"new","overall":"ok","counts":{"ok":1},"sources":{"a":{"id":"a","status":"ok"}}}
        merged=merge_states(base,partial,"cloud")
        self.assertEqual(merged["sources"]["a"]["status"],"ok")
        self.assertEqual(merged["sources"]["b"]["status"],"ok")

    def test_run_wrapper_preserves_warning_exit_code(self):
        wrapper = (TOOLS_ROOT / 'run-datawatch.cmd').read_text(encoding='utf-8')
        self.assertIn('exit /b %RC%', wrapper)
        self.assertNotIn('if %RC% GEQ 2', wrapper)

    def test_watchtower_ci_covers_standalone_package_without_live_provider_check(self):
        workflow = (TOOLS_ROOT / ".github" / "workflows" / "watchtower-ci.yml").read_text(encoding="utf-8")
        self.assertIn("pip install --disable-pip-version-check -e .", workflow)
        self.assertIn("unittest discover -s tests", workflow)
        self.assertNotIn(" check --no-save", workflow)

    def test_refresh_requires_matching_csrf_token_and_same_origin(self):
        self.assertTrue(datawatch_dashboard._valid_refresh_request('abc', 'abc', 'same-origin'))
        self.assertFalse(datawatch_dashboard._valid_refresh_request('wrong', 'abc', 'same-origin'))
        self.assertFalse(datawatch_dashboard._valid_refresh_request('abc', 'abc', 'cross-site'))

    def test_get_429_uses_rate_limit_exception_and_stops_retry_loop(self):
        import urllib.error
        from unittest.mock import patch
        err = urllib.error.HTTPError('https://example.invalid', 429, 'Too Many Requests', {'Retry-After': '60'}, None)
        with patch('urllib.request.urlopen', side_effect=err):
            with self.assertRaises(datawatch.ProviderRateLimitError):
                datawatch._request('https://example.invalid', 1)
        err.close()
        config = {'state_file': str(TOOLS_ROOT / 'datawatch' / 'test-get429-state.json'), 'history_file': str(TOOLS_ROOT / 'datawatch' / 'test-get429-history.jsonl'), 'retries': 3, 'sources': [{'id': 'rate', 'name': 'Rate', 'kind': 'arcgis_layer', 'url': 'https://example.invalid/0'}]}
        with patch.object(datawatch, 'load_state', return_value={'sources': {}}), patch.object(datawatch, '_source_check', side_effect=datawatch.ProviderRateLimitError('60')) as check:
            report = datawatch.check_sources(config, save=False)
        self.assertEqual(check.call_count, 1)
        self.assertEqual(report['sources']['rate']['attempts'], 1)

    def test_safe_provider_urls_only_allow_http_https(self):
        self.assertEqual(datawatch_dashboard._safe_url('https://example.com/x'), 'https://example.com/x')
        self.assertEqual(datawatch_dashboard._safe_url('http://example.com/x'), 'http://example.com/x')
        self.assertIsNone(datawatch_dashboard._safe_url('javascript:alert(1)'))
        self.assertIsNone(datawatch_dashboard._safe_url('data:text/html,x'))
        self.assertIsNone(datawatch_dashboard._safe_url('//example.com/x'))

    def test_nonloopback_auth_policy_allows_private_lan_but_blocks_wildcard_without_password(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD', None)
            self.assertEqual(datawatch_dashboard._dashboard_auth({'public_dashboard': {'internet_exposure': False}}, '192.168.8.236'), (None, 'watchtower'))
            with self.assertRaisesRegex(RuntimeError, 'requires CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD'):
                datawatch_dashboard._dashboard_auth({'public_dashboard': {'internet_exposure': False}}, '0.0.0.0')

    def test_county_status_uses_explicit_slug_not_substring(self):
        state = {'sources': {'lake': {'name': 'Lake County Parcels', 'county_slug': 'lake', 'status': 'ok'}, 'red-lake': {'name': 'Red Lake County Parcels', 'county_slug': 'red-lake', 'status': 'ok'}}}
        lake = datawatch_dashboard._county_status({}, {'name': 'Lake', 'slug': 'lake'}, state)
        red = datawatch_dashboard._county_status({}, {'name': 'Red Lake', 'slug': 'red-lake'}, state)
        self.assertEqual([x['name'] for x in lake['sources']], ['Lake County Parcels'])
        self.assertEqual([x['name'] for x in red['sources']], ['Red Lake County Parcels'])

    def test_arcgis_service_refuses_ambiguous_parcel_layer_without_explicit_id(self):
        from unittest.mock import patch
        service = {'name': 'County', 'layers': [{'id': 0, 'name': 'Parcels Current'}, {'id': 1, 'name': 'Tax Parcels Archive'}]}
        with patch.object(datawatch, '_json_request', return_value=(service, {'status': 200, 'transport': 'test'})):
            result = datawatch._arcgis_service({'url': 'https://example.invalid/FeatureServer', 'discover_parcel_layer': True}, 1)
        self.assertIsNone(result.get('parcel_layer_id'))
        self.assertTrue(any(('multiple parcel-like layers' in x for x in result['problems'])))

    def test_filtered_check_result_is_explicitly_source_scoped(self):
        from unittest.mock import patch
        config = {'state_file': str(TOOLS_ROOT / 'datawatch' / 'scope-state.json'), 'history_file': str(TOOLS_ROOT / 'datawatch' / 'scope-history.jsonl'), 'sources': [{'id': 'one', 'name': 'One', 'kind': 'arcgis_layer', 'url': 'https://example.invalid/0'}]}
        details = {'http_status': 200, 'transport': 'test', 'layer_name': 'One', 'geometry_type': 'esriGeometryPolygon', 'wkid': 26915, 'object_id_field': 'OBJECTID', 'field_count': 1, 'field_names': ['OBJECTID'], 'schema_hash': 'x', 'spatial_extent': None, 'problems': []}
        with patch.object(datawatch, 'load_state', return_value={'sources': {}}), patch.object(datawatch, '_source_check', return_value=details):
            result = datawatch.check_sources(config, source_filter='one', save=False)
        self.assertEqual(result['scope'], {'type': 'source', 'source_id': 'one'})
