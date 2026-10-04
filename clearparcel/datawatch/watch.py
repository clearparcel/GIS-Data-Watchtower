from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tracemalloc
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

class ProviderRateLimitError(RuntimeError):
    """Provider explicitly asked the client to slow down."""

    def __init__(self, retry_after: str | None = None):
        self.retry_after = retry_after
        super().__init__(f"provider rate limit (HTTP 429); retry-after={retry_after or 'unspecified'}")


USER_AGENT = "GIS-Data-Watchtower/0.1 (+https://github.com/clearparcel/GIS-Data-Watchtower)"

def load_config(path: str | Path) -> dict:
    config_path = Path(path).expanduser().resolve()
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    root = Path(os.environ.get("CLEARPARCEL_WATCHTOWER_ROOT") or config_path.parent.parent).expanduser().resolve()
    overrides = {
        "state_file": "CLEARPARCEL_WATCHTOWER_STATE_FILE",
        "history_file": "CLEARPARCEL_WATCHTOWER_HISTORY_FILE",
        "alerts_file": "CLEARPARCEL_WATCHTOWER_ALERTS_FILE",
        "alerts_text_file": "CLEARPARCEL_WATCHTOWER_ALERTS_TEXT_FILE",
    }
    for key, env_name in overrides.items():
        env_value = os.environ.get(env_name)
        if env_value:
            config[key] = env_value
            continue
        raw = config.get(key)
        if not raw:
            continue
        value = Path(raw).expanduser()
        if not value.is_absolute():
            value = root / value
        config[key] = str(value.resolve())
    config["_config_path"] = str(config_path)
    config["_root_dir"] = str(root)
    return config

def load_state(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"schema_version": 1, "sources": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as primary:
        backup = p.with_suffix(p.suffix + ".bak")
        if backup.is_file():
            try:
                recovered = json.loads(backup.read_text(encoding="utf-8-sig"))
                if isinstance(recovered, dict):
                    recovered["_state_recovered_from_backup"] = True
                    return recovered
            except (OSError, json.JSONDecodeError):
                pass
        raise RuntimeError(f"Watchtower state is unreadable: {p}") from primary

def _save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    if path.is_file():
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            backup.write_bytes(path.read_bytes())
        except OSError:
            pass
    tmp.replace(path)

def _hash_json(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _curl_request(url: str, timeout: int, *, transport: str = "curl") -> tuple[bytes, dict]:
    marker = b"\n__CP_HTTP__"
    curl_exe = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_exe: raise RuntimeError("curl fallback unavailable")
    cp = subprocess.run(
        [
            curl_exe, "-L",
            "--connect-timeout", str(min(timeout, 15)),
            "--max-time", str(timeout),
            "-A", USER_AGENT,
            "-sS",
            "-w", "\n__CP_HTTP__%{http_code}",
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout + 5,
    )
    if cp.returncode != 0:
        detail = cp.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"curl failed ({cp.returncode}: {detail})")
    pos = cp.stdout.rfind(marker)
    if pos < 0:
        raise RuntimeError("curl returned no HTTP status marker")
    body = cp.stdout[:pos]
    status_text = cp.stdout[pos + len(marker):].strip().decode("ascii", errors="replace")
    try:
        status = int(status_text)
    except ValueError as exc:
        raise RuntimeError(f"curl returned invalid HTTP status: {status_text}") from exc
    if status < 200 or status >= 400:
        raise RuntimeError(f"curl HTTP status {status}")
    return body, {
        "status": status,
        "headers": {},
        "final_url": url,
        "transport": transport,
    }

def _request(url: str, timeout: int, *, prefer_curl: bool = False) -> tuple[bytes, dict]:
    if prefer_curl:
        return _curl_request(url, timeout, transport="curl-preferred")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            headers = {k.lower(): v for k, v in response.headers.items()}
            return body, {
                "status": response.status,
                "headers": headers,
                "final_url": response.geturl(),
                "transport": "urllib",
            }
    except urllib.error.HTTPError as primary:
        retry_after = primary.headers.get("Retry-After") if primary.headers else None
        if primary.code == 429:
            raise ProviderRateLimitError(retry_after) from primary
        detail = f"HTTP {primary.code}"
        raise RuntimeError(f"provider returned {detail}; fallback transport not attempted") from primary
    except (urllib.error.URLError, TimeoutError, OSError) as primary:
        try:
            body, meta = _curl_request(url, timeout, transport="curl-fallback")
            meta["primary_error"] = f"{type(primary).__name__}: {primary}"
            return body, meta
        except Exception as fallback:
            raise RuntimeError(f"urllib transport failed ({type(primary).__name__}: {primary}); curl fallback failed ({type(fallback).__name__}: {fallback})") from primary

def _json_request(url: str, timeout: int, *, prefer_curl: bool = False) -> tuple[dict, dict]:
    body, meta = _request(url, timeout, prefer_curl=prefer_curl)
    data = json.loads(body.decode("utf-8-sig"))
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"ArcGIS error: {data['error']}")
    return data, meta

def _post_json(url: str, payload: dict, timeout: int) -> tuple[dict, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            meta = {
                "status": response.status,
                "transport": "urllib-post",
                "final_url": response.geturl(),
            }
    except urllib.error.HTTPError as primary:
        if primary.code == 429:
            retry_after = primary.headers.get("Retry-After") if primary.headers else None
            raise ProviderRateLimitError(retry_after) from primary
        curl_exe = shutil.which("curl") or shutil.which("curl.exe")
        if not curl_exe:
            raise RuntimeError(f"POST failed with urllib ({type(primary).__name__}: {primary}); curl fallback unavailable") from primary
        cp = subprocess.run(
            [
                curl_exe, "-L",
                "--connect-timeout", str(min(timeout, 15)),
                "--max-time", str(timeout),
                "-A", USER_AGENT,
                "-H", "Content-Type: application/json",
                "--data-binary", "@-",
                "-sS",
                "-w", "\n__CP_HTTP__%{http_code}",
                url,
            ],
            input=body,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 5,
        )
        if cp.returncode != 0:
            detail = cp.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"POST failed with urllib ({type(primary).__name__}: {primary}) "
                f"and curl ({cp.returncode}: {detail})"
            ) from primary
        marker = b"\n__CP_HTTP__"
        pos = cp.stdout.rfind(marker)
        if pos < 0:
            raise RuntimeError("curl POST returned no HTTP status marker") from primary
        raw = cp.stdout[:pos]
        status = int(cp.stdout[pos + len(marker):].strip().decode("ascii"))
        if status < 200 or status >= 400:
            raise RuntimeError(f"curl POST HTTP status {status}") from primary
        meta = {
            "status": status,
            "transport": "curl-post-fallback",
            "final_url": url,
            "primary_error": f"{type(primary).__name__}: {primary}",
        }
    data = json.loads(raw.decode("utf-8-sig"))
    return data, meta

def _arcgis_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    query["f"] = ["json"]
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))

