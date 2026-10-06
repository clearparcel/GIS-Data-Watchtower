"""Shared public classifications and conservative, offline link validation."""
from __future__ import annotations

import ipaddress
import datetime as dt
from email.utils import parsedate_to_datetime
import re
from urllib.parse import parse_qsl, urlsplit


def provider_edit_timestamp(value: object) -> str | None:
    """Validate ArcGIS epoch milliseconds without coercing strings or booleans."""
    if type(value) is not int or not 0 <= value <= 253402300799999:
        return None
    try:
        return (dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(milliseconds=value)).isoformat()
    except (OverflowError, ValueError):
        return None


def spreadsheet_cell(value: object) -> str:
    text = '' if value is None else str(value)
    start = 0
    while start < len(text) and (text[start].isspace() or ord(text[start]) < 32 or text[start] == '\ufeff'):
        start += 1
    candidate = text[start:]
    return "'" + text if candidate.startswith(('=', '+', '-', '@')) else text


def safe_public_url(value: object) -> str | None:
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        parsed.port  # Reject malformed ports.
        if parsed.scheme not in {"https", "http"} or not host or parsed.username is not None or parsed.password is not None:
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid")):
                return None
            if host == "localhost" or not re.fullmatch(r"[a-z0-9.-]+", host):
                return None
            # Browser-compatible numeric host forms can resolve to loopback.
            if all(part.isdigit() or part.startswith("0x") for part in host.split(".")):
                return None
        else:
            if not address.is_global:
                return None
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if any(word in normalized for word in ("token", "password", "secret", "credential", "apikey", "accesskey", "signature")) or normalized in {"key", "auth", "authorization", "sig", "username"}:
                return None
    except (ValueError, UnicodeError):
        return None
    return value


def public_access_classification(record: dict | None) -> str:
    if not record or record.get("research_complete") is not True:
        return "AMBIGUOUS"
    classification = record.get("county_direct_classification")
    if classification == "fee-based-parcel-data":
        return "FEE BASED"
    if classification == "free-parcel-data" and record.get("usable_direct_machine_readable_source") is True:
        return "OPEN"
    return "AMBIGUOUS"


def _metadata_text(value: object, limit: int = 512) -> str | None:
    if isinstance(value, str) and 0 < len(value) <= limit and all(ord(c) >= 32 and ord(c) != 127 for c in value):
        return value
    return None


def _metadata_date(value: object, *, http: bool = False) -> str | None:
    text = _metadata_text(value, 80)
    if text is None:
        return None
    try:
        stamp = parsedate_to_datetime(text) if http else dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.year < 1970:
            return None
        return stamp.astimezone(dt.timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def safe_geometry_type(value: object) -> str | None:
    """Accept only recognized ArcGIS geometry scalars."""
    if isinstance(value, str) and value in ('esriGeometryPoint', 'esriGeometryMultipoint',
            'esriGeometryPolyline', 'esriGeometryPolygon', 'esriGeometryEnvelope'):
        return value
    return None


def safe_file_type(value: object) -> str | None:
    """Validate a MIME scalar shared by evidence and live metadata."""
    mime = _metadata_text(value, 128)
    if mime and re.fullmatch(r'[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:;[ A-Za-z0-9=._+-]+)?', mime):
        return mime
    return None


def sanitize_source_metadata(source: dict) -> dict:
    """Extract typed scalar facts, never copy raw provider dictionaries."""
    normalized = source.get('public_metadata')
    normalized = normalized if isinstance(normalized, dict) else {}
    public = {}
    adapter = source.get('adapter', normalized.get('adapter'))
    if adapter in ('arcgis_layer', 'arcgis_service', 'arcgis_image', 'http_file', 'wms', 'wfs', 'sda_query', 'arcgis_county_catalog'):
        public['adapter'] = adapter
    geometry = safe_geometry_type(source.get('geometry_type', normalized.get('geometry_type')))
    if geometry:
        public['geometry_type'] = geometry
    editing = source.get('editing_info')
    stamp = provider_edit_timestamp(editing.get('lastEditDate')) if isinstance(editing, dict) else None
    stamp = stamp or _metadata_date(normalized.get('provider_updated_at'))
    if stamp:
        public['provider_updated_at'] = stamp
    tracked = source.get('tracked_values')
    tracked = tracked if isinstance(tracked, dict) else {}
    file = normalized.get('file')
    file = file if isinstance(file, dict) else {}
    safe_file = {}
    mime = safe_file_type(source.get('content_type', file.get('type')))
    if mime:
        safe_file['type'] = mime
    size = tracked.get('content_length', file.get('size_bytes'))
    if isinstance(size, str) and re.fullmatch(r'[0-9]{1,19}', size):
        size = int(size)
    if type(size) is int and 0 <= size <= 2**63 - 1:
        safe_file['size_bytes'] = size
    etag = _metadata_text(tracked.get('etag', file.get('etag')))
    if etag and re.fullmatch(r'(?:W/)?"[\x21\x23-\x7e]*"', etag):
        safe_file['etag'] = etag
    modified = _metadata_date(tracked.get('last_modified'), http=True) if 'last_modified' in tracked else _metadata_date(file.get('last_modified'))
    if modified:
        safe_file['last_modified'] = modified
    if safe_file:
        public['file'] = safe_file
    return public
