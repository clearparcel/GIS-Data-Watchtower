"""Map semantics must not confuse schema, access policy, health or missing data."""
import unittest

from clearparcel.datawatch.county_map_status import county_map_status, status_legend, status_patterns, MAP_STATUSES


class CountyMapStatusTests(unittest.TestCase):
    def test_standardized_product_takes_precedence_over_differing_direct_feed(self):
        profile = {'mngac_public_parcels': {'availability': 'yes'},
                   'direct_gac_schema': [{'status': 'schema-mismatch'}]}
        self.assertEqual(county_map_status(profile), 'standard')
        profile['direct_gac_schema'] = [{'status': 'not-assessed', 'reason': 'HTTP 403'}]
        self.assertEqual(county_map_status(profile), 'standard')
        profile['mngac_public_parcels']['availability'] = 'no'
        profile['direct_gac_schema'] = [{'status': 'standard-field-names'}]
        self.assertEqual(county_map_status(profile), 'standard')

    def test_differing_feed_unknown_schema_and_missing_product_are_separate(self):
        self.assertEqual(county_map_status({'direct_gac_schema': [{'status': 'schema-mismatch'}]}), 'different')
        for status in ('not-assessed', 'needs-recheck'):
            self.assertEqual(county_map_status({'direct_gac_schema': [{'status': status}],
                'access': {'public_classification': 'OPEN'}}), 'open-unassessed')
            self.assertEqual(county_map_status({'direct_gac_schema': [{'status': status}]}), 'unresolved')
        self.assertEqual(county_map_status({'access': {'public_classification': 'OPEN'}}), 'open-unassessed')
        self.assertEqual(county_map_status({}), 'unresolved')
        self.assertEqual(county_map_status({'mngac_public_parcels': {'availability': 'no'},
            'access': {'detailed_classification': 'parcel-viewer-only', 'public_classification': 'AMBIGUOUS'}}), 'unresolved')

    def test_fee_policy_is_not_overridden_by_reachable_rest_or_monitoring_health(self):
        profile = {'mngac_public_parcels': {'availability': 'no'},
                   'access': {'public_classification': 'FEE BASED'},
                   'county_arcgis_rest': {'availability': 'yes'},
                   'monitoring': {'active': False, 'health': 'ok'}}
        self.assertEqual(county_map_status(profile), 'closed')
        profile['direct_gac_schema'] = [{'status': 'not-assessed', 'reason': 'HTTP 403'}]
        self.assertEqual(county_map_status(profile), 'closed')
        profile['monitoring']['health'] = 'error'
        self.assertEqual(county_map_status(profile), 'closed')
        profile['mngac_public_parcels']['availability'] = 'unknown'
        self.assertEqual(county_map_status(profile), 'unresolved')
        profile['mngac_public_parcels']['availability'] = 'yes'
        self.assertEqual(county_map_status(profile), 'standard')

    def test_legend_and_svg_patterns_share_category_definitions(self):
        for key, (label, color, pattern) in MAP_STATUSES.items():
            self.assertIn(label, status_legend())
            self.assertIn('status-' + key, status_legend())
            self.assertIn(color, status_legend())
            if pattern:
                self.assertIn('id="' + pattern + '"', status_patterns())
