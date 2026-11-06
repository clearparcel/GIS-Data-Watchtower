"""Cloud Run IAM transport for the county scanner, separate from county storage."""

from __future__ import annotations

import os
import re
import threading
from http.server import BaseHTTPRequestHandler

from .county_attachments import MAX_ATTACHMENT_BYTES
from .county_scanner import ClamdScanner
from .dashboard import _BoundedThreadingHTTPServer, _validated_content_length

_RUN_URL = re.compile(r"https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+run\.app")


class RunScannerClient:
    def __init__(self, url, *, request=None, token=None):
        if not _RUN_URL.fullmatch(url):
            raise ValueError("county scanner requires an exact HTTPS Cloud Run service URL")
        self._url = url
        self._request = self._post if request is None else request
        self._token = self._metadata_token if token is None else token
        self._credentials = None
        self._lock = threading.Lock()

    def _metadata_token(self):
        import requests
        from google.auth.compute_engine import IDTokenCredentials
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import Request

        with self._lock:
            try:
                if self._credentials is None or not self._credentials.valid:
                    with requests.Session() as session:
                        session.trust_env = False
                        transport = Request(session)

                        def request(*args, **kwargs):
                            kwargs["timeout"] = 4
                            return transport(*args, **kwargs)

                        if self._credentials is None:
                            self._credentials = IDTokenCredentials(request, self._url, use_metadata_identity_endpoint=True)
                        self._credentials.refresh(request)
            except GoogleAuthError:
                raise OSError("scanner identity is unavailable") from None
            return self._credentials.token

    @staticmethod
    def _post(url, headers, data):
        import requests

        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.post(url, headers=headers, data=data, allow_redirects=False,
                                  timeout=(3, 16), stream=True) as response:
                    body = bytearray()
                    for chunk in response.iter_content(16):
                        body.extend(chunk)
                        if len(body) >= 16:
                            break
                    return response.status_code, bytes(body)
        except (requests.RequestException, OSError):
            raise OSError("scanner request failed") from None

    def __call__(self, data):
        token = self._token()
        if not isinstance(token, str) or not token:
            raise OSError("scanner identity is unavailable")
        status, verdict = self._request(self._url + "/scan", {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/octet-stream",
        }, data)
        if status == 200 and verdict in (b"clean", b"rejected"):
            return verdict == b"clean"
        raise OSError("scanner did not confirm a verdict")


def create_scanner_server(port, scanner, *, host="0.0.0.0"):
    """Serve bounded bytes under Cloud Run invoker IAM, with no storage backend."""
    slots = threading.BoundedSemaphore(2)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send(self, status, body=b""):
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/scan":
                return self._send(404)
            if (self.headers.get_all("Content-Type", []) != ["application/octet-stream"]
                    or "Transfer-Encoding" in self.headers or "Content-Encoding" in self.headers):
                return self._send(415)
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0]):
                return self._send(400)
            try:
                length = _validated_content_length(lengths[0], MAX_ATTACHMENT_BYTES)
            except OverflowError:
                return self._send(413)
            except ValueError:
                return self._send(400)
            if length == 0:
                return self._send(400)
            if not slots.acquire(blocking=False):
                return self._send(503)
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    return self._send(400)
                verdict = scanner(raw)
                if type(verdict) is not bool:
                    return self._send(503)
            except (OSError, ValueError):
                return self._send(503)
            finally:
                slots.release()
            return self._send(200, b"clean" if verdict else b"rejected")

    return _BoundedThreadingHTTPServer((host, port), Handler, max_connections=4, request_timeout=24)


def serve_county_scanner():
    if not os.environ.get("K_SERVICE"):
        raise ValueError("hosted county scanner requires Cloud Run invoker IAM")
    port = int(os.environ.get("PORT", "8080"))
    clamd_port = int(os.environ.get("WATCHTOWER_COUNTY_CLAMD_PORT", "3310"))
    with create_scanner_server(port, ClamdScanner(clamd_port)) as server:
        print("Watchtower county scanner ready")
        server.serve_forever()
