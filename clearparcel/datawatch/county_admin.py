"""County administration with explicit local or signed hosted authentication."""

from __future__ import annotations

import base64
import hmac
import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

from .county_attachments import CountyAttachments, MAX_ATTACHMENT_BYTES, draft_attachment_refs
from .county_monitoring import CountyMonitoringStore, build_county_monitoring_sources
from .county_directory_store import CountyDirectoryStore, CountyRevisionConflict, PublicationStatus
from .county_directory_seed import packaged_county_drafts
from .county_admin_validation import editor_validation_errors
from .county_profiles import county_identities
from .dashboard import _BoundedThreadingHTTPServer, _dashboard_auth, _validated_content_length
from .storage import LocalStorage, StorageConflictError

_HOST = "127.0.0.1"
_MAX_BODY = 256 * 1024
_COUNTY_ROUTE = re.compile(r"/api/counties/([a-z0-9-]+)(/publication)?")
_ATTACHMENT_UPLOAD = re.compile(r"/api/counties/([a-z0-9-]+)/attachments\?(.+)")
_ATTACHMENT_READ = re.compile(r"/api/counties/([a-z0-9-]+)/attachments/([a-f0-9]{32})(/status)?")
_ATTACHMENT_SCAN = re.compile(r"/api/counties/([a-z0-9-]+)/attachments/([a-f0-9]{32})/scan")
_STORE_FAILURES = (OSError, ValueError, StorageConflictError)
_ASSETS = {
    "/": ("county_admin.html", "text/html; charset=utf-8"),
    "/county-admin.css": ("county_admin.css", "text/css; charset=utf-8"),
    "/county-admin.js": ("county_admin.js", "text/javascript; charset=utf-8"),
}


def _status_payload(status: PublicationStatus) -> dict:
    return {
        "status": "published" if status.confirmed else "pending" if status.target_revision else "unsaved",
        "target_revision": status.target_revision,
        "public_revision": status.published_revision,
    }


