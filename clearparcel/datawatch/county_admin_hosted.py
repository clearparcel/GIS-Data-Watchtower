"""Cloud Run county administration with signed IAP identity verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

_ISSUER = "https://cloud.google.com/iap"
_KEYS = "https://www.gstatic.com/iap/verify/public_key"
_AUDIENCE = re.compile(r"/projects/[0-9]+/(?:locations/[a-z0-9-]+/services/[a-z0-9-]+|global/backendServices/[0-9]+)")
_SUBJECT = re.compile(r"[A-Za-z0-9._:@-]{1,200}")
_BUCKET = re.compile(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]")


class IapVerifier:
    """Verify ES256 using Google's IAP keys, with bounded certificate fetches."""

    def __init__(self):
        self._certs = {}
        self._expires = 0.0
        self._lock = threading.Lock()

    def __call__(self, assertion, audience):
        from google.auth import jwt

        header = jwt.decode_header(assertion)
        if header.get("alg") != "ES256" or not isinstance(header.get("kid"), str):
            raise ValueError("invalid IAP token header")
        with self._lock:
            now = time.monotonic()
            if now >= self._expires:
                with urlopen(_KEYS, timeout=4) as response:
                    raw = response.read(65_537)
                if len(raw) > 65_536:
                    raise OSError("IAP key response exceeded its limit")
                try:
                    keys = json.loads(raw)
                except ValueError:
                    raise OSError("invalid IAP key response") from None
                if not isinstance(keys, dict) or not keys or not all(isinstance(value, str) for value in keys.values()):
                    raise OSError("invalid IAP key response")
                self._certs, self._expires = keys, now + 300
            certs = self._certs
        claims = jwt.decode(assertion, certs=certs, audience=audience, clock_skew_in_seconds=30)
        if (type(claims.get("iat")) is not int or type(claims.get("exp")) is not int
                or not 0 < claims["exp"] - claims["iat"] <= 660 or claims.get("aud") != audience):
            raise ValueError("invalid IAP token claims")
        return claims


class IapAdminAuth:
    def __init__(self, origin, audience, subjects, csrf_secret, *, verify=None):
        parsed = urlsplit(origin)
        if (not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", parsed.netloc)
                or origin != "https://" + parsed.netloc):
            raise ValueError("county admin origin must be an exact HTTPS origin")
        if not _AUDIENCE.fullmatch(audience):
            raise ValueError("county admin requires an exact IAP service audience")
        if not subjects or not all(_SUBJECT.fullmatch(subject) for subject in subjects):
            raise ValueError("county admin requires an explicit IAP subject allowlist")
        if not isinstance(csrf_secret, bytes) or len(csrf_secret) != 32:
            raise ValueError("county admin requires a 32-byte CSRF secret")
        self.origin = origin
        self.host = parsed.netloc
        self._audience = audience
        self._subjects = frozenset(subjects)
        self._secret = csrf_secret
        self._verify = IapVerifier() if verify is None else verify

    def authorize(self, assertion):
        if not isinstance(assertion, str) or not 0 < len(assertion) <= 8192:
            return None
        try:
            claims = self._verify(assertion, self._audience)
        except ValueError:
            return None
        subject = claims.get("sub")
        if claims.get("iss") != _ISSUER or not isinstance(subject, str) or subject not in self._subjects:
            return None
        return hmac.new(self._secret, ("watchtower-county-admin-v1\0" + self.origin + "\0" + subject).encode(),
                        hashlib.sha256).hexdigest()


def hosted_storage_settings(environ):
    if not environ.get("K_SERVICE"):
        raise ValueError("hosted county administration requires Cloud Run")
    private = environ.get("WATCHTOWER_COUNTY_PRIVATE_BUCKET", "")
    public = environ.get("WATCHTOWER_COUNTY_PUBLIC_BUCKET", "")
    if not _BUCKET.fullmatch(private) or not _BUCKET.fullmatch(public) or private == public:
        raise ValueError("hosted county administration requires separate private and public buckets")
    return private, public


def hosted_public_county_bucket(environ):
    bucket = environ.get("WATCHTOWER_COUNTY_PUBLIC_BUCKET")
    if bucket is None:
        return None
    if not environ.get("K_SERVICE") or not _BUCKET.fullmatch(bucket):
        raise ValueError("hosted county directory reading requires an explicit Cloud Run public bucket")
    return bucket


def serve_hosted_county_admin():
    from google.api_core.exceptions import GoogleAPICallError
    from google.auth.exceptions import GoogleAuthError

    from .county_admin import create_county_admin_server
    from .county_attachments import CountyAttachments
    from .county_directory_store import CountyDirectoryStore
    from .county_scanner_service import RunScannerClient
    from .storage import GCSStorage

    env = os.environ
    private_bucket, public_bucket = hosted_storage_settings(env)
    try:
        secret = base64.b64decode(env.get("WATCHTOWER_COUNTY_ADMIN_CSRF_SECRET", ""), altchars=b"-_", validate=True)
    except ValueError:
        raise ValueError("county admin CSRF secret must be base64 encoded") from None
    auth = IapAdminAuth(env.get("WATCHTOWER_COUNTY_ADMIN_ORIGIN", ""), env.get("WATCHTOWER_COUNTY_ADMIN_IAP_AUDIENCE", ""),
                        {item.strip() for item in env.get("WATCHTOWER_COUNTY_ADMIN_SUBJECTS", "").split(",") if item.strip()},
                        secret)
    private = GCSStorage(private_bucket)
    store = CountyDirectoryStore(private, GCSStorage(public_bucket))
    scanner = RunScannerClient(env.get("WATCHTOWER_COUNTY_SCANNER_URL", ""))
    with create_county_admin_server(
        store, port=int(env.get("PORT", "8080")), hosted_auth=auth, attachments=CountyAttachments(private),
        scanner=scanner, backend_errors=(GoogleAPICallError, GoogleAuthError),
    ) as server:
        print("Watchtower hosted county administration ready")
        server.serve_forever()
