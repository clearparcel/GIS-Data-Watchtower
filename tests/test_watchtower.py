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

    def test_public_example_uses_supported_configuration_keys(self):
        example = json.loads((TOOLS_ROOT / 'config' / 'example_sources.json').read_text(encoding='utf-8'))
        self.assertEqual(example.get('history_max_mb'), 5)
        self.assertNotIn('history_max_lines', example)
        self.assertNotIn('history_max_bytes', example)
        self.assertNotIn('raw_state_api', example.get('public_dashboard', {}))
        arcgis = next(x for x in example['sources'] if x['id'] == 'example-arcgis-layer')
        self.assertIn('required_fields', arcgis)
        self.assertNotIn('expected_fields', arcgis)

    def test_mngac_reference_schema_has_all_official_fields_and_boundaries(self):
        schema = json.loads((TOOLS_ROOT / 'clearparcel' / 'datawatch' / 'mngac_parcel_fields.json').read_text(encoding='utf-8'))
        fields = schema['fields']
        self.assertEqual(schema['standard']['version'], '1.1.3')
        self.assertEqual(len(fields), 91)
        self.assertEqual(len({x['field'] for x in fields}), 91)
        self.assertEqual({x['inclusion'] for x in fields}, {'Mandatory', 'Conditional', 'If Available', 'Optional'})
        self.assertIn('COUNTY_PIN', {x['field'] for x in fields})
        self.assertIn('OWNER_NAME', {x['field'] for x in fields})
        self.assertIn('EXP_DATE', {x['field'] for x in fields})
        self.assertIn('PRIN_MER', {x['field'] for x in fields})

        boundaries = json.loads((TOOLS_ROOT / 'clearparcel' / 'datawatch' / 'minnesota_county_boundaries.json').read_text(encoding='utf-8'))
        counties = json.loads((TOOLS_ROOT / 'clearparcel' / 'datawatch' / 'minnesota_counties.json').read_text(encoding='utf-8'))['counties']
        self.assertEqual(len(boundaries['counties']), 87)
        self.assertEqual(
            {x['name'] for x in boundaries['counties']},
            {x['name'] for x in counties},
        )
        self.assertTrue(all(x.get('rings') for x in boundaries['counties']))

    def test_load_config_resolves_and_overrides_aggregate_state_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_dir = root / 'config'
            config_dir.mkdir()
            config_path = config_dir / 'watchtower.json'
            config_path.write_text(json.dumps({
                'state_file': 'datawatch/state.json',
                'history_file': 'datawatch/history.jsonl',
                'aggregate_state_file': 'datawatch/aggregate.json',
                'sources': [],
            }), encoding='utf-8')
            loaded = load_data_config(config_path)
            self.assertEqual(Path(loaded['aggregate_state_file']), (root / 'datawatch' / 'aggregate.json').resolve())
            override = root / 'override.json'
            with patch.dict(os.environ, {'CLEARPARCEL_WATCHTOWER_AGGREGATE_STATE_FILE': str(override)}):
                loaded = load_data_config(config_path)
            self.assertEqual(Path(loaded['aggregate_state_file']), override)

    def test_http_file_adapter_tracks_metadata_without_downloading_body(self):
        source = {
            "id": "dodge-parcels-zip",
            "kind": "http_file",
            "url": "https://example.invalid/parcels.zip",
            "expected_content_type": "zip",
        }
        meta = {
            "status": 200,
            "transport": "urllib-head",
            "headers": {
                "etag": '"abc"',
                "last-modified": "Tue, 08 Sep 2026 15:26:32 GMT",
                "content-length": "4221438",
                "content-type": "application/x-zip-compressed",
            },
        }
        with patch.object(datawatch, "_head_request", return_value=meta) as head:
            result = datawatch._source_check(source, 20)
        head.assert_called_once_with(source["url"], 20)
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["tracked_values"]["etag"], '"abc"')
        self.assertEqual(result["tracked_values"]["content_length"], "4221438")
        self.assertEqual(result["problems"], [])

    def test_http_file_adapter_reports_missing_freshness_metadata(self):
        source = {
            "id": "file",
            "adapter": "http-file",
            "url": "https://example.invalid/file.zip",
        }
        with patch.object(datawatch, "_head_request", return_value={
            "status": 200,
            "transport": "urllib-head",
            "headers": {"content-type": "application/zip"},
        }):
            result = datawatch._source_check(source, 20)
        self.assertTrue(any("freshness metadata" in x for x in result["problems"]))

    def test_mngac_population_expressions_respect_standard_no_data_rules(self):
        self.assertEqual(
            datawatch._mngac_population_expression({'field': 'OWNER_NAME', 'data_type': 'Text'}, 'OWNER_NAME'),
            "CASE WHEN OWNER_NAME IS NULL OR OWNER_NAME = '' THEN 0 ELSE 1 END",
        )
        self.assertEqual(
            datawatch._mngac_population_expression({'field': 'EMV_TOTAL', 'data_type': 'Integer'}, 'EMV_TOTAL'),
            "CASE WHEN EMV_TOTAL IS NULL OR EMV_TOTAL = 0 OR EMV_TOTAL = -9999 THEN 0 ELSE 1 END",
        )
        self.assertEqual(
            datawatch._mngac_population_expression({'field': 'ACRES_POLY', 'data_type': 'Double'}, 'ACRES_POLY'),
            "CASE WHEN ACRES_POLY IS NULL THEN 0 ELSE 1 END",
        )
        with self.assertRaises(ValueError):
            datawatch._mngac_population_expression({'field': 'OWNER_NAME', 'data_type': 'Text'}, 'OWNER_NAME); INVALID_FIELD')

    def test_mngac_completeness_uses_bounded_grouped_statistics_query(self):
        field_names = ['OBJECTID', 'CO_NAME', 'CO_CODE', 'CTU_NAME', 'OWNER_NAME']
        response = {'features': [
            {'attributes': {'CO_NAME': 'Aitkin', 'CO_CODE': '27001', 'record_count': 10, 'p0': 10, 'p1': 10, 'p2': 10, 'p3': 8}},
            {'attributes': {'CO_NAME': 'Anoka', 'CO_CODE': '27003', 'record_count': 20, 'p0': 20, 'p1': 20, 'p2': 20, 'p3': 10}},
        ]}
        with patch.object(datawatch, '_json_request', return_value=(response, {'status': 200})) as query:
            result = datawatch._arcgis_mngac_completeness(
                'https://example.invalid/FeatureServer/0',
                field_names,
                'OBJECTID',
                30,
            )
        self.assertEqual(query.call_count, 1)
        self.assertIn('/query?', query.call_args.args[0])
        self.assertIn('groupByFieldsForStatistics=CO_NAME%2CCO_CODE', query.call_args.args[0])
        self.assertEqual(result['statistics_queries'], 1)
        self.assertEqual(result['covered_counties'], 2)
        self.assertEqual(result['record_count'], 30)
        self.assertEqual(result['field_count'], 91)
        self.assertEqual(result['counties']['Aitkin']['fields']['OWNER_NAME']['percent'], 80.0)
        self.assertEqual(result['fields']['OWNER_NAME']['populated'], 18)
        self.assertEqual(result['fields']['OWNER_NAME']['percent'], 60.0)
        self.assertEqual(result['fields']['OWNER_NAME']['counties_with_values'], 2)
        self.assertIn('COUNTY_PIN', result['source_schema_missing_fields'])

    def test_mngac_full_schema_uses_eight_bounded_batches(self):
        schema = datawatch._load_mngac_schema()
        field_names = ['OBJECTID'] + [x['field'] for x in schema['fields']]
        attrs = {'CO_NAME': 'Aitkin', 'CO_CODE': '27001', 'record_count': 10}
        attrs.update({f'p{i}': 10 for i in range(20)})
        response = {'features': [{'attributes': attrs}]}
        with patch.object(datawatch, '_json_request', return_value=(response, {'status': 200})) as query:
            result = datawatch._arcgis_mngac_completeness(
                'https://example.invalid/FeatureServer/0',
                field_names,
                'OBJECTID',
                30,
                batch_size=12,
            )
        self.assertEqual(query.call_count, 8)
        self.assertEqual(result['statistics_queries'], 8)
        self.assertEqual(result['field_count'], 91)
        self.assertTrue(all('/query?' in call.args[0] for call in query.call_args_list))
        self.assertLess(max(len(call.args[0]) for call in query.call_args_list), 8000)

    def test_mngac_dashboard_map_county_page_and_exports(self):
        import tempfile
        import zipfile
        import io
        schema = datawatch_dashboard._load_mngac_schema()
        specs = schema['fields']
        def county(name, code, rows, owner_pct):
            fields = {}
            for spec in specs:
                pct = 100.0 if spec['inclusion'] == 'Mandatory' else 0.0
                if spec['field'] == 'OWNER_NAME':
                    pct = owner_pct
                populated = round(rows * pct / 100.0)
                fields[spec['field']] = {'populated': populated, 'record_count': rows, 'percent': pct}
            return {
                'county_name': name, 'county_code': code, 'record_count': rows, 'fields': fields,
                'fields_with_values': sum(1 for x in fields.values() if x['populated'] > 0),
                'field_count': 91, 'field_population_percent': 25.0,
                'mandatory_population_percent': 100.0, 'mandatory_fields_full': 7, 'mandatory_field_count': 7,
            }
        counties = {'Aitkin': county('Aitkin', '27001', 10, 80.0), 'Anoka': county('Anoka', '27003', 20, 50.0)}
        fields = {}
        for spec in specs:
            values = [counties[x]['fields'][spec['field']] for x in counties]
            populated = sum(x['populated'] for x in values)
            total = sum(x['record_count'] for x in values)
            fields[spec['field']] = {
                'label': spec['label'], 'section': spec['section'], 'section_name': spec['section_name'],
                'inclusion': spec['inclusion'], 'data_type': spec['data_type'],
                'present_in_source_schema': True, 'populated': populated, 'record_count': total,
                'percent': round(populated / total * 100.0, 2), 'counties_with_values': sum(x['populated'] > 0 for x in values),
                'counties_covered': 2, 'county_median_percent': 100.0,
            }
        mngac = {
            'standard': schema['standard'], 'method': 'test', 'covered_counties': 2, 'record_count': 30,
            'field_count': 91, 'mandatory_field_count': 7, 'statistics_queries': 1,
            'counties': counties, 'fields': fields,
        }
        state = {
            'generated_at': '2026-10-05T12:00:00+00:00', 'overall': 'ok',
            'counts': {'ok': 1, 'warn': 0, 'error': 0}, 'active_alerts': [],
            'sources': {'mn-state-parcels': {
                'id': 'mn-state-parcels', 'name': 'Minnesota Plan Parcels Open', 'status': 'ok',
                'checked_at': '2026-10-05T12:00:00+00:00', 'mngac_completeness': mngac,
            }},
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_file = root / 'state.json'
            hist = root / 'history.jsonl'
            state_file.write_text(json.dumps(state), encoding='utf-8')
            hist.write_text('', encoding='utf-8')
            config = {'state_file': str(state_file), 'history_file': str(hist), 'sources': []}
            page = datawatch_dashboard.render_mngac(config)
            self.assertIn('Interactive Minnesota county map', page)
            self.assertNotIn('http-equiv="refresh"', page)
            self.assertIn('Interactive view · reload for latest saved data', page)
            self.assertEqual(page.count('class="mngac-county"'), 87)
            self.assertIn('All 91 fields', page)
            self.assertIn('No data', page)
            self.assertIn('OWNER_NAME', page)
            county_page = datawatch_dashboard.render_county(config, 'aitkin')
            self.assertIn('MN GAC field completeness', county_page)
            self.assertIn('80.00%', county_page)
            self.assertIn('Conditional', county_page)
            statewide = datawatch_dashboard._statewide_snapshot(config)
            self.assertEqual(statewide['mngac']['covered_counties'], 2)
            self.assertIn('OWNER_NAME', datawatch_dashboard._mngac_csv(statewide['mngac']))
            xlsx = datawatch_dashboard._snapshot_xlsx(statewide)
            with zipfile.ZipFile(io.BytesIO(xlsx)) as zf:
                workbook = zf.read('xl/workbook.xml').decode('utf-8')
            self.assertIn('MNGAC Counties', workbook)
            self.assertIn('MNGAC Fields', workbook)
            self.assertIn('MNGAC Detail', workbook)

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
            self.assertIn('--navy:#10263b', overview)
            self.assertIn('--accent:#0b6fa4', overview)
            self.assertIn('Sources taking longest to respond', overview)
            self.assertIn('Data sources by category', overview)
            self.assertIn('Combined health of all cloud and local source checks', overview)
            self.assertIn('Sources currently included across the cloud and local workers', overview)
            self.assertIn('Most recent successful observation, not merely last attempt', overview)
            self.assertEqual(len(datawatch_dashboard._load_counties()), 87)
            self.assertIn('Wabasha County', counties)
            self.assertIn('Yellow Medicine County', counties)
            self.assertIn('County-direct sources', counties)
            self.assertIn('Actively checked', counties)
            self.assertIn('Health and active monitoring path', counties)
            self.assertIn('County-direct access', counties)
            self.assertIn('Statewide open access', counties)
            self.assertIn('County-specific sources actively checked', counties)
            self.assertIn('Monitoring coverage', counties)
            self.assertNotIn('Live data checks', counties)
            self.assertNotIn('County update info available', counties)
            self.assertIn('Wabasha County Parcels', wabasha)
            self.assertIn('No direct county parcel source currently monitored', aitkin)

    def test_all_minnesota_counties_have_verified_contact_authority(self):
        contacts = datawatch_dashboard._load_county_contacts()
        records = datawatch_dashboard._load_county_contact_records()
        counties = datawatch_dashboard._load_counties()
        self.assertEqual(len(counties), 87)
        self.assertEqual(len(contacts), 87)
        self.assertEqual(len(records), 87)
        self.assertFalse([name for name, record in records.items() if record.get('authority') == 'mngeo_unverified'])
        self.assertTrue(all(record.get('authority') in ('county', 'mngeo') for record in records.values()))
        config = {'state_file': str(TOOLS_ROOT / 'datawatch' / 'state.json'), 'history_file': str(TOOLS_ROOT / 'datawatch' / 'history.jsonl'), 'sources': []}
        wabasha = datawatch_dashboard.render_county(config, 'wabasha')
        lincoln = datawatch_dashboard.render_county(config, 'lincoln')
        self.assertIn('County GIS contacts', wabasha)
        self.assertIn('Official county website', wabasha)
        self.assertIn('class="contacts-table"', wabasha)
        self.assertIn('contacts-table td:nth-child(4)::before', wabasha)
        self.assertIn('MnGeo', lincoln)
        self.assertIn('retained as the fallback', lincoln)

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

    def test_county_contact_verification_prefers_official_county_override_and_keeps_mngeo_fallback(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = root / 'contacts.json'
            verification = root / 'verified.json'
            baseline.write_text(json.dumps({
                'source': {'name': 'MnGeo County GIS Contacts', 'url': 'https://mn.gov/example'},
                'counties': [
                    {'county': 'Alpha', 'contacts': [{'name': 'Old Person', 'title': 'GIS Coordinator', 'department': 'GIS', 'phone': '111', 'email': 'old@example.gov'}]},
                    {'county': 'Beta', 'contacts': [{'name': 'MnGeo Person', 'title': 'GIS Coordinator', 'department': 'GIS', 'phone': '222', 'email': 'mngeo@example.gov'}]},
                ],
            }), encoding='utf-8')
            verification.write_text(json.dumps({'counties': [
                {'county': 'Alpha', 'authority': 'county', 'verified': '2026-10-04',
                 'official_county_url': 'https://alpha.gov', 'official_contact_page_url': 'https://alpha.gov/gis',
                 'contacts': [{'name': 'New Person', 'title': 'GIS Manager', 'department': 'GIS', 'phone': '333', 'email': 'new@alpha.gov'}],
                 'evidence_note': 'Official GIS page lists updated staff.'},
                {'county': 'Beta', 'authority': 'mngeo', 'verified': '2026-10-04',
                 'official_county_url': 'https://beta.gov', 'official_contact_page_url': 'https://beta.gov/maps',
                 'contacts': [], 'evidence_note': 'No additional or changed GIS contact information found.'},
            ]}), encoding='utf-8')
            with patch.object(datawatch_dashboard, 'COUNTY_CONTACTS_FILE', baseline), patch.object(datawatch_dashboard, 'COUNTY_CONTACT_VERIFICATION_FILE', verification):
                records = datawatch_dashboard._load_county_contact_records()
                self.assertEqual(records['Alpha']['authority'], 'county')
                self.assertEqual(records['Alpha']['contacts'][0]['name'], 'New Person')
                self.assertEqual(records['Alpha']['source_url'], 'https://alpha.gov/gis')
                self.assertEqual(records['Beta']['authority'], 'mngeo')
                self.assertEqual(records['Beta']['contacts'][0]['name'], 'MnGeo Person')
                self.assertEqual(records['Beta']['source_url'], 'https://mn.gov/example')

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
            self.assertIn('County monitoring coverage', page)
            self.assertIn('MnGeo parcel update age', page)
            self.assertIn('Use Export in the page toolbar for statewide Excel, CSV, or JSON.', page)
            self.assertIn('County parcel update information', county)
            self.assertIn('Last county update', county)
            self.assertIn('Download county snapshot', county)
            self.assertNotIn('MnGeo parcel metadata', county)
            self.assertEqual(snap['county'], 'Aitkin')
            self.assertEqual(snap['contact_source'], 'county')
            self.assertEqual(snap['contact_verified'], '2026-10-04')
            self.assertIn('contact_source', csv_text)
            self.assertIn('contact_source_url', csv_text)
            self.assertIn('contact_verified', csv_text)
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
            self.assertIn('Export', page)
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
            self.assertIn('System diagnostics', page)
            self.assertIn('Memory used by Watchtower', page)
            self.assertIn('grid-template-columns:1fr', page)
            self.assertIn('mobile-nav', page)
            self.assertNotIn('overflow-x:hidden', page)

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

    def test_dashboard_hybrid_worker_cards_and_contemporary_mobile_shell(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            hist = root / 'history.jsonl'
            state.write_text(json.dumps({
                'generated_at': '2026-10-04T21:43:23+00:00',
                'overall': 'ok',
                'counts': {'ok': 2, 'warn': 0, 'error': 0},
                'active_alerts': [],
                'workers': {
                    'cloud': {'overall': 'ok', 'source_count': 22, 'last_success_at': '2026-10-04T21:43:23+00:00', 'telemetry': {'wall_ms': 28001}},
                    'local': {'overall': 'ok', 'source_count': 4, 'last_success_at': '2026-10-04T20:18:29+00:00', 'telemetry': {'wall_ms': 1796}},
                },
                'sources': {},
            }), encoding='utf-8')
            hist.write_text('', encoding='utf-8')
            page = datawatch_dashboard.render_dashboard({'state_file': str(state), 'history_file': str(hist), 'sources': []})
            self.assertIn('Cloud worker', page)
            self.assertIn('Local worker', page)
            self.assertIn('28.0s', page)
            self.assertIn('1.8s', page)
            self.assertIn('aria-label="Mobile navigation"', page)
            self.assertIn('Excel (.xlsx)', page)
            self.assertNotIn('0.0 MB', page)

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
            self.assertIn('Overall health', overview)
            self.assertIn('Source issues', overview)
            self.assertIn('Workers', overview)
            self.assertIn('id="changes"', overview)
            self.assertIn('id="alerts"', overview)
            self.assertIn('No active alerts.', overview)
            self.assertIn('Data being watched', overview)
            self.assertIn('Healthy', overview)
            self.assertNotIn('>Actively checked</span><br><span class="muted">current reporting', overview)
            self.assertIn('Records / change', overview)
            self.assertIn('Recent reliability', overview)
            self.assertIn('<details class="technical">', detail)
            self.assertIn('<summary>Technical details</summary>', detail)
            self.assertIn('About this data', detail)
            self.assertNotIn('>Provenance<', detail)


    def test_security_arcgis_count_validation_and_source_isolation(self):
        for value in ("10", None, {}, [], True, -1, 2_147_483_648):
            with patch.object(datawatch, '_json_request', return_value=({'count': value}, {'status': 200})):
                with self.assertRaises(ValueError):
                    datawatch._arcgis_count_query('https://example.invalid/0', '1=1', 1)
        with patch.object(datawatch, '_json_request', return_value=({'count': 0}, {'status': 200})):
            self.assertEqual(datawatch._arcgis_count_query('https://example.invalid/0', '1=1', 1), 0)

        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = {
                'state_file': str(root / 'state.json'), 'history_file': str(root / 'history.jsonl'),
                'retries': 0,
                'sources': [
                    {'id': 'bad', 'name': 'Bad', 'kind': 'arcgis_layer', 'url': 'https://bad.invalid'},
                    {'id': 'good', 'name': 'Good', 'kind': 'arcgis_layer', 'url': 'https://good.invalid'},
                ],
            }
            def fake(source, timeout):
                if source['id'] == 'bad':
                    return {'feature_count': 'not-an-int', 'schema_hash': 'x', 'problems': []}
                return {'feature_count': 5, 'schema_hash': 'y', 'problems': []}
            previous = {'sources': {'bad': {'feature_count': 4, 'schema_hash': 'x'}, 'good': {'feature_count': 5, 'schema_hash': 'y'}}}
            with patch.object(datawatch, 'load_state', return_value=previous), patch.object(datawatch, '_source_check', side_effect=fake):
                report = datawatch.check_sources(config, save=False)
            self.assertEqual(report['sources']['bad']['status'], 'error')
            self.assertEqual(report['sources']['good']['status'], 'ok')

    def test_security_redirect_policy_rejects_private_and_allows_public(self):
        with patch.object(datawatch, '_destination_publicity', side_effect=lambda url: False if '127.0.0.1' in url else True):
            with self.assertRaisesRegex(RuntimeError, 'redirect rejected'):
                datawatch._validated_redirect('https://provider.example/a', 'http://127.0.0.1/admin', 'https://provider.example/a')
            self.assertEqual(
                datawatch._validated_redirect('https://provider.example/a', 'https://cdn.example/b', 'https://provider.example/a'),
                'https://cdn.example/b',
            )
        with patch.dict(os.environ, {'WATCHTOWER_REDIRECT_ALLOW_HOSTS': 'internal.example'}):
            self.assertEqual(
                datawatch._validated_redirect('https://provider.example/a', 'https://internal.example/b', 'https://provider.example/a'),
                'https://internal.example/b',
            )

    def test_security_bounded_response_and_safe_diagnostics(self):
        import io
        self.assertEqual(datawatch._read_bounded(io.BytesIO(b'12345678'), limit=8), b'12345678')
        with self.assertRaises(datawatch.ProviderResponseTooLargeError):
            datawatch._read_bounded(io.BytesIO(b'123456789'), limit=8)
        dirty = "bad\r\nFORGED\x1b[31m red\t" + ("x" * 3000)
        safe = datawatch._safe_diagnostic(dirty)
        self.assertNotIn("\n", safe)
        self.assertNotIn("\r", safe)
        self.assertNotIn("\x1b", safe)
        self.assertLessEqual(len(safe), 1024)

    def test_security_static_state_omits_change_details_and_status_attributes_are_safe(self):
        state = {
            'overall': 'ok" onmouseover="alert(1)',
            'counts': {},
            'sources': {
                'a': {
                    'id': 'a', 'name': 'A', 'status': 'ok" onmouseover="alert(1)',
                    'changes': [{'previous': 'secret-old', 'current': 'secret-new', 'message': 'secret-change'}],
                }
            },
        }
        public = datawatch_dashboard._sanitize_public_state(state)
        self.assertEqual(public['sources']['a']['change_count'], 1)
        self.assertNotIn('changes', public['sources']['a'])
        self.assertNotIn('secret-old', json.dumps(public))
        self.assertEqual(datawatch_dashboard._status_class(state['overall']), 'unknown')
        self.assertEqual(datawatch_dashboard._status_class(state['sources']['a']['status']), 'unknown')

    def test_security_content_length_validation(self):
        self.assertEqual(datawatch_dashboard._validated_content_length('0'), 0)
        self.assertEqual(datawatch_dashboard._validated_content_length('4096'), 4096)
        for value in (None, '-1', 'nope'):
            with self.assertRaises(ValueError):
                datawatch_dashboard._validated_content_length(value)
        with self.assertRaises(OverflowError):
            datawatch_dashboard._validated_content_length('4097')

    def test_watchtower_user_agent_identifies_project_and_429_does_not_fallback(self):
        self.assertIn('GIS-Data-Watchtower', datawatch.USER_AGENT)
        self.assertIn('github.com/clearparcel/GIS-Data-Watchtower', datawatch.USER_AGENT)
        from unittest.mock import patch
        with patch.object(datawatch, '_urllib_request_once', side_effect=datawatch.ProviderRateLimitError('60')), patch.object(datawatch, '_curl_request') as fallback:
            with self.assertRaisesRegex(RuntimeError, 'HTTP 429'):
                datawatch._request('https://example.invalid', 1)
            fallback.assert_not_called()


    def test_post_429_stops_without_curl_fallback(self):
        from unittest.mock import patch
        with patch.object(datawatch, '_urllib_request_once', side_effect=datawatch.ProviderRateLimitError('120')), patch.object(datawatch, '_curl_request') as curl:
            with self.assertRaises(datawatch.ProviderRateLimitError):
                datawatch._post_json('https://example.invalid', {'x': 1}, 1)
            curl.assert_not_called()

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
        from unittest.mock import patch
        failures = (
            (403, RuntimeError('provider returned HTTP 403; fallback transport not attempted')),
            (429, datawatch.ProviderRateLimitError('60')),
        )
        for code, failure in failures:
            with patch.object(datawatch, '_urllib_request_once', side_effect=failure), patch.object(datawatch, '_curl_request') as fallback:
                with self.assertRaisesRegex(RuntimeError, f'HTTP {code}'):
                    datawatch._request('https://example.invalid', 1)
                fallback.assert_not_called()


    def test_curl_fallback_resolves_portable_executable(self):
        from unittest.mock import patch
        class CP:
            returncode = 0
            stderr = b''
            stdout = b'\n__CP_HTTP__200\n__CP_REDIRECT__'
        def fake_run(command, **kwargs):
            Path(command[command.index('-o') + 1]).write_bytes(b'{}')
            Path(command[command.index('-D') + 1]).write_text('', encoding='utf-8')
            return CP()
        with patch.object(datawatch.shutil, 'which', side_effect=lambda name: '/usr/bin/curl' if name == 'curl' else None), patch.object(datawatch.subprocess, 'run', side_effect=fake_run) as run:
            body, meta = datawatch._curl_request('https://example.invalid', 1)
        self.assertEqual(body, b'{}')
        self.assertEqual(meta['status'], 200)
        self.assertEqual(run.call_args.args[0][0], '/usr/bin/curl')
        self.assertIn('--max-filesize', run.call_args.args[0])
        self.assertNotIn('-L', run.call_args.args[0])

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
        state = {'schema_version': 2, 'generated_at': '2026-10-04T12:00:00+00:00', 'overall': 'ok', 'counts': {'ok': 1}, 'sources': {'x': {'id': 'x', 'name': 'X', 'provider': 'P', 'category': 'Parcels', 'status': 'ok', 'feature_count': 10, 'checked_at': 'now', 'changes': [{'type':'tracked_value','previous':'PRIVATE-OLD','current':'PRIVATE-NEW'}], 'tracked_values': {'secret':'PRIVATE-VALUE'}, 'url': 'https://secret.invalid', 'schema_hash': 'abc', 'observation_fingerprint': 'def', 'wkid': 26915, 'field_names': ['A'], 'telemetry': {'x': 1}}}}
        public = datawatch_dashboard._sanitize_public_state(state)
        row = public['sources']['x']
        self.assertEqual(row['feature_count'], 10)
        self.assertEqual(row['change_count'], 1)
        for key in ('url', 'schema_hash', 'observation_fingerprint', 'wkid', 'field_names', 'telemetry', 'adapter', 'kind', 'changes', 'tracked_values'):
            self.assertNotIn(key, row)
        self.assertNotIn('PRIVATE-', json.dumps(public))

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
        from unittest.mock import patch
        with patch.object(datawatch, '_urllib_request_once', side_effect=datawatch.ProviderRateLimitError('60')):
            with self.assertRaises(datawatch.ProviderRateLimitError):
                datawatch._request('https://example.invalid', 1)

    def test_arcgis_count_validation_rejects_malformed_and_extreme_values(self):
        for bad in ("12", None, {}, [], True, -1, 2_147_483_648):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    datawatch._validated_provider_count(bad, label="ArcGIS count")
        self.assertEqual(datawatch._validated_provider_count(0), 0)
        self.assertEqual(datawatch._validated_provider_count(123), 123)

    def test_malformed_provider_value_fails_one_source_without_aborting_fleet(self):
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = {
                'state_file': str(root / 'state.json'),
                'history_file': str(root / 'history.jsonl'),
                'retries': 0,
                'sources': [
                    {'id':'bad','name':'Bad','kind':'arcgis_layer','url':'https://example.invalid/bad'},
                    {'id':'good','name':'Good','kind':'arcgis_layer','url':'https://example.invalid/good'},
                ],
            }
            previous = {'sources': {'bad': {'feature_count': 5, 'status': 'ok'}}}
            with patch.object(datawatch, 'load_state', return_value=previous), patch.object(
                datawatch, '_source_check',
                side_effect=[
                    {'feature_count':'not-an-int','schema_hash':'same','problems':[]},
                    {'feature_count':10,'schema_hash':'same','problems':[]},
                ]
            ):
                report = datawatch.check_sources(config, save=False)
        self.assertEqual(report['sources']['bad']['status'], 'error')
        self.assertIn('TypeError', report['sources']['bad']['error'])
        self.assertEqual(report['sources']['good']['status'], 'ok')

    def test_redirect_policy_rejects_private_and_metadata_destinations(self):
        from unittest.mock import patch
        def publicity(url):
            return False if ('127.0.0.1' in url or 'metadata.google.internal' in url) else True
        with patch.object(datawatch, '_destination_publicity', side_effect=publicity):
            with self.assertRaisesRegex(RuntimeError, 'redirect rejected'):
                datawatch._validated_redirect('https://provider.example/a', 'http://127.0.0.1/admin', 'https://provider.example/a')
            with self.assertRaisesRegex(RuntimeError, 'redirect rejected'):
                datawatch._validated_redirect('https://provider.example/a', 'http://metadata.google.internal/', 'https://provider.example/a')
            self.assertEqual(
                datawatch._validated_redirect('https://provider.example/a', '/next', 'https://provider.example/a'),
                'https://provider.example/next'
            )

    def test_post_redirect_does_not_forward_payload_on_method_changing_status(self):
        from unittest.mock import patch
        with patch.object(datawatch, '_urllib_request_once', return_value=(b'', {'status':302,'location':'https://other.example/x','transport':'test'})), patch.object(datawatch, '_curl_request') as fallback:
            with self.assertRaisesRegex(RuntimeError, 'POST redirect HTTP 302 rejected'):
                datawatch._post_json('https://provider.example/post', {'x':1}, 1)
            fallback.assert_not_called()

    def test_provider_response_reader_enforces_byte_budget(self):
        import io
        with self.assertRaises(datawatch.ProviderResponseTooLargeError):
            datawatch._read_bounded(io.BytesIO(b'x' * 11), 10)
        self.assertEqual(datawatch._read_bounded(io.BytesIO(b'x' * 10), 10), b'x' * 10)

    def test_diagnostic_text_is_single_line_bounded_and_terminal_safe(self):
        value = 'first\r\nFAKE ALERT\x1b[31mRED\x1b[0m\t' + ('x' * 2000)
        safe = datawatch._safe_diagnostic(value, limit=80)
        self.assertNotIn('\n', safe)
        self.assertNotIn('\r', safe)
        self.assertNotIn('\x1b', safe)
        self.assertLessEqual(len(safe), 80)
        self.assertIn('FAKE ALERT', safe)

    def test_alert_text_cannot_gain_provider_controlled_lines(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'alerts.txt'
            datawatch._write_alert_text(path, {
                'generated_at':'now',
                'active':[{'severity':'error','name':'X','message':'boom\n[INFO] forged\x1b[31m'}],
                'events':[],
            })
            lines = path.read_text(encoding='utf-8').splitlines()
        self.assertEqual(len([line for line in lines if 'forged' in line]), 1)
        self.assertNotIn('\x1b', '\n'.join(lines))

    def test_content_length_validation_rejects_negative_invalid_and_oversized(self):
        self.assertEqual(datawatch_dashboard._validated_content_length('12', 4096), 12)
        for bad in (None, '-1', 'abc'):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    datawatch_dashboard._validated_content_length(bad, 4096)
        with self.assertRaises(OverflowError):
            datawatch_dashboard._validated_content_length('4097', 4096)

    def test_aggregate_status_is_closed_enum_before_dashboard_rendering(self):
        from clearparcel.datawatch.aggregate import merge_states
        state = merge_states({}, {
            'generated_at':'2026-10-04T12:00:00+00:00',
            'overall':'ok" onmouseover="alert(1)',
            'sources': {'x': {'id':'x','status':'ok" onmouseover="alert(1)'}},
        }, 'cloud')
        self.assertEqual(state['workers']['cloud']['overall'], 'error')
        self.assertEqual(state['sources']['x']['status'], 'error')
        self.assertEqual(datawatch_dashboard._status_class('ok" onmouseover="alert(1)'), 'unknown')

    def test_static_publication_omits_change_payload_and_fingerprints(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            history = root / 'history.jsonl'
            state.write_text(json.dumps({
                'schema_version':2,'generated_at':'2026-10-04T12:00:00+00:00',
                'overall':'ok\" onmouseover=\"alert(1)','counts':{'ok':1,'warn':0,'error':0},
                'sources':{'x':{'id':'x','name':'X','status':'ok\" onmouseover=\"alert(1)','feature_count':1,
                    'checked_at':'now','observation_fingerprint':'SECRET-FP',
                    'tracked_values':{'private':'SECRET-VALUE'},
                    'changes':[{'type':'tracked_value','previous':'SECRET-OLD','current':'SECRET-NEW'}]}}
            }), encoding='utf-8')
            history.write_text('', encoding='utf-8')
            out = root / 'site'
            datawatch_dashboard.build_static_site({'state_file':str(state),'history_file':str(history),'sources':[]}, out)
            published = (out / 'state.json').read_text(encoding='utf-8')
            index_html = (out / 'index.html').read_text(encoding='utf-8')
            detail_html = (out / 'source-x.html').read_text(encoding='utf-8')
        self.assertNotIn('SECRET-', published)
        self.assertNotIn('onmouseover', index_html)
        self.assertNotIn('onmouseover', detail_html)
        document = json.loads(published)
        self.assertEqual(document['overall'], 'unknown')
        self.assertEqual(document['sources']['x']['status'], 'unknown')
        self.assertEqual(document['sources']['x']['change_count'], 1)
        self.assertNotIn('changes', document['sources']['x'])

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
        from unittest.mock import patch
        config = {'state_file': str(TOOLS_ROOT / 'datawatch' / 'test-get-rate-state.json'), 'history_file': str(TOOLS_ROOT / 'datawatch' / 'test-get-rate-history.jsonl'), 'retries': 3, 'sources': [{'id': 'rate', 'name': 'Rate', 'kind': 'arcgis_layer', 'url': 'https://example.invalid/0'}]}
        with patch.object(datawatch, 'load_state', return_value={'sources': {}}), patch.object(datawatch, '_urllib_request_once', side_effect=datawatch.ProviderRateLimitError('60')) as request:
            report = datawatch.check_sources(config, save=False)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(report['sources']['rate']['attempts'], 1)

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

    def test_aggregate_loader_accepts_utf16(self):
        import tempfile
        from clearparcel.datawatch.aggregate import load_json
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"state.json"
            path.write_text('{"overall":"ok"}',encoding="utf-16")
            self.assertEqual(load_json(path)["overall"],"ok")

    def test_run_wrapper_preserves_warning_exit_code(self):
        wrapper = (TOOLS_ROOT / 'run-datawatch.cmd').read_text(encoding='utf-8')
        self.assertIn('exit /b %RC%', wrapper)
        self.assertIn('CLEARPARCEL_WATCHTOWER_CONFIG', wrapper)
        self.assertIn('if not exist "%ROOT%datawatch" mkdir "%ROOT%datawatch"', wrapper)
        self.assertNotIn('if %RC% GEQ 2', wrapper)

    def test_watchtower_ci_covers_standalone_package_without_live_provider_check(self):
        workflow = (TOOLS_ROOT / ".github" / "workflows" / "watchtower-ci.yml").read_text(encoding="utf-8")
        self.assertIn("pip install --disable-pip-version-check -e .", workflow)
        self.assertIn("unittest discover -s tests", workflow)
        self.assertIn("ubuntu-24.04", workflow)
        self.assertIn('"3.14"', workflow)
        self.assertNotIn("actions/checkout@v4", workflow)
        self.assertNotIn("actions/setup-python@v5", workflow)
        self.assertNotIn(" check --no-save", workflow)

    def test_refresh_requires_matching_csrf_token_and_same_origin(self):
        self.assertTrue(datawatch_dashboard._valid_refresh_request('abc', 'abc', 'same-origin'))
        self.assertFalse(datawatch_dashboard._valid_refresh_request('wrong', 'abc', 'same-origin'))
        self.assertFalse(datawatch_dashboard._valid_refresh_request('abc', 'abc', 'cross-site'))

    def test_get_429_uses_rate_limit_exception_and_stops_retry_loop(self):
        from unittest.mock import patch
        with patch.object(datawatch, '_urllib_request_once', side_effect=datawatch.ProviderRateLimitError('60')):
            with self.assertRaises(datawatch.ProviderRateLimitError):
                datawatch._request('https://example.invalid', 1)
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