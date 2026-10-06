import unittest
from clearparcel.datawatch.county_profile_panel import render_county_profile_body, render_county_profile_panel, profile_time

class CountyProfilePanelTests(unittest.TestCase):
    def test_dates_preserve_calendar_and_central_dst(self):
        self.assertEqual(profile_time('2026-10-06'), '2026-10-06')
        self.assertEqual(profile_time('2026-01-06T12:00:00+00:00'), '2026-01-06 06:00 CST')
        self.assertEqual(profile_time('2026-07-06T12:00:00+00:00'), '2026-07-06 07:00 CDT')
    def test_panel_escapes_payload_and_links(self):
        profile={'county': {'name': '</script><img src=x>', 'slug':'test'}, 'monitoring':{}, 'access':{}, 'research':{}, 'comments':[]}
        body=render_county_profile_body(profile)
        self.assertNotIn('<img', body)
        self.assertIn('Not available', body)
        self.assertNotIn('Comments', body)
        page=render_county_profile_panel({'test':profile})
        self.assertIn('id="county-profile-data"', page)
        self.assertNotIn('</script><img', page)
        for name in ('MN GAC Public Parcels','MnGeo Public County Repository','County ArcGIS REST','County Website Download'):
            self.assertIn(name, body)

    def test_labels_keep_dates_and_counts_source_specific(self):
        source={'name':'Two products', 'feature_count':0, 'provider_updated_at':'2026-01-02', 'county_acquired_at':'2026-02-03', 'catalog_refreshed_at':'2026-03-04', 'checked_at':'2026-04-05', 'last_success_at':'2026-05-06', 'approved_public_links':[{'href':'https://example.com/product','label':'Product'}, {'href':'javascript:alert(1)','label':'Unsafe'}]}
        profile={'county':{'name':'Test','slug':'test'}, 'county_download':{'sources':[source]}, 'research':{'review_date':'2026-06-07'}, 'comments':['A supported comment']}
        body=render_county_profile_body(profile)
        for label in ('Provider update', 'County acquisition','Catalog refresh','Watchtower check','Successful observation','Research review','Feature count','Comments'):
            self.assertIn(label, body)
        self.assertIn('<dd>0</dd>',body)
        self.assertIn('target="_blank" rel="noopener"',body)
        self.assertNotIn('javascript:',body)
        self.assertIn('2026-01-02',body)
    def test_county_panel_sections_are_metric_independent(self):
        from clearparcel.datawatch.dashboard import _county_profiles
        from clearparcel.datawatch.parcel_access import load_parcel_access
        profiles=_county_profiles({}, {}, load_parcel_access())
        page=render_county_profile_panel(profiles)
        self.assertIn('opener?.focus({preventScroll:true})',page)
        self.assertIn("dialog.addEventListener('close'",page)
        self.assertIn("event.key!=='Tab'",page)
        self.assertIn('max-height:90dvh',page)
        self.assertIn('overflow-wrap:anywhere',page)
        self.assertIn('window.watchtowerRefresh?.pause()',page)
        self.assertNotIn('innerHTML',page)
        self.assertEqual(page.count('<template data-profile='),87)
