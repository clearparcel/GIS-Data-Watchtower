"""Small, sanitized dashboard contracts shared by charts and refresh checks."""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import statistics
from collections import Counter

from .gac_standards import standard_keys
from .public_projection import sanitize_public_render_state


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def catalog_summary(state: dict, county_names: list[str], *, now: dt.datetime | None = None) -> dict:
    source = state.get("sources", {}).get("mn-parcel-county-catalog", {})
    records = source.get("county_records") or {}
    available = isinstance(source.get("county_records"), dict) and (
        source.get("status") == "ok" or bool(records) or source.get("catalog_retained") is True)
    observed = source.get("catalog_observed_at") or source.get("last_success_at") or (
        source.get("checked_at") if source.get("status") == "ok" else None)
    buckets = dict.fromkeys(["0–30 days", "31–90 days", "91–365 days", "Over 1 year",
                            "Provider supplied no date", "No catalog entry", "Catalog unavailable"], 0)
    now = now or dt.datetime.now(dt.timezone.utc)
    for county in county_names:
        if not available:
            buckets["Catalog unavailable"] += 1
            continue
        if county not in records:
            buckets["No catalog entry"] += 1
            continue
        value = records[county].get("acqdate")
        try:
            date = (dt.datetime.fromtimestamp(value / 1000, dt.timezone.utc) if type(value) is int
                    else dt.datetime.fromisoformat(value.replace("Z", "+00:00")))
            if date.tzinfo is None:
                date = date.replace(tzinfo=dt.timezone.utc)
            days = max(0, (now - date).days)
            key = "0–30 days" if days <= 30 else "31–90 days" if days <= 90 else "91–365 days" if days <= 365 else "Over 1 year"
        except (AttributeError, ValueError, TypeError, OverflowError, OSError):
            key = "Provider supplied no date"
        buckets[key] += 1
    return {"buckets": buckets, "observed_at": observed,
            "latest_attempt_at": source.get("checked_at"), "status": source.get("status", "unknown"),
            "retained": source.get("catalog_retained") is True or (bool(records) and source.get("status") == "error"),
            "time_inferred": source.get("catalog_time_inferred") is True or bool(observed and not source.get("catalog_observed_at"))}


