import csv
import io
import unittest
import zipfile
import xml.etree.ElementTree as ET
from unittest.mock import patch
from clearparcel.datawatch import dashboard
from clearparcel.datawatch.county_profile_exports import county_profiles_csv, parcel_sources_csv, county_profile_xlsx_sheets

def workbook_rows(raw, sheet_name):
    """Decode workbook cells by their headers rather than matching XML fragments."""
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        sheets = ET.fromstring(archive.read('xl/workbook.xml')).findall('s:sheets/s:sheet', ns)
        names = [sheet.attrib['name'] for sheet in sheets]
        tree = ET.fromstring(archive.read(f'xl/worksheets/sheet{names.index(sheet_name) + 1}.xml'))
        rows = []
        for row in tree.findall('s:sheetData/s:row', ns):
            cells = []
            for cell in row.findall('s:c', ns):
                value = cell.find('s:v', ns)
                text = ''.join(cell.itertext()) if cell.attrib.get('t') == 'inlineStr' else (value.text if value is not None else '')
                if cell.attrib.get('t') == 'b':
                    text = 'True' if text == '1' else 'False'
                cells.append(text)
            rows.append(cells)
    return [dict(zip(rows[0], row)) for row in rows[1:]]

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

    def test_decoded_workbook_matches_csv_and_json_source_identity(self):
        import json
        snap = self.snapshot()
        profile = snap['counties'][0]['parcel_source_profile']
        profile['county_download']['sources'] = [
            {'inventory_id': 'product-zero', 'monitored_source_id': 'observed-zero', 'name': 'Zero product',
             'feature_count': 0, 'provider_updated_at': '2026-10-06', 'checked_at': '2026-10-06T12:00:00+00:00'},
            {'inventory_id': 'product-unknown', 'monitored_source_id': 'observed-unknown', 'name': 'Unknown product',
             'feature_count': None, 'county_acquired_at': '2026-10-05', 'file': {'size_bytes': 0}},
        ]
        profiles = {row['parcel_source_profile']['county']['slug']: row['parcel_source_profile'] for row in json.loads(json.dumps(snap))['counties']}
        workbook = dashboard._snapshot_xlsx(snap)
        for name, csv_text in [('County Access', county_profiles_csv(profiles)), ('Parcel Sources', parcel_sources_csv(profiles))]:
            self.assertEqual(workbook_rows(workbook, name), list(csv.DictReader(io.StringIO(csv_text))))
        source_rows = [row for row in workbook_rows(workbook, 'Parcel Sources')
                       if row['county_slug'] == profile['county']['slug'] and row['category'] == 'county_download']
        self.assertEqual([row['inventory_id'] for row in source_rows], ['product-zero', 'product-unknown'])
        self.assertEqual([row['monitored_source_id'] for row in source_rows], ['observed-zero', 'observed-unknown'])
        for source, row in zip(profile['county_download']['sources'], source_rows):
            for field in ('feature_count', 'provider_updated_at', 'county_acquired_at', 'checked_at'):
                value = source.get(field)
                self.assertEqual(row[field], '' if value is None else str(value))
        self.assertEqual(source_rows[1]['file_size_bytes'], '0')
