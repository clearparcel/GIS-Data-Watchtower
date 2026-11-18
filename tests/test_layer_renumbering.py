"""Provider layer renumbering inside an ArcGIS service (MnGeo, November 2026)."""
import unittest
from unittest.mock import patch

from clearparcel.datawatch import watch

META = {"status": 200, "transport": "test"}
METADATA_LAYER = {"name": "Open Parcels Metadata Layer", "geometryType": "esriGeometryPolygon",
                  "fields": [{"name": "countyname", "type": "esriFieldTypeString"}]}


class ExpectedLayerNameTests(unittest.TestCase):
    def test_renumbered_layer_stops_before_count_or_completeness_queries(self):
        source = {"url": "https://gis.example/FeatureServer/1", "count": True,
                  "expected_layer_name": "Open Parcels In Minnesota", "mngac_completeness": {}}
        with patch.object(watch, "_json_request", return_value=(METADATA_LAYER, META)) as request, \
                patch.object(watch, "_arcgis_count_query") as count, \
                patch.object(watch, "_arcgis_mngac_completeness") as completeness:
            with self.assertRaisesRegex(watch.PermanentProviderError, "renumbered") as caught:
                watch._arcgis_layer(source, 5)
        self.assertIn("Open Parcels Metadata Layer", str(caught.exception))
        self.assertEqual(request.call_count, 1)
        count.assert_not_called()
        completeness.assert_not_called()

    def test_matching_name_ignores_case_and_surrounding_space(self):
        source = {"url": "https://gis.example/FeatureServer/1", "expected_layer_name": " open parcels metadata LAYER "}
        with patch.object(watch, "_json_request", return_value=(METADATA_LAYER, META)):
            result = watch._arcgis_layer(source, 5)
        self.assertEqual(result["service_name"], "Open Parcels Metadata Layer")

    def test_without_expected_name_behavior_is_unchanged(self):
        with patch.object(watch, "_json_request", return_value=(METADATA_LAYER, META)):
            result = watch._arcgis_layer({"url": "https://gis.example/FeatureServer/1"}, 5)
        self.assertEqual(result["field_names"], ["countyname"])

    def test_registry_rejects_a_blank_or_non_string_expected_name(self):
        for value in ("", "  ", 7, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(watch.InvalidSourceRegistryError, "expected_layer_name"):
                    watch.validate_source_registry([{"id": "a", "name": "A", "url": "https://gis.example/0",
                                                     "adapter": "arcgis_layer", "expected_layer_name": value}])

    def test_registry_accepts_a_named_layer(self):
        watch.validate_source_registry([{"id": "a", "name": "A", "url": "https://gis.example/0",
                                         "adapter": "arcgis_layer", "expected_layer_name": "Parcels"}])


class CatalogTransferLimitMessageTests(unittest.TestCase):
    def test_catalog_error_names_possible_renumbering_and_a_real_status(self):
        page = {"features": [{"attributes": {"countyname": "Aitkin"}}], "exceededTransferLimit": True}
        source = {"id": "catalog", "adapter": "arcgis_county_catalog", "url": "https://gis.example/0"}
        with patch.object(watch, "_json_request", return_value=(page, META)):
            with self.assertRaises(watch.PermanentProviderError) as caught:
                watch._arcgis_county_catalog(source, 5)
        self.assertEqual(caught.exception.status, 200)
        self.assertNotIn("provider returned HTTP", str(caught.exception))
        self.assertIn("renumbered", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
