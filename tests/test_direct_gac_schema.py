"""Keep county membership, direct schema evidence and health independent."""
import datetime as dt
import csv
import io
import unittest

from unittest.mock import patch

from tests.html_text import page_text

from clearparcel.datawatch.county_profiles import compose_county_profiles, FreshnessPolicy, county_profile_counts
from clearparcel.datawatch.county_profile_panel import render_county_profile_body
from clearparcel.datawatch.county_profile_exports import county_profiles_csv, county_profile_xlsx_sheets
from clearparcel.datawatch.direct_gac_schema import load_direct_schema_assessments, direct_schema_assessment
from clearparcel.datawatch.dashboard_gac_counties import render_county_results
from clearparcel.datawatch.public_dashboard import render_public_source
from clearparcel.datawatch.gac_standards import load_gac_standard


class DirectGacSchemaTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)
        self.overlap = {'Aitkin', 'Dakota', 'Douglas', 'Koochiching', 'Morrison', 'Olmsted',
                        'Pipestone', 'Ramsey', 'Rice', 'Scott', 'St. Louis', 'Wabasha', 'Waseca'}
        from clearparcel.datawatch.dashboard import _load_counties
        slugs = {row['name']: row['slug'] for row in _load_counties()}
        self.state = {'sources': {sid: {'county_slug': slugs[row['county']], 'category': 'Parcels',
                                      'name': row['county'] + ' direct', 'field_count': row['field_count'],
                                      'status': 'ok', 'checked_at': self.now.isoformat()}
                                  for sid, row in load_direct_schema_assessments().items()}}
        self.state['sources']['mn-state-parcels'] = {'category': 'Parcels', 'status': 'ok',
            'checked_at': self.now.isoformat(), 'mngac_completeness': {
                'fields': {'CO_NAME': {}}, 'counties': {name: {'record_count': 1} for name in self.overlap}}}

    def profiles(self):
        return compose_county_profiles(self.state, {}, now=self.now, freshness_policy=FreshnessPolicy())

    def test_all_direct_counties_and_olmsted_overlap_remain_independent(self):
        profiles = self.profiles()
        self.assertEqual(county_profile_counts(profiles)['county_direct'], 24)
        self.assertEqual(county_profile_counts(profiles)['both'], 13)
        for profile in profiles.values():
            if profile['direct_gac_schema']:
                name = profile['county']['name']
                self.assertEqual(profile['mngac_public_parcels']['availability'], 'yes' if name in self.overlap else 'no')
        olmsted = profiles['olmsted']
        self.assertEqual(olmsted['monitoring']['paths'], ['county-direct', 'mngeo-open'])
        self.assertEqual(olmsted['direct_gac_schema'][0]['status'], 'not-assessed')
        self.assertEqual(olmsted['monitoring']['health'], 'ok')
        self.assertIn('HTTP 403', render_county_profile_body(olmsted))

    def test_absence_and_presence_never_infer_direct_compliance(self):
        beltrami = self.profiles()['beltrami']
        evidence = beltrami['direct_gac_schema'][0]
        self.assertEqual(evidence['status'], 'schema-mismatch')
        self.assertEqual(evidence['standard_fields_present'], 20)
        self.assertEqual(evidence['mandatory_fields_present'], 1)
        self.assertIn('EXP_DATE', evidence['missing_mandatory_fields'])
        self.state['sources']['mn-state-parcels']['mngac_completeness']['counties']['Beltrami'] = {'record_count': 1}
        self.assertEqual(self.profiles()['beltrami']['direct_gac_schema'], beltrami['direct_gac_schema'])
        del self.state['sources']['mn-state-parcels']
        profile = self.profiles()['beltrami']
        self.assertEqual(profile['mngac_public_parcels']['availability'], 'unknown')
        self.assertEqual(profile['direct_gac_schema'], beltrami['direct_gac_schema'])

    def test_full_names_do_not_certify_compliance_and_unknown_sources_stay_unknown(self):
        sid = 'mn-wabasha-parcels'
        result = direct_schema_assessment(sid, self.state['sources'][sid])
        self.assertEqual(result['status'], 'standard-field-names')
        self.assertEqual(result['standard_fields_present'], len(load_gac_standard('parcel')['fields']))
        page = render_county_profile_body(self.profiles()['wabasha'])
        self.assertIn('Names alone do not establish full compliance', page_text(page))
        self.assertEqual(direct_schema_assessment('new-feed', self.state['sources'][sid])['status'], 'not-assessed')
        self.assertEqual(direct_schema_assessment(sid, {'category': 'Parcels', 'county_slug': 'beltrami'})['status'], 'not-assessed')
        self.state['sources'][sid]['field_count'] += 1
        self.assertEqual(direct_schema_assessment(sid, self.state['sources'][sid])['status'], 'needs-recheck')

    def test_county_results_source_page_and_exports_share_findings(self):
        profile = self.profiles()['beltrami']
        self.assertIn('Direct feed does not match', render_county_profile_body(profile))
        with patch('clearparcel.datawatch.dashboard._dashboard_state', return_value=self.state):
            page = render_county_results({'_public_mode': True}, 'parcel', profile['county'])
        self.assertIn('Not in MnGeo Open Parcels', page)
        self.assertIn('20 / 91 standard field names', page)
        self.assertIn('Missing mandatory names', page)
        with patch('clearparcel.datawatch.public_dashboard._dashboard_state', return_value=self.state):
            page = render_public_source({}, 'mn-beltrami-parcels-direct')
        self.assertIn('20 / 91 standard field names', page)
        rows = {row['county_slug']: row for row in csv.DictReader(io.StringIO(county_profiles_csv(self.profiles())))}
        self.assertEqual(rows['beltrami']['direct_gac_schema_status'], profile['direct_gac_schema'][0]['status'])
        self.assertEqual(rows['beltrami']['direct_gac_standard_names'], '20 / 91')
        self.assertEqual(rows['beltrami']['direct_gac_mandatory_names'], '1 / 7')
        self.assertEqual(rows['olmsted']['direct_gac_schema_status'], 'not-assessed')
        self.assertEqual(rows['olmsted']['direct_gac_reason'], 'HTTP 403')
        self.assertEqual(rows['olmsted']['direct_gac_standard_names'], 'Not assessed')
        sheets = county_profile_xlsx_sheets(self.profiles())
        fields, *values = sheets[0][1]
        workbook = {row[fields.index('county_slug')]: dict(zip(fields, row)) for row in values}
        self.assertEqual(workbook['beltrami']['direct_gac_schema_status'], rows['beltrami']['direct_gac_schema_status'])
        self.assertEqual(workbook['beltrami']['direct_gac_standard_names'], rows['beltrami']['direct_gac_standard_names'])


