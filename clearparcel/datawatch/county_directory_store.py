"""Durable private saves and explicit publication of county directory content."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from .county_directory import project_public_county
from .storage import StorageBackend, StorageConflictError

_DIRECTORY = "county-directory/v1/directory.json"
_VERSION = 1
_RECEIPT_LIMIT = 128
_PUBLICATION_ATTEMPTS = 5


class CountyRevisionConflict(ValueError):
    """The editor's expected private revision is no longer current."""


@dataclass(frozen=True)
class PrivateCounty:
    revision: int
    draft: dict | None


@dataclass(frozen=True)
class CountySave:
    revision: int
    publication_revision: int | None


@dataclass(frozen=True)
class PublicationStatus:
    target_revision: int
    published_revision: int

    @property
    def confirmed(self) -> bool:
        return self.target_revision > 0 and self.target_revision == self.published_revision


def _encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def _read(storage: StorageBackend, key: str, path: Path, default: dict) -> tuple[dict, str | int | None]:
    exists, version = storage.download_versioned(key, path)
    if not exists:
        return default, None
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != _VERSION:
        raise ValueError("invalid county storage schema")
    if version is None:
        raise ValueError("county storage did not return an object version")
    return value, version


def _write(storage: StorageBackend, key: str, path: Path, version: str | int | None, value: dict) -> None:
    path.write_bytes(_encoded(value))
    storage.upload_if_version(key, path, version)


def _private_key(county: dict) -> str:
    fips = county.get("fips")
    if not isinstance(fips, str) or not re.fullmatch(r"27[0-9]{3}", fips):
        raise ValueError("invalid Minnesota county FIPS")
    return f"county-directory/v1/records/{fips}.json"


def _read_directory(storage: StorageBackend, path: Path) -> tuple[dict, str | int | None]:
    document, version = _read(storage, _DIRECTORY, path, {"schema_version": _VERSION, "counties": {}})
    counties = document.get("counties")
    if not isinstance(counties, dict):
        raise ValueError("invalid stored county directory")
    for fips, entry in counties.items():
        if (
            not isinstance(entry, dict) or type(entry.get("public_revision")) is not int
            or entry["public_revision"] <= 0 or not isinstance(entry.get("published_at"), str)
        ):
            raise ValueError("invalid stored public county revision")
        content = {key: value for key, value in entry.items() if key not in ("public_revision", "published_at")}
        try:
            county = entry["county"]
            if (not isinstance(county, dict) or not all(isinstance(county.get(key), str) for key in ("fips", "slug", "name"))
                    or not re.fullmatch(r"27[0-9]{3}", fips)
                    or content != project_public_county(county, {**content, "fips": fips})):
                raise ValueError
        except (KeyError, ValueError):
            raise ValueError("invalid stored public county content") from None
    return counties, version


def read_public_directory(storage: StorageBackend) -> dict:
    """Read one directory snapshot using only the public storage backend."""
    with TemporaryDirectory() as scratch:
        counties, _ = _read_directory(storage, Path(scratch) / "directory.json")
        return counties


def _publication_status(record: dict, entry: dict | None) -> PublicationStatus:
    target = record["public_revision"]
    if entry is None:
        return PublicationStatus(target, 0)
    published = entry["public_revision"]
    if published == target:
        content = {key: value for key, value in entry.items() if key not in ("public_revision", "published_at")}
        if _fingerprint(content) != record["public_fingerprint"]:
            raise ValueError("stored public county content does not match its revision")
    return PublicationStatus(target, published)


