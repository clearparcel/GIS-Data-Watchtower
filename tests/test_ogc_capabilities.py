"""WMS/WFS GetCapabilities parsing: exception documents and layer inventory."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch

WMS_EXCEPTION = (b"<?xml version='1.0'?><ServiceExceptionReport version='1.3.0' xmlns='http://www.opengis.net/ogc'>"
                 b"<ServiceException code='OperationNotSupported'>Service temporarily unavailable</ServiceException>"
                 b"</ServiceExceptionReport>")
OWS_EXCEPTION = (b"<?xml version='1.0'?><ows:ExceptionReport xmlns:ows='http://www.opengis.net/ows' version='1.1.0'>"
                 b"<ows:Exception exceptionCode='NoApplicableCode'><ows:ExceptionText>Service temporarily unavailable"
                 b"</ows:ExceptionText></ows:Exception></ows:ExceptionReport>")
WMS_ONE_LAYER = (b"<?xml version='1.0'?><WMS_Capabilities xmlns='http://www.opengis.net/wms' version='1.3.0'>"
                 b"<Service><Name>WMS</Name><Title>t</Title></Service><Capability><Layer><Title>root</Title>"
                 b"<Layer queryable='1'><Name>sample:parcels</Name><Style><Name>default</Name></Style></Layer>"
                 b"</Layer></Capability></WMS_Capabilities>")
WMS_111 = (b"<?xml version='1.0'?><WMT_MS_Capabilities version='1.1.1'><Service><Name>OGC:WMS</Name></Service>"
           b"<Capability><Layer><Name>root</Name><Layer><Name>roads</Name></Layer></Layer></Capability>"
           b"</WMT_MS_Capabilities>")
WFS_TWO = (b"<?xml version='1.0'?><wfs:WFS_Capabilities xmlns:wfs='http://www.opengis.net/wfs'>"
           b"<FeatureTypeList><FeatureType><Name>a</Name></FeatureType><FeatureType><Name>b</Name></FeatureType>"
           b"</FeatureTypeList></wfs:WFS_Capabilities>")
EMPTY_WMS = b"<WMS_Capabilities xmlns='http://www.opengis.net/wms'><Service><Name>WMS</Name></Service></WMS_Capabilities>"
UNRELATED = b"<html><body>Maintenance</body></html>"


def reply(body):
    return patch.object(watch, "_request", return_value=(body, {"status": 200, "transport": "test"}))


class OgcExceptionTests(unittest.TestCase):
    def test_exception_documents_are_errors_for_both_adapters(self):
        for adapter in (watch._wms, watch._wfs):
            for body in (WMS_EXCEPTION, OWS_EXCEPTION):
                with self.subTest(adapter=adapter.__name__, body=body[:60]), reply(body):
                    with self.assertRaisesRegex(RuntimeError, "service exception: .*Service temporarily unavailable"):
                        adapter({"url": "https://example.invalid/ows"}, 1)

    def test_unrelated_and_malformed_xml_are_errors(self):
        for adapter in (watch._wms, watch._wfs):
            with self.subTest(adapter=adapter.__name__), reply(UNRELATED):
                with self.assertRaisesRegex(RuntimeError, "unexpected document"):
                    adapter({"url": "https://example.invalid/ows"}, 1)
            with self.subTest(adapter=adapter.__name__, malformed=True), reply(b"<WMS_Capabilities>"):
                with self.assertRaises(Exception):
                    adapter({"url": "https://example.invalid/ows"}, 1)

    def test_exception_text_is_bounded_and_inert(self):
        body = (b"<ServiceExceptionReport><ServiceException>" + b"bad\r\nline " * 200
                + b"</ServiceException></ServiceExceptionReport>")
        with reply(body), self.assertRaises(RuntimeError) as caught:
            watch._wms({"url": "https://example.invalid/ows"}, 1)
        message = str(caught.exception)
        self.assertLess(len(message), 260)
        self.assertNotIn("\n", message)
        self.assertNotIn("\r", message)

    def test_exception_reply_is_recorded_as_source_error_not_ok(self):
        sources = [{"id": "wms", "name": "WMS", "adapter": "wms", "url": "https://example.invalid/wms"},
                   {"id": "wfs", "name": "WFS", "adapter": "wfs", "url": "https://example.invalid/wfs"}]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
                      "alerts_file": str(root / "alerts.json"), "alerts_text_file": str(root / "alerts.txt"),
                      "retries": 0, "sources": sources}
            with reply(WMS_EXCEPTION):
                result = watch.check_sources(config, save=False)
        self.assertNotEqual(result["overall"], "ok")
        for source_id in ("wms", "wfs"):
            self.assertEqual(result["sources"][source_id]["status"], "error")


class WmsLayerInventoryTests(unittest.TestCase):
    def test_service_and_style_names_are_not_layers(self):
        with reply(WMS_ONE_LAYER):
            result = watch._wms({"url": "https://example.invalid/wms"}, 1)
        self.assertEqual(result["layer_count"], 1)
        self.assertEqual(result["problems"], [])

    def test_service_name_does_not_satisfy_an_expected_layer(self):
        with reply(WMS_ONE_LAYER):
            result = watch._wms({"url": "https://example.invalid/wms", "expected_layers": ["WMS", "sample:parcels"]}, 1)
        self.assertEqual(result["missing_layers"], ["WMS"])

    def test_wms_111_nested_layers_are_counted(self):
        with reply(WMS_111):
            result = watch._wms({"url": "https://example.invalid/wms"}, 1)
        self.assertEqual(result["layer_count"], 2)

    def test_valid_empty_inventory_is_a_warning_problem(self):
        with reply(EMPTY_WMS):
            result = watch._wms({"url": "https://example.invalid/wms"}, 1)
        self.assertEqual(result["layer_count"], 0)
        self.assertEqual(result["problems"], ["WMS capabilities list no named layers"])
        with reply(b"<wfs:WFS_Capabilities xmlns:wfs='http://www.opengis.net/wfs'/>"):
            result = watch._wfs({"url": "https://example.invalid/wfs"}, 1)
        self.assertEqual(result["problems"], ["WFS capabilities list no feature types"])
        with reply(WFS_TWO):
            self.assertEqual(watch._wfs({"url": "https://example.invalid/wfs"}, 1)["problems"], [])


if __name__ == "__main__":
    unittest.main()
