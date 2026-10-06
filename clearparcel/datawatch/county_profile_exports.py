"""Deterministic, offline CSV and workbook tables for composed parcel profiles."""
from __future__ import annotations

import csv
import io
import re

from .parcel_access import INVENTORY_CATEGORIES
from .public_values import safe_public_url, spreadsheet_cell

SUMMARY_FIELDS = ('county', 'county_slug', 'county_fips', 'active', 'paths', 'health', 'reporting',
    'active_parcel_source_count', 'last_checked_at', 'last_success_at', 'aggregate_generated_at',
    'public_classification', 'detailed_classification', 'dataset_fee', 'fee_product',
    'monitoring_decision', 'research_complete', 'review_date', 'evidence_links', 'comments')
SOURCE_FIELDS = ('county', 'county_slug', 'county_fips', 'category', 'availability', 'review_status',
    'inventory_id', 'monitored_source_id', 'name', 'authority', 'dataset_type', 'layer_id',
    'approved_public_links', 'geometry_type', 'feature_count', 'feature_count_basis',
    'provider_updated_at', 'county_acquired_at', 'catalog_refreshed_at', 'checked_at',
    'last_success_at', 'health', 'reporting', 'execution_profile', 'monitoring_decision',
    'file_type', 'file_size_bytes', 'file_etag', 'file_last_modified')


def _links(links: list) -> str:
    return '; '.join(url for link in links if isinstance(link, dict)
                     and (url := safe_public_url(link.get('href'))))


def county_profile_summary(profile: dict) -> dict:
    """Flatten only the documented profile summary fields."""
    county, monitoring, access, research = (profile.get(k) or {} for k in ('county', 'monitoring', 'access', 'research'))
    return {'county': county.get('name'), 'county_slug': county.get('slug'), 'county_fips': county.get('fips'),
        **{k: monitoring.get(k) for k in SUMMARY_FIELDS[3:11]},
        'paths': '; '.join(monitoring.get('paths') or []),
        **{k: access.get(k) for k in SUMMARY_FIELDS[11:17]},
        'research_complete': research.get('complete'), 'review_date': research.get('review_date'),
        'evidence_links': _links(access.get('evidence_links') or []),
        'comments': '; '.join(profile.get('comments') or [])}


def _tables(profiles: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    summaries, sources = [], []
    for slug in sorted(profiles):
        profile = profiles[slug]
        summary = county_profile_summary(profile)
        summaries.append(summary)
        for category in INVENTORY_CATEGORIES:
            group = profile.get(category) or {}
            for source in group.get('sources') or [{}]:
                row = {k: summary[k] for k in ('county', 'county_slug', 'county_fips')}
                row.update(category=category, availability=group.get('availability'), review_status=group.get('review_status'))
                row.update({k: source.get(k) for k in SOURCE_FIELDS[6:25]})
                row['approved_public_links'] = _links(source.get('approved_public_links') or [])
                row.update({'file_' + k: (source.get('file') or {}).get(k) for k in ('type', 'size_bytes', 'etag', 'last_modified')})
                sources.append(row)
    return summaries, sources


def _csv(fields: tuple, rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    writer.writerows({k: spreadsheet_cell(row.get(k)) for k in fields} for row in rows)
    return out.getvalue()


def county_profiles_csv(profiles: dict[str, dict]) -> str:
    """Return one county summary row per composed profile."""
    return _csv(SUMMARY_FIELDS, _tables(profiles)[0])


def parcel_sources_csv(profiles: dict[str, dict]) -> str:
    """Return each category's sources, including empty-category placeholders."""
    return _csv(SOURCE_FIELDS, _tables(profiles)[1])


def county_profile_xlsx_sheets(profiles: dict[str, dict]) -> list[tuple[str, list[list]]]:
    """Return the same tables with numeric/boolean cells and literal safe text."""
    summaries, sources = _tables(profiles)
    def cell(value: object) -> object:
        if value is None or isinstance(value, (int, float, bool)):
            return value
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', spreadsheet_cell(value))
    return [(name, [list(fields)] + [[cell(row.get(k)) for k in fields] for row in rows])
            for name, fields, rows in [('County Access', SUMMARY_FIELDS, summaries), ('Parcel Sources', SOURCE_FIELDS, sources)]]
