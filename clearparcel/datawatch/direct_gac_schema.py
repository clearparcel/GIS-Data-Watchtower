"""Offline, source-specific MN GAC parcel transfer-schema evidence."""
from __future__ import annotations

from functools import lru_cache
import json
import re
from pathlib import Path

from .gac_standards import load_gac_standard, canonical_minnesota_county


@lru_cache(maxsize=1)
def load_direct_schema_assessments() -> dict[str, dict]:
    """Load audited public schemas, rejecting inconsistent field evidence."""
    data = json.loads(Path(__file__).with_name('county_direct_gac_schema.json').read_text(encoding='utf-8'))
    schema = load_gac_standard('parcel')
    fields = {field['field'] for field in schema['fields']}
    if data['schema_version'] != 1 or data['standard_version'] != schema['standard']['version']:
        raise ValueError('Direct schema audit needs review against the current standard')
    records = {}
    for record in data['assessments']:
        matches = record['matched_fields']
        if record['source_id'] in records or len(set(matches)) != len(matches) or not set(matches) <= fields:
            raise ValueError('Invalid direct schema field evidence')
        if record['status'] not in {'checked', 'schema-unavailable'}:
            raise ValueError('Invalid direct schema audit status')
        records[record['source_id']] = record
    return records


def observed_standard_field_names(source: dict) -> list[str] | None:
    """MN GAC parcel field names present in the source's current schema, as the standard spells them.

    Matching follows the audit method: physical names, case-insensitive, no
    aliases. Private state carries every ``field_names``; the public projection
    carries only this standard-name subset. ``None`` means no current evidence.
    """
    names = source.get('field_names')
    if not (isinstance(names, list) and all(isinstance(name, str) for name in names)):
        names = source.get('gac_standard_field_names')
        if not (isinstance(names, list) and all(isinstance(name, str) for name in names)):
            return None
    present = {name.casefold() for name in names}
    return sorted(field['field'] for field in load_gac_standard('parcel')['fields'] if field['field'].casefold() in present)


def direct_schema_assessment(source_id: str, source: dict) -> dict:
    """Assess only the exact audited county/source, never statewide membership."""
    record = load_direct_schema_assessments().get(source_id)
    county = canonical_minnesota_county(record['county']) if record else None
    slug = re.sub(r'[^a-z0-9]+', '-', county.casefold()).strip('-') if county else None
    if not record or not county or source.get('county_slug') != slug or source.get('category') != 'Parcels':
        return {'status': 'not-assessed', 'label': 'Direct feed not assessed', 'source_id': source_id}
    schema = load_gac_standard('parcel')
    mandatory = {field['field'] for field in schema['fields'] if field['inclusion'] == 'Mandatory'}
    matched = set(record['matched_fields'])
    checked = record['status'] == 'checked'
    observed = observed_standard_field_names(source)
    count_changed = checked and type(source.get('field_count')) is int and source['field_count'] != record['field_count']
    # A rename can keep the count; compare the audited standard names themselves when known.
    names_changed = checked and observed is not None and set(observed) != matched
    changed = count_changed or names_changed
    status = 'needs-recheck' if changed else 'not-assessed' if not checked else 'standard-field-names' if len(matched) == len(schema['fields']) else 'schema-mismatch'
    labels = {'needs-recheck': 'Direct feed schema needs recheck', 'not-assessed': 'Direct feed not assessed',
              'standard-field-names': 'Direct feed has all MN GAC field names',
              'schema-mismatch': 'Direct feed does not match the MN GAC transfer schema'}
    return {'status': status, 'label': labels[status], 'source_id': source_id, 'name': source.get('name') or source_id,
            'checked_at': record['checked_at'], 'evidence_url': record['url'],
            'adoption_evidence_url': record.get('adoption_evidence_url'),
            'reason': ('Observed field count changed since the schema audit.' if count_changed
                       else 'Observed MN GAC field names changed since the schema audit.' if names_changed
                       else record.get('reason')),
            'standard_version': schema['standard']['version'],
            'standard_fields_present': len(matched) if checked else None,
            'standard_field_count': len(schema['fields']),
            'mandatory_fields_present': len(matched & mandatory) if checked else None,
            'mandatory_field_count': len(mandatory),
            'missing_mandatory_fields': sorted(mandatory - matched) if checked else []}