def build_summary(state: dict, profiles: dict, *, identity: dict, research: dict | None = None,
                  thresholds: dict | None = None) -> dict:
    from .dashboard import _gac_data, _gac_source

    public = sanitize_public_render_state(state)
    coverage = dict.fromkeys(["total", "statewide_only", "direct_only", "both", "neither"], 0)
    coverage["total"] = len(profiles)
    county_rows, category_statuses = [], Counter()
    for slug, profile in profiles.items():
        paths = set(profile.get("monitoring", {}).get("paths", []))
        key = ("both" if {"county-direct", "mngeo-open"} <= paths else
               "direct_only" if "county-direct" in paths else "statewide_only" if "mngeo-open" in paths else "neither")
        coverage[key] += 1
        category_statuses.update(profile.get("research", {}).get("category_review_statuses", {}).values())
        county_rows.append({"slug": slug, "name": profile["county"]["name"], "paths": sorted(paths)})
    standards = {}
    for key in standard_keys():
        data = _gac_data(public, key) or {}
        _, source = _gac_source(public, key)
        source = source or {}
        mandatory = [(name, field) for name, field in data.get("fields", {}).items()
                     if field.get("inclusion") == "Mandatory"]
        measured = [(name, field) for name, field in mandatory if field.get("population_scanned") is True
                    and type(field.get("populated")) is int and type(field.get("record_count")) is int]
        denominator = data.get("record_count")
        population = None
        if denominator and len(measured) == data.get("mandatory_field_count") and measured:
            population = round(100 * sum(field["populated"] for _, field in measured)
                               / (denominator * len(measured)), 2)
        rates = [c["mandatory_population_percent"] for c in data.get("counties", {}).values()
                 if c.get("mandatory_population_percent") is not None]
        gaps = [{"name": name, "label": field.get("label") or name,
                 "populated": field["populated"], "records": field["record_count"],
                 "unpopulated": max(0, field["record_count"] - field["populated"]),
                 "percent": round(100 * field["populated"] / field["record_count"], 2) if field["record_count"] else None}
                for name, field in measured]
        observed = data.get("observed_at") or source.get("last_success_at") or (
            source.get("checked_at") if source.get("status") == "ok" else None)
        standards[key] = {"version": data.get("standard", {}).get("version"),
            "covered_counties": len(data.get("counties", {})), "record_count": denominator,
            "field_count": data.get("field_count"), "scanned_field_count": data.get("scanned_field_count"),
            "mandatory_field_count": data.get("mandatory_field_count"), "population_scope": data.get("population_scope"),
            "mandatory_population_percent": population, "county_median_percent": round(statistics.median(rates), 2) if rates else None,
            "observed_at": observed, "time_inferred": bool(observed and not data.get("observed_at")),
            "latest_attempt_at": source.get("checked_at"), "status": source.get("status", "unknown"),
            "retained": source.get("gac_check_status") in {"error", "unsupported"} or source.get("status") == "error",
            "metadata_summary": data.get("metadata_summary", {}), "source_feature_count": data.get("source_feature_count"),
            "ungrouped_record_count": data.get("ungrouped_record_count"),
            "gaps": sorted(gaps, key=lambda f: (-f["unpopulated"], f["name"]))[:6]}
    stable = {k: v for k, v in public.items() if k != "public_published_at"}
    # Never hash relative ages/reporting labels: wall clock changes are not new observations.
    revision = _digest({"state": stable, "identity": identity, "research": research if research is not None else county_rows,
                        "thresholds": thresholds or {}})
    return {"schema_version": 1, "content_revision": revision, "public_published_at": public.get("public_published_at"),
            "generated_at": public.get("generated_at"), "coverage": coverage, "standards": standards,
            "counties": county_rows, "counts": public.get("counts", {}), "workers": public.get("workers", {}),
            "source_observations": {sid: {k: src.get(k) for k in ("status", "checked_at", "last_success_at")}
                                    for sid, src in public["sources"].items()},
            "research": {"total": len(profiles), "complete": sum(p.get("research", {}).get("complete") is True for p in profiles.values()),
                         "category_statuses": dict(category_statuses)}, "thresholds": thresholds or {}}


def summary_for(config: dict, state: dict, profiles: dict | None = None, research: dict | None = None) -> dict:
    from .dashboard import _county_profiles
    from .parcel_access import load_parcel_access
    from .build_info import application_identity
    research = research if research is not None else load_parcel_access()
    public = sanitize_public_render_state(state)
    profiles = profiles if profiles is not None else _county_profiles(config, public, research)
    return build_summary(public, profiles, identity=application_identity(), research=research,
                         thresholds={"source_stale_minutes": config.get("source_stale_minutes", 1560),
                                     "worker_stale_minutes": config.get("worker_stale_minutes", 1560),
                                     "publication_max_age_seconds": config.get("publication_max_age_seconds", 1800)})