def _spatial_wkid(data: dict) -> int | None:
    candidates = [
        data.get("sourceSpatialReference"),
        data.get("spatialReference"),
        (data.get("extent") or {}).get("spatialReference"),
    ]
    for sr in candidates:
        if isinstance(sr, dict):
            wkid = sr.get("latestWkid") or sr.get("wkid")
            if isinstance(wkid, int):
                return wkid
    return None

def _parcel_id_candidate(field_names: list[str]) -> tuple[str | None, str]:
    """Choose a likely parcel identifier conservatively; never treat OBJECTID as a parcel ID."""
    ranked = [
        ("parcelid", "high"), ("parcel_id", "high"), ("parcel_id_num", "high"),
        ("pin", "high"), ("pid", "high"), ("parcelno", "high"), ("parcel_no", "high"),
        ("parcelnumber", "high"), ("parcel_number", "high"),
        ("taxparcelid", "high"), ("tax_parcel_id", "high"),
        ("parcel", "medium"), ("taxid", "medium"), ("tax_id", "medium"),
    ]
    by_lower = {str(x).lower(): str(x) for x in field_names}
    for candidate, confidence in ranked:
        if candidate in by_lower:
            return by_lower[candidate], confidence
    for field in field_names:
        lower = str(field).lower()
        if ("parcel" in lower or lower.endswith("pin")) and not lower.startswith("object"):
            return str(field), "medium"
    return None, "none"


def _arcgis_count_query(url: str, where: str, timeout: int, *, prefer_curl: bool = False) -> int | None:
    query_url = url.rstrip("/") + "/query?" + urllib.parse.urlencode({
        "where": where, "returnCountOnly": "true", "f": "json",
    })
    data, _ = _json_request(query_url, timeout, prefer_curl=prefer_curl)
    return data.get("count")


def _arcgis_statistics_query(url: str, field: str, timeout: int, *, prefer_curl: bool = False) -> dict:
    stats = [
        {"statisticType": "count", "onStatisticField": field, "outStatisticFieldName": "nonnull_count"},
        {"statisticType": "count", "onStatisticField": field, "outStatisticFieldName": "row_count"},
    ]
    query_url = url.rstrip("/") + "/query?" + urllib.parse.urlencode({
        "where": "1=1", "outStatistics": json.dumps(stats), "returnGeometry": "false", "f": "json",
    })
    data, _ = _json_request(query_url, timeout, prefer_curl=prefer_curl)
    attrs = ((data.get("features") or [{}])[0].get("attributes") or {})
    return attrs


def _arcgis_duplicate_id_summary(url: str, field: str, timeout: int, *, prefer_curl: bool = False) -> dict:
    query_url = url.rstrip("/") + "/query?" + urllib.parse.urlencode({
        "where": f"{field} IS NOT NULL",
        "outFields": field,
        "groupByFieldsForStatistics": field,
        "outStatistics": json.dumps([{"statisticType":"count","onStatisticField":field,"outStatisticFieldName":"n"}]),
        "having": "COUNT(" + field + ") > 1",
        "returnGeometry": "false", "resultRecordCount": "2000", "f": "json",
    })
    data, _ = _json_request(query_url, timeout, prefer_curl=prefer_curl)
    groups = data.get("features") or []
    duplicate_groups = len(groups)
    duplicate_rows = sum(max(0, int((x.get("attributes") or {}).get("n") or 0) - 1) for x in groups)
    return {"duplicate_id_groups": duplicate_groups, "duplicate_id_extra_rows": duplicate_rows, "duplicate_scan_capped": len(groups) >= 2000}


def _field_candidate(field_names: list[str], exact: list[str], contains: list[str] | None = None) -> str | None:
    by_lower = {str(x).lower(): str(x) for x in field_names}
    for name in exact:
        if name.lower() in by_lower:
            return by_lower[name.lower()]
    for field in field_names:
        lower = str(field).lower()
        if any(token.lower() in lower for token in (contains or [])):
            return str(field)
    return None