class CountyDirectoryStore:
    """Storage operations for a server-resolved county, with no HTTP or polling."""

    def __init__(self, private: StorageBackend, public: StorageBackend):
        private_identity = private.object_identity(_DIRECTORY)
        if private is public or (private_identity is not None and private_identity == public.object_identity(_DIRECTORY)):
            raise ValueError("private records and public directory require separate storage namespaces")
        self._private = private
        self._public = public

    def _read_private(self, key: str, path: Path) -> tuple[dict, str | int | None]:
        record, version = _read(self._private, key, path, {
            "schema_version": _VERSION, "revision": 0, "draft": None,
            "public_revision": 0, "public_fingerprint": None, "requests": {},
        })
        if version is not None and (
            type(record.get("revision")) is not int or type(record.get("public_revision")) is not int
            or not 0 < record["public_revision"] <= record["revision"]
            or not isinstance(record.get("public_fingerprint"), str)
            or not isinstance(record.get("draft"), dict) or not isinstance(record.get("requests"), dict)
        ):
            raise ValueError("invalid stored private county record")
        return record, version

    def read_private(self, county: dict) -> PrivateCounty:
        with TemporaryDirectory() as scratch:
            record, _ = self._read_private(_private_key(county), Path(scratch) / "county.json")
            return PrivateCounty(record["revision"], record["draft"])

    @staticmethod
    def _replay(record: dict, request_id: str, fingerprint: str) -> CountySave | None:
        receipt = record["requests"].get(request_id)
        if receipt is None:
            return None
        if receipt["fingerprint"] != fingerprint:
            raise ValueError("request ID was already used for a different county save")
        return CountySave(receipt["revision"], receipt["publication_revision"])

    def save(self, county: dict, draft: dict, *, expected_revision: int, request_id: str, before_save=None,
             actor: str = "operator:direct-storage") -> CountySave:
        key = _private_key(county)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected revision must be a nonnegative integer")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
            raise ValueError("invalid county save request ID")
        if not isinstance(draft, dict):
            raise ValueError("county draft must be an object")
        if not isinstance(actor, str) or not 0 < len(actor) <= 256 or any(ord(c) < 32 for c in actor):
            raise ValueError("invalid county save actor")
        try:
            request_fingerprint = _fingerprint([expected_revision, draft])
        except (TypeError, ValueError, RecursionError):
            raise ValueError("county draft must contain JSON values") from None

        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "county.json"
            record, version = self._read_private(key, path)
            if receipt := self._replay(record, request_id, request_fingerprint):
                return receipt
            if expected_revision != record["revision"]:
                raise CountyRevisionConflict("county changed since the editor read it")

            public_fingerprint = _fingerprint(project_public_county(county, draft))
            public_changed = public_fingerprint != record["public_fingerprint"]
            target = record["public_revision"] + int(public_changed)
            revision = expected_revision + 1
            publication_revision = target if public_changed else None
            requests = record["requests"]
            requests[request_id] = {
                "fingerprint": request_fingerprint, "revision": revision, "publication_revision": publication_revision,
            }
            now = dt.datetime.now(dt.UTC)
            cutoff = (now - dt.timedelta(days=365)).isoformat()
            events = record.get("audit_events", [])
            if not isinstance(events, list) or not all(isinstance(event, dict) and isinstance(event.get("at"), str) for event in events):
                raise ValueError("invalid county audit history")
            events = [event for event in events if event["at"] >= cutoff]
            if len(events) >= 10000:
                raise ValueError("county audit history requires operator archival")
            events.append({"actor": actor, "at": now.isoformat(), "county": county["fips"],
                           "request_id": request_id, "prior_revision": expected_revision,
                           "revision": revision, "operation": "save"})
            if len(requests) > _RECEIPT_LIMIT:
                oldest = min(requests, key=lambda request: requests[request]["revision"])
                del requests[oldest]
            updated = {
                "schema_version": _VERSION, "revision": revision, "draft": draft, "public_revision": target,
                "public_fingerprint": public_fingerprint, "requests": requests,
                # The event and edit share one CAS: neither can commit alone.
                "audit_events": events,
            }
            if before_save is not None:
                before_save(revision)
            try:
                _write(self._private, key, path, version, updated)
            except StorageConflictError:
                current, _ = self._read_private(key, path)
                if receipt := self._replay(current, request_id, request_fingerprint):
                    return receipt
                raise CountyRevisionConflict("county changed while saving") from None
            return CountySave(revision, publication_revision)

    def publication_status(self, county: dict) -> PublicationStatus:
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "county.json"
            record, _ = self._read_private(_private_key(county), path)
            directory, _ = _read_directory(self._public, path)
            return _publication_status(record, directory.get(county["fips"]))

    def publish(self, county: dict) -> PublicationStatus:
        key = _private_key(county)
        fips = county["fips"]
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "county.json"
            for attempt in range(_PUBLICATION_ATTEMPTS):
                record, _ = self._read_private(key, path)
                directory, version = _read_directory(self._public, path)
                status = _publication_status(record, directory.get(fips))
                if status.published_revision >= status.target_revision:
                    return status

                content = project_public_county(county, record["draft"])
                if _fingerprint(content) != record["public_fingerprint"]:
                    raise ValueError("private county content does not match its publication intent")
                directory[fips] = {
                    **content,
                    "public_revision": status.target_revision,
                    "published_at": dt.datetime.now(dt.UTC).isoformat(),
                }
                try:
                    _write(self._public, _DIRECTORY, path, version, {"schema_version": _VERSION, "counties": directory})
                except StorageConflictError:
                    if attempt + 1 == _PUBLICATION_ATTEMPTS:
                        raise
                    continue
                current, _ = _read_directory(self._public, path)
                return _publication_status(record, current.get(fips))
