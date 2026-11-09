import copy
import datetime as dt
import json
import unittest

from clearparcel.datawatch.county_directory import project_public_county
from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles


COUNTY = {"fips": "27001", "slug": "aitkin", "name": "Aitkin"}
PRIVATE = "PRIVATE_SENTINEL"


def county_draft():
    return {
        "fips": "27001",
        "revision": 14,
        "contacts": [
            {
                "id": "contact-1",
                "name": "Synthetic GIS office",
                "department": "Mapping",
                "email": "gis@example.org",
                "website": "https://example.org/gis",
                "private_note": PRIVATE,
            },
            {"id": "contact-2", "name": PRIVATE, "removed": True},
        ],
        "access": {
            "parcel_polygons": {
                "classification": "open",
                "county_direct_note": "County fee applies to its direct product.",
                "methods": [
                    {
                        "kind": "mngeo_open",
                        "url": "https://example.org/statewide",
                        "evidence_date": "2026-11-06",
                        "scope": "Statewide product",
                        "internal_note": PRIVATE,
                    }
                ],
                "restrictions": {
                    "status": "restricted",
                    "text": "Confirm redistribution terms.",
                    "url": "https://example.org/terms",
                    "private_evidence": PRIVATE,
                },
                "monitoring": {"decision": PRIVATE},
            },
        },
        "policy": {
            "text": "Synthetic policy paragraph.\n\n" * 200,
            "url": "https://example.org/policy",
            "attachment_id": PRIVATE,
        },
        "correspondence": [{"subject": PRIVATE, "sent_at": PRIVATE, "notes": PRIVATE}],
        "attachments": [{"name": PRIVATE + ".pdf", "object_key": PRIVATE}],
        "publication_intent": {"request_id": PRIVATE},
    }


class CountyDirectoryProjectionTests(unittest.TestCase):
    def test_allowlist_is_recursive_and_keeps_public_evidence(self):
        draft = county_draft()
        original = copy.deepcopy(draft)
        result = project_public_county(COUNTY, draft)

        self.assertEqual(draft, original)
        self.assertEqual(set(result), {"schema_version", "county", "contacts", "access", "policy"})
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["county"], COUNTY)
        self.assertEqual(result["contacts"], [{
            "name": "Synthetic GIS office",
            "department": "Mapping",
            "email": "gis@example.org",
            "website": "https://example.org/gis",
        }])
        parcels = result["access"]["parcel_polygons"]
        self.assertEqual(parcels["classification"], "open")
        self.assertEqual(parcels["county_direct_note"], "County fee applies to its direct product.")
        self.assertEqual(parcels["methods"][0]["scope"], "Statewide product")
        self.assertEqual(parcels["restrictions"]["status"], "restricted")
        self.assertEqual(result["policy"]["text"], draft["policy"]["text"])
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_missing_classifications_and_contacts_are_explicit(self):
        result = project_public_county(COUNTY, {"fips": "27001"})
        self.assertEqual(result["contacts"], [])
        self.assertEqual(set(result["access"]), {"parcel_polygons", "road_centerlines", "address_points"})
        for access in result["access"].values():
            self.assertEqual(access, {
                "classification": "unknown",
                "methods": [],
                "restrictions": {"status": "unreviewed"},
            })

    def test_update_frequency_is_optional_direct_source_metadata(self):
        draft = {"fips": "27001", "access": {"parcel_polygons": {
            "classification": "open", "restrictions": {"status": "reviewed_none"}, "methods": [{
                "kind": "direct_rest", "url": "https://example.org/FeatureServer/0",
                "evidence_date": "2026-11-06", "scope": "Synthetic parcel polygons",
                "update_frequency": "Every spring",
            }],
        }}}
        public = project_public_county(COUNTY, draft)
        self.assertEqual(public["access"]["parcel_polygons"]["methods"][0]["update_frequency"], "Every spring")
        draft["access"]["parcel_polygons"]["methods"][0].pop("update_frequency")
        self.assertNotIn("update_frequency", project_public_county(COUNTY, draft)["access"]["parcel_polygons"]["methods"][0])
        method = draft["access"]["parcel_polygons"]["methods"][0]
        method.update(kind="mngeo_open", update_frequency="Every spring")
        with self.assertRaisesRegex(ValueError, "only available for direct data"):
            project_public_county(COUNTY, draft)

    def test_each_existing_profile_has_a_unique_directory_identity(self):
        profiles = compose_county_profiles(
            {}, {}, now=dt.datetime(2026, 11, 6, tzinfo=dt.UTC), freshness_policy=FreshnessPolicy()
        )
        public = [
            project_public_county(profile["county"], {"fips": profile["county"]["fips"]})
            for profile in profiles.values()
        ]
        self.assertEqual(len(public), 87)
        self.assertEqual(len({record["county"]["fips"] for record in public}), 87)
        self.assertEqual({record["county"]["slug"] for record in public}, set(profiles))

    def test_inactive_methods_and_unreviewed_restriction_details_stay_private(self):
        draft = county_draft()
        parcels = draft["access"]["parcel_polygons"]
        parcels.update(classification="fee", restrictions={"status": "unreviewed", "text": PRIVATE})
        draft["access"]["road_centerlines"] = {"restrictions": {"status": "reviewed_none"}}
        result = project_public_county(COUNTY, draft)
        self.assertEqual(result["access"]["parcel_polygons"]["methods"], [])
        self.assertEqual(result["access"]["parcel_polygons"]["restrictions"], {"status": "unreviewed"})
        self.assertEqual(result["access"]["road_centerlines"]["restrictions"], {"status": "reviewed_none"})
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_rejects_invalid_public_fields_without_echoing_values(self):
        for path, value in [
            (("fips",), "27003"),
            (("policy", "text"), {"notes": PRIVATE}),
            (("policy", "url"), "https://example.org/?token=" + PRIVATE),
            (("contacts", 0, "email"), PRIVATE),
            (("contacts", 0, "removed"), "false"),
            (("access", "parcel_polygons", "methods"), []),
            (("access", "parcel_polygons", "methods", 0, "kind"), "other"),
            (("access", "parcel_polygons", "methods", 0, "evidence_date"), "2026-02-30"),
            (("access", "parcel_polygons", "restrictions", "text"), " "),
        ]:
            with self.subTest(path=path):
                draft = county_draft()
                node = draft
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = value
                with self.assertRaises(ValueError) as error:
                    project_public_county(COUNTY, draft)
                self.assertNotIn(PRIVATE, str(error.exception))