def _extent_basis(data: dict) -> dict | None:
    extent = data.get("extent") or {}
    keys = ("xmin", "ymin", "xmax", "ymax")
    if not all(isinstance(extent.get(k), (int, float)) for k in keys):
        return None
    return {k: extent[k] for k in keys} | {"wkid": _spatial_wkid(data)}


def _extent_change(previous: dict | None, current: dict | None) -> dict | None:
    if not previous or not current:
        return None
    deltas = {k: current[k] - previous[k] for k in ("xmin","ymin","xmax","ymax")}
    old_w = max(abs(previous["xmax"] - previous["xmin"]), 1e-12)
    old_h = max(abs(previous["ymax"] - previous["ymin"]), 1e-12)
    normalized = max(abs(deltas["xmin"])/old_w, abs(deltas["xmax"])/old_w, abs(deltas["ymin"])/old_h, abs(deltas["ymax"])/old_h) * 100.0
    return {"coordinate_deltas": deltas, "max_extent_shift_percent": normalized}


def _field_completeness(url: str, field: str, total: int | None, timeout: int, *, prefer_curl: bool = False) -> dict:
    missing = _arcgis_count_query(url, f"{field} IS NULL OR {field} = ''", timeout, prefer_curl=prefer_curl)
    populated = None if total is None or missing is None else max(0, total - missing)
    pct = None if total in (None, 0) or populated is None else round((populated / total) * 100.0, 2)
    return {"field": field, "missing": missing, "populated": populated, "complete_percent": pct}


def _arcgis_geometry_sample(url: str, timeout: int, *, sample_size: int = 250, prefer_curl: bool = False) -> dict:
    """Retrieve a bounded geometry sample and calculate lightweight geometry signals."""
    query_url = url.rstrip("/") + "/query?" + urllib.parse.urlencode({
        "where": "1=1",
        "outFields": "",
        "returnGeometry": "true",
        "returnZ": "false",
        "returnM": "false",
        "resultRecordCount": str(max(1, min(int(sample_size), 1000))),
        "f": "json",
    })
    data, _ = _json_request(query_url, timeout, prefer_curl=prefer_curl)
    features = data.get("features") or []
    sampled = len(features)
    empty = 0
    multipart = 0
    rings_total = 0
    vertices_total = 0
    max_vertices = 0
    for feature in features:
        geometry = feature.get("geometry") or {}
        rings = geometry.get("rings")
        if not rings:
            empty += 1
            continue
        ring_count = len(rings)
        multipart += 1 if ring_count > 1 else 0
        rings_total += ring_count
        vertices = sum(len(ring or []) for ring in rings)
        vertices_total += vertices
        max_vertices = max(max_vertices, vertices)
    return {
        "geometry_sample_size": sampled,
        "geometry_sample_empty": empty,
        "geometry_sample_multipart": multipart,
        "geometry_sample_multipart_percent": None if not sampled else round(multipart / sampled * 100.0, 2),
        "geometry_sample_avg_vertices": None if not sampled else round(vertices_total / sampled, 2),
        "geometry_sample_max_vertices": max_vertices,
        "geometry_sample_rings": rings_total,
    }


def _arcgis_layer(source: dict, timeout: int) -> dict:
    data, meta = _json_request(_arcgis_url(source["url"]), timeout, prefer_curl=bool(source.get("prefer_curl")))
    fields = [
        {
            "name": f.get("name"),
            "type": f.get("type"),
            "length": f.get("length"),
            "nullable": f.get("nullable"),
        }
        for f in data.get("fields", [])
        if f.get("name")
    ]
    fields_sorted = sorted(fields, key=lambda x: x["name"].lower())
    schema_basis = {
        "geometryType": data.get("geometryType"),
        "wkid": _spatial_wkid(data),
        "objectIdField": data.get("objectIdField") or data.get("objectIdFieldName"),
        "fields": fields_sorted,
    }
    result = {
        "http_status": meta["status"],
        "transport": meta.get("transport"),
        "service_name": data.get("name"),
        "type": data.get("type"),
        "geometry_type": data.get("geometryType"),
        "wkid": _spatial_wkid(data),
        "field_count": len(fields_sorted),
        "field_names": [x["name"] for x in fields_sorted],
        "max_record_count": data.get("maxRecordCount"),
        "current_version": data.get("currentVersion"),
        "schema_hash": _hash_json(schema_basis),
        "spatial_extent": _extent_basis(data),
    }
    if source.get("count"):
        result["feature_count"] = _arcgis_count_query(source["url"], "1=1", timeout, prefer_curl=bool(source.get("prefer_curl")))
    if source.get("parcel_quality"):
        id_field, confidence = _parcel_id_candidate(result["field_names"])
        result["parcel_id_field"] = id_field
        result["parcel_id_confidence"] = confidence
        result["null_geometry_count"] = _arcgis_count_query(source["url"], "SHAPE IS NULL", timeout, prefer_curl=bool(source.get("prefer_curl")))
        if id_field and confidence == "high":
            null_count = _arcgis_count_query(source["url"], f"{id_field} IS NULL OR {id_field} = ''", timeout, prefer_curl=bool(source.get("prefer_curl")))
            result["parcel_id_null_count"] = null_count
            profiles = {}
            owner_field = _field_candidate(result["field_names"], ["owner_name","owner","tax_name","ownername"], ["owner"])
            site_address_field = _field_candidate(result["field_names"], ["site_address","property_address","prop_addr","site_addr","physical_address"], ["siteaddr","site_addr","propaddr","prop_addr"])
            mailing_address_field = _field_candidate(result["field_names"], ["ownraddr1","owner_address","mail_address","mail_addr","tax_add_l1"], ["ownraddr","owner_addr","mail_addr"])
            for label, field in (("parcel_id", id_field), ("owner", owner_field), ("site_address", site_address_field), ("mailing_address", mailing_address_field)):
                if field:
                    try:
                        profiles[label] = _field_completeness(source["url"], field, result.get("feature_count"), timeout, prefer_curl=bool(source.get("prefer_curl")))
                    except Exception as exc:
                        profiles[label] = {"field": field, "status": "unsupported", "error": str(exc)[:160]}
            result["completeness_profiles"] = profiles
            if source.get("geometry_sample"):
                try:
                    result.update(_arcgis_geometry_sample(
                        source["url"], timeout,
                        sample_size=int(source.get("geometry_sample_size", 250)),
                        prefer_curl=bool(source.get("prefer_curl")),
                    ))
                except Exception as exc:
                    result["geometry_sample_status"] = "unsupported"
                    result["geometry_sample_error"] = str(exc)[:180]
            try:
                result.update(_arcgis_duplicate_id_summary(source["url"], id_field, timeout, prefer_curl=bool(source.get("prefer_curl"))))
            except Exception as exc:
                result["duplicate_id_check"] = "unsupported"
                result["duplicate_id_check_error"] = str(exc)[:180]

    problems = []
    expected_geom = source.get("expected_geometry")
    if expected_geom and result["geometry_type"] != expected_geom:
        problems.append(f'geometry changed: expected {expected_geom}, got {result["geometry_type"]}')
    expected_wkid = source.get("expected_wkid")
    if expected_wkid and result["wkid"] not in (expected_wkid, None):
        problems.append(f'WKID changed: expected {expected_wkid}, got {result["wkid"]}')
    missing = sorted(set(source.get("required_fields", [])) - set(result["field_names"]))
    if missing:
        problems.append("required fields missing: " + ", ".join(missing))
    result["problems"] = problems
    return result

