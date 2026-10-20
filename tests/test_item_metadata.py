import copy
import unittest
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.public_projection import _sanitize_catalog_records
from clearparcel.datawatch.public_values import county_metadata_dates, sanitize_item_metadata

ITEM_A = "bf8ef9d0b3f1455c9af61ef6b60329e2"
ITEM_B = "02fb2175c6554f56b4f39ba6829e3817"
ITEM_HELD = "0123456789abcdef0123456789abcdef"
FGDC = b"""<?xml version="1.0"?><metadata><idinfo><citation><citeinfo><origin>Example County</origin>
<pubdate>20260622</pubdate></citeinfo></citation><timeperd><timeinfo><sngdate><caldate>20260620</caldate>
</sngdate></timeinfo><current>publication date</current></timeperd><status><update>As needed</update></status>
</idinfo><metainfo><metd>20260623</metd></metainfo></metadata>"""
ARCGIS = b"""<metadata xml:lang="en"><Esri><ModDate>20260707</ModDate></Esri><dataIdInfo><idCitation>
<resTitle>Parcels</resTitle><date><pubDate>2026-01-30T00:00:00</pubDate><reviseDate>2026-02-15T09:30:00</reviseDate>
</date></idCitation></dataIdInfo><mdDateSt>20260708</mdDateSt></metadata>"""
CATALOG = {"features": [
    {"attributes": {"countyname": "Wabasha", "acqdate": 1784764800000, "rundate": 1785974400000,
                    "data_url": f"https://hub.arcgis.com/api/v3/datasets/{ITEM_A}_0/downloads/data?format=fgdb"}},
    {"attributes": {"countyname": "Houston", "acqdate": 1782691200000, "rundate": 1785974400000,
                    "data_url": f"Non-scriptable, download from: https://maps-beta.hub.arcgis.com/datasets/{ITEM_B}_0/explore"}},
    {"attributes": {"countyname": "Fillmore", "acqdate": 1782691200000, "rundate": 1785974400000,
                    "data_url": f"https://hub.arcgis.com/api/v3/datasets/{ITEM_A}_0/downloads/data?format=shp"}},
    {"attributes": {"countyname": "Anoka", "acqdate": 1782691200000, "rundate": 1785974400000,
                    "data_url": "https://gisdata.metc.state.mn.us/gisdata/Parcels/plan_regional_parcels.zip"}},
    {"attributes": {"countyname": "Brown", "acqdate": 1782691200000, "rundate": 1785974400000,
                    "data_url": f"https://hub.arcgis.com/api/v3/datasets/{ITEM_HELD}_0/downloads/data"}},
]}
SOURCE = {"id": "mn-parcel-county-catalog", "kind": "arcgis_county_catalog",
          "url": "https://catalog.example.invalid/arcgis/rest/services/x/FeatureServer/0"}


def fake_request(bodies):
    calls = []

    def request(url, timeout, **_):
        calls.append(url)
        item = url.split("/items/")[1].split("/")[0]
        body = bodies[item]
        if isinstance(body, Exception):
            raise body
        return body, {"status": 200}
    return request, calls


class ItemIdTests(unittest.TestCase):
    def test_item_ids_come_only_from_arcgis_hosts(self):
        cases = {
            f"https://hub.arcgis.com/api/v3/datasets/{ITEM_A}_0/downloads/data?format=fgdb": ITEM_A,
            f"see https://maps-lyonmn.hub.arcgis.com/datasets/{ITEM_B}_0/explore": ITEM_B,
            f"https://www.arcgis.com/home/item.html?id={ITEM_B}": None,  # may be a web app, not a layer
            f"https://opendata.arcgis.com/api/v3/datasets/{ITEM_A}_0/downloads/data": ITEM_A,
            f"https://evil.example/datasets/{ITEM_A}_0": None,
            f"https://arcgis.com.evil.example/datasets/{ITEM_A}": None,
            "https://gisdata.metc.state.mn.us/gisdata/Parcels/plan_regional_parcels.zip": None,
            "": None, None: None,
        }
        for value, expected in cases.items():
            self.assertEqual(watch.catalog_item_id(value), expected, value)


class MetadataParseTests(unittest.TestCase):
    def test_fgdc_dates_and_currentness(self):
        self.assertEqual(watch.item_metadata_dates(FGDC), {
            "publication_date": "2026-06-22", "content_date": "2026-06-20", "metadata_date": "2026-06-23",
            "currentness_reference": "publication date", "update_frequency": "As needed"})

    def test_arcgis_format_dates(self):
        self.assertEqual(watch.item_metadata_dates(ARCGIS), {
            "publication_date": "2026-01-30", "revision_date": "2026-02-15", "metadata_date": "2026-07-08"})

    def test_missing_or_invalid_dates_are_omitted(self):
        body = b"<metadata><idinfo><citation><citeinfo><pubdate>Unknown</pubdate></citeinfo></citation></idinfo>" \
               b"<metainfo><metd>20261340</metd></metainfo></metadata>"
        self.assertEqual(watch.item_metadata_dates(body), {})

    def test_dtd_and_entities_are_refused_however_encoded_or_placed(self):
        bomb = '<?xml version="1.0"?><!DOCTYPE m [<!ENTITY a "aaaa">]><metadata>&a;</metadata>'
        padded = "<!--" + "x" * 300000 + "-->" + bomb.split("?>", 1)[1]
        utf16 = bomb.replace('version="1.0"', 'version="1.0" encoding="UTF-16"').encode("utf-16")
        for body in (bomb.encode(), padded.encode(), utf16):
            with self.assertRaises(ValueError):
                watch.item_metadata_dates(body)


