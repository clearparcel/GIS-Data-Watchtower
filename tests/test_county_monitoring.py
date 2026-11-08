"""Synthetic editor enrollment through scheduled checks and public publication."""
import base64
import contextlib
import copy
import datetime as dt
import http.client
import io
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import cli, transport, watch
from clearparcel.datawatch.aggregate import merge_states
from clearparcel.datawatch.cloud_job import publish_worker_result
from clearparcel.datawatch.county_admin import create_county_admin_server
from clearparcel.datawatch.county_directory import project_public_county
from clearparcel.datawatch.county_directory_store import CountyDirectoryStore, CountyRevisionConflict, read_public_directory
from clearparcel.datawatch.county_monitoring import CountyMonitoringStore, build_county_monitoring_sources
from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles, county_identities
from clearparcel.datawatch.parcel_access import CountyPermission, load_parcel_access
from clearparcel.datawatch.public_dashboard import render_public_dashboard, render_public_source
from clearparcel.datawatch.public_projection import sanitize_public_render_state
from clearparcel.datawatch.public_publish import publish_public_snapshot
from clearparcel.datawatch.storage import LocalStorage

OBJECT = "county-directory/v1/monitoring/sources.json"
URL = "https://gis.example.gov/arcgis/rest/services/Parcels/FeatureServer/0"
PRIVATE = "PRIVATE_PERMISSION_REFERENCE"


def draft(slug="aitkin", *, kind="direct_rest", dataset="parcel_polygons", profile="cloud"):
    return {"fips": county_identities()[slug]["fips"], "contacts": [], "access": {dataset: {
        "classification": "open", "restrictions": {"status": "reviewed_none"}, "methods": [{
            "kind": kind, "url": URL + "?f=pjson" if kind == "direct_rest" else "https://gis.example.gov/data.zip",
            "evidence_date": "2026-11-07", "scope": "Synthetic county data",
            "monitoring": {"enabled": True, "execution_profile": profile,
                "terms_url": "https://example.gov/terms", "terms_reviewed_on": "2026-11-07", "terms_confirmed": True,
                "county_permission": {"reply": "permitted", "scope": "details-and-count", "received_on": "2026-11-07",
                    "reference": PRIVATE, "evidence_url": ""}},
        }]}}, "policy": {}, "correspondence": []}


def config(root, sources=()):
    return {"state_file": str(root / "state.json"), "history_file": str(root / "history.jsonl"),
            "alerts_file": str(root / "alerts.json"), "alerts_text_file": str(root / "alerts.txt"),
            "retries": 0, "sources": list(sources)}


class CountyMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.county = county_identities()["aitkin"]
        self.storage = LocalStorage(self.root / "private")
        self.registry = CountyMonitoringStore(self.storage)
        self.enterContext(patch.dict(os.environ, {"WATCHTOWER_COUNTY_MONITORING_BUCKET": "",
            "WATCHTOWER_COUNTY_MONITORING_ROOT": str(self.storage.root), "WATCHTOWER_ALLOW_INVENTORY_SHRINK": ""}))

    def test_enrollment_is_explicit_private_and_bounded(self):
        value = draft()
        sources = build_county_monitoring_sources(self.county, value)
        self.assertEqual(sources[0]["url"], URL)
        self.assertEqual(sources[0]["execution_profiles"], ["cloud"])
        self.assertTrue(sources[0]["count"])
        self.assertNotIn(PRIVATE, json.dumps(project_public_county(self.county, value)))
        self.assertNotIn("monitoring", project_public_county(self.county, value)["access"]["parcel_polygons"]["methods"][0])
        value["access"]["parcel_polygons"]["methods"][0]["monitoring"]["enabled"] = False
        self.assertEqual(build_county_monitoring_sources(self.county, value), [])

    def test_incomplete_reviews_human_pages_and_filtered_layers_are_rejected(self):
        for location, replacement in [
            (("classification",), "fee"), (("restrictions", "status"), "unreviewed"),
            (("methods", 0, "monitoring", "terms_confirmed"), False),
            (("methods", 0, "monitoring", "county_permission", "reply"), "no-reply"),
            (("methods", 0, "monitoring", "county_permission", "reference"), ""),
            (("methods", 0, "url"), "https://example.gov/parcel-viewer"),
            (("methods", 0, "url"), URL + "?where=privateFilter"),
            (("methods", 0, "url"), URL + "?token=secret"),
            (("methods", 0, "url"), "http://127.0.0.1/rest/services/Parcels/FeatureServer/0"),
        ]:
            value = draft()
            node = value["access"]["parcel_polygons"]
            for key in location[:-1]:
                node = node[key]
            node[location[-1]] = replacement
            with self.subTest(location=location, replacement=replacement), self.assertRaises(ValueError):
                build_county_monitoring_sources(self.county, value)

    def test_enrolled_file_and_layer_reject_private_dns_before_dispatch(self):
        addresses = ((socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),)
        for revision, kind in enumerate(("direct_rest", "direct_download"), 1):
            self.registry.replace_county(self.county, draft(kind=kind), revision=revision)
            with (self.subTest(kind=kind),
                  patch.object(watch, "resolve_addresses", return_value=addresses),
                  patch.object(transport.socket, "socket") as sock,
                  patch.object(watch.urllib.request, "build_opener") as opener,
                  patch.object(watch.subprocess, "run") as curl):
                report = watch.check_sources(config(self.root), save=False, execution_profile="cloud")
            row, = report["sources"].values()
            self.assertEqual(row["status"], "error")
            self.assertIn("destination is not public", row["error"])
            self.assertFalse(watch._PUBLIC_SOURCE_REQUESTS.get())
            sock.assert_not_called()
            opener.assert_not_called()
            curl.assert_not_called()

    def test_enrolled_layer_count_keeps_public_destination_boundary(self):
        self.registry.replace_county(self.county, draft(), revision=1)
        public = ((socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),)
        private = ((socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd00::1", 443, 0, 0)),)
        with (patch.object(watch, "resolve_addresses", side_effect=[public, private]) as resolve,
              patch.object(watch, "_urllib_request_once", return_value=(b'{"fields": []}', {"status": 200})) as request,
              patch.object(watch.subprocess, "run") as curl):
            report = watch.check_sources(config(self.root), save=False, execution_profile="cloud")
        row, = report["sources"].values()
        self.assertEqual(row["status"], "error")
        self.assertIn("destination is not public", row["error"])
        self.assertEqual(resolve.call_count, 2)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0].addresses, public)
        curl.assert_not_called()

    def test_county_holds_and_stop_decisions_remain_authoritative(self):
        for decision in ({"decision": "hold-for-terms"}, {"decision": "not-appropriate"},
                         {"decision": "not-assessed", "scope": "none"},
                         {"decision": "not-assessed", "stop_requested": True},
                         {"decision": "not-assessed", "reply": "declined", "scope": "none"}):
            with self.subTest(decision=decision), patch("clearparcel.datawatch.county_monitoring.load_parcel_access",
                    return_value={"Aitkin": {"monitoring": decision}}), self.assertRaises(ValueError):
                build_county_monitoring_sources(self.county, draft())
        self.registry.replace_county(self.county, draft(), revision=1)
        held = load_parcel_access()
        held["Aitkin"]["monitoring"]["decision"] = "hold-for-terms"
        with patch("clearparcel.datawatch.parcel_access.load_parcel_access", return_value=held), \
                patch.object(watch, "_source_check") as check:
            report = watch.check_sources(config(self.root), save=False, execution_profile="cloud")
        check.assert_not_called()
        self.assertIn("hold-for-terms", report["skipped_sources"].values())

    def test_cas_preserves_other_counties_and_old_retries_cannot_reinstate_a_source(self):
        other = county_identities()["anoka"]
        original = self.storage.upload_if_version
        racing = True
        def upload(name, path, version):
            nonlocal racing
            if racing:
                racing = False
                self.registry.replace_county(other, draft("anoka"), revision=1)
            original(name, path, version)
        with patch.object(self.storage, "upload_if_version", side_effect=upload):
            self.registry.replace_county(self.county, draft(), revision=1)
        self.assertEqual({s["county_slug"] for s in self.registry.read_sources()}, {"aitkin", "anoka"})
        disabled = draft()
        disabled["access"]["parcel_polygons"]["methods"][0]["monitoring"]["enabled"] = False
        self.registry.replace_county(self.county, disabled, revision=2)
        self.registry.replace_county(self.county, draft(), revision=1)
        self.assertEqual([s["county_slug"] for s in self.registry.read_sources()], ["anoka"])

    def test_ordinary_config_cannot_forge_private_enrollment_and_is_not_mutated(self):
        source = build_county_monitoring_sources(self.county, draft())[0]
        cfg = config(self.root, [source])
        cfg["_county_monitoring_sources"] = [source]
        cfg["_county_monitoring_sources_loaded"] = True
        before = copy.deepcopy(cfg)
        with patch.dict(os.environ, {"WATCHTOWER_COUNTY_MONITORING_ROOT": ""}), patch.object(watch, "_source_check") as check:
            report = watch.check_sources(cfg, save=False, execution_profile="cloud")
        check.assert_not_called()
        self.assertEqual(cfg, before)
        self.assertEqual(report["skipped_sources"][source["id"]], "awaiting-permission")

    def test_failed_removal_write_does_not_accept_private_save(self):
        store = CountyDirectoryStore(self.storage, LocalStorage(self.root / "directory"))
        store.save(self.county, draft(), expected_revision=0, request_id="first")
        self.registry.replace_county(self.county, draft(), revision=1)
        value = draft()
        value["access"]["parcel_polygons"]["methods"][0]["monitoring"]["enabled"] = False
        with patch.object(self.storage, "upload_if_version", side_effect=OSError("synthetic write failure")), self.assertRaises(OSError):
            store.save(self.county, value, expected_revision=1, request_id="disable", before_save=lambda revision:
                self.registry.prepare_removals(self.county, value, revision=revision))
        self.assertEqual(store.read_private(self.county).revision, 1)
        self.assertEqual(len(self.registry.read_sources()), 1)

    def test_prepared_removal_after_private_cas_conflict_reconciles_the_winning_draft(self):
        for winner_enabled in (True, False):
            with self.subTest(winner_enabled=winner_enabled):
                private = LocalStorage(self.root / str(winner_enabled))
                registry = CountyMonitoringStore(private)
                store = CountyDirectoryStore(private, LocalStorage(self.root / (str(winner_enabled) + "-public")))
                store.save(self.county, draft(), expected_revision=0, request_id="first")
                registry.replace_county(self.county, draft(), revision=1)
                disabled, winner = draft(), draft()
                disabled["access"]["parcel_polygons"]["methods"][0]["monitoring"]["enabled"] = False
                winner["access"]["parcel_polygons"]["methods"][0]["monitoring"]["enabled"] = winner_enabled
                original, raced = private.upload_if_version, False
                def race(name, path, version):
                    nonlocal raced
                    if not raced and "/records/" in name:
                        raced = True
                        store.save(self.county, winner, expected_revision=1, request_id="winner")
                    original(name, path, version)
                with patch.object(private, "upload_if_version", side_effect=race), self.assertRaises(CountyRevisionConflict):
                    store.save(self.county, disabled, expected_revision=1, request_id="loser", before_save=lambda revision:
                        registry.prepare_removals(self.county, disabled, revision=revision))
                self.assertEqual(registry.read_sources(), [])
                saved = store.read_private(self.county)
                registry.replace_county(self.county, saved.draft, revision=saved.revision)
                self.assertEqual(len(registry.read_sources()), int(winner_enabled))

    def test_worker_registry_read_requests_only_the_enrollment_object(self):
        self.registry.replace_county(self.county, draft(), revision=1)
        with patch.object(self.storage, "download_versioned", wraps=self.storage.download_versioned) as read:
            self.registry.read_registry()
        self.assertEqual([call.args[0] for call in read.call_args_list], [OBJECT])

    def test_bad_enrollment_fails_before_daily_guard_and_good_snapshot_is_reused(self):
        self.registry.replace_county(self.county, draft(), revision=1)
        cfg_path = self.root / "config.json"
        cfg_path.write_text(json.dumps(config(self.root)), encoding="utf-8")
        registry_path = self.storage.root / OBJECT
        valid = registry_path.read_text(encoding="utf-8")
        for command in ("check", "cloud-job"):
            registry_path.write_text("{invalid", encoding="utf-8")
            with patch.dict(os.environ, {"WATCHTOWER_MIN_DISPATCH_HOURS": "23", "WATCHTOWER_RUN_RECEIPTS": "0"}), \
                    patch("sys.argv", ["watchtower", "--config", str(cfg_path), command]), \
                    patch("clearparcel.datawatch.dispatch_guard.guard_dispatch") as guard, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(), cli.EXIT_TOOL_FAILURE)
            guard.assert_not_called()
        registry_path.write_text(valid, encoding="utf-8")
        duplicate = config(self.root, self.registry.read_sources())
        cfg_path.write_text(json.dumps(duplicate), encoding="utf-8")
        with patch("sys.argv", ["watchtower", "--config", str(cfg_path), "check"]), \
                patch("clearparcel.datawatch.dispatch_guard.guard_dispatch") as guard, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(), cli.EXIT_TOOL_FAILURE)
        guard.assert_not_called()
        cfg_path.write_text(json.dumps(config(self.root)), encoding="utf-8")
        # A change after the slot claim is for the next run, not a second load.
        with patch("sys.argv", ["watchtower", "--config", str(cfg_path), "check", "--no-save", "--execution-profile", "cloud"]), \
                patch("clearparcel.datawatch.dispatch_guard.guard_dispatch", side_effect=lambda *args, **kwargs:
                      registry_path.write_text("{invalid", encoding="utf-8")) as guard, \
                patch.object(watch, "_source_check", return_value={"problems": []}) as check, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(), cli.EXIT_OK)
        guard.assert_called_once()
        check.assert_called_once()

    def test_invalid_registry_and_colliding_static_id_fail_before_any_poll(self):
        self.registry.replace_county(self.county, draft(), revision=1)
        source = self.registry.read_sources()[0]
        with patch.object(watch, "_source_check") as check, self.assertRaises(watch.InvalidSourceRegistryError):
            watch.check_sources(config(self.root, [source]), save=False, execution_profile="cloud")
        check.assert_not_called()
        path = self.storage.root / OBJECT
        path.write_text('{"schema_version":1,"counties":{"aitkin":null}}', encoding="utf-8")
        with patch.object(watch, "_source_check") as check, self.assertRaises(ValueError):
            watch.check_sources(config(self.root), save=False, execution_profile="cloud")
        check.assert_not_called()

    def test_file_header_check_and_local_worker_assignment(self):
        value = draft(kind="direct_download", dataset="road_centerlines", profile="local")
        self.registry.replace_county(self.county, value, revision=1)
        with patch.object(watch, "_head_request", return_value={"status": 200, "headers": {"etag": "synthetic"}}) as head, \
                patch.object(watch, "_request", side_effect=AssertionError("No file downloads")):
            cloud = watch.check_sources(config(self.root), save=False, execution_profile="cloud")
            head.assert_not_called()
            local = watch.check_sources(config(self.root), save=False, execution_profile="local")
        self.assertFalse(cloud["sources"])
        self.assertEqual(len(local["sources"]), 1)
        source = next(iter(local["sources"].values()))
        self.assertEqual(source["category"], "Roads")
        self.assertEqual(source["monitoring_review"]["mode"], "file-update-metadata")
        head.assert_called_once()

    def test_road_and_address_sources_are_public_without_claiming_parcel_coverage(self):
        for dataset in ("road_centerlines", "address_points"):
            with self.subTest(dataset=dataset):
                value = draft(dataset=dataset)
                research = {"Aitkin": {"monitoring": {"decision": "not-assessed", "scope": "none"}}}
                with patch("clearparcel.datawatch.county_monitoring.load_parcel_access", return_value=research):
                    self.registry.replace_county(self.county, value, revision=1 if dataset == "road_centerlines" else 2)
                with patch("clearparcel.datawatch.parcel_access.load_parcel_access", return_value=research), \
                        patch.object(watch, "_source_check", return_value={"feature_count": 42, "problems": []}):
                    result = watch.check_sources(config(self.root), save=False, execution_profile="cloud")
                public = sanitize_public_render_state(merge_states({}, result, "cloud"))
                sid = next(iter(public["sources"]))
                self.assertIn(public["sources"][sid]["name"], render_public_dashboard({"_render_state": public}))
                self.assertIn("Limited check", render_public_source({"_render_state": public}, sid))
                profiles = compose_county_profiles(public, {}, now=dt.datetime.now(dt.UTC), freshness_policy=FreshnessPolicy())
                self.assertNotIn("county-direct", profiles["aitkin"]["monitoring"]["paths"])

    def test_removal_is_retired_but_an_unconfigured_or_missing_registry_is_not_a_removal(self):
        self.registry.replace_county(self.county, draft(), revision=1)
        cfg = config(self.root)
        with patch.object(watch, "_source_check", return_value={"problems": []}):
            first = watch.check_sources(cfg, execution_profile="cloud")
        sid = next(iter(first["sources"]))
        base = merge_states({}, first, "cloud")
        for root in ("", str(self.root / "missing")):
            with patch.dict(os.environ, {"WATCHTOWER_COUNTY_MONITORING_ROOT": root}), \
                    patch.object(watch, "_source_check") as check, self.assertRaises(ValueError):
                watch.check_sources(config(self.root, [{"id": "static", "name": "Static", "kind": "http_file",
                    "url": "https://example.gov/static.zip", "execution_profiles": ["cloud"]}]),
                    save=False, execution_profile="cloud")
            check.assert_not_called()
        value = draft()
        value["access"]["parcel_polygons"]["methods"][0]["monitoring"]["enabled"] = False
        self.registry.replace_county(self.county, value, revision=2)
        retired = watch.check_sources(cfg, execution_profile="cloud")
        self.assertEqual(retired["scope"]["type"], "fleet")
        self.assertEqual(retired["skipped_sources"][sid], "disabled")
        self.assertNotIn(sid, merge_states(base, retired, "cloud")["sources"])

    def test_http_save_to_regular_worker_to_public_snapshot_and_county_status(self):
        directory = LocalStorage(self.root / "directory")
        store = CountyDirectoryStore(self.storage, directory)
        with create_county_admin_server(store, port=0, username="editor", password="synthetic") as server:
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            worker.start()
            try:
                headers = {"Authorization": "Basic " + base64.b64encode(b"editor:synthetic").decode()}
                origin = f"http://127.0.0.1:{server.server_port}"
                def request(method, path, body=None):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    try:
                        connection.request(method, path, None if body is None else json.dumps(body), headers)
                        response = connection.getresponse()
                        return response.status, json.loads(response.read())
                    finally:
                        connection.close()
                token = request("GET", "/api/counties")[1]["csrf_token"]
                headers.update({"Origin": origin, "Content-Type": "application/json", "X-Watchtower-CSRF": token})
                with patch.object(watch, "_source_check", side_effect=AssertionError("Save never polls")):
                    status, receipt = request("POST", "/api/counties/aitkin", {
                        "expected_revision": 0, "request_id": "synthetic-enrollment", "draft": draft()})
                self.assertEqual((status, receipt["status"], receipt["monitoring_status"]), (200, "published", "current"))
                self.assertEqual(receipt["monitoring_source_count"], 1)
            finally:
                server.shutdown()
                worker.join(3)
        self.assertNotIn(PRIVATE, json.dumps(read_public_directory(directory)))
        responses = [({"name": "Synthetic parcels", "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}],
                       "geometryType": "esriGeometryPolygon"}, {"status": 200}), ({"count": 42}, {"status": 200})]
        cfg = config(self.root)
        with patch.object(watch, "_json_request", side_effect=responses) as transport:
            result = watch.check_sources(cfg, execution_profile="cloud")
        self.assertEqual(len(transport.call_args_list), 2)
        self.assertEqual(transport.call_args_list[0].args[0], URL + "?f=json")
        self.assertIn(URL + "/query?", transport.call_args_list[1].args[0])
        self.assertIn("returnCountOnly=true", transport.call_args_list[1].args[0])
        aggregate = LocalStorage(self.root / "aggregate")
        cfg["aggregate_object"] = "aggregate-state.json"
        with patch("clearparcel.datawatch.cloud_job.backend_from_env", return_value=aggregate):
            merged = publish_worker_result(cfg, result, "cloud", workdir=self.root / "merge")
        public_store = LocalStorage(self.root / "public")
        publication = publish_public_snapshot(aggregate, public_store, workdir=self.root / "publisher")
        self.assertTrue(publication["published"])
        public = json.loads((public_store.root / "aggregate-state.json").read_text(encoding="utf-8"))
        sid = next(iter(public["sources"]))
        self.assertEqual(public["sources"][sid]["feature_count"], 42)
        self.assertEqual(public["sources"][sid]["worker"], "cloud")
        self.assertNotIn(PRIVATE, json.dumps(merged))
        self.assertNotIn("monitoring_approval", json.dumps(public))
        self.assertNotIn("county_monitoring_revision", json.dumps(public))
        page = render_public_source({"_render_state": public}, sid)
        self.assertIn("Limited check: service details and a record count only.", page)
        profiles = compose_county_profiles(public, load_parcel_access(), now=dt.datetime.now(dt.UTC), freshness_policy=FreshnessPolicy())
        county = profiles["aitkin"]
        self.assertIn("county-direct", county["monitoring"]["paths"])
        self.assertEqual(county["monitoring"]["reporting"], "current")
        self.assertTrue(any(s["monitored_source_id"] == sid for s in county["county_arcgis_rest"]["sources"]))


if __name__ == "__main__":
    unittest.main()