def _arcgis_service(source: dict, timeout: int) -> dict:
    data, meta = _json_request(_arcgis_url(source["url"]), timeout, prefer_curl=bool(source.get("prefer_curl")))
    layers = [{"id": x.get("id"), "name": x.get("name")} for x in data.get("layers", [])]
    result = {
        "http_status": meta["status"], "transport": meta.get("transport"),
        "service_name": data.get("mapName") or data.get("name"),
        "current_version": data.get("currentVersion"),
        "service_description": data.get("serviceDescription"),
        "layers": layers, "schema_hash": _hash_json(layers), "problems": [],
    }
    if source.get("discover_parcel_layer"):
        terms = [str(x).lower() for x in source.get("parcel_layer_terms", ["parcel", "tax"])]
        explicit_layer_id = source.get("parcel_layer_id")
        if explicit_layer_id is not None:
            candidates = [x for x in layers if str(x.get("id")) == str(explicit_layer_id)]
            if not candidates:
                result["problems"].append(f"configured parcel layer {explicit_layer_id} not found in service")
                return result
        else:
            candidates = [x for x in layers if any(term in str(x.get("name","")).lower() for term in terms)]
            if not candidates:
                result["problems"].append("no parcel-like layer found in service")
                return result
            if len(candidates) > 1:
                labels = ", ".join(f'{x.get("id")}:{x.get("name")}' for x in candidates)
                result["problems"].append(f"multiple parcel-like layers found; configure parcel_layer_id ({labels})")
                return result
        chosen = candidates[0]
        layer_source = dict(source)
        layer_source["url"] = source["url"].rstrip("/") + "/" + str(chosen["id"])
        layer_source["count"] = True
        layer_source["parcel_quality"] = bool(source.get("parcel_quality"))
        layer_source.pop("discover_parcel_layer", None)
        layer = _arcgis_layer(layer_source, timeout)
        result.update({
            "parcel_layer_id": chosen["id"], "parcel_layer_name": chosen["name"],
            "geometry_type": layer.get("geometry_type"), "wkid": layer.get("wkid"),
            "field_count": layer.get("field_count"), "field_names": layer.get("field_names"),
            "feature_count": layer.get("feature_count"), "parcel_schema_hash": layer.get("schema_hash"),
            "parcel_id_field": layer.get("parcel_id_field"), "parcel_id_confidence": layer.get("parcel_id_confidence"),
            "parcel_id_null_count": layer.get("parcel_id_null_count"), "null_geometry_count": layer.get("null_geometry_count"),
            "duplicate_id_groups": layer.get("duplicate_id_groups"), "duplicate_id_extra_rows": layer.get("duplicate_id_extra_rows"),
            "duplicate_scan_capped": layer.get("duplicate_scan_capped"), "duplicate_id_check": layer.get("duplicate_id_check"),
            "spatial_extent": layer.get("spatial_extent"), "completeness_profiles": layer.get("completeness_profiles"),
            "geometry_sample_size": layer.get("geometry_sample_size"), "geometry_sample_empty": layer.get("geometry_sample_empty"),
            "geometry_sample_multipart": layer.get("geometry_sample_multipart"), "geometry_sample_multipart_percent": layer.get("geometry_sample_multipart_percent"),
            "geometry_sample_avg_vertices": layer.get("geometry_sample_avg_vertices"), "geometry_sample_max_vertices": layer.get("geometry_sample_max_vertices"),
            "geometry_sample_rings": layer.get("geometry_sample_rings"), "geometry_sample_status": layer.get("geometry_sample_status"),
        })
        result["problems"].extend(layer.get("problems", []))
    return result

