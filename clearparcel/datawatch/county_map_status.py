"""Evidence-based map categories, independent of health and population rates."""
from __future__ import annotations

import html


MAP_STATUSES = {
    'standard': ('MN GAC data available', '#56b4e9', None),
    'different': ('Direct feed differs from MN GAC', '#e69f00', 'schema-lines'),
    'closed': ('No confirmed open parcel data', '#596577', 'closed-crosses'),
    'open-unassessed': ('Open data, schema unassessed', '#a88ac9', None),
    'unresolved': ('Open-data status unresolved', '#151d2b', 'unresolved-dots'),
}


def county_map_status(profile: dict) -> str:
    """Classify available datasets, never certify a county's compliance."""
    membership = (profile.get('mngac_public_parcels') or {}).get('availability')
    audits = profile.get('direct_gac_schema') or []
    if membership == 'yes' or any(a.get('status') == 'standard-field-names' for a in audits):
        return 'standard'
    if any(a.get('status') == 'schema-mismatch' for a in audits):
        return 'different'
    access = profile.get('access') or {}
    # Reachable REST services alone do not override fee/license policies.
    if access.get('public_classification') == 'OPEN':
        return 'open-unassessed'
    if membership == 'no' and access.get('public_classification') == 'FEE BASED':
        return 'closed'
    return 'unresolved'


def status_legend() -> str:
    return '<div class="mngac-legend" role="group" aria-label="Parcel data and schema legend">' + ''.join(
        f'<span><i class="mngac-swatch status-{key}" style="background-color:{color}"></i>{html.escape(label)}</span>'
        for key, (label, color, _) in MAP_STATUSES.items()) + '</div>'


def status_patterns() -> str:
    """Patterns also separate categories when colors cannot be distinguished."""
    return '''<defs>
<pattern id="schema-lines" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#e69f00"/><path d="M-2 2L2-2M0 8L8 0M6 10L10 6" stroke="#654900" stroke-width="1"/></pattern>
<pattern id="closed-crosses" width="10" height="10" patternUnits="userSpaceOnUse"><rect width="10" height="10" fill="#596577"/><path d="M2 2L8 8M8 2L2 8" stroke="#26303d" stroke-width="1"/></pattern>
<pattern id="unresolved-dots" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#151d2b"/><circle cx="4" cy="4" r="1" fill="#8593a6"/></pattern>
</defs>'''