if __name__ == '__main__':
    unittest.main()


class DirectSchemaNameDriftTests(unittest.TestCase):
    """Audit WT-A07: unchanged field count alone does not re-establish audited names."""

    def setUp(self):
        self.record = load_direct_schema_assessments()['mn-wabasha-parcels']
        self.standard = [field['field'] for field in load_gac_standard('parcel')['fields']]
        self.extra = [f'COUNTY_ONLY_{n}' for n in range(self.record['field_count'] - len(self.standard))]

    def assess(self, **source):
        return direct_schema_assessment('mn-wabasha-parcels', {'county_slug': 'wabasha', 'category': 'Parcels',
                                                               'field_count': self.record['field_count'], **source})

    def test_same_count_rename_needs_recheck(self):
        renamed = [f'RENAMED_{n}' for n in range(self.record['field_count'])]
        result = self.assess(field_names=renamed)
        self.assertEqual(result['status'], 'needs-recheck')
        self.assertEqual(result['reason'], 'Observed MN GAC field names changed since the schema audit.')
        self.assertEqual(result['checked_at'], self.record['checked_at'])  # audit date is kept

    def test_same_count_mandatory_replacement_needs_recheck(self):
        mandatory = next(f['field'] for f in load_gac_standard('parcel')['fields'] if f['inclusion'] == 'Mandatory')
        names = [name for name in self.standard if name != mandatory] + self.extra + ['REPLACEMENT']
        self.assertEqual(len(names), self.record['field_count'])
        self.assertEqual(self.assess(field_names=names)['status'], 'needs-recheck')

    def test_order_case_and_non_standard_renames_are_harmless(self):
        names = [name.lower() for name in reversed(self.standard)] + [f'OTHER_{n}' for n in range(len(self.extra))]
        self.assertEqual(self.assess(field_names=names)['status'], 'standard-field-names')

    def test_count_change_and_absent_evidence_keep_existing_behavior(self):
        changed = self.assess(field_names=self.standard + self.extra, field_count=self.record['field_count'] + 1)
        self.assertEqual((changed['status'], changed['reason']),
                         ('needs-recheck', 'Observed field count changed since the schema audit.'))
        self.assertEqual(self.assess()['status'], 'standard-field-names')  # no names known: count only

    def test_public_projection_carries_only_standard_names_and_detects_renames(self):
        from clearparcel.datawatch.public_projection import sanitize_public_render_state
        state = {'schema_version': 3, 'generated_at': '2026-10-24T10:00:00+00:00', 'counts': {}, 'workers': {},
                 'sources': {'mn-wabasha-parcels': {'id': 'mn-wabasha-parcels', 'county_slug': 'wabasha',
                                                    'category': 'Parcels', 'status': 'ok',
                                                    'field_count': self.record['field_count'],
                                                    'field_names': self.standard[1:] + self.extra + ['PRIVATE_NAME']},
                             'roads': {'id': 'roads', 'category': 'Road centerlines', 'status': 'ok',
                                       'field_names': self.standard}}}
        public = sanitize_public_render_state(state)['sources']
        parcel = public['mn-wabasha-parcels']
        self.assertNotIn('field_names', parcel)
        self.assertEqual(parcel['gac_standard_field_names'], sorted(self.standard[1:]))
        self.assertNotIn('gac_standard_field_names', public['roads'])
        self.assertEqual(direct_schema_assessment('mn-wabasha-parcels', parcel)['status'], 'needs-recheck')
