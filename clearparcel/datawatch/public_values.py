"""Shared public classifications and conservative, offline link validation."""
from __future__ import annotations

import ipaddress
import datetime as dt
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
