import io
import json
import os
import sys
import unittest
import urllib.parse
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import clearparcel.datawatch.watch as watch
from clearparcel.datawatch.analytics import posthog_config, posthog_csp_sources, posthog_html
from clearparcel.datawatch.dashboard import _snapshot_csv, _snapshot_xlsx, render_mngac
from clearparcel.datawatch.gac_standards import gac_defaults, load_gac_standard
from clearparcel.datawatch.public_dashboard import sanitize_public_render_state
from clearparcel.datawatch.public_publish import _snapshot_is_superseded


class GACStandardsTests(unittest.TestCase):
    def test_official_address_and_road_schema_inventory(self):
        address = load_gac_standard("address")
        road = load_gac_standard("road")
        self.assertEqual(address["standard"]["version"], "1.3.2")
        self.assertEqual(address["standard"]["field_count"], 53)
        self.assertEqual(len(address["fields"]), 53)
        self.assertEqual(sum(x["inclusion"] == "Mandatory" for x in address["fields"]), 18)
        self.assertIn("ADD_ID", {x["field"] for x in address["fields"]})
        self.assertIn("GIS911POC", {x["field"] for x in address["fields"]})

        self.assertEqual(road["standard"]["version"], "1.1.1")
        self.assertEqual(road["standard"]["field_count"], 73)
        self.assertEqual(len(road["fields"]), 73)
        self.assertEqual(sum(x["inclusion"] == "Mandatory" for x in road["fields"]), 34)
        self.assertIn("ROADSEG_ID", {x["field"] for x in road["fields"]})
        self.assertIn("CO_NAME_L", {x["field"] for x in road["fields"]})
        self.assertIn("CO_NAME_R", {x["field"] for x in road["fields"]})

    def test_routine_defaults_are_provider_tuned(self):
        self.assertEqual(gac_defaults("parcel")["routine_batch_size"], 12)
        self.assertEqual(gac_defaults("parcel")["routine_population_scope"], "all")
        self.assertEqual(gac_defaults("address")["routine_batch_size"], 12)
        self.assertEqual(gac_defaults("address")["routine_population_scope"], "mandatory")
        self.assertEqual(gac_defaults("address")["routine_text_population_mode"], "nonblank")
        self.assertEqual(gac_defaults("road")["routine_batch_size"], 12)
        self.assertEqual(gac_defaults("road")["routine_population_scope"], "mandatory")
        self.assertEqual(gac_defaults("road")["routine_text_population_mode"], "nonblank")

    def test_generic_address_and_road_statistics_support_routine_and_nonblank_modes(self):
        self.assertEqual(
            watch._gac_statistic(
                {"data_type": "Text", "field": "ST_NAME"}, "st_name", "address",
                text_population_mode="non_null",
            ),
            ("count", "st_name"),
        )
        self.assertEqual(
            watch._gac_statistic(
                {"data_type": "Text", "field": "ST_NAME"}, "st_name", "address",
                text_population_mode="nonblank",
            ),
            ("count", "NULLIF(st_name, '')"),
        )
        self.assertEqual(
            watch._gac_statistic({"data_type": "Integer", "field": "ANUMBER"}, "anumber", "address"),
            ("count", "anumber"),
        )
        self.assertEqual(
            watch._gac_statistic(
                {"data_type": "Text", "field": "ST_NAME"}, "st_name", "road",
                text_population_mode="non_null",
            ),
            ("count", "st_name"),
        )
        self.assertEqual(
            watch._gac_statistic({"data_type": "Text", "field": "OWNER_NAME"}, "OWNER_NAME", "parcel")[0],
            "sum",
        )

    def test_address_completeness_uses_generic_bounded_grouped_statistics(self):
        response = {"features": [{
            "attributes": {
                "CO_NAME": "Aitkin", "CO_CODE": "27001", "record_count": 10,
                "p0": 10, "p1": 9, "p2": 8,
            }
        }]}
        fields = ["OBJECTID", "CO_NAME", "CO_CODE", "ADD_ID", "ANUMBER", "ST_NAME"]
        with patch.object(watch, "_json_request", return_value=(response, {"status": 200})) as request:
            result = watch._arcgis_gac_completeness(
                "https://example.invalid/FeatureServer/0",
                fields,
                "OBJECTID",
                30,
                standard_key="address",
            )
        self.assertEqual(request.call_count, 1)
        self.assertIn("groupByFieldsForStatistics=CO_NAME&outFields=CO_NAME", request.call_args.args[0])
        self.assertNotIn("groupByFieldsForStatistics=CO_NAME%2CCO_CODE", request.call_args.args[0])
        self.assertEqual(result["standard_key"], "address")
        self.assertEqual(result["field_count"], 53)
        self.assertEqual(result["mandatory_field_count"], 18)
        self.assertEqual(result["covered_counties"], 1)
        self.assertEqual(result["counties"]["Aitkin"]["fields"]["ADD_ID"]["percent"], 100.0)

    def test_road_completeness_groups_on_left_county_fields(self):
        response = {"features": [{
            "attributes": {
                "CO_NAME_L": "Olmsted", "CO_CODE_L": "27109", "record_count": 20,
                "p0": 20, "p1": 20, "p2": 18,
            }
        }]}
        fields = ["OBJECTID", "CO_NAME_L", "CO_CODE_L", "ROADSEG_ID", "ROUTE_SYS", "ST_NAME"]
        with patch.object(watch, "_json_request", return_value=(response, {"status": 200})) as request:
            result = watch._arcgis_gac_completeness(
                "https://example.invalid/FeatureServer/1",
                fields,
                "OBJECTID",
                30,
                standard_key="road",
            )
        self.assertIn("groupByFieldsForStatistics=CO_NAME_L&outFields=CO_NAME_L", request.call_args.args[0])
        self.assertNotIn("groupByFieldsForStatistics=CO_NAME_L%2CCO_CODE_L", request.call_args.args[0])
        self.assertEqual(result["standard_key"], "road")
        self.assertEqual(result["field_count"], 73)
        self.assertEqual(result["mandatory_field_count"], 34)
        self.assertIn("left-side county", result["county_grouping"]["note"])

    def test_nonparcel_text_population_uses_nullif_count_without_second_pass(self):
        fields = ["OBJECTID", "CO_NAME", "ADD_ID", "ST_NAME"]
        response = {"features": [{
            "attributes": {"CO_NAME": "Aitkin", "record_count": 10, "p0": 8, "p1": 9}
        }]}
        with patch.object(
            watch, "_json_request", return_value=(response, {"status": 200})
        ) as request:
            result = watch._arcgis_gac_completeness(
                "https://example.invalid/FeatureServer/0",
                fields,
                "OBJECTID",
                30,
                standard_key="address",
                text_population_mode="nonblank",
            )
        self.assertEqual(request.call_count, 1)
        add_id = result["counties"]["Aitkin"]["fields"]["ADD_ID"]
        self.assertEqual(add_id["populated"], 8)
        self.assertEqual(add_id["percent"], 80.0)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.call_args.args[0]).query)
        statistics = json.loads(query["outStatistics"][0])
        self.assertTrue(any(
            stat["statisticType"] == "count" and "NULLIF(ADD_ID, '')" == stat["onStatisticField"]
            for stat in statistics
        ))

    def test_road_excludes_non_minnesota_groups_and_normalizes_saint_louis(self):
        response = {"features": [
            {"attributes": {"CO_NAME_L": "Saint Louis", "record_count": 10, "p0": 10}},
            {"attributes": {"CO_NAME_L": "Out of Jurisdiction", "record_count": 5, "p0": 5}},
            {"attributes": {"CO_NAME_L": "Howard", "record_count": 3, "p0": 3}},
        ]}
        fields = ["OBJECTID", "CO_NAME_L", "ROADSEG_ID"]
        with patch.object(watch, "_json_request", return_value=(response, {"status": 200})):
            result = watch._arcgis_gac_completeness(
                "https://example.invalid/FeatureServer/0",
                fields,
                "OBJECTID",
                30,
                standard_key="road",
            )
        self.assertEqual(set(result["counties"]), {"St. Louis"})
        self.assertEqual(result["record_count"], 10)
        self.assertEqual(result["excluded_county_groups"], 2)
        self.assertEqual(result["excluded_county_names"], ["Howard", "Out of Jurisdiction"])

    def test_gac_metadata_separates_ng911_open_opt_in_and_submission(self):
        response = {"features": [{
            "attributes": {
                "agency_county": "Olmsted", "county_name": "Olmsted",
                "county_code": "109", "county_fips": "27109",
                "gac_open": "Yes", "ng911_upload": "true",
                "s2e_date_adp": 1790899200000,
            }
        }]}
        with patch.object(watch, "_json_request", return_value=(response, {"status": 200})):
            result = watch._arcgis_gac_metadata(
                "https://example.invalid/FeatureServer/0",
                30,
                standard_key="address",
            )
        row = result["Olmsted"]
        self.assertIs(row["gac_open"], True)
        self.assertIs(row["ng911_upload"], True)
        self.assertTrue(row["submitted_at"].startswith("2026-10-02"))

    def test_public_projection_allowlists_gac_metadata_and_retirement(self):
        state = {
            "schema_version": 3,
            "generated_at": "2026-10-07T15:00:00+00:00",
            "overall": "ok",
            "counts": {"ok": 1, "warn": 0, "error": 0},
            "workers": {},
            "retired_sources": {
                "old-road": {"worker": "cloud", "retired_at": "2026-10-07T14:00:00+00:00", "secret": "DROP"}
            },
            "sources": {
                "addresses": {
                    "id": "addresses", "name": "Addresses", "status": "ok",
                    "gac_completeness": {
                        "standard_key": "address",
                        "standard": {
                            "key": "address", "name": "Address", "short_name": "Address",
                            "version": "1.3.2", "published": "2024-10-25",
                            "source_url": "https://example.com/standard",
                        },
                        "method": "grouped",
                        "record_count": 1, "field_count": 53, "covered_counties": 1,
                        "mandatory_field_count": 18,
                        "source_feature_count": 2, "ungrouped_record_count": 1,
                        "field_population_percent": 90.0, "mandatory_population_percent": 99.0,
                        "fields": {
                            "ADD_ID": {
                                "label": "Address Unique Identifier", "section": 1,
                                "section_name": "Identification Elements", "inclusion": "Mandatory",
                                "data_type": "Text", "present_in_source_schema": True,
                                "populated": 1, "record_count": 1, "percent": 100.0,
                                "counties_with_values": 1, "counties_covered": 1,
                            }
                        },
                        "counties": {
                            "Olmsted": {
                                "record_count": 1, "fields_with_values": 1, "field_count": 53,
                                "mandatory_fields_full": 1, "mandatory_field_count": 18,
                                "field_population_percent": 90.0, "mandatory_population_percent": 99.0,
                                "fields": {"ADD_ID": {"populated": 1, "record_count": 1, "percent": 100.0}},
                            }
                        },
                        "county_metadata": {
                            "Olmsted": {
                                "county_name": "Olmsted", "county_code": "109", "county_fips": "27109",
                                "gac_open": True, "ng911_upload": True,
                                "submitted_at": "2026-10-02T00:00:00+00:00",
                                "secret": "DROP",
                            }
                        },
                        "metadata_summary": {
                            "metadata_counties": 87, "ng911_participants": 85,
                            "gac_open_counties": 56, "represented_without_gac_open": 0,
                            "gac_open_without_representation": 55, "secret": 99,
                        },
                        "statistics_queries": 5,
                    },
                }
            },
        }
        public = sanitize_public_render_state(state)
        self.assertEqual(public["retired_sources"]["old-road"], {
            "worker": "cloud", "retired_at": "2026-10-07T14:00:00+00:00"
        })
        gac = public["sources"]["addresses"]["gac_completeness"]
        self.assertEqual(gac["standard"]["version"], "1.3.2")
        self.assertEqual(gac["source_feature_count"], 2)
        self.assertEqual(gac["ungrouped_record_count"], 1)
        self.assertEqual(gac["metadata_summary"]["ng911_participants"], 85)
        self.assertEqual(gac["metadata_summary"]["gac_open_counties"], 56)
        self.assertNotIn("secret", gac["metadata_summary"])
        self.assertTrue(gac["county_metadata"]["Olmsted"]["gac_open"])
        self.assertNotIn("secret", gac["county_metadata"]["Olmsted"])
        self.assertNotIn("statistics_queries", gac)

    def test_public_snapshot_requires_explicit_newer_retirement_for_omission(self):
        current = {
            "generated_at": "2026-10-07T14:00:00+00:00",
            "workers": {},
            "sources": {"roads": {"checked_at": "2026-10-07T14:00:00+00:00"}},
        }
        candidate = {
            "generated_at": "2026-10-07T15:00:00+00:00",
            "workers": {}, "sources": {}, "retired_sources": {},
        }
        self.assertTrue(_snapshot_is_superseded(candidate, current))
        candidate["retired_sources"]["roads"] = {
            "worker": "cloud", "retired_at": "2026-10-07T15:00:00+00:00"
        }
        self.assertFalse(_snapshot_is_superseded(candidate, current))

        current_retired = {
            "generated_at": "2026-10-07T15:00:00+00:00",
            "workers": {}, "sources": {},
            "retired_sources": {
                "roads": {"worker": "cloud", "retired_at": "2026-10-07T15:00:00+00:00"}
            },
        }
        dropped_tombstone = {
            "generated_at": "2026-10-07T16:00:00+00:00",
            "workers": {}, "sources": {}, "retired_sources": {},
        }
        self.assertTrue(_snapshot_is_superseded(dropped_tombstone, current_retired))

    def test_address_and_road_dashboard_surface_from_generic_state(self):
        def state_for(key, county_fields):
            schema = load_gac_standard(key)
            first = schema["fields"][0]
            return {
                "generated_at": "2026-10-07T15:00:00+00:00",
                "sources": {
                    key: {
                        "checked_at": "2026-10-07T15:00:00+00:00",
                        "gac_completeness": {
                            "standard_key": key,
                            "standard": schema["standard"],
                            "record_count": 10, "field_count": len(schema["fields"]),
                            "covered_counties": 1,
                            "mandatory_field_count": sum(x["inclusion"] == "Mandatory" for x in schema["fields"]),
                            "field_population_percent": 50.0, "mandatory_population_percent": 80.0,
                            "fields": {
                                first["field"]: {
                                    "label": first["label"], "section": first["section"],
                                    "section_name": first["section_name"], "inclusion": first["inclusion"],
                                    "data_type": first["data_type"], "populated": 10,
                                    "record_count": 10, "percent": 100.0,
                                    "counties_with_values": 1, "counties_covered": 1,
                                }
                            },
                            "counties": {
                                "Olmsted": {
                                    "record_count": 10, "fields_with_values": 1,
                                    "field_count": len(schema["fields"]),
                                    "mandatory_population_percent": 80.0,
                                    "field_population_percent": 50.0,
                                    "fields": {first["field"]: {"populated": 10, "record_count": 10, "percent": 100.0}},
                                }
                            },
                            "county_metadata": {
                                "Olmsted": {
                                    "gac_open": True, "ng911_upload": True,
                                    "submitted_at": "2026-10-02T00:00:00+00:00",
                                }
                            },
                        },
                    }
                },
            }

        for key, text in (("address", "Address Point"), ("road", "Road Centerline")):
            with self.subTest(key=key):
                state = state_for(key, {})
                with patch("clearparcel.datawatch.dashboard._dashboard_state", return_value=state):
                    page = render_mngac({"_public_mode": True}, key)
                self.assertIn(text, page)
                self.assertIn("NG911 participants", page)
                self.assertIn(f"standard={key}", page)


    def test_county_exports_include_generic_address_and_road_gac_data(self):
        def payload(key, records, pct, open_flag):
            schema = load_gac_standard(key)
            first = next(x for x in schema["fields"] if x["inclusion"] == "Mandatory")
            field_stats = {
                "populated": records, "record_count": records, "percent": 100.0,
            }
            return {
                "standard_key": key,
                "standard": schema["standard"],
                "population_scope": "mandatory",
                "covered_counties": 1,
                "record_count": records,
                "field_count": len(schema["fields"]),
                "mandatory_field_count": sum(x["inclusion"] == "Mandatory" for x in schema["fields"]),
                "mandatory_population_percent": pct,
                "fields": {
                    first["field"]: {
                        "label": first["label"], "section_name": first["section_name"],
                        "inclusion": first["inclusion"], "data_type": first["data_type"],
                        "present_in_source_schema": True, "population_scanned": True,
                        "populated": records, "record_count": records, "percent": 100.0,
                        "counties_with_values": 1, "counties_covered": 1,
                    }
                },
                "county": {
                    "record_count": records,
                    "field_count": len(schema["fields"]),
                    "mandatory_population_percent": pct,
                    "fields": {first["field"]: field_stats},
                },
                "metadata": {
                    "ng911_upload": True, "gac_open": open_flag,
                    "submitted_at": "2026-05-20T00:00:00+00:00",
                },
            }

        snapshot = {
            "county": "Olmsted",
            "status": "ok",
            "actively_monitored": False,
            "monitoring_path_label": "None",
            "parcel_access": {},
            "direct_sources": [],
            "contacts": [],
            "mngac": None,
            "gac": {
                "address": payload("address", 100, 97.21, True),
                "road": payload("road", 50, 95.94, False),
            },
        }
        csv_text = _snapshot_csv(snapshot)
        self.assertIn("address_record_count", csv_text)
        self.assertIn("road_mandatory_population_percent", csv_text)
        self.assertIn("97.21", csv_text)
        self.assertIn("95.94", csv_text)

        xlsx = _snapshot_xlsx(snapshot)
        with zipfile.ZipFile(io.BytesIO(xlsx)) as archive:
            workbook = archive.read("xl/workbook.xml").decode("utf-8")
        for sheet in ("GAC Standards", "GAC Counties", "GAC Fields", "GAC Detail"):
            self.assertIn(sheet, workbook)


