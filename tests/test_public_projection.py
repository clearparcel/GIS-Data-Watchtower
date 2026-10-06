import json
import tempfile
import unittest
from pathlib import Path

from clearparcel.datawatch.public_dashboard import sanitize_public_render_state
from clearparcel.datawatch.public_publish import publish_public_snapshot
from clearparcel.datawatch.storage import LocalStorage


def hostile_state():
    private = {'private_registry': 'PRIVATE', 'provenance': {'token': 'PRIVATE'}}
    return {'schema_version': private, 'generated_at': private, 'overall': private,
        'counts': {'ok': 2, 'warn': private, 'unexpected': private},
        'workers': {'cloud': {'overall': private, 'source_count': private, 'checked_at': private}},
        'sources': {'parcels': {'name': private, 'status': private, 'feature_count': private,
            'worker': private, 'elapsed_ms': private, 'changes': private,
            'completeness_profiles': {
                'parcel_id': {'field': 'PIN', 'missing': 0, 'populated': 42, 'complete_percent': 100.0,
                    'provenance': private, 'private_registry': private,
                    'error': 'https://user:PRIVATE@example.com?token=PRIVATE'},
                'owner': {'field': private, 'missing': private, 'populated': True,
                    'complete_percent': private, 'status': 'unsupported', 'error': 'PRIVATE'},
                'unknown': private}},
            'mn-parcel-county-catalog': {'county_records': {'Aitkin': {
                'gac_open_approval': private, 'acqdate': private, 'rundate': private,
                'data_url': private, 'viewer_url': 'https://example.com/view'}}}}}


def without_provenance(value):
    if isinstance(value, dict):
        return {key: without_provenance(item) for key, item in value.items() if key != 'provenance'}
    return value


class PublicProjectionTests(unittest.TestCase):
    def assert_safe(self, public):
        self.assertNotIn('PRIVATE', json.dumps(public))
        self.assertEqual(public['counts'], {'ok': 2})
        source = public['sources']['parcels']
        self.assertNotIn('feature_count', source)
        self.assertEqual(source['status'], 'unknown')
        self.assertEqual(source['change_count'], 0)
        self.assertEqual(source['completeness_profiles'], {
            'parcel_id': {'field': 'PIN', 'missing': 0, 'populated': 42, 'complete_percent': 100.0},
            'owner': {'status': 'unsupported'}})
        self.assertEqual(public, sanitize_public_render_state(public))

    def test_nested_diagnostics_and_malformed_scalars_are_projected(self):
        self.assert_safe(sanitize_public_render_state(hostile_state()))

    def test_publisher_uploads_typed_projection(self):
        for raw in (hostile_state(), without_provenance(hostile_state())):
            self.publish_and_assert_safe(raw)

    def publish_and_assert_safe(self, raw):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = LocalStorage(root / 'source')
            destination = LocalStorage(root / 'destination')
            source.root.mkdir()
            (source.root / 'aggregate-state.json').write_text(json.dumps(raw), encoding='utf-8')
            publish_public_snapshot(source, destination, workdir=root / 'work')
            self.assert_safe(json.loads((destination.root / 'aggregate-state.json').read_text(encoding='utf-8')))

    def test_unknown_private_payloads_are_removed_without_forbidden_key_names(self):
        self.assert_safe(sanitize_public_render_state(without_provenance(hostile_state())))

    def test_legitimate_metrics_catalog_and_worker_values_survive(self):
        stamp = '2026-10-06T12:00:00+00:00'
        state = {'schema_version': 2, 'generated_at': stamp, 'overall': 'ok',
            'counts': {'ok': 1, 'warn': 0, 'error': 0},
            'workers': {'local': {'overall': 'ok', 'source_count': 1, 'last_report_at': stamp}},
            'sources': {'x': {'name': 'Parcels', 'worker': 'local', 'status': 'ok', 'feature_count': 0,
                'field_count': 12, 'null_geometry_count': 0, 'elapsed_ms': 1.2,
                'mngac_completeness': {'record_count': 0, 'field_count': 91, 'fields': {'PIN': {'section': 1,
                    'present_in_source_schema': True, 'populated': 0, 'percent': 0.0}},
                    'counties': {'Aitkin': {'record_count': 0, 'mandatory_field_count': 3}}},
                'completeness_profiles': {'parcel_id': {'field': 'PIN', 'missing': 0, 'populated': 0, 'complete_percent': None}}},
                'mn-parcel-county-catalog': {'county_records': {'Aitkin': {'gac_open_approval': 'true',
                    'acqdate': 1780617600000, 'rundate': 1783296000000, 'data_url': 'https://example.com/parcels.zip'}}}}}
        public = sanitize_public_render_state(state)
        self.assertEqual(public['workers'], state['workers'])
        mngac = public['sources']['x']['mngac_completeness']
        self.assertEqual(mngac['fields']['PIN'], state['sources']['x']['mngac_completeness']['fields']['PIN'])
        self.assertEqual(mngac['counties']['Aitkin']['record_count'], 0)
        self.assertEqual(public['sources']['x']['feature_count'], 0)
        self.assertEqual(public['sources']['x']['elapsed_ms'], 1.2)
        self.assertEqual(public['sources']['x']['completeness_profiles']['parcel_id'], {'field': 'PIN', 'missing': 0, 'populated': 0})
        self.assertEqual(public['sources']['mn-parcel-county-catalog']['county_records'], state['sources']['mn-parcel-county-catalog']['county_records'])
        self.assertEqual(public, sanitize_public_render_state(public))

    def test_wrong_numeric_types_and_nested_mngac_leaves_are_rejected(self):
        private = {'private_registry': 'PRIVATE'}
        state = {'sources': {'x': {'feature_count': True, 'field_count': '1', 'null_geometry_count': [],
            'geometry_sample_avg_vertices': float('nan'), 'elapsed_ms': -1,
            'mngac_completeness': {'method': private, 'record_count': 'PRIVATE',
                'fields': {'PIN': {'record_count': private, 'populated': True, 'percent': float('inf'), 'label': private}},
                'counties': {'Aitkin': {'record_count': private, 'fields_with_values': True, 'fields': {'PIN': private}}}}}}}
        public = sanitize_public_render_state(state)
        self.assertNotIn('PRIVATE', json.dumps(public))
        self.assertNotIn('feature_count', public['sources']['x'])
        self.assertEqual(public['sources']['x']['mngac_completeness']['fields']['PIN'], {})
        self.assertEqual(public, sanitize_public_render_state(public))

    def test_malformed_containers_are_empty(self):
        public = sanitize_public_render_state({'counts': [], 'workers': [], 'sources': {'catalog': {'completeness_profiles': []},
            'mn-parcel-county-catalog': {'county_records': []}}})
        self.assertEqual(public['counts'], {})
        self.assertEqual(public['workers'], {})
        self.assertEqual(public['sources']['mn-parcel-county-catalog']['county_records'], {})