def _arcgis_image(source: dict, timeout: int) -> dict:
    data, meta = _json_request(_arcgis_url(source["url"]), timeout, prefer_curl=bool(source.get("prefer_curl")))
    basis = {
        "service_name": data.get("name"),
        "pixelType": data.get("pixelType"),
        "pixelSizeX": data.get("pixelSizeX"),
        "pixelSizeY": data.get("pixelSizeY"),
        "bandCount": data.get("bandCount"),
        "wkid": _spatial_wkid(data),
        "capabilities": data.get("capabilities"),
    }
    return {
        "http_status": meta["status"],
        "transport": meta.get("transport"),
        **basis,
        "schema_hash": _hash_json(basis),
        "problems": [],
    }
def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def _wms(source: dict, timeout: int) -> dict:
    query = urllib.parse.urlencode({
        "service": "WMS",
        "request": "GetCapabilities",
    })
    body, meta = _request(source["url"].rstrip("?") + "?" + query, timeout, prefer_curl=bool(source.get("prefer_curl")))
    root = ET.fromstring(body)
    names = sorted({
        (element.text or "").strip()
        for element in root.iter()
        if _local_name(element.tag) == "Name" and (element.text or "").strip()
    })
    expected = source.get("expected_layers", [])
    missing = [x for x in expected if x not in names]
    problems = ["expected WMS layers missing: " + ", ".join(missing)] if missing else []
    return {
        "http_status": meta["status"],
        "transport": meta.get("transport"),
        "layer_count": len(names),
        "expected_layers": expected,
        "missing_layers": missing,
        "schema_hash": _hash_json(names),
        "problems": problems,
    }

def _wfs(source: dict, timeout: int) -> dict:
    query = urllib.parse.urlencode({
        "SERVICE": "WFS",
        "VERSION": source.get("version", "1.1.0"),
        "REQUEST": "GetCapabilities",
    })
    body, meta = _request(
        source["url"].rstrip("?") + "?" + query,
        timeout,
        prefer_curl=bool(source.get("prefer_curl")),
    )
    root = ET.fromstring(body)
    feature_types = []
    for element in root.iter():
        if _local_name(element.tag) != "FeatureType":
            continue
        for child in element:
            if _local_name(child.tag) == "Name" and (child.text or "").strip():
                feature_types.append((child.text or "").strip())
                break
    feature_types = sorted(set(feature_types))
    expected = source.get("expected_feature_types", [])
    missing = [x for x in expected if x not in feature_types]
    problems = (
        ["expected WFS feature types missing: " + ", ".join(missing)]
        if missing else []
    )
    return {
        "http_status": meta["status"],
        "transport": meta.get("transport"),
        "feature_type_count": len(feature_types),
        "feature_types": feature_types,
        "expected_feature_types": expected,
        "missing_feature_types": missing,
        "schema_hash": _hash_json(feature_types),
        "problems": problems,
    }

