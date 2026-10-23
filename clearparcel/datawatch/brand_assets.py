"""Packaged brand images: embedded for offline exports, hosted for the live site.

Hosted pages reference content-hashed URLs so browsers cache each image once
(immutable) instead of re-downloading base64 copies inside every HTML response.
Only the fixed asset map below is served; no request path reaches the filesystem.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from pathlib import Path

ASSET_PREFIX = "/assets/"
_ASSETS = {
    "clearparcel-logo": ("clearparcel-logo-transparent.png", "image/png"),
    "watchtower-logo": ("watchtower-logo.webp", "image/webp"),
    "favicon-16": ("favicon-16.png", "image/png"),
    "favicon-32": ("favicon-32.png", "image/png"),
}
_IMMUTABLE = "public, max-age=31536000, immutable"


@lru_cache(maxsize=None)
def asset_bytes(key: str) -> bytes:
    filename, _ = _ASSETS[key]
    return Path(__file__).with_name(filename).read_bytes()


def asset_data_uri(key: str) -> str:
    return f"data:{_ASSETS[key][1]};base64," + base64.b64encode(asset_bytes(key)).decode("ascii")


@lru_cache(maxsize=None)
def asset_url(key: str) -> str:
    filename, _ = _ASSETS[key]
    digest = hashlib.sha256(asset_bytes(key)).hexdigest()[:12]
    return f"{ASSET_PREFIX}{key}-{digest}{Path(filename).suffix}"


def asset_src(key: str, *, hosted: bool) -> str:
    return asset_url(key) if hosted else asset_data_uri(key)


@lru_cache(maxsize=None)
def _routes() -> dict[str, str]:
    return {asset_url(key): key for key in _ASSETS}


def favicon_html(*, hosted: bool = False) -> str:
    return "".join(
        f'<link rel="icon" type="image/png" sizes="{size}x{size}" href="{asset_src(f"favicon-{size}", hosted=hosted)}">'
        for size in (16, 32)
    )


def dispatch_brand_asset(handler, path: str) -> bool:
    """Serve an exact hosted asset URL; any other /assets/ path is a 404."""
    if not path.startswith(ASSET_PREFIX):
        return False
    key = _routes().get(path)
    if key is None:
        raw = b"Not found"
        handler.send_response(404)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.end_headers()
        if handler.command != "HEAD":
            handler.wfile.write(raw)
        return True
    raw = asset_bytes(key)
    etag = '"' + path.rsplit("-", 1)[1].split(".", 1)[0] + '"'
    not_modified = etag in {tag.strip() for tag in (handler.headers.get("If-None-Match") or "").split(",")}
    handler.send_response(304 if not_modified else 200)
    handler.send_header("Content-Type", _ASSETS[key][1])
    if not not_modified:
        handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", _IMMUTABLE)
    handler.send_header("ETag", etag)
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
    handler.end_headers()
    if handler.command != "HEAD" and not not_modified:
        handler.wfile.write(raw)
    return True
