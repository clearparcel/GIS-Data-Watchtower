"""One GAC route dispatcher for both servers; exports never substitute standards."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import dashboard, dashboard_exports, public_dashboard
from clearparcel.datawatch.dashboard_exports import GacExportUnavailable, _mngac_csv
from clearparcel.datawatch.dashboard_routes import dispatch_gac_routes
from clearparcel.datawatch.gac_standards import load_gac_standard
from clearparcel.datawatch.public_projection import sanitize_public_render_state


def _gac(key: str) -> dict:
    schema = load_gac_standard(key)
    first = schema["fields"][0]["field"]
    return {"standard_key": key, "standard": schema["standard"], "record_count": 10, "covered_counties": 1,
            "field_count": len(schema["fields"]), "fields": {first: {"populated": 5, "record_count": 10}},
            "counties": {"Douglas": {"record_count": 10, "mandatory_population_percent": 50.0}}}


def _state() -> dict:
    return {"schema_version": 3, "generated_at": "2026-10-23T10:00:00+00:00", "overall": "ok",
            "counts": {"ok": 2, "warn": 0, "error": 0}, "workers": {},
            "sources": {key: {"id": key, "status": "ok", "gac_completeness": _gac(key)}
                        for key in ("parcel", "address")}}


REQUESTS = [
    ("/mngac.csv", "standard=address"),
    ("/mngac.csv", "standard=road"),
    ("/mngac.csv", "standard=bogus"),
    ("/mngac.json", "standard=address"),
    ("/mngac.json", "standard=road"),
    ("/mngac", "standard=parcel&view=nope"),
    ("/mngac", "standard=parcel&view=county&county=not-a-county"),
    ("/mngac", "standard=bogus"),
]


class Recorder:
    def __init__(self):
        self.responses = []

    def __call__(self, status, content, content_type="text/html; charset=utf-8"):
        self.responses.append((status, content_type.split(";")[0], content))


class ExportSchemaTests(unittest.TestCase):
    def test_missing_address_schema_is_an_error_not_parcel_rows(self):
        real = dashboard_exports.load_gac_standard

        def failing(key="parcel"):
            if key == "address":
                raise OSError("synthetic missing schema")
            return real(key)

        with patch.object(dashboard_exports, "load_gac_standard", side_effect=failing):
            with self.assertRaises(GacExportUnavailable):
                _mngac_csv(_gac("address"))
            self.assertIn("field,", _mngac_csv(_gac("parcel")).splitlines()[0].replace('"', ""))

    def test_invalid_schema_json_and_unknown_identity_are_errors(self):
        with patch.object(dashboard_exports, "load_gac_standard",
                          side_effect=json.JSONDecodeError("bad", "x", 0)):
            with self.assertRaises(GacExportUnavailable):
                _mngac_csv(_gac("road"))
        with self.assertRaises(GacExportUnavailable):
            _mngac_csv({**_gac("parcel"), "standard_key": "unknown"})
        with self.assertRaises(GacExportUnavailable):
            _mngac_csv(_gac("parcel"), standard_key="address")
        with patch.object(dashboard_exports, "load_gac_standard", return_value={"standard": {}, "fields": []}):
            with self.assertRaises(GacExportUnavailable):
                _mngac_csv(_gac("road"))

    def test_valid_exports_and_legacy_parcel_payload(self):
        for key in ("parcel", "address", "road"):
            with self.subTest(key=key):
                rows = _mngac_csv(_gac(key), standard_key=key).splitlines()
                self.assertEqual(len(rows) - 1, len(load_gac_standard(key)["fields"]))
        legacy = {k: v for k, v in _gac("parcel").items() if k not in ("standard_key", "standard")}
        parcel_only = ({f["field"] for f in load_gac_standard("parcel")["fields"]}
                       - {f["field"] for f in load_gac_standard("address")["fields"]})
        marker = sorted(parcel_only)[0]
        self.assertIn(f",{marker},", _mngac_csv(legacy))
        self.assertNotIn(f",{marker},", _mngac_csv(_gac("address"), standard_key="address"))

    def test_failed_export_is_not_downloadable_as_success(self):
        recorder = Recorder()
        with patch.object(dashboard, "_dashboard_state", return_value=_state()), \
                patch.object(dashboard_exports, "load_gac_standard", side_effect=OSError("synthetic")):
            dispatch_gac_routes("/mngac.csv", "standard=address", config={}, send=recorder)
        status, kind, body = recorder.responses[0]
        self.assertEqual((status, kind), (503, "text/plain"))
        self.assertNotIn("element,field", body)


class AdapterEquivalenceTests(unittest.TestCase):
    def _capture(self, module, start):
        captured = {}

        class Server:
            def __init__(self, addr, handler, **kwargs):
                captured["handler"] = handler

            def serve_forever(self):
                pass

            def server_close(self):
                pass

        with patch.object(module, "_BoundedThreadingHTTPServer", Server), \
                contextlib.redirect_stdout(io.StringIO()):
            start()
        return captured["handler"]

    def _get(self, handler_class, path, query):
        handler = object.__new__(handler_class)
        handler.headers, handler.wfile, handler.command = {}, io.BytesIO(), "GET"
        handler.path = path + ("?" + query if query else "")
        recorder = Recorder()
        handler._send = recorder
        handler.do_GET()
        return recorder.responses[0]

    def test_private_public_and_shared_dispatch_agree(self):
        state = _state()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_file = root / "state.json"
            state_file.write_text(json.dumps(state), encoding="utf-8")
            (root / "history.jsonl").write_text("", encoding="utf-8")
            config = {"state_file": str(state_file), "history_file": str(root / "history.jsonl"), "sources": []}

            with patch.dict(os.environ, {"CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD": ""}):
                private = self._capture(dashboard, lambda: dashboard.serve(config))

            class Storage:
                def download(self, name, destination):
                    Path(destination).write_text(json.dumps(sanitize_public_render_state(state)), encoding="utf-8")
                    return True

            with patch.dict(os.environ, {"WATCHTOWER_PUBLIC_WORKDIR": str(root / "public")}), \
                    patch.object(public_dashboard, "backend_from_env", return_value=Storage()):
                public = self._capture(public_dashboard, public_dashboard.serve_public)
                for path, query in REQUESTS:
                    with self.subTest(path=path, query=query):
                        shared = Recorder()
                        dispatch_gac_routes(path, query, config=config, send=shared)
                        expected = shared.responses[0][:2]
                        self.assertEqual(self._get(private, path, query)[:2], expected)
                        self.assertEqual(self._get(public, path, query)[:2], expected)
                # A schema failure is the same explicit error everywhere.
                with patch.object(dashboard_exports, "load_gac_standard", side_effect=OSError("synthetic")):
                    for handler in (private, public):
                        status, kind, body = self._get(handler, "/mngac.csv", "standard=address")
                        self.assertEqual((status, kind), (503, "text/plain"))

    def test_dispatcher_import_compatibility(self):
        self.assertIs(dashboard.dispatch_gac_routes, dispatch_gac_routes)


if __name__ == "__main__":
    unittest.main()
