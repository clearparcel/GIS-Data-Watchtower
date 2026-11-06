"""Private county PDFs with durable, fail-closed scan state."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from zoneinfo import ZoneInfo

from .storage import StorageBackend, StorageConflictError

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
_MAX_HEADER = 2048
_CHICAGO = ZoneInfo("America/Chicago")
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.\-]{0,110}\.pdf", re.IGNORECASE)
_EVENT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


def _key(fips, attachment_id):
    if (not isinstance(fips, str) or not re.fullmatch(r"27[0-9]{3}", fips)
            or not isinstance(attachment_id, str) or not re.fullmatch(r"[a-f0-9]{32}", attachment_id)):
        raise ValueError("invalid county attachment identifier")
    return f"county-directory/v1/attachments/{fips}/{attachment_id}.bin"


def _read(path, fips, attachment_id, *, with_data):
    with path.open("rb") as stream:
        length = int.from_bytes(stream.read(4), "big")
        if not 0 < length <= _MAX_HEADER:
            raise ValueError("invalid county attachment metadata")
        meta = json.loads(stream.read(length))
        if (not isinstance(meta, dict) or meta.get("fips") != fips or meta.get("id") != attachment_id
                or meta.get("status") not in ("pending", "clean", "rejected")
                or not isinstance(meta.get("filename"), str) or not _FILENAME.fullmatch(meta["filename"])
                or type(meta.get("size")) is not int or not 0 < meta["size"] <= MAX_ATTACHMENT_BYTES
                or not isinstance(meta.get("sha256"), str)):
            raise ValueError("invalid county attachment metadata")
        data = stream.read(MAX_ATTACHMENT_BYTES + 1) if with_data else None
        if data is not None and (len(data) != meta["size"] or hashlib.sha256(data).hexdigest() != meta["sha256"]):
            raise ValueError("county attachment bytes failed verification")
    return meta, data


def _write(path, meta, data):
    header = json.dumps(meta, separators=(",", ":")).encode("ascii")
    with path.open("wb") as stream:
        stream.write(len(header).to_bytes(4, "big"))
        stream.write(header)
        stream.write(data)


def _event_time(value):
    if value in (None, ""):
        return
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}-0[56]:00", value):
        raise ValueError("correspondence time must include its Central time offset")
    timestamp = dt.datetime.fromisoformat(value)
    if timestamp.astimezone(_CHICAGO).isoformat(timespec="minutes") != value:
        raise ValueError("correspondence time is invalid in America/Chicago")


def draft_attachment_refs(draft):
    if not isinstance(draft, dict):
        raise ValueError("invalid county draft")
    policy = draft.get("policy", {})
    events = draft.get("correspondence", [])
    if not isinstance(policy, dict) or not isinstance(events, list):
        raise ValueError("invalid private county record")
    refs = []
    if policy.get("attachment_id") is not None:
        refs.append((policy["attachment_id"], "policy", None))
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("attachment_ids", []), list):
            raise ValueError("invalid correspondence event")
        _event_time(event.get("sent_at"))
        _event_time(event.get("reply_at"))
        refs.extend((attachment_id, "correspondence", event.get("id")) for attachment_id in event.get("attachment_ids", []))
    if len(refs) > 20:
        raise ValueError("county record has too many attachments")
    return refs


class CountyAttachments:
    def __init__(self, storage: StorageBackend):
        self._storage = storage

    def upload(self, fips, kind, event, filename, data, *, attachment_id=None):
        if (kind not in ("policy", "correspondence") or (kind == "policy" and event is not None)
                or (kind == "correspondence" and (not isinstance(event, str) or not _EVENT_ID.fullmatch(event)))):
            raise ValueError("invalid county attachment association")
        if not isinstance(filename, str) or not _FILENAME.fullmatch(filename):
            raise ValueError("invalid county PDF filename")
        if (not isinstance(data, bytes) or len(data) > MAX_ATTACHMENT_BYTES
                or not re.match(rb"%PDF-(?:1\.[0-9]|2\.0)[\r\n]", data) or not data.rstrip().endswith(b"%%EOF")):
            raise ValueError("invalid county PDF upload")
        attachment_id = uuid4().hex if attachment_id is None else attachment_id
        key = _key(fips, attachment_id)
        meta = {"id": attachment_id, "fips": fips, "kind": kind, "event_id": event, "filename": filename,
                "status": "pending", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "uploaded_at": dt.datetime.now(dt.UTC).isoformat()}
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "attachment.bin"
            _write(path, meta, data)
            try:
                self._storage.upload_if_version(key, path, None)
            except StorageConflictError:
                current = self.info(fips, attachment_id)
                if current is None or any(current[field] != meta[field] for field in
                                          ("kind", "event_id", "filename", "sha256", "size")):
                    raise ValueError("upload ID was already used for a different attachment") from None
                return current
        return meta

    def info(self, fips, attachment_id):
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "attachment.bin"
            if not self._storage.download(_key(fips, attachment_id), path):
                return None
            meta, _ = _read(path, fips, attachment_id, with_data=False)
            return meta

    def validate_refs(self, fips, refs):
        for attachment_id, kind, event in refs:
            meta = self.info(fips, attachment_id)
            if meta is None or meta["kind"] != kind or meta["event_id"] != event:
                raise ValueError("attachment does not match its county record")

    def scan(self, fips, attachment_id, scanner):
        """Set a verdict using a trusted scanner callable. Exceptions leave quarantine intact."""
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "attachment.bin"
            key = _key(fips, attachment_id)
            exists, version = self._storage.download_versioned(key, path)
            if not exists:
                return None
            if version is None:
                raise ValueError("county attachment has no storage version")
            meta, data = _read(path, fips, attachment_id, with_data=True)
            if meta["status"] == "pending":
                verdict = scanner(data)
                if type(verdict) is not bool:
                    raise ValueError("scanner returned no authoritative verdict")
                meta["status"] = "clean" if verdict else "rejected"
                meta["scanned_at"] = dt.datetime.now(dt.UTC).isoformat()
                _write(path, meta, data)
                self._storage.upload_if_version(key, path, version)
            return meta

    def download(self, fips, attachment_id):
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "attachment.bin"
            if not self._storage.download(_key(fips, attachment_id), path):
                return None
            meta, _ = _read(path, fips, attachment_id, with_data=False)
            return _read(path, fips, attachment_id, with_data=True) if meta["status"] == "clean" else None
