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
    def test_final_inventory_batch_preserves_policy_and_exact_observation_identity(self):
        research = load_parcel_access()
        empty = compose(research=research)
        self.assertEqual(empty['swift']['access']['public_classification'], 'FEE BASED')
        self.assertEqual(empty['wilkin']['access']['public_classification'], 'OPEN')
        for slug in ('swift', 'wilkin'):
            self.assertEqual(empty[slug]['access']['monitoring_decision'], 'hold-for-terms')
            self.assertFalse(empty[slug]['monitoring']['active'])
        self.assertFalse(empty['swift']['research']['complete'])
        self.assertFalse(empty['traverse']['research']['complete'])
        self.assertTrue(empty['washington']['research']['complete'])
        ids = {'wabasha': 'mn-wabasha-parcels', 'waseca': 'mn-waseca-parcels-direct', 'swift': 'mn-swift-parcels-direct'}
        state = {'sources': {source_id: {'id': source_id, 'county_slug': slug, 'category': 'Parcels',
            'adapter': 'arcgis_layer', 'status': 'ok', 'checked_at': STAMP, 'feature_count': 17}
            for slug, source_id in ids.items()}}
        profiles = compose(state, research)
        for slug, source_id in ids.items():
            self.assertEqual(profiles[slug]['county_arcgis_rest']['sources'][0]['monitored_source_id'], source_id)
            self.assertEqual(profiles[slug]['county_arcgis_rest']['sources'][0]['feature_count'], 17)
            self.assertEqual(profiles[slug]['monitoring']['active_parcel_source_count'], 1)
        for category in ('mngeo_public_repository', 'county_download'):
            self.assertEqual(profiles['wabasha'][category]['sources'][0]['feature_count'], 17)
        self.assertIsNone(profiles['washington']['county_arcgis_rest']['sources'][0]['feature_count'])

    def test_st_louis_native_product_identity_and_inventory_completion(self):
        research = load_parcel_access()
        profiles = compose(research=research)
        for name, slug in (('Sherburne', 'sherburne'), ('St. Louis', 'st-louis'),
                           ('Stearns', 'stearns'), ('Stevens', 'stevens')):
            self.assertFalse(profiles[slug]['research']['complete'])
        self.assertTrue(profiles['steele']['research']['complete'])
        for category in ('county_arcgis_rest', 'county_download'):
            source = research['St. Louis']['source_inventory'][category]['sources'][0]
            self.assertEqual(source['monitored_source_id'], 'mn-st-louis-parcels-direct')
            self.assertEqual(source['layer_id'], 7)
        self.assertFalse(profiles['st-louis']['monitoring']['active'])

    def test_olmsted_scott_inventory_keeps_blocks_products_and_observations_separate(self):
        research = load_parcel_access()
        names = ('Olmsted', 'Otter Tail', 'Pipestone', 'Polk', 'Pope',
                 'Ramsey', 'Renville', 'Rice', 'Scott')
        profiles = compose(research=research)
        for name in names:
            record = research[name]
            self.assertTrue(record['statewide_open_coverage']['available'])
            self.assertTrue(all(c['review_status'] != 'pending'
                                for c in record['source_inventory'].values()))
            self.assertEqual(record['monitoring']['decision'], 'not-assessed')
            self.assertIsNone(record['parcel_dataset_fee'])
            self.assertFalse(profiles[name.lower().replace(' ', '-')]['research']['complete'])
        for name in ('Olmsted', 'Ramsey'):
            self.assertEqual(research[name]['source_inventory']['county_arcgis_rest']['review_status'], 'blocked')
            self.assertEqual(research[name]['source_inventory']['county_arcgis_rest']['availability'], 'unknown')
            self.assertEqual(research[name]['source_inventory']['county_download']['availability'], 'yes')
        self.assertFalse(research['Rice']['research_complete'])
        self.assertFalse(research['Rice']['usable_direct_machine_readable_source'])
        self.assertIsNone(research['Rice']['county_direct_classification'])
        self.assertEqual(research['Rice']['source_inventory']['county_download']['availability'], 'unknown')
        for category in ('mngeo_public_repository', 'county_arcgis_rest'):
            self.assertEqual(research['Rice']['source_inventory'][category]['availability'], 'yes')
        state = {'sources': {f'mn-{slug}-parcels-direct': {
            'id': f'mn-{slug}-parcels-direct', 'county_slug': slug, 'category': 'Parcels',
            'adapter': 'arcgis_layer', 'status': 'ok', 'checked_at': STAMP,
            'last_success_at': STAMP, 'feature_count': 42}
            for slug in ('pipestone', 'rice', 'ramsey', 'scott', 'olmsted')}}
        profiles = compose(state)
        for slug, categories in (
            ('pipestone', ('county_arcgis_rest', 'county_download')),
            ('rice', ('mngeo_public_repository', 'county_arcgis_rest')),
            ('ramsey', ('county_download',)),
            ('scott', ('county_arcgis_rest', 'county_download')),
        ):
            for category in categories:
                source = profiles[slug][category]['sources'][0]
                self.assertEqual(source['monitored_source_id'], f'mn-{slug}-parcels-direct')
                self.assertEqual(source['feature_count'], 42)
        source = profiles['olmsted']['county_download']['sources'][0]
        self.assertIsNone(source['monitored_source_id'])
        self.assertIsNone(source['feature_count'])
        self.assertEqual(profiles['ramsey']['county_arcgis_rest']['availability'], 'unknown')
        self.assertFalse(profiles['rice']['research']['complete'])

    def test_isanti_mower_inventory_preserves_delegation_terms_and_identity(self):
        research = load_parcel_access()
        names = ('Isanti', 'Itasca', 'Koochiching', 'Lake', 'Lyon', 'McLeod',
                 'Mille Lacs', 'Morrison', 'Mower')
        for name in names:
            self.assertTrue(research[name]['statewide_open_coverage']['available'])
            self.assertTrue(all(c['review_status'] != 'pending'
                                for c in research[name]['source_inventory'].values()))
        for name in ('Lake', 'Lyon', 'McLeod'):
            self.assertEqual(research[name]['county_direct_classification'], 'free-parcel-data')
            self.assertEqual(research[name]['monitoring']['decision'], 'hold-for-terms')
            self.assertTrue(research[name]['monitoring']['terms_urls'])
        for name in ('Itasca', 'Lake', 'Morrison'):
            self.assertEqual(research[name]['source_inventory']['mngeo_public_repository']['availability'], 'yes')
        self.assertEqual(research['Koochiching']['source_inventory']['county_download']['availability'], 'unknown')
        self.assertEqual(research['McLeod']['source_inventory']['county_arcgis_rest']['availability'], 'unknown')
        mille = research['Mille Lacs']['source_inventory']
        self.assertIsNone(mille['county_download']['sources'][0]['layer_id'])
        self.assertEqual(mille['county_download']['sources'][0]['dataset_type'], 'File Geodatabase parcel download')
        self.assertEqual(mille['county_arcgis_rest']['sources'][0]['layer_id'], 3)
        state = {'sources': {'mn-morrison-parcels-direct': {
            'id': 'mn-morrison-parcels-direct', 'county_slug': 'morrison', 'category': 'Parcels',
            'adapter': 'arcgis_service', 'status': 'ok', 'checked_at': STAMP,
            'last_success_at': STAMP, 'feature_count': 42}, 'mn-koochiching-parcels-direct': {
            'id': 'mn-koochiching-parcels-direct', 'county_slug': 'koochiching', 'category': 'Parcels',
            'adapter': 'arcgis_layer', 'status': 'ok', 'checked_at': STAMP,
            'last_success_at': STAMP, 'feature_count': 99}}}
        profiles = compose(state)
        for category in ('mngeo_public_repository', 'county_arcgis_rest', 'county_download'):
            source = profiles['morrison'][category]['sources'][0]
            self.assertEqual(source['monitored_source_id'], 'mn-morrison-parcels-direct')
            self.assertEqual(source['feature_count'], 42)
        source = profiles['koochiching']['county_arcgis_rest']['sources'][0]
        self.assertIsNone(source['monitored_source_id'])
        self.assertIsNone(source['feature_count'])
        for category in ('mngeo_public_repository', 'county_arcgis_rest', 'county_download'):
            self.assertTrue(all(s['monitored_source_id'] is None
                                for s in profiles['itasca'][category]['sources']))

    def test_clearwater_houston_inventory_preserves_product_identity_and_policy(self):
        research = load_parcel_access()
        names = ('Clearwater', 'Cook', 'Crow Wing', 'Dakota', 'Douglas',
                 'Fillmore', 'Grant', 'Hennepin', 'Houston')
        for name in names:
            record = research[name]
            self.assertEqual(record['county_direct_classification'], 'free-parcel-data')
            self.assertTrue(record['research_complete'])
            self.assertTrue(record['statewide_open_coverage']['available'])
            self.assertEqual(record['monitoring']['decision'], 'not-assessed')
            self.assertTrue(all(c['review_status'] != 'pending'
                                for c in record['source_inventory'].values()))
        self.assertEqual(research['Clearwater']['source_inventory']['county_arcgis_rest']['availability'], 'unknown')
        for name in ('Dakota', 'Hennepin', 'Fillmore', 'Houston'):
            self.assertEqual(research[name]['source_inventory']['mngeo_public_repository']['availability'], 'yes')
        state = {'sources': {'mn-dakota-parcels-direct': {
            'id': 'mn-dakota-parcels-direct', 'county_slug': 'dakota', 'category': 'Parcels',
            'adapter': 'arcgis_layer', 'status': 'ok', 'checked_at': STAMP,
            'last_success_at': STAMP, 'feature_count': 42}, 'mn-douglas-parcels-direct': {
            'id': 'mn-douglas-parcels-direct', 'county_slug': 'douglas', 'category': 'Parcels',
            'adapter': 'arcgis_layer', 'status': 'ok', 'checked_at': STAMP,
            'last_success_at': STAMP, 'feature_count': 99}}}
        profiles = compose(state)
        for category in ('county_arcgis_rest', 'county_download'):
            source = profiles['dakota'][category]['sources'][0]
            self.assertEqual(source['feature_count'], 42)
            self.assertEqual(source['monitored_source_id'], 'mn-dakota-parcels-direct')
            source = profiles['douglas'][category]['sources'][0]
            self.assertIsNone(source['feature_count'])
            self.assertIsNone(source['monitored_source_id'])
        self.assertTrue(all(s['monitored_source_id'] is None
                            for s in profiles['dakota']['mngeo_public_repository']['sources']))

    def test_aitkin_clay_batch_reviews_keep_policy_and_runtime_independent(self):
        names = ('Aitkin', 'Anoka', 'Becker', 'Beltrami', 'Benton', 'Big Stone',
                 'Carlton', 'Carver', 'Cass', 'Chippewa', 'Chisago', 'Clay')
        research = load_parcel_access()
        profiles = compose(research=research)
        for name in names:
            record = research[name]
            profile = profiles[name.lower().replace(' ', '-')]
            self.assertFalse(profile['monitoring']['active'])
            self.assertEqual(record['monitoring']['decision'], 'not-assessed')
            self.assertIsNone(record['parcel_dataset_fee'])
            for category in record['source_inventory'].values():
                self.assertNotEqual(category['review_status'], 'pending')
                self.assertTrue(category['evidence'])
        self.assertFalse(research['Beltrami']['statewide_open_coverage']['available'])
        self.assertEqual(research['Beltrami']['county_direct_classification'], 'free-parcel-data')
        self.assertEqual(profiles['beltrami']['county_download']['availability'], 'yes')
        self.assertEqual(profiles['benton']['county_download']['availability'], 'unknown')
        self.assertEqual(profiles['benton']['county_arcgis_rest']['availability'], 'yes')
        for name, layer in (('Anoka', 0), ('Carver', 1)):
            source = research[name]['source_inventory']['mngeo_public_repository']['sources'][0]
            self.assertEqual(source['layer_id'], layer)
            self.assertTrue(any('arcgis.metc.state.mn.us' in link['href'] for link in source['approved_public_links']))
            self.assertNotIn('monitored_source_id', source)
        for name in ('Aitkin', 'Big Stone', 'Cass'):
            self.assertIsNone(research[name]['county_direct_classification'])
            self.assertFalse(profiles[name.lower().replace(' ', '-')]['research']['complete'])

    def test_aitkin_beltrami_exact_dataset_joins_share_observation(self):
        for name, layer in (('Aitkin', 0), ('Beltrami', 2)):
            slug = name.lower()
            source_id = 'mn-' + slug + '-parcels-direct'
            state = {'sources': {source_id: {'id': source_id, 'county_slug': slug,
                'category': 'Parcels', 'adapter': 'arcgis_layer', 'status': 'ok',
                'checked_at': STAMP, 'last_success_at': STAMP, 'feature_count': 42}}}
            profile = compose(state)[slug]
            for category in ('county_arcgis_rest', 'county_download'):
                source = profile[category]['sources'][0]
                self.assertEqual(source['monitored_source_id'], source_id)
                self.assertEqual(source['layer_id'], layer)
                self.assertEqual(source['feature_count'], 42)
            self.assertEqual(profile['monitoring']['active_parcel_source_count'], 1)

    def test_inventory_completion_requires_all_four_evidence_reviews(self):
        research = load_parcel_access()
        record = research['Brown']
        for category in INVENTORY_CATEGORIES:
            record['source_inventory'][category]['review_status'] = 'reviewed'
        self.assertTrue(compose(research=research)['brown']['research']['complete'])
        for category in INVENTORY_CATEGORIES:
            for status in ('pending', 'blocked'):
                with self.subTest(category=category, status=status):
                    record['source_inventory'][category]['review_status'] = status
                    self.assertFalse(compose(research=research)['brown']['research']['complete'])
                    record['source_inventory'][category]['review_status'] = 'reviewed'

    def test_original_inventory_batch_preserves_fee_viewer_and_holds(self):
        research = load_parcel_access()
        self.assertEqual(research['Winona']['county_direct_classification'], 'fee-based-parcel-data')
        self.assertEqual(research['Cottonwood']['county_direct_classification'], 'parcel-viewer-only')
        brown = research['Brown']
        self.assertEqual(brown['county_direct_classification'], 'fee-based-parcel-data')
        self.assertEqual(brown['parcel_dataset_fee'], '$697')
        self.assertEqual(brown['monitoring']['decision'], 'hold-for-terms')
        self.assertIn('shapefile', brown['fee_product'].lower())
        for name in ('Blue Earth', 'Faribault', 'Kandiyohi', 'Lincoln'):
            self.assertEqual(research[name]['monitoring']['decision'], 'hold-for-terms')
        for name in ('Brown', 'Dodge'):
            for category in INVENTORY_CATEGORIES:
                self.assertNotEqual(research[name]['source_inventory'][category]['review_status'], 'pending')

    def test_brown_fee_hold_retains_exact_observed_source_join(self):
        source_id = 'mn-brown-parcels-direct'
        state = {'sources': {source_id: {'id': source_id, 'county_slug': 'brown',
            'category': 'Parcels', 'adapter': 'arcgis_layer', 'status': 'ok',
            'checked_at': STAMP, 'last_success_at': STAMP, 'feature_count': 42}}}
        profile = compose(state)['brown']
        source = profile['county_arcgis_rest']['sources'][0]
        self.assertEqual(profile['access']['public_classification'], 'FEE BASED')
        self.assertEqual(profile['access']['monitoring_decision'], 'hold-for-terms')
        self.assertEqual(source['monitored_source_id'], source_id)
        self.assertEqual(source['feature_count'], 42)
        self.assertTrue(profile['monitoring']['active'])
        self.assertFalse(profile['research']['complete'])

    def test_hub_download_and_rest_share_one_observation(self):
        source_id = 'mn-hubbard-parcels-direct'
        state = {'sources': {source_id: {'id': source_id, 'county_slug': 'hubbard',
            'category': 'Parcels', 'adapter': 'arcgis_layer', 'status': 'ok',
            'checked_at': STAMP, 'last_success_at': STAMP, 'feature_count': 42}}}
        profile = compose(state)['hubbard']
        self.assertEqual(profile['county_download']['availability'], 'yes')
        self.assertEqual(profile['county_download']['sources'][0]['feature_count'], 42)
        self.assertEqual(profile['county_arcgis_rest']['sources'][0]['feature_count'], 42)
        self.assertEqual(profile['monitoring']['active_parcel_source_count'], 1)


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
        source = next(s for s in p['aitkin']['mngac_public_parcels']['sources'] if s['monitored_source_id'] == 'statewide')
        self.assertEqual(source['feature_count'], 1000)
        self.assertNotEqual(source['feature_count'], 999999)

    def test_no_observation_means_unknown(self):
        self.assertEqual(compose()['winona']['mngac_public_parcels']['availability'], 'unknown')
        state = coverage_state()
        state['sources']['statewide']['mngac_completeness']['counties']['Aitkin']['record_count'] = None
        observed = lambda: next(s for s in compose(state)['aitkin']['mngac_public_parcels']['sources'] if s['monitored_source_id'] == 'statewide')
        self.assertIsNone(observed()['feature_count'])
        state['sources']['statewide']['mngac_completeness']['counties']['Aitkin']['record_count'] = 0
        self.assertEqual(observed()['feature_count'], 0)

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
        source = next(s for s in p['anoka']['county_arcgis_rest']['sources'] if s['monitored_source_id'] == 'parcel')
        self.assertEqual(source['health'], 'error')
        self.assertEqual(source['reporting'], 'overdue')
        self.assertEqual(source['feature_count'], 42)
        self.assertEqual(source['last_success_at'], '2026-10-01T00:00:00+00:00')
        self.assertEqual(p['becker']['monitoring']['health'], 'unknown')
        self.assertEqual(p['becker']['monitoring']['reporting'], 'unknown')

    def test_repository_requires_distinct_parcel_evidence(self):
        state = {'sources': {'mn-parcel-county-catalog': {'status': 'ok', 'checked_at': STAMP,
            'county_records': {'Aitkin': {'data_url': 'https://example.com/parcels.zip', 'acqdate': 1760000000000}}}}}
        p = compose(state, research={})['aitkin']
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
        p = compose({'sources': {'parcel': {'county_slug': 'aitkin', 'category': 'Parcels', 'checked_at': STAMP}}}, research={})['aitkin']
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
