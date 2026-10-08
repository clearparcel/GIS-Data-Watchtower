"""Read-only public detail routes and HTTP representation handling."""
from __future__ import annotations
import gzip
import hashlib
import json
from urllib.parse import parse_qs

from .county_profile_panel import render_county_profile_body


def dispatch_public_details(handler, path: str, query: str, view: dict) -> bool:
    if path == "/api/summary":
        handler._send(200, json.dumps(view["summary"], separators=(",", ":"), ensure_ascii=False), "application/json; charset=utf-8")
        return True
    if path != "/api/county-profile":
        return False
    params = parse_qs(query)
    profile = view["profiles"].get(params.get("slug", [""])[0])
    if profile is None:
        handler._send(404, "County not found", "text/plain; charset=utf-8")
    elif params.get("revision", [""])[0] != view["summary"]["content_revision"]:
        handler._send(409, "Snapshot changed; refresh the summary", "text/plain; charset=utf-8")
    else:
        handler._send(200, render_county_profile_body(profile), "text/html; charset=utf-8")
    return True


def encode_response(status: int, raw: bytes, content_type: str, accept_encoding: str,
                    if_none_match: str | None) -> tuple[int, bytes, dict]:
    headers = {"Vary": "Accept-Encoding"}
    if status != 200 or not content_type.startswith(("text/html", "application/json")):
        return status, raw, headers
    etag = 'W/"' + hashlib.sha256(raw).hexdigest() + '"'
    headers["ETag"] = etag
    if if_none_match and (if_none_match.strip() == '*' or etag in [tag.strip() for tag in if_none_match.split(',')]):
        return 304, b'', headers
    encodings = {}
    for item in accept_encoding.lower().split(','):
        parts = item.strip().split(';')
        try:
            quality = next((float(p.strip()[2:]) for p in parts[1:] if p.strip().startswith('q=')), 1.0)
        except ValueError:
            quality = 0
        encodings[parts[0]] = quality
    if encodings.get('gzip', encodings.get('*', 0)) > 0 and len(raw) >= 1024:
        raw = gzip.compress(raw, mtime=0)
        headers['Content-Encoding'] = 'gzip'
    return status, raw, headers