def _coerce_scalar(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    try:
        return int(stripped)
    except ValueError:
        try:
            return float(stripped)
        except ValueError:
            return value

def _sda_query(source: dict, timeout: int) -> dict:
    payload = {
        "query": source["query"],
        "format": source.get("format", "JSON+COLUMNNAME"),
    }
    data, meta = _post_json(source["url"], payload, timeout)
    table = data.get("Table")
    if not isinstance(table, list) or not table or not isinstance(table[0], list):
        raise RuntimeError("Soil Data Access returned no tabular result")
    columns = [str(x) for x in table[0]]
    expected = source.get("expected_columns", [])
    missing = [x for x in expected if x not in columns]
    values = {}
    if len(table) > 1 and isinstance(table[1], list):
        values = {
            columns[i]: _coerce_scalar(table[1][i])
            for i in range(min(len(columns), len(table[1])))
        }
    problems = (
        ["expected SDA columns missing: " + ", ".join(missing)]
        if missing else []
    )
    return {
        "http_status": meta["status"],
        "transport": meta.get("transport"),
        "columns": columns,
        "values": values,
        "row_count": max(0, len(table) - 1),
        "schema_hash": _hash_json(columns),
        "tracked_values": {
            key: values.get(key)
            for key in source.get("tracked_values", [])
            if key in values
        },
        "problems": problems,
    }

def _arcgis_county_catalog(source: dict, timeout: int) -> dict:
    """Query a small ArcGIS metadata layer and retain county-level catalog observations."""
    params = {
        "where": source.get("where", "1=1"),
        "outFields": ",".join(source.get("out_fields") or ["countyname", "rundate", "acqdate", "data_url", "viewer_url", "gac_open_approval"]),
        "returnGeometry": "false",
        "f": "json",
    }
    url = source["url"].rstrip("/") + "/query?" + urllib.parse.urlencode(params)
    data, meta = _json_request(url, timeout, prefer_curl=bool(source.get("prefer_curl")))
    county_field = source.get("county_field", "countyname")
    records = {}
    for feature in data.get("features", []):
        attrs = feature.get("attributes") or {}
        county = attrs.get(county_field)
        if county:
            records[str(county)] = attrs
    problems = []
    expected = source.get("expected_count")
    if expected is not None and len(records) != int(expected):
        problems.append(f"expected {expected} county records, got {len(records)}")
    stable = {name: records[name] for name in sorted(records)}
    return {
        "http_status": meta.get("status"),
        "transport": meta.get("transport"),
        "county_record_count": len(records),
        "county_records": records,
        "schema_hash": _hash_json(sorted({k for row in records.values() for k in row.keys()})),
        "catalog_hash": _hash_json(stable),
        "problems": problems,
    }


def _adapter_name(source: dict) -> str:
    """Return the canonical adapter name while preserving v0.1 kind compatibility."""
    raw = source.get("adapter") or source.get("kind")
    if not raw:
        raise ValueError("Source must define 'adapter' (preferred) or legacy 'kind'")
    aliases = {
        "arcgis-feature-layer": "arcgis_layer",
        "arcgis-feature-service": "arcgis_layer",
        "arcgis-map-service": "arcgis_service",
        "arcgis-image-service": "arcgis_image",
        "soil-data-access": "sda_query",
    }
    return aliases.get(str(raw).strip().lower(), str(raw).strip().lower().replace("-", "_"))


def _observation_fingerprint(details: dict) -> str:
    """Fingerprint stable observations, excluding transport/timing/error chatter."""
    volatile = {
        "http_status", "transport", "problems", "elapsed_ms", "attempts",
        "checked_at", "changes", "error", "observation_fingerprint",
    }
    stable = {k: v for k, v in details.items() if k not in volatile}
    return _hash_json(stable)


def _source_check(source: dict, timeout: int) -> dict:
    kind = _adapter_name(source)
    if kind == "arcgis_county_catalog":
        return _arcgis_county_catalog(source, timeout)
    if kind == "arcgis_layer":
        return _arcgis_layer(source, timeout)
    if kind == "arcgis_service":
        return _arcgis_service(source, timeout)
    if kind == "arcgis_image":
        return _arcgis_image(source, timeout)
    if kind == "wms":
        return _wms(source, timeout)
    if kind == "wfs":
        return _wfs(source, timeout)
    if kind == "sda_query":
        return _sda_query(source, timeout)
    raise ValueError(f"Unsupported source adapter: {kind}")
def _compare(previous: dict | None, current: dict, source: dict | None = None) -> list[dict]:
    changes = []
    if not previous:
        return changes
    source = source or {}
    thresholds = source.get("thresholds") or {}

    if previous.get("schema_hash") and current.get("schema_hash") != previous.get("schema_hash"):
        changes.append({
            "severity": thresholds.get("schema_change_severity", "warn"),
            "type": "schema",
            "message": "schema/capability fingerprint changed",
            "previous": previous.get("schema_hash"),
            "current": current.get("schema_hash"),
        })

    if "feature_count" in current and previous.get("feature_count") is not None:
        previous_count = previous.get("feature_count")
        current_count = current.get("feature_count")
        if current_count != previous_count:
            delta = current_count - previous_count
            delta_percent = None
            if previous_count:
                delta_percent = (delta / previous_count) * 100.0
            warn_percent = thresholds.get("feature_count_change_percent")
            severity = "info"
            if (
                warn_percent is not None
                and delta_percent is not None
                and abs(delta_percent) >= float(warn_percent)
            ):
                severity = "warn"
            changes.append({
                "severity": severity,
                "type": "feature_count",
                "message": (
                    f"feature count changed {previous_count} -> {current_count} "
                    f"({delta:+d}{'' if delta_percent is None else f', {delta_percent:+.2f}%'})"
                ),
                "previous": previous_count,
                "current": current_count,
                "delta": delta,
                "delta_percent": delta_percent,
            })

    previous_values = previous.get("tracked_values", {}) or {}
    current_values = current.get("tracked_values", {}) or {}
    for key, value in current_values.items():
        if key in previous_values and previous_values[key] != value:
            changes.append({
                "severity": "info",
                "type": "tracked_value",
                "key": key,
                "message": f'{key} changed {previous_values[key]} -> {value}',
                "previous": previous_values[key],
                "current": value,
            })

    extent_delta = _extent_change(previous.get("spatial_extent"), current.get("spatial_extent"))
    if extent_delta and extent_delta["max_extent_shift_percent"] > float(thresholds.get("extent_shift_percent", 0.5)):
        changes.append({
            "severity": thresholds.get("extent_change_severity", "info"),
            "type": "spatial_extent",
            "message": f"published spatial extent shifted by up to {extent_delta['max_extent_shift_percent']:.3f}% of prior extent",
            **extent_delta,
        })

    previous_fingerprint = previous.get("observation_fingerprint")
    current_fingerprint = current.get("observation_fingerprint")
    if previous_fingerprint and current_fingerprint and previous_fingerprint != current_fingerprint:
        if not changes:
            changes.append({
                "severity": "info",
                "type": "observation",
                "message": "observed dataset/service fingerprint changed",
                "previous": previous_fingerprint,
                "current": current_fingerprint,
            })
    return changes

def _build_alerts(
    previous_sources: dict,
    current_sources: dict,
    checked_ids: set[str],
    now: str,
) -> tuple[list[dict], list[dict]]:
    active = []
    events = []
    for sid, current in current_sources.items():
        status = current.get("status", "unknown")
        if status == "error":
            message = current.get("error") or "; ".join(current.get("problems", [])) or "source check failed"
            active.append({
                "severity": "error",
                "source": sid,
                "name": current.get("name"),
                "type": "source_error",
                "message": message,
                "checked_at": current.get("checked_at", now),
            })
        elif status == "warn":
            warning_changes = [
                change for change in current.get("changes", [])
                if change.get("severity") == "warn"
            ]
            message = (
                "; ".join(change.get("message", "source warning") for change in warning_changes)
                or "; ".join(current.get("problems", []))
                or "source warning"
            )
            active.append({
                "severity": "warn",
                "source": sid,
                "name": current.get("name"),
                "type": "source_warning",
                "message": message,
                "checked_at": current.get("checked_at", now),
            })

        if sid not in checked_ids:
            continue
        previous = previous_sources.get(sid, {})
        if previous.get("status") in ("warn", "error") and status == "ok":
            events.append({
                "severity": "info",
                "source": sid,
                "name": current.get("name"),
                "type": "recovered",
                "message": f"source recovered from {previous.get('status')} to ok",
                "checked_at": now,
            })
        for change in current.get("changes", []):
            if change.get("severity") == "info":
                events.append({
                    "severity": "info",
                    "source": sid,
                    "name": current.get("name"),
                    "type": change.get("type", "change"),
                    "message": change.get("message", "source value changed"),
                    "checked_at": now,
                })
    return active, events

def _write_alert_text(path: Path, document: dict) -> None:
    lines = [
        f"ClearParcel GIS Data Watchtower Alerts - {document.get('generated_at')}",
        f"Active alerts: {len(document.get('active', []))}",
        "",
    ]
    if not document.get("active"):
        lines.append("No active GIS data-source alerts.")
    else:
        for alert in document["active"]:
            lines.append(
                f"[{alert.get('severity', 'info').upper()}] "
                f"{alert.get('name') or alert.get('source')}: {alert.get('message')}"
            )
    if document.get("events"):
        lines.extend(["", "Recent informational events:"])
        for event in document["events"]:
            lines.append(
                f"[INFO] {event.get('name') or event.get('source')}: {event.get('message')}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

class WatchtowerRunLockedError(RuntimeError):
    pass


def _acquire_run_lock(state_path: Path, stale_seconds: int = 7200) -> Path:
    lock = state_path.with_suffix(state_path.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        try:
            age = time.time() - lock.stat().st_mtime
            if age > stale_seconds:
                lock.unlink()
        except OSError:
            pass
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise WatchtowerRunLockedError(f"another Watchtower check is already running: {lock}") from exc
    try:
        os.write(fd, f"pid={os.getpid()}\nstarted={dt.datetime.now(dt.timezone.utc).isoformat()}\n".encode("utf-8"))
    finally:
        os.close(fd)
    return lock


def _release_run_lock(lock: Path | None) -> None:
    if lock is None:
        return
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def _check_sources_unlocked(
    config: dict,
    *,
    source_filter: str | None = None,
    save: bool = True,
    execution_profile: str | None = None,
) -> dict:
    timeout = int(config.get("timeout_seconds", 20))
    run_started_perf = time.perf_counter()
    run_started_cpu = time.process_time()
    tracemalloc.start()
    state_path = Path(config["state_file"])
    previous_state = load_state(state_path)
    previous_sources = previous_state.get("sources", {})
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    records = {}
    filtered = source_filter.lower() if source_filter else None

    for source in config.get("sources", []):
        if filtered and filtered not in source["id"].lower() and filtered not in source["name"].lower():
            continue
        profiles = source.get("execution_profiles")
        if execution_profile:
            if not profiles or (execution_profile not in profiles and "any" not in profiles):
                continue
        started = dt.datetime.now(dt.timezone.utc)
        source_timeout = int(source.get("timeout_seconds", timeout))
        retries = int(source.get("retries", config.get("retries", 1)))
        details = None
        last_error = None
        attempts = 0
        for attempt in range(retries + 1):
            attempts = attempt + 1
            try:
                details = _source_check(source, source_timeout)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if isinstance(exc, ProviderRateLimitError):
                    break
                if attempt < retries:
                    time.sleep(float(config.get("retry_delay_seconds", 1)))

        elapsed_ms = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
        if details is not None:
            details["observation_fingerprint"] = _observation_fingerprint(details)
            changes = _compare(previous_sources.get(source["id"]), details, source)
            problems = details.get("problems", [])
            status = "error" if problems else ("warn" if any(x["severity"] == "warn" for x in changes) else "ok")
            records[source["id"]] = {
                "id": source["id"],
                "name": source["name"],
                "provider": source.get("provider"),
                "category": source.get("category"),
                "county_slug": source.get("county_slug"),
                "kind": source.get("kind") or _adapter_name(source),
                "adapter": _adapter_name(source),
                "url": source["url"],
                "provenance": {
                    "source_url": source["url"],
                    "adapter": _adapter_name(source),
                    "observed_at": now,
                    "publisher_modified": details.get("last_modified") or details.get("modified") or details.get("editing_info"),
                },
                "status": status,
                "checked_at": now,
                "elapsed_ms": elapsed_ms,
                "attempts": attempts,
                **details,
                "changes": changes,
            }
        else:
            records[source["id"]] = {
                "id": source["id"],
                "name": source["name"],
                "provider": source.get("provider"),
                "category": source.get("category"),
                "county_slug": source.get("county_slug"),
                "kind": source.get("kind") or _adapter_name(source),
                "adapter": _adapter_name(source),
                "url": source["url"],
                "provenance": {
                    "source_url": source["url"],
                    "adapter": _adapter_name(source),
                    "observed_at": now,
                    "publisher_modified": None,
                },
                "status": "error",
                "checked_at": now,
                "elapsed_ms": elapsed_ms,
                "attempts": attempts,
                "error": f"{type(last_error).__name__}: {last_error}",
                "changes": [],
            }
    counts = {
        status: sum(1 for x in records.values() if x["status"] == status)
        for status in ("ok", "warn", "error")
    }
    active_alerts, events = _build_alerts(
        previous_sources,
        records,
        set(records),
        now,
    )
    run_wall_ms = int((time.perf_counter() - run_started_perf) * 1000)
    run_cpu_ms = int((time.process_time() - run_started_cpu) * 1000)
    try:
        _, peak_memory_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    telemetry = {
        "wall_ms": run_wall_ms,
        "cpu_ms": run_cpu_ms,
        "peak_python_memory_kb": int(peak_memory_bytes / 1024),
        "sources_checked": len(records),
        "total_source_elapsed_ms": sum(int(x.get("elapsed_ms") or 0) for x in records.values()),
    }
    result = {
        "schema_version": 2,
        "generated_at": now,
        "scope": {"type": "source", "source_id": source_filter} if source_filter else {"type": "fleet"},
        "telemetry": telemetry,
        "overall": "error" if counts["error"] else "warn" if counts["warn"] else "ok",
        "counts": counts,
        "sources": records,
        "active_alerts": active_alerts,
        "events": events,
    }
    if save:
        state_records = dict(previous_sources) if filtered else {}
        state_records.update(records)
        state_counts = {
            status: sum(1 for x in state_records.values() if x.get("status") == status)
            for status in ("ok", "warn", "error")
        }
        state_active_alerts, state_events = _build_alerts(
            previous_sources,
            state_records,
            set(records),
            now,
        )
        state_result = {
            "schema_version": 2,
            "generated_at": now,
            "telemetry": telemetry,
            "overall": "error" if state_counts["error"] else "warn" if state_counts["warn"] else "ok",
            "counts": state_counts,
            "sources": state_records,
            "active_alerts": state_active_alerts,
            "events": state_events,
        }
        _save_json(state_path, state_result)
        alerts_document = {
            "schema_version": 2,
            "generated_at": now,
            "active": state_active_alerts,
            "events": state_events,
        }
        alerts_file = config.get("alerts_file")
        if alerts_file:
            _save_json(Path(alerts_file), alerts_document)
        alerts_text_file = config.get("alerts_text_file")
        if alerts_text_file:
            _write_alert_text(Path(alerts_text_file), alerts_document)
        history_path = Path(config["history_file"])
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_limit = int(config.get("history_max_mb", 10)) * 1024 * 1024
        if history_path.exists() and history_path.stat().st_size >= history_limit:
            rotated = history_path.with_suffix(history_path.suffix + ".1")
            try:
                rotated.unlink()
            except FileNotFoundError:
                pass
            history_path.replace(rotated)
        summary = {
            "generated_at": now,
            "overall": result["overall"],
            "telemetry": telemetry,
            "counts": counts,
            "source_filter": source_filter,
            "active_alert_count": len(state_active_alerts),
            "event_count": len(state_events),
            "sources": {
                sid: {
                    "name": rec.get("name"),
                    "status": rec.get("status"),
                    "elapsed_ms": rec.get("elapsed_ms"),
                    "attempts": rec.get("attempts"),
                    "feature_count": rec.get("feature_count"),
                    "tracked_values": rec.get("tracked_values", {}),
                    "schema_hash": rec.get("schema_hash"),
                    "error": rec.get("error"),
                    "changes": rec.get("changes", []),
                }
                for sid, rec in records.items()
            },
            "changes": [
                {"source": sid, **change}
                for sid, rec in records.items()
                for change in rec.get("changes", [])
            ],
        }
        with history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(summary, separators=(",", ":")) + "\n")
    return result


def check_sources(
    config: dict,
    *,
    source_filter: str | None = None,
    save: bool = True,
    execution_profile: str | None = None,
) -> dict:
    state_path = Path(config["state_file"])
    run_lock = _acquire_run_lock(state_path, int(config.get("run_lock_stale_seconds", 7200)))
    try:
        return _check_sources_unlocked(config, source_filter=source_filter, save=save, execution_profile=execution_profile)
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        _release_run_lock(run_lock)


def load_history(
    config: dict,
    *,
    source_filter: str | None = None,
    limit: int = 50,
) -> dict:
    history_path = Path(config["history_file"])
    paths = [
        history_path.with_suffix(history_path.suffix + ".1"),
        history_path,
    ]
    rows = []
    for path in paths:
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    needle = source_filter.lower() if source_filter else None
    if needle:
        filtered = []
        for item in rows:
            sources = item.get("sources") or {}
            matches = [
                (sid, rec)
                for sid, rec in sources.items()
                if needle in sid.lower()
                or needle in str((rec or {}).get("name", "")).lower()
            ]
            for sid, rec in matches:
                filtered.append({
                    "generated_at": item.get("generated_at"),
                    "source": sid,
                    "name": (rec or {}).get("name"),
                    "status": (rec or {}).get("status"),
                    "elapsed_ms": (rec or {}).get("elapsed_ms"),
                    "attempts": (rec or {}).get("attempts"),
                    "feature_count": (rec or {}).get("feature_count"),
                    "tracked_values": (rec or {}).get("tracked_values", {}),
                    "schema_hash": (rec or {}).get("schema_hash"),
                    "error": (rec or {}).get("error"),
                    "changes": (rec or {}).get("changes", []),
                })
        rows = filtered
    limit = max(1, min(int(limit), 1000))
    rows = rows[-limit:]
    return {
        "history_file": str(history_path),
        "source_filter": source_filter,
        "entry_count": len(rows),
        "entries": rows,
    }
