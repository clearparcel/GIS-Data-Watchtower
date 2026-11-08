"""Private, permission-gated county source enrollments for regular checks."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from .county_profiles import county_identities
from .parcel_access import load_parcel_access
from .public_values import safe_public_url
from .storage import StorageBackend, StorageConflictError

_OBJECT = "county-directory/v1/monitoring/sources.json"
_SCHEMA_VERSION = 1
_ATTEMPTS = 5
_PROFILES = frozenset({"cloud", "local"})
_DATASETS = {
    "parcel_polygons": ("Parcels", "parcel boundaries"),
    "road_centerlines": ("Roads", "road centerlines"),
    "address_points": ("Address Points", "address locations"),
}
_FILE_SUFFIXES = frozenset({".zip", ".gpkg", ".geojson", ".json", ".csv"})


def _date(value: object) -> bool:
    try:
        return isinstance(value, str) and dt.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _read(storage: StorageBackend, path: Path) -> tuple[dict, str | int | None]:
    exists, version = storage.download_versioned(_OBJECT, path)
    if not exists:
        return {"schema_version": _SCHEMA_VERSION, "counties": {}}, None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("invalid county monitoring registry") from None
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value["schema_version"] != _SCHEMA_VERSION or not isinstance(value.get("counties"), dict)
            or version is None):
        raise ValueError("invalid county monitoring registry")
    return value, version


def _write(storage: StorageBackend, path: Path, version: str | int | None, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    storage.upload_if_version(_OBJECT, path, version)


def _monitoring_options(value: object) -> dict:
    if not isinstance(value, dict) or value.get("enabled") is not True:
        raise ValueError("regular checks need explicit review and county permission")
    profile = value.get("execution_profile")
    if not isinstance(profile, str) or profile not in _PROFILES:
        raise ValueError("choose a monitoring worker")
    terms_url = safe_public_url(value.get("terms_url"))
    if not terms_url or not _date(value.get("terms_reviewed_on")):
        raise ValueError("record the public terms link and review date")
    if value.get("terms_confirmed") is not True:
        raise ValueError("confirm that the reviewed terms allow this regular check")
    permission = value.get("county_permission")
    if not isinstance(permission, dict) or permission.get("reply") != "permitted":
        raise ValueError("record the county's affirmative permission")
    if permission.get("scope") != "details-and-count" or not _date(permission.get("received_on")):
        raise ValueError("record permission for service details and one record count")
    reference = permission.get("reference")
    if (not isinstance(reference, str) or not reference.strip() or len(reference) > 240
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in reference)):
        raise ValueError("add a private reference to the county's permission")
    raw_evidence_url = permission.get("evidence_url")
    evidence_url = safe_public_url(raw_evidence_url)
    if raw_evidence_url and not evidence_url:
        raise ValueError("use a public permission link without credentials")
    return {
        "status": "approved",
        "scope": "details-and-count",
        "execution_profile": profile,
        "terms_url": terms_url,
        "terms_reviewed_on": value["terms_reviewed_on"],
        "county_permission": {
            "reply": "permitted",
            "scope": "details-and-count",
            "received_on": permission["received_on"],
            "reference": reference.strip(),
            "evidence_url": evidence_url,
        },
    }


def _source_kind(method: dict) -> tuple[str, str]:
    kind = method.get("kind")
    url = safe_public_url(method.get("url"))
    if not url:
        raise ValueError("regular checks require a public http or https data link")
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    if kind == "direct_rest":
        match = re.search(r"/rest/services/.+/(?:FeatureServer|MapServer)/([0-9]+)$", path, re.IGNORECASE)
        if not match:
            raise ValueError("use a direct ArcGIS REST layer link ending in a layer number")
        if any(key.lower() != "f" or value.lower() not in {"json", "pjson"}
               for key, value in parse_qsl(parsed.query, keep_blank_values=True)):
            raise ValueError("use an unfiltered direct ArcGIS REST layer link")
        # Browser links commonly carry ?f=pjson. Count requests append /query
        # to the layer endpoint, so presentation parameters cannot travel with it.
        return "arcgis_layer", urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    if kind == "direct_download":
        if Path(path).suffix.lower() not in _FILE_SUFFIXES:
            raise ValueError("use a direct download link to a supported data file")
        return "http_file", url
    raise ValueError("regular checks support direct GIS service and data file links")


def build_county_monitoring_sources(county: dict, draft: object) -> list[dict]:
    """Build bounded source records from a private draft; never from public URL input alone."""
    if not isinstance(draft, dict) or draft.get("fips") != county.get("fips"):
        raise ValueError("monitoring record does not match the selected county")
    access = draft.get("access", {})
    if not isinstance(access, dict):
        raise ValueError("county data access is invalid")
    enabled = []
    for dataset in _DATASETS:
        record = access.get(dataset)
        if not isinstance(record, dict):
            continue
        methods = record.get("methods", [])
        if not isinstance(methods, list):
            raise ValueError("county data access methods are invalid")
        enabled.extend((dataset, record, method) for method in methods
                       if isinstance(method, dict) and isinstance(method.get("monitoring"), dict)
                       and method["monitoring"].get("enabled") is True)
    if not enabled:
        return []
    research = load_parcel_access().get(county.get("name"), {})
    county_decision = (research.get("monitoring") or {}).get("decision")
    if (any(dataset == "parcel_polygons" for dataset, _record, _method in enabled)
            and county_decision in {"hold-for-terms", "not-appropriate"}):
        raise ValueError("this county's current monitoring decision does not allow new direct checks")
    monitoring = research.get("monitoring") or {}
    if monitoring.get("stop_requested") is True or monitoring.get("reply") in {"declined", "stop"}:
        raise ValueError("the county asked Watchtower not to check its direct sources")

    sources, seen_urls = [], set()
    for dataset, record, method in enabled:
        category, label = _DATASETS[dataset]
        options = method["monitoring"]
        if record.get("classification") != "open":
            raise ValueError("only open data sources can be included in regular checks")
        restrictions = record.get("restrictions") or {}
        if not isinstance(restrictions, dict) or restrictions.get("status") != "reviewed_none":
            raise ValueError("review this dataset's use restrictions before enabling checks")
        adapter, url = _source_kind(method)
        identity = (dataset, url)
        if identity in seen_urls:
            raise ValueError("the same direct source is listed more than once")
        seen_urls.add(identity)
        approval = _monitoring_options(options)
        digest = hashlib.sha256(f"{county['slug']}\0{dataset}\0{url}".encode("utf-8")).hexdigest()[:16]
        source = {
            "id": f"county-{county['slug']}-{digest}",
            "name": f"{county['name']} County {label}",
            "provider": f"{county['name']} County",
            "category": category,
            "kind": adapter,
            "url": url,
            "county_slug": county["slug"],
            "execution_profiles": [approval["execution_profile"]],
            "monitoring_approval": approval,
        }
        if adapter == "arcgis_layer":
            source["count"] = True
        sources.append(source)
    return sources


def _validate_source(source: object, slug: str) -> dict:
    if not isinstance(source, dict):
        raise ValueError("invalid county monitoring source")
    required = {"id", "name", "provider", "category", "kind", "url", "county_slug", "execution_profiles", "monitoring_approval"}
    if not required <= set(source) <= required | {"count"}:
        raise ValueError("invalid county monitoring source")
    if (source.get("county_slug") != slug or not isinstance(source.get("kind"), str)
            or source["kind"] not in {"arcgis_layer", "http_file"}
            or not isinstance(source.get("category"), str)
            or source["category"] not in {entry[0] for entry in _DATASETS.values()}):
        raise ValueError("invalid county monitoring source")
    if not safe_public_url(source.get("url")) or source.get("execution_profiles") not in (["cloud"], ["local"]):
        raise ValueError("invalid county monitoring source")
    approval = source.get("monitoring_approval")
    if (not isinstance(approval, dict)
            or set(approval) != {"status", "scope", "execution_profile", "terms_url", "terms_reviewed_on", "county_permission"}
            or approval.get("status") != "approved" or approval.get("scope") != "details-and-count"
            or not isinstance(approval.get("execution_profile"), str) or approval["execution_profile"] not in _PROFILES
            or source["execution_profiles"] != [approval["execution_profile"]]
            or not safe_public_url(approval.get("terms_url")) or not _date(approval.get("terms_reviewed_on"))):
        raise ValueError("invalid county monitoring approval")
    permission = approval.get("county_permission")
    if (not isinstance(permission, dict)
            or set(permission) != {"reply", "scope", "received_on", "reference", "evidence_url"}
            or permission.get("reply") != "permitted" or permission.get("scope") != "details-and-count"
            or not _date(permission.get("received_on"))
            or not isinstance(permission.get("reference"), str) or not permission["reference"].strip()
            or len(permission["reference"]) > 240
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in permission["reference"])
            or permission.get("evidence_url") is not None and not safe_public_url(permission["evidence_url"])):
        raise ValueError("invalid county monitoring permission record")
    direct_kind = "direct_rest" if source["kind"] == "arcgis_layer" else "direct_download"
    adapter, validated_url = _source_kind({"kind": direct_kind, "url": source["url"]})
    if adapter != source["kind"] or validated_url != source["url"]:
        raise ValueError("invalid county monitoring endpoint")
    if source["kind"] == "arcgis_layer" and source.get("count") is not True:
        raise ValueError("ArcGIS monitoring must include one record count")
    if source["kind"] == "http_file" and "count" in source:
        raise ValueError("file monitoring cannot query a record count")
    if not re.fullmatch(r"county-[a-z0-9-]+-[0-9a-f]{16}", str(source.get("id"))):
        raise ValueError("invalid county monitoring source ID")
    return source


class CountyMonitoringStore:
    """Separate private source registry; provider workers need only read this object."""

    def __init__(self, storage: StorageBackend):
        self._storage = storage

    def prepare_removals(self, county: dict, draft: object, *, revision: int) -> None:
        """Remove old/changed checks before accepting a private save; never add here."""
        if type(revision) is not int or revision < 1:
            raise ValueError("county monitoring requires a saved private revision")
        desired = build_county_monitoring_sources(county, draft)
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "sources.json"
            for attempt in range(_ATTEMPTS):
                manifest, version = _read(self._storage, path)
                counties = manifest["counties"]
                _validate_counties(counties)
                previous = counties.get(county["slug"])
                if previous is None or previous["revision"] >= revision:
                    return
                retained = [source for source in previous["sources"] if source in desired]
                if retained == previous["sources"]:
                    return
                counties[county["slug"]] = {"revision": revision, "sources": retained, "pending": True}
                try:
                    _write(self._storage, path, version, manifest)
                    return
                except StorageConflictError:
                    if attempt + 1 == _ATTEMPTS:
                        raise

    def replace_county(self, county: dict, draft: object, *, revision: int) -> int:
        if type(revision) is not int or revision < 1:
            raise ValueError("county monitoring requires a saved private revision")
        sources = build_county_monitoring_sources(county, draft)
        for source in sources:
            _validate_source(source, county["slug"])
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "sources.json"
            for attempt in range(_ATTEMPTS):
                manifest, version = _read(self._storage, path)
                counties = dict(manifest["counties"])
                _validate_counties(counties)
                existing = counties.get(county["slug"], {})
                if existing.get("revision", 0) > revision:
                    if existing.get("pending"):
                        raise StorageConflictError("county monitoring removal awaits a saved revision")
                    return len(existing["sources"])
                if existing.get("revision") == revision and not existing.get("pending"):
                    if existing["sources"] != sources:
                        raise ValueError("county monitoring revision has different content")
                    return len(sources)
                # Retain an empty entry as a revisioned removal. A delayed
                # publisher cannot reinstate an older enrollment after a stop.
                counties[county["slug"]] = {"revision": revision, "sources": sources}
                updated = {"schema_version": _SCHEMA_VERSION, "counties": counties}
                try:
                    _write(self._storage, path, version, updated)
                    return len(sources)
                except StorageConflictError:
                    if attempt + 1 == _ATTEMPTS:
                        raise
        raise StorageConflictError("county monitoring registry changed repeatedly")

    def read_registry(self) -> tuple[list[dict], dict]:
        with TemporaryDirectory() as scratch:
            manifest, version = _read(self._storage, Path(scratch) / "sources.json")
        if version is None:
            raise ValueError("county monitoring registry is not initialized")
        counties = manifest["counties"]
        _validate_counties(counties)
        return ([{**source, "_county_monitoring_revision": record["revision"]}
                 for record in counties.values() for source in record["sources"]],
                {slug: record["revision"] for slug, record in counties.items()})

    def read_sources(self) -> list[dict]:
        return self.read_registry()[0]


def _validate_counties(counties: dict) -> None:
    identities = county_identities()
    seen = set()
    for slug, record in counties.items():
        if (slug not in identities or not isinstance(record, dict)
                or not {"revision", "sources"} <= set(record) <= {"revision", "sources", "pending"}
                or type(record["revision"]) is not int or record["revision"] < 1
                or not isinstance(record["sources"], list)
                or "pending" in record and record["pending"] is not True):
            raise ValueError("invalid county monitoring registry")
        for item in record["sources"]:
            source = _validate_source(item, slug)
            if source["id"].casefold() in seen:
                raise ValueError("duplicate county monitoring source ID")
            seen.add(source["id"].casefold())