class CatalogMetadataTests(unittest.TestCase):
    def run_catalog(self, source, bodies, *, blocked=()):
        request, calls = fake_request(bodies)
        token = watch._RUN_BLOCKED_HOSTS.set(set(blocked))
        try:
            with patch.object(watch, "_json_request", return_value=(copy.deepcopy(CATALOG), {"status": 200})), \
                    patch.object(watch, "_request", side_effect=request):
                result = watch._arcgis_county_catalog(source, 30)
        finally:
            watch._RUN_BLOCKED_HOSTS.reset(token)
        return result, calls

    def test_disabled_by_default_makes_no_metadata_requests(self):
        result, calls = self.run_catalog(SOURCE, {})
        self.assertEqual(calls, [])
        self.assertTrue(all("item_metadata" not in r for r in result["county_records"].values()))

    def test_enabled_reads_each_item_once_and_keeps_catalog_hashes(self):
        plain, _ = self.run_catalog(SOURCE, {})
        result, calls = self.run_catalog({**SOURCE, "item_metadata": True}, {ITEM_A: FGDC, ITEM_B: ARCGIS})
        self.assertEqual(sorted(calls), sorted(watch.ITEM_METADATA_URL.format(i) for i in (ITEM_A, ITEM_B)))
        records = result["county_records"]
        self.assertEqual(records["Wabasha"]["item_metadata"]["publication_date"], "2026-06-22")
        self.assertEqual(records["Fillmore"]["item_metadata"]["item_id"], ITEM_A)
        self.assertEqual(records["Houston"]["item_metadata"]["revision_date"], "2026-02-15")
        self.assertNotIn("item_metadata", records["Anoka"])
        self.assertEqual(result["catalog_hash"], plain["catalog_hash"])
        self.assertEqual(result["schema_hash"], plain["schema_hash"])
        self.assertEqual(watch._observation_fingerprint(result), watch._observation_fingerprint(plain))

    def test_failures_are_display_context_not_source_errors(self):
        result, _ = self.run_catalog({**SOURCE, "item_metadata": True},
                                     {ITEM_A: RuntimeError("404"), ITEM_B: b"<not xml"})
        self.assertEqual({r["item_metadata"]["status"] for c, r in result["county_records"].items()
                          if c not in ("Anoka", "Brown")}, {"unavailable"})
        self.assertEqual(result["problems"], [])

    def test_backed_off_metadata_host_is_not_contacted(self):
        result, calls = self.run_catalog({**SOURCE, "item_metadata": True}, {ITEM_A: FGDC, ITEM_B: FGDC},
                                         blocked={"www.arcgis.com"})
        self.assertEqual(calls, [])
        self.assertEqual(result["county_records"]["Wabasha"]["item_metadata"]["status"], "deferred")

    def test_rate_limit_keeps_the_catalog_and_signals_the_backoff(self):
        result, calls = self.run_catalog({**SOURCE, "item_metadata": True},
                                         {ITEM_A: watch.ProviderRateLimitError("60", "www.arcgis.com"), ITEM_B: FGDC})
        self.assertEqual(len(calls), 1)  # Fillmore is read first; nothing more after the 429
        self.assertEqual(result["_auxiliary_rate_limit"], {"host": "www.arcgis.com", "retry_after": "60"})
        self.assertEqual({r["item_metadata"]["status"] for c, r in result["county_records"].items()
                          if c in ("Houston", "Wabasha", "Fillmore")}, {"deferred"})
        self.assertEqual(result["county_record_count"], 5)

    def test_held_counties_are_never_read(self):
        result, calls = self.run_catalog({**SOURCE, "item_metadata": True}, {ITEM_A: FGDC, ITEM_B: FGDC})
        self.assertNotIn(watch.ITEM_METADATA_URL.format(ITEM_HELD), calls)
        self.assertEqual(result["county_records"]["Brown"]["item_metadata"]["status"], "held")

    def test_item_limit_skips_the_rest(self):
        result, calls = self.run_catalog({**SOURCE, "item_metadata": True, "item_metadata_max_items": 1},
                                         {ITEM_A: FGDC, ITEM_B: FGDC})
        self.assertEqual(len(calls), 1)
        statuses = sorted(r["item_metadata"]["status"] for c, r in result["county_records"].items()
                          if "item_metadata" in r and c != "Brown")
        self.assertEqual(statuses, ["ok", "ok", "skipped"])  # Wabasha reuses Fillmore's item


