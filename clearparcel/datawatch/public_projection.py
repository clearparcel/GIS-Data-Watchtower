from __future__ import annotations

import datetime as dt
import math

from clearparcel.datawatch.public_values import safe_public_url, sanitize_source_metadata, _metadata_text


def _public_count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _public_number(value: object) -> int | float | None:
    return value if (type(value) is int and value >= 0) or (type(value) is float and math.isfinite(value) and value >= 0) else None


def _public_status(value: object) -> str | None:
    return value if isinstance(value, str) and value in {'ok', 'warn', 'error', 'unknown', 'unsupported'} else None


def _observation_status(value: object) -> str | None:
    return value if isinstance(value, str) and value in {'complete', 'partial', 'error', 'unsupported', 'unknown'} else None


def _public_date(value: object) -> str | None:
    if not isinstance(value, str) or not _metadata_text(value, 80):
        return None
    try:
        dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return value


def _catalog_date(value: object) -> int | str | None:
    return value if type(value) is int and 0 <= value <= 253402300799999 else _public_date(value)


def _approval(value: object) -> str | bool | None:
    return value if type(value) is bool or isinstance(value, str) and value.lower() in {'true', 'false', 'yes', 'no'} else None


def _project(record: object, schema: dict) -> dict:
    """Project known leaves through their types; never copy arbitrary objects."""
    if not isinstance(record, dict):
        return {}
    return {key: value for key, validate in schema.items()
            if (value := validate(record.get(key))) is not None}


def _records(value: object) -> dict:
    return value if isinstance(value, dict) else {}


_SOURCE_SCHEMA = {
    **{key: _metadata_text for key in ('id', 'name', 'provider', 'category', 'worker', 'county_slug')},
    **{key: _public_date for key in ('checked_at', 'last_success_at', 'last_report_at')},
    **{key: _public_count for key in ('feature_count', 'field_count', 'parcel_id_null_count',
        'duplicate_id_extra_rows', 'null_geometry_count')},
    **{key: _public_number for key in ('geometry_sample_multipart_percent', 'geometry_sample_avg_vertices', 'elapsed_ms')},
    'status': _public_status,
    'gac_check_status': _public_status,
    'gac_check_error': lambda value: _metadata_text(value, 280),
    'catalog_observed_at': _public_date,
    **{key: lambda value: value if type(value) is bool else None
       for key in ('catalog_retained', 'catalog_time_inferred')},
}
_WORKER_SCHEMA = {**{key: _public_date for key in ('checked_at', 'last_success_at', 'last_report_at')},
                  'overall': _public_status, 'source_count': _public_count}
_COMPLETENESS_SCHEMA = {'field': _metadata_text, 'missing': _public_count, 'populated': _public_count,
                        'complete_percent': _public_number, 'status': _public_status}


def _sanitize_completeness(value: object) -> dict:
    return {key: _project(record, _COMPLETENESS_SCHEMA)
            for key, record in _records(value).items()
            if key in ('parcel_id', 'owner', 'site_address', 'mailing_address') and isinstance(record, dict)}


def _sanitize_catalog_records(records: object) -> dict:
    schema = {'gac_open_approval': _approval, 'acqdate': _catalog_date, 'rundate': _catalog_date,
              'data_url': safe_public_url, 'viewer_url': safe_public_url}
    return {county: _project(record, schema) for county, record in _records(records).items()
            if _metadata_text(county) and isinstance(record, dict)}


