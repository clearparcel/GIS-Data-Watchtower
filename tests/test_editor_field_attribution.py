"""Editor validation points at the enrolled method that actually failed."""
import copy
import unittest

from clearparcel.datawatch.county_admin_validation import editor_validation_errors
from clearparcel.datawatch.county_profiles import county_identities

GOOD_URL = "https://gis.example.gov/arcgis/rest/services/Parcels/FeatureServer/0"
NO_LAYER_URL = "https://gis.example.gov/arcgis/rest/services/Roads/MapServer"


def method(url):
    return {"kind": "direct_rest", "url": url, "evidence_date": "2026-11-07", "scope": "Synthetic county data",
            "monitoring": {"enabled": True, "execution_profile": "cloud",
                           "terms_url": "https://example.gov/terms", "terms_reviewed_on": "2026-11-07",
                           "terms_confirmed": True}}


def dataset(*methods):
    return {"classification": "open", "restrictions": {"status": "reviewed_none"}, "methods": list(methods)}


def draft(access):
    return {"fips": county_identities()["aitkin"]["fips"], "contacts": [], "access": access,
            "policy": {}, "correspondence": []}


def fields(value):
    names = [error.get("field", "") for error in editor_validation_errors(value)]
    return [name for name in names if "monitoring" in name or name.endswith(".url")]


class EditorFieldAttributionTests(unittest.TestCase):
    def test_invalid_road_link_is_reported_on_the_road_method(self):
        value = draft({"parcel_polygons": dataset(method(GOOD_URL)), "road_centerlines": dataset(method(NO_LAYER_URL))})
        self.assertEqual(fields(value), ["access.road_centerlines.methods.0.url"])

    def test_second_and_third_methods_of_one_dataset(self):
        for bad_index in (1, 2):
            methods = [method(GOOD_URL), method(GOOD_URL + "1"), method(GOOD_URL + "2")]
            methods[bad_index] = method(NO_LAYER_URL)
            with self.subTest(bad_index=bad_index):
                value = draft({"address_points": dataset(*methods)})
                self.assertEqual(fields(value), [f"access.address_points.methods.{bad_index}.url"])

    def test_missing_worker_on_a_later_method(self):
        later = method(GOOD_URL + "1")
        later["monitoring"]["execution_profile"] = "nowhere"
        value = draft({"address_points": dataset(method(GOOD_URL), later)})
        self.assertEqual(fields(value), ["access.address_points.methods.1.monitoring.execution_profile"])

    def test_valid_draft_has_no_monitoring_errors(self):
        value = draft({"parcel_polygons": dataset(method(GOOD_URL)), "road_centerlines": dataset(method(GOOD_URL + "1"))})
        self.assertEqual(fields(copy.deepcopy(value)), [])


if __name__ == "__main__":
    unittest.main()
