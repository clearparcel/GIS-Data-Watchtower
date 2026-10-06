import copy
import datetime as dt
import json
from pathlib import Path
import unittest

from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles, county_profile_counts
from clearparcel.datawatch.parcel_access import INVENTORY_CATEGORIES, load_parcel_access

NOW = dt.datetime(2026, 10, 6, 12, tzinfo=dt.timezone.utc)
STAMP = NOW.isoformat()
COUNTIES = json.loads((Path(__file__).parents[1] / 'clearparcel/datawatch/minnesota_counties.json').read_text())['counties']


def coverage_state():
    sources = {'statewide': {'id': 'statewide', 'category': 'Parcels', 'status': 'ok', 'checked_at': STAMP,
        'last_success_at': STAMP, 'feature_count': 999999, 'mngac_completeness': {
            'fields': {'PIN': {}}, 'counties': {c['name']: {'record_count': 1000 + i} for i, c in enumerate(COUNTIES[:59])}}}}
    for i, c in enumerate(COUNTIES[46:70]):
        sources[c['slug']] = {'id': c['slug'], 'county_slug': c['slug'], 'category': 'Parcels',
            'adapter': 'arcgis_layer', 'name': c['name'] + ' parcels', 'status': 'ok', 'checked_at': STAMP,
            'last_success_at': STAMP, 'feature_count': 2000 + i}
    return {'generated_at': STAMP, 'sources': sources}


def compose(state=None, research=None):
    return compose_county_profiles(state or {}, research if research is not None else load_parcel_access(), now=NOW, freshness_policy=FreshnessPolicy())