class PostHogIntegrationTests(unittest.TestCase):
    def test_analytics_is_dormant_without_project_token(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(posthog_config())
            self.assertIsNone(posthog_csp_sources())
            self.assertEqual(posthog_html(page="Overview", version="1", build="abc", environment="production"), "")

    def test_token_alone_does_not_enable_analytics_without_ip_discard_confirmation(self):
        with patch.dict(os.environ, {
            "WATCHTOWER_POSTHOG_PROJECT_TOKEN": "watchtower_test_project_token_123456789",
        }, clear=True):
            self.assertIsNone(posthog_config())

    def test_analytics_uses_privacy_first_configuration(self):
        env = {
            "WATCHTOWER_POSTHOG_PROJECT_TOKEN": "watchtower_test_project_token_123456789",
            "WATCHTOWER_POSTHOG_HOST": "https://us.i.posthog.com",
            "WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            config = posthog_config()
            html = posthog_html(page="MN GAC", version="1", build="abc", environment="production")
            self.assertEqual(config["api_host"], "https://us.i.posthog.com")
            self.assertEqual(posthog_csp_sources()[1], "https://us.i.posthog.com")
        for required in (
            "autocapture:false", "capture_pageview:false", "capture_pageleave:false",
            "capture_exceptions:false", "disable_session_recording:true",
            "person_profiles:'identified_only'", "persistence:'memory'",
            "advanced_disable_flags:true", "watchtower page viewed",
        ):
            self.assertIn(required, html)
        self.assertIn("$current_url", html)
        self.assertNotIn("posthog.identify", html)

    def test_analytics_rejects_non_https_host(self):
        env = {
            "WATCHTOWER_POSTHOG_PROJECT_TOKEN": "watchtower_test_project_token_123456789",
            "WATCHTOWER_POSTHOG_HOST": "http://posthog.example.com",
            "WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(posthog_config())


if __name__ == "__main__":
    unittest.main()
