"""Offline regressions for the November 8 repository findings."""
import base64
import contextlib
import datetime as dt
from email.message import Message
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from clearparcel.datawatch import dashboard, public_dashboard
from clearparcel.datawatch.county_admin import create_county_admin_server
from clearparcel.datawatch.county_admin_hosted import IapAdminAuth
from clearparcel.datawatch.county_attachments import CountyAttachments
from clearparcel.datawatch.county_directory_store import CountyDirectoryStore, read_public_directory
from clearparcel.datawatch.county_profiles import county_identities
from clearparcel.datawatch.private_dashboard import StateSync, HISTORY_OBJECT
from clearparcel.datawatch.storage import LocalStorage, GCSStorage, StorageConflictError
from tests.test_private_dashboard import _aggregate


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def cache(self):
        with patch.dict(os.environ, {"WATCHTOWER_STORAGE": "local", "WATCHTOWER_PUBLIC_WORKDIR": str(self.root / "cache")}, clear=True):
            cache = public_dashboard._PublicStateCache()
        cache.public_path.write_text(json.dumps({**_aggregate(), "public_published_at": dt.datetime.now(dt.UTC).isoformat()}))
        return cache

    def test_corrupt_state_never_replaces_good_snapshot_and_sync_recovers(self):
        source = self.root / "source"
        source.mkdir()
        path = source / "aggregate.json"
        target = self.root / "cache.json"
        good = json.dumps(_aggregate())
        path.write_text(good)
        sync = StateSync(LocalStorage(source), {"aggregate.json": target}, required=("aggregate.json",))
        sync.sync()
        for bad in ('{', '[]', 'null', '{"sources": []}', json.dumps({**_aggregate(), "counts": {"ok": 9}})):
            with self.subTest(bad=bad):
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    sync.sync()
                self.assertEqual(target.read_text(), good)
                self.assertTrue(sync.status["refresh_failed"])
                self.assertIsNotNone(sync.status["last_success_at"])
        path.write_text(good)
        sync.sync()
        self.assertFalse(sync.status["refresh_failed"])
        path.write_text('[]')
        startup = StateSync(LocalStorage(source), {"aggregate.json": self.root / "new.json"})
        with self.assertRaises(ValueError):
            startup.sync()
        self.assertFalse((self.root / "new.json").exists())

    def test_invalid_history_preserves_previous_history(self):
        source = self.root / "source"
        source.mkdir()
        path = source / HISTORY_OBJECT
        path.write_text('{"sources": {}}\n')
        target = self.root / "history.jsonl"
        sync = StateSync(LocalStorage(source), {HISTORY_OBJECT: target})
        sync.sync()
        good = target.read_bytes()
        for value in ('{', '[]', '{"sources": []}', '{"counts": []}'):
            path.write_text(value + '\n')
            with self.assertRaises(ValueError):
                sync.sync()
            self.assertEqual(target.read_bytes(), good)

    def test_nested_corruption_rejected_in_aggregate_and_both_histories(self):
        source = self.root / "nested"
        source.mkdir()
        values = []
        for key, bad in (("worker", []), ("status", []), ("category", ["bad"]), ("changes", 1), ("provenance", ["bad"])):
            value = _aggregate()
            value["sources"]["sample"][key] = bad
            if key == "status": value["counts"]["ok"] = 0
            values.append(value)
        value = _aggregate()
        value["workers"]["cloud"]["telemetry"] = ["broken"]
        values.extend((value, {**_aggregate(), "telemetry": {"wall_ms": "broken"}},
                       {**_aggregate(), "counts": {"ok": "broken"}}))
        for name in ("aggregate.json", HISTORY_OBJECT, HISTORY_OBJECT + ".1"):
            path = source / name
            good = json.dumps(_aggregate()) + "\n"
            path.write_text(good)
            target = self.root / ("cached-" + name)
            sync = StateSync(LocalStorage(source), {name: target})
            sync.sync()
            for bad in values:
                with self.subTest(name=name, bad=bad):
                    path.write_text(json.dumps(bad))
                    with self.assertRaises(ValueError): sync.sync()
                    self.assertEqual(target.read_text(), good)
                    self.assertTrue(sync.status["refresh_failed"])
            path.write_text(good)
            sync.sync()
            self.assertFalse(sync.status["refresh_failed"])
        # The preserved aggregate and legacy history are still renderable.
        dashboard.render_dashboard({"sources": [], "state_file": str(self.root / "cached-aggregate.json"),
                                    "history_file": str(self.root / ("cached-" + HISTORY_OBJECT))})

    def test_directory_outage_backs_off_all_export_routes_and_health(self):
        cache = self.cache()
        captured = {}
        class Server:
            def __init__(self, addr, handler, **kwargs): captured["handler"] = handler
            def serve_forever(self): pass
            def server_close(self): pass
        with patch.object(public_dashboard, "_PublicStateCache", return_value=cache), patch.object(cache, "refresh"), \
                patch.object(public_dashboard, "hosted_public_county_bucket", return_value=None), \
                patch.object(public_dashboard, "_BoundedThreadingHTTPServer", Server), contextlib.redirect_stdout(io.StringIO()):
            public_dashboard.serve_public(county_directory_root=self.root / "directory")
        with patch.object(public_dashboard, "read_public_directory", side_effect=OSError("outage")) as read, patch.object(cache, "refresh"):
            for path in ("/", "/snapshot.csv", "/county-profiles.csv", "/parcel-sources.csv", "/healthz"):
                handler = object.__new__(captured["handler"])
                handler.path, handler.headers = path, {}
                replies = []
                handler._send = lambda status, body, *args: replies.append((status, body))
                handler.do_GET()
                self.assertEqual(replies[0][0], 503, path)
                if path == "/healthz":
                    self.assertEqual(json.loads(replies[0][1])["directory_status"], "unavailable")
            self.assertEqual(read.call_count, 1)
        with patch.object(public_dashboard.time, "monotonic", return_value=cache._directory_read_at + 6), \
                patch.object(public_dashboard, "read_public_directory", return_value={}):
            self.assertEqual(cache.directory(), {})
            self.assertFalse(cache.directory_failed)

    def test_warm_views_do_not_reload_research(self):
        cache = self.cache()
        cache.view()
        with patch.object(public_dashboard, "load_parcel_access", side_effect=AssertionError("redundant research read")):
            for _ in range(10): cache.view()

    def test_password_free_access_is_only_loopback(self):
        with patch.dict(os.environ, {}, clear=True):
            for host in ("127.0.0.1", "::1", "localhost"):
                self.assertIsNone(dashboard._dashboard_auth({}, host)[0])
            for host in ("192.168.1.5", "10.0.0.2", "172.16.0.2", "fd00::1", "fe80::1", "0.0.0.0", "::", "8.8.8.8"):
                with self.subTest(host=host), self.assertRaises(RuntimeError):
                    dashboard._dashboard_auth({}, host)
            with self.assertRaises(RuntimeError):
                dashboard._dashboard_auth({"public_dashboard": {"internet_exposure": True}}, "127.0.0.1")
        with patch.dict(os.environ, {"CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD": "synthetic"}, clear=True):
            self.assertEqual(dashboard._dashboard_auth({}, "192.168.1.5")[0], "synthetic")

    def test_attachment_metadata_is_bounded_and_download_still_verifies_bytes(self):
        storage = LocalStorage(self.root / "attachments")
        attachments = CountyAttachments(storage)
        pdf = b'%PDF-1.7\n' + b' ' * (1024 * 1024) + b'\n%%EOF'
        meta = attachments.upload("27001", "policy", None, "policy.pdf", pdf)
        with patch.object(storage, "download", side_effect=AssertionError("full download")), \
                patch.object(storage, "read_prefix", wraps=storage.read_prefix) as reads:
            self.assertEqual(attachments.info("27001", meta["id"])["size"], len(pdf))
            attachments.validate_refs("27001", [(meta["id"], "policy", None)])
            self.assertEqual(reads.call_count, 2)
            self.assertEqual(reads.call_args.args[1], 2052)
        attachments.scan("27001", meta["id"], lambda _: True)
        self.assertEqual(attachments.download("27001", meta["id"])[1], pdf)
        path = next(storage.root.rglob("*.bin"))
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + b'X')
        with self.assertRaises(ValueError):
            attachments.download("27001", meta["id"])

    def test_gcs_prefix_is_bound_to_generation_and_conflicts_fail(self):
        from google.api_core.exceptions import PreconditionFailed
        storage = object.__new__(GCSStorage)
        storage.client, storage.bucket, storage.prefix = Mock(), Mock(), ""
        blob = storage.bucket.blob.return_value
        blob.generation = 41
        blob.download_as_bytes.return_value = b'header'
        self.assertEqual(storage.read_prefix("attachment", 2052), b'header')
        blob.download_as_bytes.assert_called_once_with(start=0, end=2051, raw_download=True, if_generation_match=41)
        blob.download_as_bytes.side_effect = PreconditionFailed("changed")
        with self.assertRaises(StorageConflictError):
            storage.read_prefix("attachment", 2052)

    def test_warm_editor_list_avoids_county_reads(self):
        store = CountyDirectoryStore(LocalStorage(self.root / "private"), LocalStorage(self.root / "public"))
        with create_county_admin_server(store, port=0, username="synthetic", password="synthetic") as server:
            handler = object.__new__(server.RequestHandlerClass)
            handler.server, handler.path = server, "/api/counties"
            handler.headers = Message()
            handler.headers["Host"] = f"127.0.0.1:{server.server_port}"
            handler.headers["Authorization"] = "Basic " + base64.b64encode(b"synthetic:synthetic").decode()
            handler._send = Mock()
            handler.do_GET()
            with patch.object(store, "read_private", side_effect=AssertionError("warm list read")):
                handler.do_GET()
            self.assertEqual(handler._send.call_args.args[0], 200)

    def test_verified_actors_and_edits_commit_together_without_duplicate_audit(self):
        private, public = LocalStorage(self.root / "private"), LocalStorage(self.root / "public")
        store = CountyDirectoryStore(private, public)
        county = county_identities()["aitkin"]
        auth = IapAdminAuth("https://admin.example.org", "/projects/123/global/backendServices/456", {"one", "two"}, bytes(32),
                            verify=lambda assertion, _: {"iss": "https://cloud.google.com/iap", "sub": assertion})
        draft = {"fips": county["fips"], "policy": {"text": "Public"}}
        for revision, subject in enumerate(("one", "two")):
            csrf, actor = auth.authorize_identity(subject)
            self.assertEqual(csrf, auth.authorize(subject))
            for _ in range(2):
                store.save(county, draft, expected_revision=revision, request_id=subject, actor=actor)
        stored = json.loads(next(private.root.rglob("*.json")).read_text())
        self.assertEqual([e["actor"] for e in stored["audit_events"]], ["iap:one", "iap:two"])
        self.assertEqual([e["prior_revision"] for e in stored["audit_events"]], [0, 1])
        store.publish(county)
        self.assertNotIn("iap:", json.dumps(read_public_directory(public)))
        with patch.object(private, "upload_if_version", side_effect=OSError("write failed")), self.assertRaises(OSError):
            store.save(county, draft, expected_revision=2, request_id="third", actor="iap:one")
        self.assertEqual(json.loads(next(private.root.rglob("*.json")).read_text()), stored)
