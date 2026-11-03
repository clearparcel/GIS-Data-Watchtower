import copy
import csv
import datetime as dt
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.county_profile_exports import county_data_fees_csv, county_profile_xlsx_sheets
from clearparcel.datawatch.county_profile_panel import render_county_profile_body, render_data_fees
from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles
from clearparcel.datawatch.dashboard_counties import render_fee_summary
from clearparcel.datawatch.data_fees import (LAYER_KEYS, county_fee_rows, fee_counts, load_data_fees,
                                             validate_data_fees)
from clearparcel.datawatch.parcel_access import load_parcel_access

DATA = Path(__file__).resolve().parents[1] / 'clearparcel' / 'datawatch' / 'minnesota_county_data_fees.json'
NOW = dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)


def entry(**overrides):
    base = {'fee_status': 'fee', 'rest_download': 'unconfirmed', 'amount': '$100', 'product': 'Parcel shapefile',
            'source_kind': 'published-fee-schedule', 'source_url': 'https://example.mn.us/fees.pdf',
            'source_date': '2026-10-06', 'note': 'Published fee.'}
    return {**base, **overrides}


def doc(layers, county='Brown'):
    return {'schema_version': 1, 'scope': 'test', 'counties': [{'county': county, 'layers': layers}]}


class DataFeeValidationTests(unittest.TestCase):
    def test_shipped_file_is_valid_and_covers_known_counties(self):
        fees = load_data_fees()
        for county in ('Brown', 'Swift', 'Blue Earth', 'Faribault', 'Kandiyohi', 'Lincoln', 'Goodhue',
                       'Le Sueur', 'Nicollet', 'Nobles', 'Redwood', 'Winona', 'Jackson'):
            self.assertEqual(fees[county]['parcels']['fee_status'], 'fee', county)
        self.assertEqual(fees['Blue Earth']['road_centerlines']['amount'], fees['Blue Earth']['parcels']['amount'])

    def test_every_research_parcel_fee_has_a_matching_fee_record(self):
        # The research dataset and the fee dataset must not drift apart.
        fees = load_data_fees()
        for name, record in load_parcel_access().items():
            if record.get('parcel_dataset_fee'):
                parcels = fees[name]['parcels']
                # A later county reply supersedes the researched schedule.
                if parcels['source_kind'] == 'county-response' and parcels['source_date'] > record['review_date']:
                    continue
                self.assertEqual(parcels['amount'], record['parcel_dataset_fee'], name)
                self.assertEqual(parcels['source_url'], record['fee_policy_url'], name)

    def test_seeded_rest_download_is_never_assumed(self):
        for layers in load_data_fees().values():
            for value in layers.values():
                if value['source_kind'] == 'published-fee-schedule':
                    self.assertEqual(value['rest_download'], 'unconfirmed')

    def test_rejects_inconsistent_or_unsourced_records(self):
        bad = [
            entry(fee_status='no-fee', amount=None, product=None, rest_download='fee'),
            entry(fee_status='no-fee', amount=None, product=None, rest_download='unconfirmed'),
            entry(amount=None),
            entry(source_url=None),
            entry(source_date='Oct 6'),
            entry(note='Ask gis@example.mn.us'),
            entry(source_url='javascript:alert(1)'),
            entry(fee_status='free'),
            entry(rest_download='not-offered'),
            {**entry(), 'extra': 1},
        ]
        for layer in bad:
            with self.subTest(layer=layer), self.assertRaises(ValueError):
                validate_data_fees(doc({'parcels': layer}))
        with self.assertRaises(ValueError):
            validate_data_fees(doc({'roads': entry()}))
        with self.assertRaises(ValueError):
            validate_data_fees(doc({'parcels': entry()}, county='Atlantis'), ['Brown'])

    def test_access_answer_without_fees_stays_unconfirmed(self):
        answer = entry(fee_status='unconfirmed', amount=None, product=None, rest_download='not-offered',
                       source_kind='county-response', source_url=None)
        validate_data_fees(doc({'parcels': answer}))
        for bad in ({**answer, 'source_kind': 'published-fee-schedule', 'source_url': 'https://example.mn.us/f.pdf'},
                    {**answer, 'rest_download': 'unconfirmed'}, {**answer, 'amount': '$5'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_data_fees(doc({'parcels': bad}))
        row = county_fee_rows({'parcels': answer})[0]
        self.assertEqual(row['fee_status_label'], 'Not yet confirmed')
        self.assertNotIn('$0', render_data_fees([row]))

    def test_county_response_may_cite_by_date_without_publishing_correspondence(self):
        validate_data_fees(doc({'address_points': entry(
            fee_status='no-fee', amount=None, product=None, rest_download='no-fee',
            source_kind='county-response', source_url=None, note='County GIS office confirmed no fee.')}))


class DataFeeProfileTests(unittest.TestCase):
    def profiles(self, fees=None):
        return compose_county_profiles({}, load_parcel_access(), now=NOW, freshness_policy=FreshnessPolicy(), fees=fees)

    def test_missing_layers_are_unconfirmed_not_free(self):
        rows = county_fee_rows(None)
        self.assertEqual([r['layer'] for r in rows], list(LAYER_KEYS))
        self.assertTrue(all(r['fee_status'] == 'unconfirmed' and r['amount'] is None for r in rows))
        html = render_data_fees(rows)
        self.assertIn('Not yet confirmed', html)
        self.assertNotIn('$0', html)
        self.assertIn('does not mean the data is free', html)

    def test_every_profile_carries_three_layers(self):
        profiles = self.profiles()
        self.assertEqual(len(profiles), 87)
        for profile in profiles.values():
            self.assertEqual([r['layer'] for r in profile['data_fees']], list(LAYER_KEYS))
        swift = profiles['swift']['data_fees'][0]
        self.assertEqual(swift['rest_download'], 'unconfirmed')
        brown = profiles['brown']['data_fees'][0]
        self.assertEqual((brown['source_kind'], brown['rest_download']), ('county-response', 'not-offered'))
        self.assertIn('data by request only', render_county_profile_body(profiles['brown']))

    def test_profile_panel_escapes_and_links_source(self):
        fees = {'Brown': {'parcels': entry(product='<b>Parcels</b>')}}
        html = render_county_profile_body(self.profiles(fees)['brown'])
        self.assertIn('<h3>Data fees</h3>', html)
        self.assertIn('&lt;b&gt;Parcels&lt;/b&gt;', html)
        self.assertIn('href="https://example.mn.us/fees.pdf"', html)

    def test_counts_and_statewide_card_separate_unknown_from_free(self):
        fees = {'Brown': {'parcels': entry()},
                'Wabasha': {'address_points': entry(fee_status='no-fee', amount=None, product=None, rest_download='no-fee',
                                                    source_kind='county-response', source_url=None, note='Confirmed.')}}
        profiles = self.profiles(fees)
        counts = fee_counts(profiles)
        self.assertEqual((counts['with_published_fee'], counts['with_confirmed_no_fee'], counts['fully_unconfirmed']), (1, 1, 85))
        card = render_fee_summary(profiles)
        self.assertIn('1 of 87 counties', card)
        self.assertIn('85 have no confirmed fee information yet', card)
        self.assertIn('Wabasha County', card)
        self.assertNotIn('Aitkin County', card)

    def test_csv_and_workbook_have_a_row_per_county_layer(self):
        profiles = self.profiles()
        rows = list(csv.DictReader(io.StringIO(county_data_fees_csv(profiles))))
        self.assertEqual(len(rows), 87 * 3)
        swift = next(r for r in rows if r['county'] == 'Swift' and r['layer'] == 'parcels')
        self.assertTrue(swift['amount'].startswith('$0.03'))
        anoka = next(r for r in rows if r['county'] == 'Anoka' and r['layer'] == 'parcels')
        self.assertEqual((anoka['fee_status'], anoka['amount']), ('unconfirmed', ''))
        aitkin = next(r for r in rows if r['county'] == 'Aitkin' and r['layer'] == 'address_points')
        self.assertEqual((aitkin['fee_status'], aitkin['rest_download'], aitkin['source_url']), ('no-fee', 'no-fee', ''))
        sheets = dict(county_profile_xlsx_sheets(profiles))
        self.assertEqual(len(sheets['Data Fees']), 87 * 3 + 1)


class DataFeeRouteTests(unittest.TestCase):
    def test_private_counties_page_shows_fee_card_and_export_link(self):
        with patch.object(dashboard, '_dashboard_state', return_value={'sources': {}}):
            html = dashboard.render_counties({})
        self.assertIn('County data fees', html)
        self.assertIn('/county-data-fees.csv', html)


if __name__ == '__main__':
    unittest.main()
