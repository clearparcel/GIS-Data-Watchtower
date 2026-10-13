"""Offline regressions for the October 12 Watchtower review."""
import json
import unittest
from unittest.mock import patch

from clearparcel.datawatch import dashboard, watch
from clearparcel.datawatch.dashboard_templates import _accessible_tables
from clearparcel.datawatch.public_dashboard import sanitize_public_render_state
from clearparcel.datawatch.public_publish import validate_public_state


class Review022Tests(unittest.TestCase):
    def test_private_gac_diagnostics_never_enter_public_state(self):
        state = {'sources': {'x': {'gac_check_status': 'warn',
            'gac_check_error': 'https://private.invalid/query?token=SYNTHETIC_SECRET',
            'mngac_completeness': {'record_count': 10, 'fields': {'PIN': {'populated': 10}},
                'counties': {'Aitkin': {'record_count': 10}}}}}}
        public = sanitize_public_render_state(state)
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(public))
        self.assertEqual(public['sources']['x']['gac_check_status'], 'warn')
        self.assertEqual(public['sources']['x']['mngac_completeness']['record_count'], 10)
        validate_public_state(public)
        with self.assertRaises(RuntimeError):
            validate_public_state(state)

    def test_arcgis_body_refusals_stop_source_retries(self):
        config = {'state_file': 'unused', 'history_file': 'unused', 'retries': 2,
            'retry_delay_seconds': 0, 'sources': [{'id': 'x', 'name': 'Test',
                'kind': 'arcgis_layer', 'url': 'https://example.invalid/0'}]}
        for code in (401, 403, 404, 410, 429, 498, 499, '429', '403'):
            with self.subTest(code=code), \
                 patch.object(watch, 'load_state', return_value={'sources': {}}), \
                 patch.object(watch, '_request', return_value=(
                     json.dumps({'error': {'code': code, 'message': 'refused'}}).encode(),
                     {'status': 200})) as request:
                result = watch.check_sources(config, save=False)
                self.assertEqual(result['sources']['x']['attempts'], 1)
                self.assertEqual(request.call_count, 1)

    def test_arcgis_transient_body_errors_remain_retryable(self):
        for code in (500, 503, 408, None):
            with self.subTest(code=code), patch.object(watch, '_request', return_value=(
                    json.dumps({'error': {'code': code}}).encode(), {'status': 200})):
                with self.assertRaises(RuntimeError) as caught:
                    watch._json_request('https://example.invalid/0', 2)
                self.assertNotIsInstance(caught.exception,
                    (watch.PermanentProviderError, watch.ProviderRateLimitError))

    def test_optional_quality_stops_after_arcgis_body_refusal(self):
        metadata = {'fields': [{'name': 'OBJECTID', 'type': 'esriFieldTypeOID'}],
                    'objectIdField': 'OBJECTID', 'geometryType': 'esriGeometryPolygon'}
        for code, expected in ((403, watch.PermanentProviderError),
                               (429, watch.ProviderRateLimitError),
                               (498, watch.PermanentProviderError)):
            responses = [(json.dumps(body).encode(), {'status': 200})
                         for body in (metadata, {'error': {'code': code}})]
            with self.subTest(code=code), patch.object(watch, '_request', side_effect=responses) as request:
                with self.assertRaises(expected):
                    watch._arcgis_layer({'url': 'https://example.invalid/0', 'parcel_quality': True}, 2)
                self.assertEqual(request.call_count, 2)

    def test_both_gac_failure_paths_retain_history_without_public_diagnostic(self):
        prior = {'observed_at': '2026-10-06T10:00:00+00:00', 'record_count': 10,
                 'fields': {'PIN': {'populated': 10}}, 'counties': {'Aitkin': {'record_count': 10}}}
        config = {'state_file': 'unused', 'history_file': 'unused', 'retries': 0,
                  'sources': [{'id': 'x', 'name': 'Test', 'kind': 'arcgis_layer',
                               'url': 'https://example.invalid/0', 'mngac_completeness': True}]}
        secret = 'private-provider?token=SYNTHETIC_SECRET'
        metadata = {'fields': [{'name': 'OBJECTID', 'type': 'esriFieldTypeOID'}], 'objectIdField': 'OBJECTID'}
        for whole_source in (False, True):
            with self.subTest(whole_source=whole_source), \
                 patch.object(watch, 'load_state', return_value={'sources': {'x': {'mngac_completeness': prior}}}), \
                 patch.object(watch, '_json_request', return_value=(metadata, {'status': 200}),
                              side_effect=RuntimeError(secret) if whole_source else None), \
                 patch.object(watch, '_arcgis_mngac_completeness', side_effect=ValueError(secret)):
                result = watch.check_sources(config, save=False)
            self.assertEqual(result['sources']['x']['mngac_completeness'], prior)
            self.assertIn('SYNTHETIC_SECRET', result['sources']['x']['gac_check_error'])
            public = sanitize_public_render_state(result)
            self.assertNotIn('SYNTHETIC_SECRET', json.dumps(public))
            self.assertEqual(public['sources']['x']['mngac_completeness']['observed_at'], prior['observed_at'])
            validate_public_state(public)

    def gac(self, attrs):
        with patch.object(watch, 'load_gac_standard', return_value={'fields': [
                {'field': 'CO_NAME', 'inclusion': 'Mandatory', 'data_type': 'Text'}]}), \
             patch.object(watch, '_json_request', return_value=(
                 {'features': [{'attributes': attrs}]}, {'status': 200})):
            return watch._arcgis_gac_completeness('https://example.invalid/0',
                ['OBJECTID', 'CO_NAME', 'CO_CODE'], 'OBJECTID', 10)

    def test_malformed_gac_counts_cannot_become_complete_statistics(self):
        for field, values in [('record_count', [-1, 2.9, True, '10', None]),
                              ('p0', [-1, 11, 2.9, True, '5', None])]:
            for value in values:
                with self.subTest(field=field, value=value):
                    attrs = {'CO_NAME': 'Aitkin', 'CO_CODE': '001', 'record_count': 10, 'p0': 5}
                    attrs[field] = value
                    with self.assertRaises(ValueError):
                        self.gac(attrs)
        for missing in ('record_count', 'p0'):
            attrs = {'CO_NAME': 'Aitkin', 'record_count': 10, 'p0': 5}
            del attrs[missing]
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                self.gac(attrs)

    def test_empty_gac_sum_can_be_null_without_losing_real_zero(self):
        result = self.gac({'CO_NAME': 'Aitkin', 'record_count': 0, 'p0': None})
        self.assertEqual(result['counties']['Aitkin']['record_count'], 0)
        self.assertEqual(result['counties']['Aitkin']['fields']['CO_NAME']['populated'], 0)

    def test_statewide_contacts_loaded_once_and_preserved(self):
        with patch.object(dashboard, '_dashboard_state', return_value={}), \
             patch.object(dashboard, '_load_county_contact_records',
                          wraps=dashboard._load_county_contact_records) as loader:
            result = dashboard._statewide_snapshot({})
        self.assertEqual(result['county_count'], 87)
        self.assertEqual(loader.call_count, 1)
        aitkin = next(row for row in result['counties'] if row['county'] == 'Aitkin')
        self.assertTrue(aitkin['contacts'])

    def test_table_regions_are_single_labelled_focus_targets_and_idempotent(self):
        for wrapper in ('', '<div class="table-scroll">',
                        '<div class="table-scroll" tabindex="0" role="region" aria-label="Parcel paths">'):
            body = wrapper + '<table><thead><tr><th>Name</th></tr></thead></table>'
            if wrapper:
                body += '</div>'
            output = _accessible_tables(body)
            self.assertEqual(output.count('class="table-scroll"'), 1)
            self.assertEqual(output.count('tabindex="0"'), 1)
            self.assertEqual(output.count('role="region"'), 1)
            self.assertIn('aria-label=', output)
            if 'Parcel paths' in wrapper:
                self.assertIn('aria-label="Parcel paths"', output)
            self.assertEqual(_accessible_tables(output), output)
            self.assertIn('scope="col"', output)
