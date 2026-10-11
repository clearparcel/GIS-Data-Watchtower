import html
import re
import unittest
from unittest.mock import patch

from clearparcel.datawatch.dashboard import render_mngac
from clearparcel.datawatch.gac_standards import load_gac_standard


def county_state(key='parcel'):
    schema = load_gac_standard(key)
    scanned = next(f for f in schema['fields'] if f['inclusion'] == 'Mandatory')
    unscanned = next(f for f in schema['fields'] if f['inclusion'] != 'Mandatory')
    data = {
        'standard_key': key, 'standard': schema['standard'], 'population_scope': 'mandatory',
        'record_count': 1000, 'field_count': len(schema['fields']), 'covered_counties': 1,
        'mandatory_population_percent': 99.0, 'observed_at': '2026-10-09T14:00:00+00:00',
        'fields': {
            scanned['field']: {**scanned, 'present_in_source_schema': True,
                              'population_scanned': True, 'populated': 990, 'record_count': 1000, 'percent': 99.0},
            unscanned['field']: {**unscanned, 'present_in_source_schema': True, 'population_scanned': False},
        },
        'counties': {'Douglas': {'record_count': 20, 'mandatory_population_percent': 25.0,
                                'fields': {scanned['field']: {'populated': 5, 'record_count': 20, 'percent': 25.0}}}},
    }
    return {'sources': {key: {'status': 'ok', 'gac_completeness': data}}}, scanned, unscanned


class GACCountyViewTests(unittest.TestCase):
    def render(self, key='parcel', **kwargs):
        state, _, _ = county_state(key)
        with patch('clearparcel.datawatch.dashboard._dashboard_state', return_value=state):
            return render_mngac({'_public_mode': True}, key, **kwargs)

    def test_landing_puts_county_search_first_and_links_all_counties(self):
        page = self.render()
        self.assertIn('County results', page)
        self.assertIn('Statewide overview', page)
        self.assertIn('View county results', page)
        self.assertLess(page.index('Choose county'), page.index('Interactive Minnesota county map'))
        self.assertNotIn('Statewide MN GAC field completeness', page)
        links = re.findall(r'<a class="gac-map-link"[^>]*href="([^"]+)"', page)
        self.assertEqual(len(links), 87)
        self.assertTrue(all('view=county' in link and 'county=' in link for link in links))
        self.assertNotIn('dialog.showModal()', page)

    def test_county_results_use_county_denominators_for_every_standard(self):
        for key in ('parcel', 'address', 'road'):
            with self.subTest(key=key):
                page = self.render(key, county='douglas')
                self.assertIn('Douglas County', page)
                self.assertIn('25.00%', page)
                self.assertNotIn('99.00%', page)
                self.assertNotIn('>990<', page)
                self.assertIn('>5</td><td>20</td><td>25.00%</td>', page)
                self.assertIn('Not scanned', page)
                self.assertNotIn('>0.00%</td>', page)
                self.assertIn('County field results', page)

    def test_navigation_preserves_county_and_scope_across_standards(self):
        page = html.unescape(self.render('road', county='Douglas County'))
        for key in ('parcel', 'address', 'road'):
            self.assertIn(f'/mngac?standard={key}&view=county&county=douglas', page)
        self.assertIn('/mngac?standard=road&view=statewide&county=douglas', page)
        statewide = html.unescape(self.render('road', county='douglas', view='statewide'))
        self.assertIn('Statewide field completeness', statewide)
        self.assertIn('99.00%', statewide)
        self.assertIn('/mngac?standard=parcel&view=statewide&county=douglas', statewide)
        self.assertNotIn('dialog.showModal()', statewide)

    def test_unrepresented_county_and_missing_observation_remain_unavailable(self):
        page = self.render(county='aitkin')
        self.assertIn('Not in MnGeo Open Parcels', page)
        self.assertIn('N/A', page)
        self.assertNotIn('>0.00%', page)
        with patch('clearparcel.datawatch.dashboard._dashboard_state', return_value={}):
            page = render_mngac({'_public_mode': True}, 'address', county='douglas')
        self.assertIn('Douglas County', page)
        self.assertIn('Statewide results unavailable', page)
        self.assertIn('N/A', page)
        self.assertIn('Choose county', page)

    def test_invalid_county_and_scope_are_rejected(self):
        for kwargs in ({'county': '<script>'}, {'view': 'invalid'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.render(**kwargs)

    def test_county_suggestions_show_only_the_county_name(self):
        page = self.render()
        options = re.search(r'<datalist id="gac-county-options">(.*?)</datalist>', page, re.S).group(1)
        self.assertEqual(options.count('<option'), 87)
        self.assertIn('<option value="Douglas"></option>', options)
        self.assertNotIn(' County', options)

    def test_zero_population_is_distinct_from_unscanned(self):
        state, field, _ = county_state()
        stats = state['sources']['parcel']['gac_completeness']['counties']['Douglas']['fields'][field['field']]
        stats.update(populated=0, percent=0.0)
        with patch('clearparcel.datawatch.dashboard._dashboard_state', return_value=state):
            page = render_mngac({'_public_mode': True}, county='douglas')
        self.assertIn('>0</td><td>20</td><td>0.00%</td>', page)


    def test_parcel_map_uses_all_field_population_but_address_uses_mandatory(self):
        from clearparcel.datawatch.dashboard_gac_counties import county_map
        from clearparcel.datawatch.county_profile_panel import PERCENT_COLORS, NO_DATA_COLOR

        data = {'counties': {'Douglas': {
            'field_population_percent': 20.0,
            'mandatory_population_percent': 80.0,
        }}}

        def douglas_fill(key):
            markup = county_map(key, data)
            match = re.search(r'<a[^>]+county=douglas[^>]*><path[^>]+style="fill:([^"]+)"', markup)
            self.assertIsNotNone(match, markup)
            return match.group(1)

        self.assertEqual(douglas_fill('parcel'), PERCENT_COLORS[0])
        self.assertEqual(douglas_fill('address'), PERCENT_COLORS[3])
        data['counties']['Douglas']['field_population_percent'] = float('nan')
        self.assertEqual(douglas_fill('parcel'), NO_DATA_COLOR)
        data['counties']['Douglas']['field_population_percent'] = 101.0
        self.assertEqual(douglas_fill('parcel'), NO_DATA_COLOR)

    def test_parcel_county_result_explains_repeated_mandatory_rates(self):
        state, _, _ = county_state('parcel')
        county = state['sources']['parcel']['gac_completeness']['counties']['Douglas']
        county['field_population_percent'] = 23.45
        state['sources']['parcel']['gac_completeness']['population_scope'] = 'all'
        with patch('clearparcel.datawatch.dashboard._dashboard_state', return_value=state):
            page = render_mngac({'_public_mode': True}, 'parcel', county='douglas')
        self.assertIn('23.45%', page)
        self.assertIn('seven mandatory fields', page)
        self.assertIn('All-field population', page)

if __name__ == '__main__':
    unittest.main()