def render_diagnostics(summary: dict) -> str:
    from .county_profile_panel import profile_time
    esc = lambda value: html.escape(str(value))
    pct = lambda value: "Not measured" if value is None else f"{value:.2f}%"
    coverage = summary["coverage"]
    path_rows = "".join(f'<tr><th scope="row">{label}</th><td>{coverage[key]}</td>'
                        f'<td><meter min="0" max="{max(1, coverage["total"])}" value="{coverage[key]}" aria-label="{label}">{coverage[key]}</meter></td></tr>'
                        for key, label in [("statewide_only", "MnGeo only"), ("direct_only", "County-direct only"),
                                           ("both", "Both paths"), ("neither", "Neither path")])
    rows, gaps = [], []
    for key, data in summary["standards"].items():
        label = {"parcel": "Parcels", "address": "Address points", "road": "Road centerlines"}[key]
        time = profile_time(data["observed_at"]) + (" (inferred from successful check)" if data["time_inferred"] else "")
        time += " · retained after failed check" if data["retained"] else ""
        rows.append(f'<tr><th scope="row"><a href="/mngac?standard={key}">{label}</a><br>v{esc(data["version"] or "unavailable")}</th>'
                    f'<td>{data["covered_counties"]}/{coverage["total"]}</td><td>{esc(data["record_count"] if data["record_count"] is not None else "Unavailable")}</td>'
                    f'<td>{esc(pct(data["mandatory_population_percent"]))}</td><td>{esc(pct(data["county_median_percent"]))}</td>'
                    f'<td>{esc(data["mandatory_field_count"] if data["mandatory_field_count"] is not None else "—")} mandatory; '
                    f'{esc(data["scanned_field_count"] if data["scanned_field_count"] is not None else "—")} scanned / '
                    f'{esc(data["field_count"] if data["field_count"] is not None else "—")} schema fields<br>{esc(data["population_scope"] or "Not measured")}</td>'
                    f'<td>{esc(time)}</td></tr>')
        field_rows = "".join(f'<tr><th scope="row">{esc(f["label"])} <code>{esc(f["name"])}</code></th>'
                             f'<td>{esc(pct(f["percent"]))}<br><meter min="0" max="100" value="{f["percent"] or 0}" aria-label="{esc(f["label"])} population">{esc(pct(f["percent"]))}</meter></td>'
                             f'<td>{f["populated"]:,} / {f["records"]:,}</td><td>{f["unpopulated"]:,}</td></tr>' for f in data["gaps"])
        gaps.append(f'<section data-gap-standard="{key}" {"hidden" if key != "parcel" else ""}><h3>{label}: mandatory-field gaps</h3>'
                    f'<p>{esc(time)} · Denominator: {esc(data["record_count"] if data["record_count"] is not None else "Unavailable")} records. '
                    'Six largest unpopulated counts; an unpopulated field does not establish an invalid record.</p>'
                    '<div class="table-scroll" tabindex="0" role="region" aria-label="Mandatory-field gaps"><table><thead><tr><th scope="col">Field</th><th scope="col">Population</th><th scope="col">Populated / records</th><th scope="col">Unpopulated records</th></tr></thead>'
                    f'<tbody>{field_rows}</tbody></table></div>' + ('<p>No scanned mandatory-field measurements available.</p>' if not field_rows else '')
                    + f'<a href="/mngac.csv?standard={key}">Download field measurements (CSV)</a></section>')
    road = summary["standards"]["road"]
    metadata = road["metadata_summary"]
    road_note = (f'<p>Road representation: {road["covered_counties"]} counties; GAC-open metadata: {metadata.get("gac_open_counties", "unavailable")}; '
                 f'represented without the open flag: {metadata.get("represented_without_gac_open", "unavailable")}. '
                 'The cause of this classification difference has not been established. '
                 f'Layer features: {road.get("source_feature_count")}; Minnesota grouped denominator: {road.get("record_count")}; '
                 f'records outside that denominator: {road.get("ungrouped_record_count")}.</p>' if metadata else '')
    return ('<div class="section-head"><h2>Coverage and field population</h2></div><div class="card">'
            '<h3>Parcel monitoring paths</h3><p>Unique counties; this measures observation paths, separately from access rights and source health.</p>'
            '<div class="table-scroll" tabindex="0" role="region" aria-label="Parcel monitoring paths"><table><thead><tr><th scope="col">Path</th><th scope="col">Counties</th><th scope="col">Share of counties</th></tr></thead>'
            f'<tbody>{path_rows}</tbody></table></div><a href="/county-profiles.csv">Download county profiles (CSV)</a></div>'
            '<div class="card"><h3>Three-standard comparison</h3><p>Record-weighted rates weight each mandatory cell; median county rates give each represented county one position. Population does not certify value accuracy or standards compliance.</p>'
            '<div class="table-scroll" tabindex="0" role="region" aria-label="Three-standard comparison"><table><thead><tr><th scope="col">Standard</th><th scope="col">County coverage</th><th scope="col">Record denominator</th><th scope="col">Mandatory population</th><th scope="col">Median county</th><th scope="col">Scan scope</th><th scope="col">Observation</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>{road_note}<a href="/snapshot.xlsx">Download standards workbook</a></div>'
            '<div class="card"><label for="gap-standard">Field-gap standard</label><select id="gap-standard"><option value="parcel">Parcels</option><option value="address">Address points</option><option value="road">Road centerlines</option></select>'
            + "".join(gaps) + '</div><script>document.getElementById("gap-standard").addEventListener("change",event=>{document.querySelectorAll("[data-gap-standard]").forEach(section=>{section.hidden=section.dataset.gapStandard!==event.target.value})});</script>')