def _sanitize_mngac(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    field_schema = {
        **{key: _metadata_text for key in ('label', 'section_name', 'inclusion', 'data_type')},
        'section': _public_count,
        'present_in_source_schema': lambda value: value if type(value) is bool else None,
        'population_scanned': lambda value: value if type(value) is bool else None,
        **{key: _public_count for key in (
            'populated', 'record_count', 'counties_with_values', 'counties_covered',
        )},
        'observation_status': _public_status,
        'observed_at': _public_date,
        **{key: _public_number for key in ('percent', 'county_median_percent')},
    }
    county_schema = {
        **{key: _public_count for key in (
            'record_count', 'fields_with_values', 'field_count', 'scanned_field_count',
            'scanned_fields_with_values', 'mandatory_fields_full', 'mandatory_field_count',
        )},
        'population_scope': _metadata_text,
        **{key: _public_number for key in ('field_population_percent', 'mandatory_population_percent')},
    }
    metadata_schema = {
        **{key: _metadata_text for key in ('county_name', 'county_code', 'county_fips')},
        'gac_open': lambda value: value if type(value) is bool else None,
        'ng911_upload': lambda value: value if type(value) is bool else None,
        'submitted_at': _public_date,
    }

    def fields(records):
        return {name: _project(record, field_schema) for name, record in _records(records).items()
                if _metadata_text(name, 128) and isinstance(record, dict)}

    public = _project(data, {
        'method': _metadata_text,
        'observed_at': _public_date,
        'observation_status': _observation_status,
        'standard_key': _metadata_text,
        'population_scope': _metadata_text,
        'text_population_mode': _metadata_text,
        **{key: _public_count for key in (
            'record_count', 'field_count', 'scanned_field_count', 'covered_counties',
            'mandatory_field_count', 'excluded_county_groups',
            'source_feature_count', 'ungrouped_record_count',
        )},
        **{key: _public_number for key in ('field_population_percent', 'mandatory_population_percent')},
    })
    standard = data.get('standard')
    public['standard'] = _project(
        standard,
        {'key': _metadata_text, 'name': _metadata_text, 'short_name': _metadata_text,
         'version': _metadata_text, 'published': _public_date, 'published_at': _public_date},
    )
    link = safe_public_url(standard.get('source_url')) if isinstance(standard, dict) else None
    if link:
        public['standard']['source_url'] = link
    public['fields'] = fields(data.get('fields'))
    public['counties'] = {}
    counties = data.get('counties')
    for county, record in (counties if isinstance(counties, dict) else {}).items():
        if _metadata_text(county) and isinstance(record, dict):
            public['counties'][county] = {**_project(record, county_schema), 'fields': fields(record.get('fields'))}
    metadata = data.get('county_metadata')
    if isinstance(metadata, dict):
        public['county_metadata'] = {
            county: _project(record, metadata_schema)
            for county, record in metadata.items()
            if _metadata_text(county) and isinstance(record, dict)
        }
    metadata_summary = data.get('metadata_summary')
    if isinstance(metadata_summary, dict):
        public['metadata_summary'] = _project(
            metadata_summary,
            {key: _public_count for key in (
                'metadata_counties', 'ng911_participants', 'gac_open_counties',
                'represented_without_gac_open', 'gac_open_without_representation',
            )},
        )
    missing = data.get('source_schema_missing_fields')
    if isinstance(missing, list):
        public['source_schema_missing_fields'] = [name for name in missing if _metadata_text(name, 128)]
    return public if public.get("fields") and public.get("counties") else None


_sanitize_gac = _sanitize_mngac


def sanitize_public_render_state(state: dict) -> dict:
    """Reduce aggregate state to facts intentionally safe for anonymous display."""
    public = {key: validate(state.get(key)) for key, validate in {
        'schema_version': _public_count, 'generated_at': _public_date,
        'public_published_at': _public_date, 'overall': _public_status}.items()}
    public.update(counts=_project(state.get('counts'), {key: _public_count for key in ('ok', 'warn', 'error')}),
                  workers={}, sources={}, retired_sources={}, retired_workers={})
    for name, worker in _records(state.get('retired_workers')).items():
        if _metadata_text(name) and isinstance(worker, dict):
            public['retired_workers'][name] = _project(worker, {**_WORKER_SCHEMA, 'retired_at': _public_date})
    for source_id, record in _records(state.get('retired_sources')).items():
        if _metadata_text(source_id) and isinstance(record, dict):
            public['retired_sources'][source_id] = _project(
                record, {'worker': _metadata_text, 'retired_at': _public_date}
            )

    for worker_name, worker in _records(state.get('workers')).items():
        if _metadata_text(worker_name) and isinstance(worker, dict):
            public['workers'][worker_name] = _project(worker, _WORKER_SCHEMA)

    for source_id, source in _records(state.get('sources')).items():
        if not _metadata_text(source_id) or not isinstance(source, dict):
            continue
        summary = _project(source, _SOURCE_SCHEMA)
        summary['id'] = summary.get('id') or source_id
        summary['status'] = summary.get('status') or 'unknown'
        changes = source.get('changes')
        summary['change_count'] = len(changes) if isinstance(changes, list) else (_public_count(source.get('change_count')) or 0)
        if isinstance(source.get('completeness_profiles'), dict):
            summary['completeness_profiles'] = _sanitize_completeness(source['completeness_profiles'])
        metadata = sanitize_source_metadata(source)
        if metadata:
            summary['public_metadata'] = metadata

        if source_id == "mn-parcel-county-catalog":
            summary["county_records"] = _sanitize_catalog_records(source.get("county_records"))

        gac = _sanitize_gac(source.get("gac_completeness"))
        if gac:
            summary["gac_completeness"] = gac
        mngac = _sanitize_mngac(source.get("mngac_completeness"))
        if mngac:
            summary["mngac_completeness"] = mngac

        public["sources"][str(source_id)] = summary

    return public
