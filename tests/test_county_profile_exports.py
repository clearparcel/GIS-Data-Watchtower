import csv
import io
import unittest
import zipfile
import xml.etree.ElementTree as ET
from unittest.mock import patch
from clearparcel.datawatch import dashboard
from clearparcel.datawatch.county_profile_exports import county_profiles_csv, parcel_sources_csv, county_profile_xlsx_sheets

class CountyProfileExportTests(unittest.TestCase):
    def snapshot(self):
        with patch.object(dashboard, '_dashboard_state', side_effect=[{'sources': {}}, {'sources': {'changed': {'name': 'Changed'}}}]) as loader, patch.object(dashboard, 'load_parcel_access', wraps=dashboard.load_parcel_access) as research:
            snap = dashboard._statewide_snapshot({})
            self.assertEqual(loader.call_count, 1)
            self.assertEqual(research.call_count, 1)
        return snap

    def test_all_87_counties_in_json_csv_and_xlsx(self):
        snap = self.snapshot()
        profiles = {r['parcel_source_profile']['county']['slug']: r['parcel_source_profile'] for r in snap['counties']}
        rows = list(csv.DictReader(io.StringIO(county_profiles_csv(profiles))))
        self.assertEqual(len({r['county_slug'] for r in rows}), 87)
        sources = list(csv.DictReader(io.StringIO(parcel_sources_csv(profiles))))
        self.assertGreaterEqual(len(sources), 348)
        self.assertEqual(len({(r['county_slug'], r['category']) for r in sources}), 348)
        with zipfile.ZipFile(io.BytesIO(dashboard._snapshot_xlsx(snap))) as z:
            ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            sheets = ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet', ns)
            names = [s.attrib['name'] for s in sheets]
            self.assertIn('Counties', names)
            for name, minimum in [('County Access', 88), ('Parcel Sources', 349)]:
                tree = ET.fromstring(z.read(f'xl/worksheets/sheet{names.index(name)+1}.xml'))
                self.assertGreaterEqual(len(tree.findall('s:sheetData/s:row', ns)), minimum)

    def test_export_counts_dates_and_nulls_agree(self):
        p = self.snapshot()['counties'][0]['parcel_source_profile']
        p['county_download']['sources'] = [{'name': ' \t=1\x01', 'feature_count': 0, 'provider_updated_at': '2026-10-06', 'approved_public_links': [{'href':'https://example.com/data'}, {'href':'http://localhost/private'}]}, {'name':'Unknown', 'feature_count':None}]
        profiles = {p['county']['slug']:p}
        rows = [r for r in csv.DictReader(io.StringIO(parcel_sources_csv(profiles))) if r['category']=='county_download']
        self.assertEqual([r['feature_count'] for r in rows], ['0',''])
        self.assertEqual(rows[0]['provider_updated_at'], '2026-10-06')
        self.assertEqual(rows[1]['provider_updated_at'], '')
        self.assertEqual(len(rows), 2)
        county_csv = next(csv.DictReader(io.StringIO(dashboard._snapshot_csv({'parcel_source_profile': p}))))
        self.assertEqual(county_csv['profile_active_parcel_source_count'], str(p['monitoring']['active_parcel_source_count']))
        self.assertTrue(rows[0]['name'].startswith("'"))
        self.assertNotIn('localhost', rows[0]['approved_public_links'])
        with zipfile.ZipFile(io.BytesIO(dashboard._snapshot_xlsx({'parcel_source_profile':p}))) as z:
            xml = z.read('xl/worksheets/sheet5.xml')
            ET.fromstring(xml)
            self.assertIn(b'2026-10-06', xml)
            self.assertIn(b'<v>0</v>', xml)
            self.assertNotIn(b'<f>', xml)
            self.assertNotIn(b'\x01',xml)

    def test_legacy_aggregate_source_csv_still_contains_every_source(self):
        with patch.object(dashboard, '_dashboard_state', return_value={'sources':{'one':{'name':'One'},'two':{'name':'Two'}}}):
            snap = dashboard._statewide_snapshot({})
        self.assertEqual({r['source_id'] for r in csv.DictReader(io.StringIO(dashboard._snapshot_csv(snap)))}, {'one','two'})
