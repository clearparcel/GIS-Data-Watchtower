"""Parcel-quality predicates follow field types; the parcel-ID count runs once."""
import unittest
from unittest.mock import patch

from clearparcel.datawatch import watch


def layer(id_type: str | None, owner_type: str | None = "esriFieldTypeString") -> dict:
    fields = [{"name": "OBJECTID", "type": "esriFieldTypeOID"}, {"name": "PIN", "type": id_type},
              {"name": "OWNER_NAME", "type": owner_type}]
    return {"fields": [{k: v for k, v in f.items() if v is not None} for f in fields],
            "geometryType": "esriGeometryPolygon"}


class StrictNumericProvider:
    """Mock provider that, like strict SQL dialects, rejects '' on numeric fields."""

    def __init__(self, metadata: dict, *, total: int = 100, missing: int = 4, fail_id: bool = False):
        self.metadata, self.total, self.missing, self.fail_id = metadata, total, missing, fail_id
        self.wheres = []
        self.numeric = {f["name"] for f in metadata["fields"]
                        if f.get("type") not in (None, "esriFieldTypeString")}

    def json_request(self, url, timeout, **kwargs):
        return self.metadata, {"status": 200}

    def count(self, url, where, timeout, **kwargs):
        self.wheres.append(where)
        if where == "1=1":
            return self.total
        if self.fail_id and where.startswith("PIN "):
            raise RuntimeError("synthetic provider rejection")
        if any(f"{name} = ''" in where for name in self.numeric):
            raise RuntimeError("Invalid query: cannot compare a numeric field with a string")
        return 0 if "SHAPE" in where else self.missing


def run(provider: StrictNumericProvider) -> dict:
    with patch.object(watch, "_json_request", side_effect=provider.json_request), \
            patch.object(watch, "_arcgis_count_query", side_effect=provider.count):
        return watch._arcgis_layer({"url": "https://example.invalid/0", "parcel_quality": True}, 2)


class ParcelQualityPredicateTests(unittest.TestCase):
    def test_predicates_by_field_type(self):
        cases = {
            "esriFieldTypeString": "PIN IS NULL OR PIN = ''",
            "esriFieldTypeInteger": "PIN IS NULL",
            "esriFieldTypeBigInteger": "PIN IS NULL",
            "esriFieldTypeDouble": "PIN IS NULL",
            "esriFieldTypeOID": "PIN IS NULL",
            "esriFieldTypeDate": "PIN IS NULL",
            "esriFieldTypeGUID": "PIN IS NULL",
            None: "PIN IS NULL OR PIN = ''",
            "not-an-esri-type": "PIN IS NULL OR PIN = ''",
        }
        for field_type, expected in cases.items():
            with self.subTest(field_type=field_type):
                self.assertEqual(watch._missing_predicate("PIN", field_type), expected)
        with self.assertRaises(ValueError):
            watch._missing_predicate("PIN OR 1=1", "esriFieldTypeInteger")

    def test_numeric_parcel_id_is_supported_and_queried_once(self):
        provider = StrictNumericProvider(layer("esriFieldTypeInteger"))
        result = run(provider)
        id_queries = [w for w in provider.wheres if w.startswith("PIN ")]
        self.assertEqual(id_queries, ["PIN IS NULL"])
        self.assertEqual(result["parcel_id_null_count"], 4)
        self.assertNotIn("parcel_id_null_check", result)
        profile = result["completeness_profiles"]["parcel_id"]
        self.assertEqual(profile["missing"], 4)
        self.assertEqual(profile["missing"], result["parcel_id_null_count"])
        self.assertEqual(profile, watch._completeness_from_missing("PIN", result.get("feature_count"), 4))
        self.assertIn("OWNER_NAME IS NULL OR OWNER_NAME = ''", provider.wheres)

    def test_text_parcel_id_keeps_blank_check_once(self):
        provider = StrictNumericProvider(layer("esriFieldTypeString"))
        run(provider)
        self.assertEqual([w for w in provider.wheres if w.startswith("PIN ")], ["PIN IS NULL OR PIN = ''"])

    def test_failed_id_query_is_unsupported_without_a_second_attempt(self):
        provider = StrictNumericProvider(layer("esriFieldTypeString"), fail_id=True)
        result = run(provider)
        self.assertEqual(len([w for w in provider.wheres if w.startswith("PIN ")]), 1)
        self.assertIsNone(result["parcel_id_null_count"])
        self.assertEqual(result["parcel_id_null_check"], "unsupported")
        self.assertEqual(result["completeness_profiles"]["parcel_id"]["status"], "unsupported")
        self.assertEqual(result["completeness_profiles"]["owner"]["missing"], 4)

    def test_rate_limit_on_id_query_still_stops_the_check(self):
        provider = StrictNumericProvider(layer("esriFieldTypeInteger"))

        def limited(url, where, timeout, **kwargs):
            if where.startswith("PIN "):
                raise watch.ProviderRateLimitError("60")
            return provider.count(url, where, timeout)

        with patch.object(watch, "_json_request", side_effect=provider.json_request), \
                patch.object(watch, "_arcgis_count_query", side_effect=limited):
            with self.assertRaises(watch.ProviderRateLimitError):
                watch._arcgis_layer({"url": "https://example.invalid/0", "parcel_quality": True}, 2)


if __name__ == "__main__":
    unittest.main()