class CountyProfilesTests(unittest.TestCase):
    def test_composes_all_87_profiles_from_empty_state(self):
        profiles = compose(research={})
        self.assertEqual(list(profiles), [c['slug'] for c in COUNTIES])
        self.assertEqual(profiles['aitkin']['county']['fips'], '27001')
        self.assertEqual(profiles['yellow-medicine']['county']['fips'], '27173')
        self.assertEqual(profiles['st-louis']['county']['fips'], '27137')
        self.assertEqual(profiles['scott']['county']['fips'], '27139')
        for p in profiles.values():
            self.assertFalse(p['monitoring']['active'])
            self.assertIsNone(p['monitoring']['last_checked_at'])
            self.assertFalse(p['research']['complete'])
            for category in INVENTORY_CATEGORIES:
                self.assertEqual(p[category]['availability'], 'unknown')
                self.assertEqual(p[category]['sources'], [])

    def test_current_coverage_overrides_static_membership(self):
        research = load_parcel_access()
        research['Aitkin']['statewide_open_coverage']['available'] = False
        p = compose(coverage_state(), research)
        self.assertEqual(p['aitkin']['mngac_public_parcels']['availability'], 'yes')
        self.assertEqual(p['yellow-medicine']['mngac_public_parcels']['availability'], 'no')
        source = p['aitkin']['mngac_public_parcels']['sources'][0]
        self.assertEqual(source['feature_count'], 1000)
        self.assertNotEqual(source['feature_count'], 999999)

    def test_no_observation_means_unknown(self):
        self.assertEqual(compose()['winona']['mngac_public_parcels']['availability'], 'unknown')
        state = coverage_state()
        state['sources']['statewide']['mngac_completeness']['counties']['Aitkin']['record_count'] = None
        self.assertIsNone(compose(state)['aitkin']['mngac_public_parcels']['sources'][0]['feature_count'])
        state['sources']['statewide']['mngac_completeness']['counties']['Aitkin']['record_count'] = 0
        self.assertEqual(compose(state)['aitkin']['mngac_public_parcels']['sources'][0]['feature_count'], 0)

    def test_70_county_union_and_source_identity(self):
        state = coverage_state()
        research = load_parcel_access()
        county = COUNTIES[46]
        item = {'inventory_id': 'shared', 'monitored_source_id': county['slug'], 'name': 'Shared parcel data',
            'authority': 'county', 'dataset_type': 'parcels', 'layer_id': 0, 'approved_public_links': [],
            'monitoring_decision': 'candidate-low-frequency'}
        for key in ('county_arcgis_rest', 'county_download'):
            research[county['name']]['source_inventory'][key].update(availability='yes', sources=[copy.deepcopy(item)])
        p = compose(state, research)
        self.assertEqual(county_profile_counts(p), {'total': 87, 'active': 70, 'county_direct': 24, 'mngeo_open': 59, 'both': 13})
        self.assertEqual(p[county['slug']]['monitoring']['active_parcel_source_count'], 2)
        self.assertEqual(p[county['slug']]['county_download']['sources'][0]['feature_count'], 2000)

    def test_nonparcel_slug_alias_and_failed_observation(self):
        state = {'sources': {'image': {'county_slug': 'aitkin', 'category': 'Imagery', 'status': 'ok'},
            'alias': {'county_slug': 'lake-extra', 'category': 'Parcels'},
            'parcel': {'county_slug': 'anoka', 'category': 'Parcels', 'adapter': 'arcgis_layer', 'status': 'error',
                'checked_at': STAMP, 'last_success_at': '2026-10-01T00:00:00+00:00', 'feature_count': 42},
            'undated': {'county_slug': 'becker', 'category': 'Parcels', 'adapter': 'arcgis_layer', 'status': 'ok'}}}
        p = compose(state)
        self.assertFalse(p['aitkin']['monitoring']['active'])
        self.assertFalse(p['lake']['monitoring']['active'])
        source = p['anoka']['county_arcgis_rest']['sources'][0]
        self.assertEqual(source['health'], 'error')
        self.assertEqual(source['reporting'], 'overdue')
        self.assertEqual(source['feature_count'], 42)
        self.assertEqual(source['last_success_at'], '2026-10-01T00:00:00+00:00')
        self.assertEqual(p['becker']['monitoring']['health'], 'unknown')
        self.assertEqual(p['becker']['monitoring']['reporting'], 'unknown')

    def test_repository_requires_distinct_parcel_evidence(self):
        state = {'sources': {'mn-parcel-county-catalog': {'status': 'ok', 'checked_at': STAMP,
            'county_records': {'Aitkin': {'data_url': 'https://example.com/parcels.zip', 'acqdate': 1760000000000}}}}}
        p = compose(state)['aitkin']
        self.assertFalse(p['monitoring']['active'])
        self.assertEqual(p['mngeo_public_repository']['sources'], [])

    def test_repository_exact_dataset_identity_retains_observation(self):
        research = load_parcel_access()
        dataset = {'inventory_id': 'repo-dataset', 'monitored_source_id': 'parcel-data', 'name': 'Repository parcels',
            'authority': 'statewide', 'dataset_type': 'parcels', 'approved_public_links': []}
        catalog = {**dataset, 'inventory_id': 'repo-catalog', 'monitored_source_id': 'mn-parcel-county-catalog'}
        research['Aitkin']['source_inventory']['mngeo_public_repository'].update(availability='yes', sources=[dataset, catalog])
        research['Aitkin']['source_inventory']['county_arcgis_rest'].update(availability='yes', sources=[copy.deepcopy(dataset)])
        state = {'sources': {'parcel-data': {'county_slug': 'aitkin', 'category': 'Parcels', 'adapter': 'arcgis_layer',
            'feature_count': 1234, 'checked_at': STAMP, 'last_success_at': STAMP, 'status': 'ok',
            'geometry_type': 'esriGeometryPolygon', 'editing_info': {'lastEditDate': 1735689600000}},
            'mn-parcel-county-catalog': {'county_slug': 'aitkin', 'category': 'Parcels', 'feature_count': 87,
                'checked_at': STAMP, 'status': 'ok', 'county_records': {'Aitkin': {'acqdate': 1735689600000}}}}}
        p = compose(state, research)['aitkin']
        observed, catalog_only = p['mngeo_public_repository']['sources']
        self.assertEqual(observed['feature_count'], 1234)
        self.assertEqual(observed['checked_at'], STAMP)
        self.assertEqual(observed['last_success_at'], STAMP)
        self.assertEqual(observed['health'], 'ok')
        self.assertEqual(observed['reporting'], 'current')
        self.assertEqual(observed['geometry_type'], 'esriGeometryPolygon')
        self.assertEqual(observed['provider_updated_at'], '2025-01-01T00:00:00+00:00')
        self.assertIsNone(catalog_only['feature_count'])
        self.assertIsNone(catalog_only['checked_at'])
        self.assertEqual(catalog_only['health'], 'unknown')
        self.assertEqual(catalog_only['county_acquired_at'], '2025-01-01T00:00:00+00:00')
        self.assertEqual(p['monitoring']['active_parcel_source_count'], 1)
        self.assertEqual(p['county_arcgis_rest']['sources'][0]['monitored_source_id'], observed['monitored_source_id'])
        del state['sources']['parcel-data']
        p = compose(state, research)['aitkin']
        self.assertFalse(p['monitoring']['active'])
        self.assertIsNone(p['mngeo_public_repository']['sources'][0]['feature_count'])

    def test_research_change_propagates_without_observation_change(self):
        research = load_parcel_access()
        before = compose(coverage_state(), research)
        research['Aitkin']['comments'] = 'New official evidence'
        after = compose(coverage_state(), research)
        self.assertEqual(after['aitkin']['comments'], ['New official evidence'])
        self.assertEqual(before['aitkin']['monitoring'], after['aitkin']['monitoring'])

    def test_fee_holds_and_viewer_remain_separate(self):
        p = compose(coverage_state())
        self.assertEqual(p['winona']['access']['public_classification'], 'FEE BASED')
        for slug in ('blue-earth', 'faribault', 'kandiyohi', 'lincoln'):
            self.assertEqual(p[slug]['access']['monitoring_decision'], 'hold-for-terms')
        self.assertEqual(p['aitkin']['access']['public_classification'], 'AMBIGUOUS')

    def test_missing_adapter_does_not_invent_category(self):
        p = compose({'sources': {'parcel': {'county_slug': 'aitkin', 'category': 'Parcels', 'checked_at': STAMP}}})['aitkin']
        self.assertTrue(p['monitoring']['active'])
        self.assertEqual(p['county_arcgis_rest']['sources'], [])
        self.assertEqual(p['county_download']['sources'], [])

    def test_inventory_identity_does_not_join_imagery_health(self):
        research = load_parcel_access()
        research['Aitkin']['source_inventory']['county_arcgis_rest'].update(availability='yes', sources=[{
            'inventory_id': 'parcel', 'monitored_source_id': 'parcel', 'name': 'Parcels', 'authority': 'county',
            'dataset_type': 'parcels', 'approved_public_links': [], 'monitoring_decision': 'candidate-low-frequency'}])
        p = compose({'sources': {'image': {'county_slug': 'aitkin', 'category': 'Imagery', 'checked_at': STAMP, 'status': 'error'}}}, research)['aitkin']
        self.assertEqual(p['county_arcgis_rest']['sources'][0]['health'], 'unknown')
        self.assertFalse(p['monitoring']['active'])

    def test_statewide_inventory_retained_without_wrong_identity_health(self):
        research = load_parcel_access()
        research['Aitkin']['source_inventory']['mngac_public_parcels'].update(availability='yes', sources=[{
            'inventory_id': 'other-statewide', 'monitored_source_id': 'other-statewide', 'name': 'Other parcel dataset',
            'authority': 'statewide', 'dataset_type': 'parcels', 'approved_public_links': []}])
        unknown = compose({}, research)['aitkin']['mngac_public_parcels']
        self.assertEqual(unknown['availability'], 'unknown')
        self.assertEqual(unknown['sources'][0]['inventory_id'], 'other-statewide')
        live = compose(coverage_state(), research)['aitkin']['mngac_public_parcels']
        self.assertEqual(live['sources'][0]['health'], 'unknown')
        self.assertIsNone(live['sources'][0]['feature_count'])
        self.assertEqual(live['sources'][1]['feature_count'], 1000)