def create_county_admin_server(store: CountyDirectoryStore, *, port: int, username: str | None = None,
                               password: str | None = None, attachments: CountyAttachments | None = None,
                               hosted_auth=None, scanner=None, monitoring_store: CountyMonitoringStore | None = None,
                               backend_errors=()):
    if hosted_auth is None and (not username or ":" in username or not password):
        raise ValueError("County administration requires a username and password")
    if hosted_auth is not None and (username is not None or password is not None):
        raise ValueError("hosted and local authentication cannot be combined")
    expected = f"{username}:{password}".encode("utf-8")
    token = secrets.token_urlsafe(32)
    scan_slots = threading.BoundedSemaphore(2)
    store_failures = _STORE_FAILURES + backend_errors
    backend_failures = (OSError, StorageConflictError) + backend_errors
    monitoring_store = monitoring_store or CountyMonitoringStore(store._private)
    counties = county_identities()
    drafts = packaged_county_drafts(counties)
    assets = {route: (Path(__file__).with_name(name).read_bytes(), content_type)
              for route, (name, content_type) in _ASSETS.items()}

    def directory():
        summary = []
        for county in sorted(counties.values(), key=lambda county: county["name"]):
            stored = store.read_private(county).draft
            draft = drafts[county["slug"]] if stored is None else stored
            contacts = [contact for contact in draft.get("contacts", []) if not contact.get("removed")]
            summary.append({
                **county, "contact_count": len(contacts),
                "search_terms": [contact[field] for contact in contacts for field in ("name", "email", "department", "role")
                                 if isinstance(contact.get(field), str)],
            })
        return summary

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _one(self, name):
            values = self.headers.get_all(name, [])
            return values[0] if len(values) == 1 else None

        def _send(self, status, body, content_type="application/json; charset=utf-8", *, filename=None):
            data = body if isinstance(body, bytes) else json.dumps(body, allow_nan=False).encode("ascii")
            self.send_response(status)
            if status == 401:
                self.send_header("WWW-Authenticate", 'Basic realm="Watchtower County Administration"')
            self.send_header("Content-Type", content_type)
            if filename is not None:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(data)

        @property
        def _host(self):
            return hosted_auth.host if hosted_auth is not None else f"{_HOST}:{self.server.server_port}"

        def _authorized(self):
            if self._one("Host") != self._host:
                self._send(403, {"status": "request_rejected"})
                return False
            if hosted_auth is not None:
                try:
                    self._csrf = hosted_auth.authorize(self._one("X-Goog-IAP-JWT-Assertion"))
                except OSError:
                    self._send(503, {"status": "identity_unavailable"})
                    return False
                if self._csrf is None:
                    self._send(403, {"status": "authentication_required"})
                    return False
                return True
            authorization = self._one("Authorization") or ""
            if authorization.startswith("Basic "):
                try:
                    credentials = base64.b64decode(authorization[6:], validate=True)
                except ValueError:
                    credentials = b""
                if hmac.compare_digest(credentials, expected):
                    self._csrf = token
                    return True
            self._send(401, {"status": "authentication_required"})
            return False

        def _target(self):
            match = _COUNTY_ROUTE.fullmatch(self.path)
            if match and (county := counties.get(match[1])):
                return county, bool(match[2])
            self._send(404, {"status": "not_found"})
            return None

        def do_GET(self):
            if not self._authorized():
                return
            if self.path in assets:
                self._send(200, *assets[self.path])
                return
            if match := _ATTACHMENT_READ.fullmatch(self.path):
                self._read_attachment(match)
                return
            if self.path == "/api/counties":
                try:
                    self._send(200, {"counties": directory(), "csrf_token": self._csrf, "scanner_enabled": scanner is not None})
                except store_failures:
                    self._send(503, {"status": "storage_unavailable"})
                return
            target = self._target()
            if target is None:
                return
            county, publication = target
            try:
                if publication:
                    status = store.publication_status(county)
                    monitoring_status, monitoring_count = self._sync_monitoring(county)
                    body = {**_status_payload(status), "monitoring_status": monitoring_status,
                            "monitoring_source_count": monitoring_count}
                else:
                    private = store.read_private(county)
                    body = {"county": county, "revision": private.revision,
                            "draft": drafts[county["slug"]] if private.draft is None else private.draft}
            except store_failures:
                self._send(503, {"status": "storage_unavailable"})
                return
            self._send(200, body)

        def _read_body(self, content_type, maximum):
            request_token = self._one("X-Watchtower-CSRF") or ""
            origin = hosted_auth.origin if hosted_auth is not None else f"http://{self._host}"
            if (self._one("Origin") != origin
                    or self.headers.get_all("Sec-Fetch-Site", []) not in ([], ["same-origin"])
                    or not hmac.compare_digest(request_token.encode("utf-8"), self._csrf.encode("utf-8"))):
                self._send(403, {"status": "request_rejected"})
                return None
            if self._one("Content-Type") is None or self.headers.get_content_type() != content_type:
                self._send(415, {"status": "unsupported_media_type"})
                return None
            try:
                if "Transfer-Encoding" in self.headers:
                    raise ValueError
                raw_length = self._one("Content-Length")
                if raw_length is None or not re.fullmatch(r"[0-9]+", raw_length):
                    raise ValueError
                length = _validated_content_length(raw_length, maximum)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError
            except OverflowError:
                self._send(413, {"status": "body_too_large"})
                return None
            except ValueError:
                self._send(400, {"status": "invalid_request"})
                return None
            return raw

        def _read_mutation(self):
            raw = self._read_body("application/json", _MAX_BODY)
            if raw is None:
                return None
            try:
                body = json.loads(raw.decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError
            except (ValueError, RecursionError):
                self._send(400, {"status": "invalid_request"})
                return None
            return body

        def _upload_attachment(self, match):
            if attachments is None or (county := counties.get(match[1])) is None:
                self._send(404, {"status": "not_found"})
                return
            data = self._read_body("application/pdf", MAX_ATTACHMENT_BYTES)
            if data is None:
                return
            try:
                query = parse_qs(match[2], keep_blank_values=True, strict_parsing=True, max_num_fields=2)
                if not query.get("kind") or query.keys() - {"kind", "event"} or any(len(items) != 1 for items in query.values()):
                    raise ValueError
                upload_id = self._one("X-Watchtower-Upload-ID")
                if upload_id is None:
                    raise ValueError
                meta = attachments.upload(county["fips"], query["kind"][0], query.get("event", [None])[0],
                                          self._one("X-Watchtower-Filename"), data, attachment_id=upload_id)
            except ValueError:
                self._send(400, {"status": "invalid_attachment"})
                return
            except backend_failures:
                self._send(503, {"status": "storage_unavailable"})
                return
            meta = self._try_scan(county["fips"], meta)
            self._send(201, {key: meta[key] for key in ("id", "status", "filename")})

        def _try_scan(self, fips, meta):
            if scanner is None or meta["status"] != "pending" or not scan_slots.acquire(blocking=False):
                return meta
            try:
                return attachments.scan(fips, meta["id"], scanner) or meta
            except store_failures:
                return meta
            finally:
                scan_slots.release()

        def _linked_attachment(self, county, attachment_id):
            fips = county["fips"]
            draft = store.read_private(county).draft or {}
            refs = [(kind, event) for ref, kind, event in draft_attachment_refs(draft) if ref == attachment_id]
            meta = attachments.info(fips, attachment_id) if refs else None
            return meta if meta is not None and (meta["kind"], meta["event_id"]) in refs else None

        def _scan_attachment(self, match):
            if attachments is None or scanner is None or (county := counties.get(match[1])) is None:
                self._send(404, {"status": "not_found"})
                return
            body = self._read_mutation()
            if body is None:
                return
            if body:
                self._send(400, {"status": "invalid_request"})
                return
            try:
                meta = self._linked_attachment(county, match[2])
            except store_failures:
                self._send(503, {"status": "storage_unavailable"})
                return
            if meta is None:
                self._send(404, {"status": "not_found"})
                return
            meta = self._try_scan(county["fips"], meta)
            self._send(202 if meta["status"] == "pending" else 200,
                       {key: meta[key] for key in ("id", "status", "filename")})

        def _read_attachment(self, match):
            if attachments is None or (county := counties.get(match[1])) is None:
                self._send(404, {"status": "not_found"})
                return
            fips = county["fips"]
            attachment_id = match[2]
            try:
                meta = self._linked_attachment(county, attachment_id)
                if meta is None:
                    self._send(404, {"status": "not_found"})
                    return
                if match[3]:
                    self._send(200, {key: meta[key] for key in ("id", "status", "filename")})
                    return
                if meta["status"] != "clean" or (download := attachments.download(fips, attachment_id)) is None:
                    self._send(423, {"status": "attachment_unavailable"})
                    return
            except store_failures:
                self._send(503, {"status": "storage_unavailable"})
                return
            metadata, data = download
            self._send(200, data, "application/pdf", filename=metadata["filename"])

        def _publish(self, county, receipt=None):
            body = {} if receipt is None else {"revision": receipt.revision,
                                               "target_revision": receipt.publication_revision}
            monitoring_status, monitoring_count = self._sync_monitoring(county)
            body.update(monitoring_status=monitoring_status, monitoring_source_count=monitoring_count)
            try:
                status = store.publish(county)
            except store_failures:
                self._send(202, {**body, "status": "pending"})
                return
            if receipt is None:
                self._send(202 if status.target_revision and not status.confirmed else 200,
                           {**_status_payload(status), "monitoring_status": monitoring_status,
                            "monitoring_source_count": monitoring_count})
                return
            published = status.published_revision
            requested = receipt.publication_revision
            outcome = "superseded" if published > requested else "published" if published == requested else "pending"
            self._send(202 if outcome == "pending" else 200,
                       {**body, "status": outcome, "public_revision": published,
                        "monitoring_status": monitoring_status,
                        "monitoring_source_count": monitoring_count})

        def _sync_monitoring(self, county):
            try:
                private = store.read_private(county)
                if private.draft is None:
                    return "current", 0
                return "current", monitoring_store.replace_county(county, private.draft, revision=private.revision)
            except store_failures:
                # A durable private save owns enrollment, including removals,
                # even when public publication needs a retry. Never poll here.
                return "pending", None

        def do_POST(self):
            if not self._authorized():
                return
            if match := _ATTACHMENT_UPLOAD.fullmatch(self.path):
                self._upload_attachment(match)
                return
            if match := _ATTACHMENT_SCAN.fullmatch(self.path):
                self._scan_attachment(match)
                return
            if (target := self._target()) is None:
                return
            body = self._read_mutation()
            if body is None:
                return
            county, publication = target
            if publication:
                if body:
                    self._send(400, {"status": "invalid_request"})
                else:
                    self._publish(county)
                return
            if set(body) != {"draft", "expected_revision", "request_id"}:
                self._send(400, {"status": "invalid_request"})
                return
            try:
                refs = draft_attachment_refs(body["draft"])
                build_county_monitoring_sources(county, body["draft"])
                if refs:
                    if attachments is None:
                        raise ValueError
                    attachments.validate_refs(county["fips"], refs)
                receipt = store.save(county, body["draft"], expected_revision=body["expected_revision"],
                                     request_id=body["request_id"],
                                     before_save=lambda revision: monitoring_store.prepare_removals(
                                         county, body["draft"], revision=revision))
            except CountyRevisionConflict:
                # A losing CAS may already have prepared conservative removals.
                # Reconcile the winning saved draft before returning to its editor.
                monitoring_status, monitoring_count = self._sync_monitoring(county)
                self._send(409, {"status": "revision_conflict", "monitoring_status": monitoring_status,
                                 "monitoring_source_count": monitoring_count})
                return
            except ValueError:
                self._send(400, {"status": "invalid_draft", "errors": editor_validation_errors(body["draft"])})
                return
            except backend_failures:
                self._send(503, {"status": "storage_unavailable"})
                return
            if receipt.publication_revision is None:
                monitoring_status, monitoring_count = self._sync_monitoring(county)
                self._send(200, {"status": "saved_private", "revision": receipt.revision,
                                 "monitoring_status": monitoring_status,
                                 "monitoring_source_count": monitoring_count})
            else:
                self._publish(county, receipt)

    bind = "0.0.0.0" if hosted_auth is not None else _HOST
    return _BoundedThreadingHTTPServer((bind, port), Handler, max_connections=16,
                                       request_timeout=50 if hosted_auth is not None else 10)


def serve_county_admin(*, private_root: Path, public_root: Path, port: int) -> None:
    private_root = private_root.resolve()
    public_root = public_root.resolve()
    if private_root.is_relative_to(public_root) or public_root.is_relative_to(private_root):
        raise ValueError("County administration requires nonoverlapping private and public roots")
    password, username = _dashboard_auth({}, _HOST)
    if not password:
        raise ValueError("Set CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD for county administration")
    private = LocalStorage(private_root)
    store = CountyDirectoryStore(private, LocalStorage(public_root))
    with create_county_admin_server(store, port=port, username=username, password=password,
                                    attachments=CountyAttachments(private)) as server:
        print(f"Watchtower County Administration: http://{_HOST}:{server.server_port}")
        server.serve_forever()
