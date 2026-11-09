import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.county_admin import create_county_admin_server
from clearparcel.datawatch.county_attachments import CountyAttachments
from clearparcel.datawatch.county_directory import project_public_county
from clearparcel.datawatch.county_directory_seed import packaged_county_drafts
from clearparcel.datawatch.county_directory_store import CountyDirectoryStore, read_public_directory
from clearparcel.datawatch.county_profiles import county_identities
from clearparcel.datawatch.county_monitoring import CountyMonitoringStore
from clearparcel.datawatch.storage import LocalStorage


class FailingPublicStorage(LocalStorage):
    unavailable = False

    def upload_if_version(self, name, source, version):
        if self.unavailable:
            raise OSError("synthetic private diagnostic")
        super().upload_if_version(name, source, version)


class CountyAdminTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.public = FailingPublicStorage(root / "public")
        private = LocalStorage(root / "private")
        self.store = CountyDirectoryStore(private, self.public)
        self.attachments = CountyAttachments(private)
        self.server = self.enterContext(create_county_admin_server(
            self.store, port=0, username="editor", password="synthetic-password", attachments=self.attachments,
            monitoring_profiles=("cloud",)
        ))
        worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        worker.start()
        self.addCleanup(worker.join, 3)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_port
        self.headers = {"Authorization": "Basic " + base64.b64encode(b"editor:synthetic-password").decode()}
        self.origin = f"http://127.0.0.1:{self.port}"

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body, self.headers if headers is None else headers)
            response = connection.getresponse()
            return response.status, response.headers, response.read()
        finally:
            connection.close()

    def json_request(self, method, path, payload=None, headers=None):
        status, _, body = self.request(method, path, None if payload is None else json.dumps(payload), headers)
        return status, json.loads(body)

    def get_mutation_headers(self):
        status, directory = self.json_request("GET", "/api/counties")
        self.assertEqual(status, 200)
        return {**self.headers, "Content-Type": "application/json", "Origin": self.origin,
                "X-Watchtower-CSRF": directory["csrf_token"]}

    def apply_payload(self, request_id="first", revision=0):
        return {"expected_revision": revision, "request_id": request_id, "draft": {
            "fips": "27001", "policy": {"text": "Public policy"},
            "correspondence": [{"subject": "PRIVATE_SENTINEL"}],
        }}

    def monitoring_payload(self):
        payload = self.apply_payload()
        payload["draft"]["access"] = {"parcel_polygons": {"classification": "open",
            "restrictions": {"status": "reviewed_none"}, "methods": [{"kind": "direct_rest",
                "url": "https://example.gov/arcgis/rest/services/Parcels/FeatureServer/0", "scope": "County parcels",
                "evidence_date": "2026-11-07", "monitoring": {"enabled": True, "execution_profile": "cloud",
                    "terms_url": "https://example.gov/terms", "terms_reviewed_on": "2026-11-07", "terms_confirmed": True,
                    "county_permission": {"reply": "permitted", "scope": "details-and-count", "received_on": "2026-11-07",
                        "reference": "SYNTHETIC_PRIVATE_REFERENCE"}}}]}}
        return payload

    def test_all_reads_and_writes_require_authentication(self):
        for method, path in [("GET", "/"), ("GET", "/api/counties"),
                             ("GET", "/api/counties/aitkin"), ("GET", "/api/counties/aitkin/publication"),
                             ("POST", "/api/counties/aitkin"), ("POST", "/api/counties/aitkin/publication")]:
            with self.subTest(method=method, path=path):
                status, headers, _ = self.request(method, path, headers={})
                self.assertEqual(status, 401)
                self.assertIn("Basic", headers["WWW-Authenticate"])
                self.assertEqual(headers["Cache-Control"], "no-store")

    def test_editor_assets_are_authenticated_and_use_same_origin_csp(self):
        status, headers, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"County information editor", page)
        self.assertIn(b'src="/county-admin.js"', page)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        for path in ("/county-admin.js", "/county-admin.css"):
            self.assertEqual(self.request("GET", path)[0], 200)
            self.assertEqual(self.request("GET", path, headers={})[0], 401)

    def test_directory_resolves_all_counties_and_apply_confirms_readback(self):
        status, directory = self.json_request("GET", "/api/counties")
        self.assertEqual(status, 200)
        counties = directory["counties"]
        self.assertEqual(len({county["fips"] for county in counties}), 87)
        self.assertEqual([county["name"] for county in counties], sorted(county["name"] for county in counties))
        self.assertEqual(self.json_request("GET", "/api/counties/missing")[0], 404)
        headers = self.get_mutation_headers()
        status, applied = self.json_request("POST", "/api/counties/aitkin", self.apply_payload(), headers)
        self.assertEqual((status, applied["status"], applied["public_revision"]), (200, "published", 1))
        public = read_public_directory(self.public)
        self.assertEqual(public["27001"]["policy"]["text"], "Public policy")
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(public))
        status, detail = self.json_request("GET", "/api/counties/aitkin")
        self.assertEqual(status, 200)
        self.assertEqual(detail["draft"]["correspondence"][0]["subject"], "PRIVATE_SENTINEL")

    def test_host_origin_csrf_and_json_bounds_are_enforced_before_apply(self):
        headers = self.get_mutation_headers()
        path = "/api/counties/aitkin"
        for override, expected in [
            ({"Host": "rebound.example:8765"}, 403),
            ({"Origin": "https://foreign.example"}, 403),
            ({"X-Watchtower-CSRF": "bad"}, 403),
            ({"Sec-Fetch-Site": "cross-site"}, 403),
            ({"Content-Type": "text/plain"}, 415),
            ({"Content-Length": str(300_000)}, 413),
        ]:
            with self.subTest(override=override):
                self.assertEqual(self.json_request("POST", path, self.apply_payload(), {**headers, **override})[0], expected)
        self.assertEqual(self.json_request("GET", path)[1]["revision"], 0)

    def test_failed_publication_returns_pending_then_retries_and_handles_conflict(self):
        self.public.unavailable = True
        headers = self.get_mutation_headers()
        path = "/api/counties/aitkin"
        status, result = self.json_request("POST", path, self.apply_payload(), headers)
        self.assertEqual((status, result["status"], result["revision"]), (202, "pending", 1))
        self.assertNotIn("private diagnostic", json.dumps(result))
        self.assertEqual(self.json_request("GET", path + "/publication")[1]["status"], "pending")
        self.assertEqual(self.json_request("POST", path, self.apply_payload("stale"), headers)[0], 409)
        self.public.unavailable = False
        status, result = self.json_request("POST", path + "/publication", {}, headers)
        self.assertEqual((status, result["status"], result["public_revision"]), (200, "published", 1))
        self.assertEqual(self.json_request("POST", path, self.apply_payload(), headers)[1]["revision"], 1)

    def test_private_only_save_never_claims_to_publish(self):
        headers = self.get_mutation_headers()
        path = "/api/counties/aitkin"
        self.assertEqual(self.json_request("POST", path, self.apply_payload(), headers)[0], 200)
        private_change = self.apply_payload("next", 1)
        private_change["draft"]["correspondence"][0]["subject"] = "Changed private note"
        status, result = self.json_request("POST", path, private_change, headers)
        self.assertEqual((status, result["status"]), (200, "saved_private"))

    def test_monitoring_removal_survives_failed_publication_and_old_save_replay(self):
        headers = self.get_mutation_headers()
        payload = self.monitoring_payload()
        route = "/api/counties/aitkin"
        self.assertEqual(self.json_request("POST", route, payload, headers)[0], 200)
        registry = CountyMonitoringStore(self.store._private)
        self.assertEqual(len(registry.read_sources()), 1)
        newer = json.loads(json.dumps(payload))
        newer.update(expected_revision=1, request_id="disable-monitoring")
        newer["draft"]["access"]["parcel_polygons"]["methods"][0]["monitoring"]["enabled"] = False
        newer["draft"]["policy"]["text"] = "Changed public text"
        self.public.unavailable = True
        with patch.object(CountyMonitoringStore, "replace_county", side_effect=OSError("synthetic registry failure")):
            status, receipt = self.json_request("POST", route, newer, headers)
        self.assertEqual((status, receipt["status"], receipt["monitoring_status"]), (202, "pending", "pending"))
        self.assertEqual(registry.read_sources(), [])
        self.json_request("POST", route, payload, headers)
        self.assertEqual(registry.read_sources(), [])
        self.assertEqual(self.store.read_private(county_identities()["aitkin"]).revision, 2)

    def test_silent_county_policy_allows_limited_rest_enrollment_without_permission(self):
        with patch("clearparcel.datawatch.county_monitoring.load_parcel_access", return_value={
                "Aitkin": {"monitoring": {"decision": "not-assessed", "scope": "none"}}}):
            status, receipt = self.json_request("POST", "/api/counties/aitkin", self.monitoring_payload(), self.get_mutation_headers())
        self.assertEqual((status, receipt["status"], receipt["monitoring_source_count"]), (200, "published", 1))
        self.assertEqual(self.store.read_private(county_identities()["aitkin"]).revision, 1)

    def test_unavailable_worker_cannot_be_enrolled(self):
        payload = self.monitoring_payload()
        payload["draft"]["access"]["parcel_polygons"]["methods"][0]["monitoring"]["execution_profile"] = "local"
        headers = self.get_mutation_headers()
        self.assertEqual(self.json_request("GET", "/api/counties")[1]["monitoring_profiles"], ["cloud"])
        status, receipt = self.json_request("POST", "/api/counties/aitkin", payload, headers)
        self.assertEqual((status, receipt["status"]), (400, "invalid_draft"))
        self.assertIn("access.parcel_polygons.methods.0.monitoring.execution_profile", {e.get("field") for e in receipt["errors"]})
        self.assertEqual(self.store.read_private(county_identities()["aitkin"]).revision, 0)

    def test_conflicting_removal_reconciles_winning_enrollment_before_response(self):
        headers = self.get_mutation_headers()
        payload = self.monitoring_payload()
        self.json_request("POST", "/api/counties/aitkin", payload, headers)
        losing = json.loads(json.dumps(payload))
        losing.update(expected_revision=1, request_id="loser")
        losing["draft"]["access"]["parcel_polygons"]["methods"][0]["monitoring"]["enabled"] = False
        private = self.store._private
        original, raced = private.upload_if_version, False
        def race(name, path, version):
            nonlocal raced
            if not raced and "/records/" in name:
                raced = True
                self.store.save(county_identities()["aitkin"], payload["draft"], expected_revision=1, request_id="winner")
            original(name, path, version)
        with patch.object(private, "upload_if_version", side_effect=race):
            status, receipt = self.json_request("POST", "/api/counties/aitkin", losing, headers)
        self.assertEqual((status, receipt["status"], receipt["monitoring_status"]), (409, "revision_conflict", "current"))
        cfg = {"sources": [], "state_file": str(private.root / "state.json"), "history_file": str(private.root / "history.jsonl")}
        with patch.dict(os.environ, {"WATCHTOWER_COUNTY_MONITORING_ROOT": str(private.root), "WATCHTOWER_COUNTY_MONITORING_BUCKET": ""}), \
                patch.object(watch, "_source_check", return_value={"problems": []}) as check:
            report = watch.check_sources(cfg, save=False, execution_profile="cloud")
        check.assert_called_once()
        self.assertEqual(len(report["sources"]), 1)

    def test_invalid_save_returns_safe_field_hints_without_writing(self):
        payload = self.apply_payload()
        payload['draft']['contacts'] = [{'name': 'Invented office', 'email': 'PRIVATE_BAD_VALUE'}]
        payload['draft']['policy']['url'] = 'javascript:PRIVATE_BAD_VALUE'
        status, result = self.json_request('POST', '/api/counties/aitkin', payload, self.get_mutation_headers())
        self.assertEqual((status, result['status']), (400, 'invalid_draft'))
        self.assertIn('contacts.0.email', {e.get('field') for e in result['errors']})
        self.assertIn('policy.url', {e.get('field') for e in result['errors']})
        self.assertNotIn('PRIVATE_BAD_VALUE', json.dumps(result))
        self.assertEqual(self.json_request('GET', '/api/counties/aitkin')[1]['revision'], 0)

    def test_directory_search_includes_public_department_and_role(self):
        payload = self.apply_payload()
        payload['draft']['contacts'] = [{'name': 'Invented office', 'department': 'Invented mapping', 'role': 'Invented coordinator'}]
        self.json_request('POST', '/api/counties/aitkin', payload, self.get_mutation_headers())
        directory = self.json_request('GET', '/api/counties')[1]
        terms = next(c['search_terms'] for c in directory['counties'] if c['slug'] == 'aitkin')
        self.assertIn('Invented mapping', terms)
        self.assertIn('Invented coordinator', terms)

    def test_packaged_seed_preserves_current_contacts_and_separate_access_evidence(self):
        counties = county_identities()
        seeds = packaged_county_drafts(counties)
        self.assertEqual(set(seeds), set(counties))
        self.assertEqual(seeds["fillmore"]["contacts"], [])
        self.assertTrue(seeds["aitkin"]["contacts"])
        jackson = seeds["jackson"]["access"]["parcel_polygons"]
        self.assertEqual(jackson["classification"], "open")
        self.assertIn("Fee-based", jackson["county_direct_note"])
        self.assertIn("mngeo_open", [method["kind"] for method in jackson["methods"]])
        for slug, county in counties.items():
            with self.subTest(county=slug):
                first = seeds[slug]
                public = project_public_county(county, first)
                self.assertEqual(public["access"]["road_centerlines"]["classification"], "unknown")
                self.assertEqual(public["access"]["address_points"]["classification"], "unknown")
        self.assertEqual(seeds["aitkin"], self.json_request("GET", "/api/counties/aitkin")[1]["draft"])
        self.assertEqual(self.store.read_private(counties["aitkin"]).revision, 0)

    def test_attachment_upload_link_and_download_require_private_access_and_scan(self):
        headers = self.get_mutation_headers()
        upload_headers = {**headers, "Content-Type": "application/pdf", "X-Watchtower-Filename": "Private policy.pdf",
                          "X-Watchtower-Upload-ID": "a" * 32}
        route = "/api/counties/aitkin"
        pdf = b"%PDF-1.4\nPRIVATE_ATTACHMENT_SENTINEL\n%%EOF\n"
        status, _, raw = self.request("POST", route + "/attachments?kind=policy", pdf, upload_headers)
        self.assertEqual(status, 201)
        upload = json.loads(raw)
        self.assertEqual(upload["status"], "pending")
        download = route + "/attachments/" + upload["id"]
        self.assertEqual(self.request("GET", download)[0], 404)
        payload = self.apply_payload()
        payload["draft"]["policy"]["attachment_id"] = upload["id"]
        self.assertEqual(self.json_request("POST", route, payload, headers)[0], 200)
        self.assertEqual(self.request("GET", download)[0], 423)
        self.assertEqual(self.request("GET", download, headers={})[0], 401)
        self.assertEqual(self.request("GET", download.replace("aitkin", "anoka"))[0], 404)
        self.attachments.scan("27001", upload["id"], lambda data: data == pdf)
        status, response, downloaded = self.request("GET", download)
        self.assertEqual((status, downloaded), (200, pdf))
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertNotIn("Private policy.pdf", json.dumps(read_public_directory(self.public)))
        self.assertNotIn(upload["id"], json.dumps(read_public_directory(self.public)))
