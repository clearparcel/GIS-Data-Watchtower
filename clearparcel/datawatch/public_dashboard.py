from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from clearparcel.datawatch.dashboard import (
    _BoundedThreadingHTTPServer,
    _county_snapshot,
    _dashboard_state,
    _esc,
    _health_status,
    _mngac_csv,
    _mngac_data,
    _snapshot_csv,
    _snapshot_xlsx,
    _statewide_snapshot,
    _status_class,
    _layout,
    render_counties,
    render_county,
    render_mngac,
)
from clearparcel.datawatch.storage import backend_from_env


_PUBLIC_SOURCE_FIELDS = (
    "id",
    "name",
    "provider",
    "category",
    "status",
    "feature_count",
    "checked_at",
    "worker",
    "last_success_at",
    "last_report_at",
    "county_slug",
    "field_count",
    "parcel_id_null_count",
    "duplicate_id_extra_rows",
    "null_geometry_count",
    "geometry_sample_multipart_percent",
    "geometry_sample_avg_vertices",
    "elapsed_ms",
    "completeness_profiles",
)

_PUBLIC_WORKER_FIELDS = (
    "overall",
    "source_count",
    "checked_at",
    "last_success_at",
    "last_report_at",
)

_PUBLIC_CATALOG_FIELDS = (
    "gac_open_approval",
    "acqdate",
    "rundate",
    "data_url",
    "viewer_url",
)

_PUBLIC_MNGAC_FIELDS = (
    "standard",
    "method",
    "record_count",
    "field_count",
    "covered_counties",
    "field_population_percent",
    "mandatory_field_count",
    "mandatory_population_percent",
    "source_schema_missing_fields",
    "fields",
    "counties",
)


def _json_copy(value):
    return json.loads(json.dumps(value))


def _sanitize_catalog_records(records: dict | None) -> dict:
    public: dict = {}
    for county, record in (records or {}).items():
        if not isinstance(record, dict):
            continue
        public[str(county)] = {
            key: record.get(key)
            for key in _PUBLIC_CATALOG_FIELDS
            if record.get(key) is not None
        }
    return public


