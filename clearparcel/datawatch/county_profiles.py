"""Offline composition of county research and source-specific observations."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from .parcel_access import INVENTORY_CATEGORIES
from .public_values import public_access_classification, safe_public_url, provider_edit_timestamp, sanitize_source_metadata


@dataclass(frozen=True)
class FreshnessPolicy:
    source_stale_minutes: int = 1560
    worker_stale_minutes: int = 1560


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp if stamp.tzinfo is not None else None
    except ValueError:
        return None


def _latest(values):
    valid = [(stamp, value) for value in values if (stamp := _timestamp(value)) is not None]
    return max(valid, key=lambda pair: pair[0])[1] if valid else None


def _links(values):
    return [{'label': item['label'], 'href': item['href']} for item in values
            if isinstance(item, dict) and isinstance(item.get('label'), str) and safe_public_url(item.get('href'))]


def _evidence(record):
    return [{'label': item.get('finding') or 'Official evidence', 'href': item['url']}
            for item in record.get('evidence', []) if isinstance(item, dict) and safe_public_url(item.get('url'))]


def _health(source, state, now, policy):
    checked = _timestamp(source.get('checked_at'))
    success = _timestamp(source.get('last_success_at'))
    health = source.get('status') if checked and source.get('status') in {'ok', 'warn', 'error'} else 'unknown'
    observed = success or checked
    reporting = 'unknown' if observed is None else 'overdue' if now - observed > dt.timedelta(minutes=policy.source_stale_minutes) else 'current'
    worker = (state.get('workers') or {}).get(source.get('worker'))
    if isinstance(worker, dict):
        report = _timestamp(worker.get('last_report_at')) or _timestamp(worker.get('checked_at'))
        if report is None:
            reporting = 'unknown' if reporting != 'overdue' else reporting
        elif now - report > dt.timedelta(minutes=policy.worker_stale_minutes):
            reporting = 'overdue'
    return health, reporting


def _source(item, observed, sid, state, now, policy, *, count=None, basis=None, catalog=None):
    observed = observed or {}
    metadata = sanitize_source_metadata(observed)
    health, reporting = _health(observed, state, now, policy)
    if basis is None:
        count = observed.get('feature_count')
        basis = 'source-feature-count' if type(count) is int and count >= 0 else None
    if type(count) is not int or count < 0:
        count = None
        basis = None
    catalog = catalog or {}
    file = metadata.get('file') or {}
    return {
        'inventory_id': item.get('inventory_id'), 'monitored_source_id': sid,
        'name': item.get('name') or observed.get('name'), 'authority': item.get('authority'),
        'dataset_type': item.get('dataset_type'), 'layer_id': item.get('layer_id'),
        'approved_public_links': _links(item.get('approved_public_links') or []),
        'geometry_type': metadata.get('geometry_type'), 'feature_count': count, 'feature_count_basis': basis,
        'provider_updated_at': metadata.get('provider_updated_at'),
        'county_acquired_at': provider_edit_timestamp(catalog.get('acqdate')),
        'catalog_refreshed_at': provider_edit_timestamp(catalog.get('rundate')),
        'checked_at': observed.get('checked_at') if _timestamp(observed.get('checked_at')) else None,
        'last_success_at': observed.get('last_success_at') if _timestamp(observed.get('last_success_at')) else None,
        'health': health, 'reporting': reporting, 'execution_profile': observed.get('worker'),
        'monitoring_decision': item.get('monitoring_decision'),
        'file': {key: file.get(key) for key in ('type', 'size_bytes', 'etag', 'last_modified')},
    }


def compose_county_profiles(state: dict, research: dict[str, dict], *, now: dt.datetime,
                            freshness_policy: FreshnessPolicy) -> dict[str, dict]:
    """Join approved evidence and observations without activating discoveries."""
    counties = json.loads(Path(__file__).with_name('minnesota_counties.json').read_text(encoding='utf-8'))['counties']
    boundaries = json.loads(Path(__file__).with_name('minnesota_county_boundaries.json').read_text(encoding='utf-8'))['counties']
    fips = {county['name']: '27' + county['fips'] for county in boundaries}
    sources = {sid: source for sid, source in (state.get('sources') or {}).items() if isinstance(source, dict)}
    statewide = next(((sid, source) for sid, source in sources.items()
                      if source.get('category') == 'Parcels' and isinstance(source.get('mngac_completeness'), dict)
                      and source['mngac_completeness'].get('fields') and source['mngac_completeness'].get('counties')), (None, None))
    statewide_id, statewide_source = statewide
    members = (statewide_source or {}).get('mngac_completeness', {}).get('counties', {})
    catalog_records = sources.get('mn-parcel-county-catalog', {}).get('county_records') or {}
    profiles = {}
    for county in counties:
        name, slug = county['name'], county['slug']
        record = research.get(name) or research.get(slug) or {}
        inventory = record.get('source_inventory') or {}
        direct = {sid: source for sid, source in sources.items() if sid != statewide_id
                  and sid != 'mn-parcel-county-catalog' and source.get('category') == 'Parcels'
                  and source.get('county_slug') == slug}
        categories = {}
        for category in INVENTORY_CATEGORIES:
            static = inventory.get(category) or {}
            composed = []
            for item in static.get('sources') or []:
                sid = item.get('monitored_source_id') or item.get('inventory_id')
                observed = direct.get(sid) if category in ('county_arcgis_rest', 'county_download') else None
                composed.append(_source(item, observed, sid if observed else item.get('monitored_source_id'),
                                        state, now, freshness_policy,
                                        catalog=catalog_records.get(name) if category == 'mngeo_public_repository' else None))
            categories[category] = {'availability': static.get('availability', 'unknown'),
                                    'review_status': static.get('review_status', 'pending'), 'sources': composed}
        # A missing statewide observation cannot confirm historical membership.
        categories['mngac_public_parcels']['availability'] = 'unknown' if statewide_source is None else 'yes' if isinstance(members.get(name), dict) else 'no'
        if isinstance(members.get(name), dict):
            item = {'inventory_id': None, 'name': 'MnGeo Plan Parcels Open', 'authority': 'statewide',
                    'dataset_type': 'parcels', 'approved_public_links': [], 'monitoring_decision': None}
            static_sources = (inventory.get('mngac_public_parcels') or {}).get('sources') or []
            item = next((source for source in static_sources
                         if (source.get('monitored_source_id') or source.get('inventory_id')) == statewide_id), item)
            categories['mngac_public_parcels']['sources'] = [source for source in categories['mngac_public_parcels']['sources']
                if source.get('inventory_id') != item.get('inventory_id')] + [_source(item, statewide_source, statewide_id,
                state, now, freshness_policy, count=members[name].get('record_count'),
                basis='statewide-county-record-count', catalog=catalog_records.get(name))]
        for sid, observed in direct.items():
            adapter = sanitize_source_metadata(observed).get('adapter')
            category = 'county_download' if adapter == 'http_file' else 'county_arcgis_rest' if adapter in ('arcgis_layer', 'arcgis_service') else None
            if category and not any(s.get('monitored_source_id') == sid for s in categories[category]['sources']):
                categories[category]['sources'].append(_source({}, observed, sid, state, now, freshness_policy))
        active = dict(direct)
        paths = ['county-direct'] if direct else []
        if isinstance(members.get(name), dict):
            active[statewide_id] = statewide_source
            paths.append('mngeo-open')
        statuses = [_health(source, state, now, freshness_policy) for source in active.values()]
        health = next((status for status in ('error', 'warn', 'unknown', 'ok') if any(h == status for h, _ in statuses)), 'unknown')
        reporting = next((status for status in ('overdue', 'unknown', 'current') if any(r == status for _, r in statuses)), 'unknown')
        evidence = _evidence(record)
        decision = (record.get('monitoring') or {}).get('decision')
        if slug in ('blue-earth', 'faribault', 'kandiyohi', 'lincoln'):
            decision = 'hold-for-terms'
        profiles[slug] = {
            'schema_version': 1, 'county': {**county, 'fips': fips[name]},
            'monitoring': {'active': bool(active), 'paths': paths, 'health': health, 'reporting': reporting,
                'active_parcel_source_count': len(active), 'last_checked_at': _latest(s.get('checked_at') for s in active.values()),
                'last_success_at': _latest(s.get('last_success_at') for s in active.values()),
                'aggregate_generated_at': state.get('generated_at') if _timestamp(state.get('generated_at')) else None},
            **categories,
            'access': {'public_classification': public_access_classification(record),
                'detailed_classification': record.get('county_direct_classification'),
                'dataset_fee': record.get('parcel_dataset_fee'), 'fee_product': record.get('fee_product'),
                'monitoring_decision': decision, 'evidence_links': evidence},
            'comments': [record['comments']] if record.get('comments') else [],
            'research': {'complete': record.get('research_complete') is True and all(
                categories[key]['review_status'] in ('reviewed', 'not-found') for key in INVENTORY_CATEGORIES),
                'review_date': record.get('review_date'),
                'category_review_statuses': {key: categories[key]['review_status'] for key in INVENTORY_CATEGORIES},
                'evidence_links': evidence},
        }
    return profiles


def county_profile_counts(profiles: dict[str, dict]) -> dict[str, int]:
    monitoring = [profile['monitoring'] for profile in profiles.values()]
    return {'total': len(profiles), 'active': sum(m['active'] for m in monitoring),
            'county_direct': sum('county-direct' in m['paths'] for m in monitoring),
            'mngeo_open': sum('mngeo-open' in m['paths'] for m in monitoring),
            'both': sum(set(m['paths']) == {'county-direct', 'mngeo-open'} for m in monitoring)}