class CheckLoopTests(unittest.TestCase):
    def test_metadata_429_persists_the_backoff_and_keeps_the_catalog_ok(self):
        import json, os, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=False):
            for name in ("WATCHTOWER_EXECUTION_PROFILE", "WATCHTOWER_AGGREGATE_OBJECT", "WATCHTOWER_STORAGE"):
                os.environ.pop(name, None)
            root = Path(td)
            config = {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
                      "retries": 1, "retry_delay_seconds": 0,
                      "sources": [{**SOURCE, "name": "Catalog", "item_metadata": True, "execution_profiles": ["cloud"]}]}
            request, calls = fake_request({ITEM_A: watch.ProviderRateLimitError("120", "www.arcgis.com"),
                                           ITEM_B: FGDC})
            with patch.object(watch, "_json_request", return_value=(copy.deepcopy(CATALOG), {"status": 200})), \
                    patch.object(watch, "_request", side_effect=request):
                report = watch.check_sources(config, execution_profile="cloud")
            source = report["sources"]["mn-parcel-county-catalog"]
            self.assertEqual(source["status"], "ok")
            self.assertNotIn("_auxiliary_rate_limit", source)
            self.assertEqual(len(calls), 1)
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(set(state["rate_limits"]), {"www.arcgis.com"})
            # Next run: the backed-off host is not contacted; the last good dates are kept.
            request, calls = fake_request({ITEM_A: FGDC, ITEM_B: FGDC})
            with patch.object(watch, "_json_request", return_value=(copy.deepcopy(CATALOG), {"status": 200})), \
                    patch.object(watch, "_request", side_effect=request):
                report = watch.check_sources(config, execution_profile="cloud")
            self.assertEqual(calls, [])
            self.assertEqual(report["sources"]["mn-parcel-county-catalog"]["status"], "ok")

    def test_failed_read_retains_the_last_good_dates(self):
        previous = {"county_records": {"Wabasha": {"item_metadata": {
            "item_id": ITEM_A, "status": "ok", "publication_date": "2026-01-30"}}}}
        details = {"county_records": {"Wabasha": {"item_metadata": {"item_id": ITEM_A, "status": "unavailable"}},
                                      "Houston": {"item_metadata": {"item_id": ITEM_B, "status": "unavailable"}}}}
        watch._retain_item_metadata(details, previous)
        kept = details["county_records"]["Wabasha"]["item_metadata"]
        self.assertEqual((kept["status"], kept["publication_date"], kept["retained"], kept["latest_attempt"]),
                         ("ok", "2026-01-30", True, "unavailable"))
        self.assertEqual(details["county_records"]["Houston"]["item_metadata"]["status"], "unavailable")


class PublicProjectionTests(unittest.TestCase):
    def test_item_metadata_is_projected_through_types_only(self):
        records = {"Alpha": {"acqdate": 1784764800000, "item_metadata": {
            "status": "ok", "item_id": ITEM_A, "publication_date": "2026-01-30", "content_date": "2026-13-01",
            "update_frequency": "Continually", "observed_at": "2026-10-21T10:03:00+00:00",
            "raw_xml": "<metadata/>", "token": "secret"}},
                   "Beta": {"item_metadata": {"status": "weird", "publication_date": "2026-01-30"}}}
        out = _sanitize_catalog_records(records)
        self.assertEqual(out["Alpha"]["item_metadata"], {
            "status": "ok", "item_id": ITEM_A, "publication_date": "2026-01-30"})
        self.assertNotIn("item_metadata", out["Beta"])

    def test_county_dates_need_a_successful_read(self):
        self.assertEqual(county_metadata_dates({"item_metadata": {"status": "ok", "revision_date": "2026-02-15",
                                                                  "content_date": "2026-02-01"}}),
                         {"publication_date": None, "content_date": "2026-02-01"})
        self.assertEqual(county_metadata_dates({"item_metadata": {"status": "unavailable"}}),
                         {"publication_date": None, "content_date": None})
        self.assertEqual(county_metadata_dates(None), {"publication_date": None, "content_date": None})
        self.assertIsNone(sanitize_item_metadata("x"))



class PanelTests(unittest.TestCase):
    def test_panel_shows_mngeo_acquisition_and_county_metadata_dates_separately(self):
        from clearparcel.datawatch.county_profile_panel import render_county_profile_body
        source = {"name": "Statewide", "county_acquired_at": "2026-07-23", "county_metadata_published_at": "2026-01-30",
                  "county_metadata_content_at": None}
        body = render_county_profile_body({"county": {"name": "Wabasha", "slug": "wabasha"},
                                           "mngeo_public_repository": {"sources": [source]}})
        self.assertIn("MnGeo acquisition", body)
        self.assertIn("2026-07-23", body)
        self.assertIn("County metadata publication", body)
        self.assertIn("2026-01-30", body)


if __name__ == "__main__":
    unittest.main()