def _sanitize_mngac(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    public = {
        key: _json_copy(data.get(key))
        for key in _PUBLIC_MNGAC_FIELDS
        if data.get(key) is not None
    }
    return public if public.get("fields") and public.get("counties") else None


def sanitize_public_render_state(state: dict) -> dict:
    """Reduce aggregate state to facts intentionally safe for anonymous display."""
    public = {
        "schema_version": state.get("schema_version"),
        "generated_at": state.get("generated_at"),
        "overall": state.get("overall"),
        "counts": _json_copy(state.get("counts") or {}),
        "workers": {},
        "sources": {},
    }

    for worker_name, worker in (state.get("workers") or {}).items():
        if not isinstance(worker, dict):
            continue
        public["workers"][str(worker_name)] = {
            key: worker.get(key)
            for key in _PUBLIC_WORKER_FIELDS
            if worker.get(key) is not None
        }

    for source_id, source in (state.get("sources") or {}).items():
        if not isinstance(source, dict):
            continue
        summary = {
            key: _json_copy(source.get(key))
            for key in _PUBLIC_SOURCE_FIELDS
            if source.get(key) is not None
        }
        summary["id"] = source.get("id") or source_id
        summary["status"] = source.get("status") or "unknown"
        summary["change_count"] = len(source.get("changes") or [])

        if source_id == "mn-parcel-county-catalog":
            summary["county_records"] = _sanitize_catalog_records(source.get("county_records"))

        mngac = _sanitize_mngac(source.get("mngac_completeness"))
        if mngac:
            summary["mngac_completeness"] = mngac

        public["sources"][str(source_id)] = summary

    return public


def render_public_dashboard(config: dict) -> str:
    state = _dashboard_state(config)
    sources = state.get("sources") or {}
    counts = state.get("counts") or {}
    workers = state.get("workers") or {}
    mngac = _mngac_data(state)
    changed = sum(1 for source in sources.values() if int(source.get("change_count") or 0) > 0)

    worker_cards = []
    for name in sorted(workers):
        worker = workers[name] or {}
        status = str(worker.get("overall") or "unknown")
        reporting = "Reporting overdue" if worker.get("stale") else "Reporting on time"
        worker_cards.append(
            '<div class="card worker-card">'
            f'<div><h3><span class="status-dot {_status_class(status)}"></span>{_esc(name.title())} worker</h3>'
            f'<span class="subtext">{_esc(_health_status(status))} · {_esc(reporting)}</span></div>'
            '<div class="worker-meta">'
            f'<div><span class="muted">Sources</span><strong>{_esc(worker.get("source_count", "—"))}</strong></div>'
            f'<div><span class="muted">Last success</span><strong style="font-size:13px">{_esc(worker.get("last_success_at") or worker.get("checked_at") or "—")}</strong></div>'
            '</div></div>'
        )

    rows = []
    for source_id, source in sorted(
        sources.items(),
        key=lambda item: str((item[1] or {}).get("name") or item[0]).lower(),
    ):
        name = source.get("name") or source_id
        rows.append(
            f'<tr data-name="{_esc(str(name).lower())}" '
            f'data-category="{_esc(source.get("category") or "Other")}" '
            f'data-status="{_esc(source.get("status") or "unknown")}">'
            f'<td><a href="/source?{urllib.parse.urlencode({"id": source_id})}"><strong>{_esc(name)}</strong></a></td>'
            f'<td>{_esc(source.get("provider") or "—")}<br><span class="muted">{_esc(source.get("category") or "Other")}</span></td>'
            f'<td><span class="pill {_status_class(source.get("status") or "unknown")}">{_esc(_health_status(source.get("status") or "unknown"))}</span>'
            f'<br><span class="muted">{_esc(source.get("reporting") or "current")} reporting</span></td>'
            f'<td>{_esc(f"{source.get("feature_count"):,}" if isinstance(source.get("feature_count"), int) else source.get("feature_count") or "—")}</td>'
            f'<td>{_esc(source.get("change_count") or 0)}</td>'
            f'<td>{_esc(source.get("last_success_at") or source.get("checked_at") or "—")}</td>'
            '</tr>'
        )

    mngac_card = (
        f'<div class="card"><div class="muted">MN GAC counties represented</div>'
        f'<div class="metric">{_esc(mngac.get("covered_counties") or 0)}/87</div>'
        f'<span class="subtext"><a href="/mngac">Explore field completeness and the interactive map →</a></span></div>'
        if mngac
        else '<div class="card"><div class="muted">MN GAC completeness</div><div class="metric">—</div>'
             '<span class="subtext">No statewide completeness observation is available yet.</span></div>'
    )

    body = (
        '<div class="grid primary-grid">'
        f'<div class="card"><div class="muted">Overall health</div><div class="metric {_status_class(state.get("overall") or "unknown")}">{_esc(_health_status(state.get("overall") or "unknown"))}</div>'
        '<span class="subtext">Latest published health across the shared Watchtower aggregate.</span></div>'
        f'<div class="card"><div class="muted">Monitored sources</div><div class="metric">{len(sources)}</div>'
        '<span class="subtext">Cloud and provider-restricted local observations combined.</span></div>'
        f'<div class="card"><div class="muted">Source issues</div><div class="metric">{int(counts.get("warn") or 0) + int(counts.get("error") or 0)}</div>'
        '<span class="subtext">Sources whose latest observation reported a warning or error.</span></div>'
        f'{mngac_card}</div>'
        '<div class="section-head"><div><h2>Coverage</h2><p>Public-facing summary of statewide monitoring coverage.</p></div></div>'
        '<div class="activity-strip">'
        f'<div class="card" id="changes"><div class="muted">Sources changed in latest observation</div><div class="metric">{changed}</div>'
        '<span class="subtext">Change details remain private; this shows only the source-level count.</span></div>'
        f'<div class="card"><div class="muted">Last aggregate update</div><strong>{_esc(state.get("generated_at") or "No saved observation")}</strong>'
        '<span class="subtext"><a href="/counties">Browse all 87 Minnesota county dashboards →</a></span></div></div>'
        '<div class="section-head"><div><h2>Workers</h2><p>Freshness of the cloud and provider-restricted local observations.</p></div></div>'
        f'<div class="grid worker-grid">{"".join(worker_cards) or "<div class=\"card muted\">Worker metadata is unavailable.</div>"}</div>'
        '<div class="card" id="alerts"><h2>Public data boundary</h2>'
        '<p>This site publishes derived monitoring results and standardized completeness metrics. '
        'Provider connection URLs, internal fingerprints, raw change payloads, and operational controls are not exposed.</p></div><br>'
        '<div class="card" id="sources"><h2>Data being watched</h2>'
        '<div class="filters"><input id="q" placeholder="Filter datasets…" oninput="filterRows()">'
        '<select id="health" onchange="filterRows()"><option value="">All statuses</option>'
        '<option>ok</option><option>warn</option><option>error</option></select></div>'
        '<table id="datasets"><thead><tr><th>Data source</th><th>Provided by / type</th><th>Status</th>'
        '<th>Records</th><th>Changes found</th><th>Last successful check</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        '<script>function filterRows(){const q=document.getElementById("q").value.toLowerCase(),h=document.getElementById("health").value;'
        'document.querySelectorAll("#datasets tbody tr").forEach(r=>{r.style.display=(!q||r.dataset.name.includes(q))&&(!h||r.dataset.status===h)?"":"none"})}</script>'
    )
    return _layout("GIS Data Watchtower", body, refresh_seconds=30, static=True)


def render_public_source(config: dict, source_id: str) -> str:
    source = (_dashboard_state(config).get("sources") or {}).get(source_id)
    if not source:
        return _layout(
            "Source not found",
            '<div class="card"><h2>Source not found</h2><p><a href="/">Return to dashboard</a></p></div>',
            refresh_seconds=30,
            static=True,
        )

    body = (
        '<p><a href="/">← Watchtower overview</a></p>'
        '<div class="grid">'
        f'<div class="card"><div class="muted">Data source</div><h2>{_esc(source.get("name") or source_id)}</h2></div>'
        f'<div class="card"><div class="muted">Status</div><div class="metric {_status_class(source.get("status") or "unknown")}">{_esc(_health_status(source.get("status") or "unknown"))}</div></div>'
        f'<div class="card"><div class="muted">Records</div><div class="metric">{_esc(source.get("feature_count") or "—")}</div></div>'
        '</div>'
        '<div class="card"><h2>Public monitoring summary</h2><dl class="definition-list">'
        f'<dt>Provided by</dt><dd>{_esc(source.get("provider") or "—")}</dd>'
        f'<dt>Data type</dt><dd>{_esc(source.get("category") or "—")}</dd>'
        f'<dt>Latest successful check</dt><dd>{_esc(source.get("last_success_at") or source.get("checked_at") or "—")}</dd>'
        f'<dt>Reporting</dt><dd>{_esc(source.get("reporting") or "current")}</dd>'
        f'<dt>Changes found</dt><dd>{_esc(source.get("change_count") or 0)}</dd>'
        f'<dt>Information fields</dt><dd>{_esc(source.get("field_count") or "—")}</dd>'
        f'<dt>Missing parcel IDs</dt><dd>{_esc(source.get("parcel_id_null_count") if source.get("parcel_id_null_count") is not None else "Not checked")}</dd>'
        f'<dt>Duplicate-ID extra rows</dt><dd>{_esc(source.get("duplicate_id_extra_rows") if source.get("duplicate_id_extra_rows") is not None else "Not checked")}</dd>'
        f'<dt>Missing mapped shape</dt><dd>{_esc(source.get("null_geometry_count") if source.get("null_geometry_count") is not None else "Not checked")}</dd>'
        '</dl></div>'
    )
    return _layout(
        f'{source.get("name") or source_id} — GIS Data Watchtower',
        body,
        refresh_seconds=30,
        static=True,
    )


class _PublicStateCache:
    def __init__(self) -> None:
        self.root = Path(os.environ.get("WATCHTOWER_PUBLIC_WORKDIR", "/tmp/watchtower-public"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.raw_path = self.root / "aggregate-raw.json"
        self.public_path = self.root / "aggregate-public.json"
        self.history_path = self.root / "history-empty.jsonl"
        self.history_path.touch(exist_ok=True)
        self.storage = backend_from_env(self.root)
        self.object_name = os.environ.get("WATCHTOWER_AGGREGATE_OBJECT", "aggregate-state.json")
        self.refresh_seconds = max(5, min(int(os.environ.get("WATCHTOWER_PUBLIC_REFRESH_SECONDS", "30")), 300))
        self._last_refresh = 0.0
        self._lock = threading.Lock()

    @property
    def config(self) -> dict:
        return {
            "state_file": str(self.public_path),
            "aggregate_state_file": str(self.public_path),
            "history_file": str(self.history_path),
            "sources": [],
            "_public_mode": True,
            "worker_stale_minutes": int(os.environ.get("WATCHTOWER_WORKER_STALE_MINUTES", "1560")),
            "source_stale_minutes": int(os.environ.get("WATCHTOWER_SOURCE_STALE_MINUTES", "1560")),
        }

    def refresh(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and self.public_path.is_file() and now - self._last_refresh < self.refresh_seconds:
            return
        with self._lock:
            now = time.monotonic()
            if not force and self.public_path.is_file() and now - self._last_refresh < self.refresh_seconds:
                return
            if not self.storage.download(self.object_name, self.raw_path):
                raise FileNotFoundError(f"aggregate object not found: {self.object_name}")
            raw = json.loads(self.raw_path.read_text(encoding="utf-8"))
            public = sanitize_public_render_state(raw)
            tmp = self.public_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.public_path)
            self._last_refresh = now


def serve_public(host: str = "0.0.0.0", port: int = 8080) -> None:
    cache = _PublicStateCache()
    cache.refresh(force=True)
    max_connections = max(1, min(int(os.environ.get("WATCHTOWER_PUBLIC_MAX_CONNECTIONS", "64")), 256))

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content: str, content_type: str = "text/html; charset=utf-8"):
            raw = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "public, max-age=30")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(raw)

        def _send_bytes(self, status: int, raw: bytes, content_type: str, filename: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "public, max-age=30")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/healthz":
                try:
                    cache.refresh()
                    return self._send(200, '{"status":"ok"}', "application/json; charset=utf-8")
                except Exception:
                    return self._send(503, '{"status":"unavailable"}', "application/json; charset=utf-8")

            try:
                cache.refresh()
            except Exception:
                return self._send(503, "Dashboard data is temporarily unavailable.", "text/plain; charset=utf-8")

            config = cache.config
            if parsed.path == "/":
                return self._send(200, render_public_dashboard(config))
            if parsed.path == "/counties":
                return self._send(200, render_counties(config))
            if parsed.path == "/county":
                slug = urllib.parse.parse_qs(parsed.query).get("slug", [""])[0]
                return self._send(200, render_county(config, slug))
            if parsed.path == "/mngac":
                return self._send(200, render_mngac(config))
            if parsed.path == "/source":
                source_id = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
                return self._send(200, render_public_source(config, source_id))
            if parsed.path == "/api/state":
                return self._send(200, cache.public_path.read_text(encoding="utf-8"), "application/json; charset=utf-8")
            if parsed.path == "/snapshot.json":
                return self._send(200, json.dumps(_statewide_snapshot(config), indent=2), "application/json; charset=utf-8")
            if parsed.path == "/snapshot.csv":
                return self._send(200, _snapshot_csv(_statewide_snapshot(config)), "text/csv; charset=utf-8")
            if parsed.path == "/snapshot.xlsx":
                return self._send_bytes(
                    200,
                    _snapshot_xlsx(_statewide_snapshot(config)),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "watchtower-snapshot.xlsx",
                )
            if parsed.path == "/county-snapshot.json":
                slug = urllib.parse.parse_qs(parsed.query).get("slug", [""])[0]
                snap = _county_snapshot(config, slug)
                return self._send(200 if snap else 404, json.dumps(snap or {"error": "county not found"}, indent=2), "application/json; charset=utf-8")
            if parsed.path == "/county-snapshot.csv":
                slug = urllib.parse.parse_qs(parsed.query).get("slug", [""])[0]
                snap = _county_snapshot(config, slug)
                return self._send(200 if snap else 404, _snapshot_csv(snap) if snap else "county not found", "text/csv; charset=utf-8")
            if parsed.path == "/county-snapshot.xlsx":
                slug = urllib.parse.parse_qs(parsed.query).get("slug", [""])[0]
                snap = _county_snapshot(config, slug)
                if not snap:
                    return self._send(404, "county not found", "text/plain; charset=utf-8")
                return self._send_bytes(
                    200,
                    _snapshot_xlsx(snap),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    f"{slug}-watchtower.xlsx",
                )
            if parsed.path == "/mngac.json":
                data = _mngac_data(_dashboard_state(config))
                return self._send(200 if data else 404, json.dumps(data or {"error": "MNGAC completeness data unavailable"}, indent=2), "application/json; charset=utf-8")
            if parsed.path == "/mngac.csv":
                data = _mngac_data(_dashboard_state(config))
                return self._send(200 if data else 404, _mngac_csv(data) if data else "MNGAC completeness data unavailable", "text/csv; charset=utf-8")
            return self._send(404, "Not found", "text/plain; charset=utf-8")

        def do_POST(self):
            return self._send(405, "Method not allowed", "text/plain; charset=utf-8")

        def log_message(self, format, *args):
            return

    server = _BoundedThreadingHTTPServer((host, port), Handler, max_connections=max_connections)
    print(f"GIS Data Watchtower public dashboard: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
