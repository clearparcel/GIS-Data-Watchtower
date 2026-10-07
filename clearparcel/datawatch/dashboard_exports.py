from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile

from clearparcel.datawatch.county_profile_exports import SUMMARY_FIELDS, county_profile_summary, county_profile_xlsx_sheets
from clearparcel.datawatch.gac_standards import load_gac_standard, normalize_standard_key, standard_keys
from clearparcel.datawatch.public_values import spreadsheet_cell


def _load_mngac_schema() -> dict:
    """Backward-compatible parcel standard loader for export builders."""
    try:
        return load_gac_standard("parcel")
    except (OSError, json.JSONDecodeError):
        return {"standard": {}, "fields": []}


def _mngac_csv(data: dict | None) -> str:
    out = io.StringIO()
    fields = [
        "element","field","section","inclusion","data_type","counties_with_values",
        "counties_represented","populated_records","record_count","statewide_population_percent",
        "median_county_population_percent",
    ]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    if not isinstance(data, dict):
        return out.getvalue()
    try:
        standard_key = normalize_standard_key(
            data.get("standard_key") or (data.get("standard") or {}).get("key") or "parcel"
        )
        schema = load_gac_standard(standard_key)
    except (ValueError, OSError, json.JSONDecodeError):
        schema = _load_mngac_schema()
    summaries = data.get("fields") or {}
    for spec in schema.get("fields") or []:
        field = str(spec.get("field") or "")
        stats = summaries.get(field) or {}
        writer.writerow({key: _csv_safe(value) for key, value in {
            "element": spec.get("label"),
            "field": field,
            "section": spec.get("section_name"),
            "inclusion": spec.get("inclusion"),
            "data_type": spec.get("data_type"),
            "counties_with_values": stats.get("counties_with_values"),
            "counties_represented": stats.get("counties_covered"),
            "populated_records": stats.get("populated"),
            "record_count": stats.get("record_count"),
            "statewide_population_percent": stats.get("percent"),
            "median_county_population_percent": stats.get("county_median_percent"),
        }.items()})
    return out.getvalue()


def _csv_safe(value) -> str:
    return spreadsheet_cell(value)


def _snapshot_csv(snapshot: dict) -> str:
    out = io.StringIO()
    if "sources" in snapshot:
        fields = ["source_id","source_name","county","status","feature_count","worker","reporting","stale_source","stale_worker","last_success_at","checked_at"]
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for source in snapshot.get("sources", []):
            writer.writerow({key: _csv_safe(value) for key, value in {
                "source_id": source.get("id"),
                "source_name": source.get("name"),
                "county": source.get("county"),
                "status": source.get("status"),
                "feature_count": source.get("feature_count"),
                "worker": source.get("worker"),
                "reporting": source.get("reporting"),
                "stale_source": source.get("stale"),
                "stale_worker": source.get("worker_stale"),
                "last_success_at": source.get("last_success_at"),
                "checked_at": source.get("checked_at"),
            }.items()})
        return out.getvalue()
    fields = ["county","status","actively_monitored","monitoring_path","county_direct_access","statewide_open_access","county_direct_source_count","parcel_dataset_fee","fee_product","last_county_update","catalog_refresh_date","public_data_approved","parcel_data_url","parcel_viewer_url","worker_provenance","stale_source_count","contact_names","contact_source","contact_source_url","contact_verified","mngac_record_count","mngac_fields_with_values","mngac_field_count","mngac_field_population_percent","mngac_mandatory_population_percent",
              "address_record_count","address_mandatory_population_percent","address_ng911_participant","address_gac_public_opt_in","address_submitted_at",
              "road_record_count","road_mandatory_population_percent","road_ng911_participant","road_gac_public_opt_in","road_submitted_at"]
    fields += ["profile_" + key for key in SUMMARY_FIELDS]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in [snapshot]:
        writer.writerow({key: _csv_safe(value) for key, value in {
            **{"profile_" + key: value for key, value in county_profile_summary(row.get("parcel_source_profile") or {}).items()},
            "county": row.get("county"), "status": row.get("status"),
            "actively_monitored": row.get("actively_monitored"),
            "monitoring_path": row.get("monitoring_path_label"),
            "county_direct_access": (row.get("parcel_access") or {}).get("county_direct_label"),
            "statewide_open_access": (row.get("parcel_access") or {}).get("statewide_open_label"),
            "county_direct_source_count": len(row.get("direct_sources") or []),
            "parcel_dataset_fee": (row.get("parcel_access") or {}).get("parcel_dataset_fee"),
            "fee_product": (row.get("parcel_access") or {}).get("fee_product"),
            "last_county_update": row.get("last_county_update"),
            "catalog_refresh_date": row.get("catalog_refresh_date"),
            "public_data_approved": row.get("public_data_approved"),
            "parcel_data_url": row.get("parcel_data_url"),
            "parcel_viewer_url": row.get("parcel_viewer_url"),
            "worker_provenance": "; ".join(sorted({str(x.get("worker")) for x in row.get("direct_sources",[]) if x.get("worker")})),
            "stale_source_count": sum(1 for x in row.get("direct_sources",[]) if x.get("stale") or x.get("worker_stale")),
            "contact_names": "; ".join(x.get("name","") for x in row.get("contacts",[]) if x.get("name")),
            "contact_source": row.get("contact_source"),
            "contact_source_url": row.get("contact_source_url"),
            "contact_verified": row.get("contact_verified"),
            "mngac_record_count": (((row.get("mngac") or {}).get("county") or {}).get("record_count")),
            "mngac_fields_with_values": (((row.get("mngac") or {}).get("county") or {}).get("fields_with_values")),
            "mngac_field_count": (((row.get("mngac") or {}).get("county") or {}).get("field_count")),
            "mngac_field_population_percent": (((row.get("mngac") or {}).get("county") or {}).get("field_population_percent")),
            "mngac_mandatory_population_percent": (((row.get("mngac") or {}).get("county") or {}).get("mandatory_population_percent")),
            "address_record_count": ((((row.get("gac") or {}).get("address") or {}).get("county") or {}).get("record_count")),
            "address_mandatory_population_percent": ((((row.get("gac") or {}).get("address") or {}).get("county") or {}).get("mandatory_population_percent")),
            "address_ng911_participant": ((((row.get("gac") or {}).get("address") or {}).get("metadata") or {}).get("ng911_upload")),
            "address_gac_public_opt_in": ((((row.get("gac") or {}).get("address") or {}).get("metadata") or {}).get("gac_open")),
            "address_submitted_at": ((((row.get("gac") or {}).get("address") or {}).get("metadata") or {}).get("submitted_at")),
            "road_record_count": ((((row.get("gac") or {}).get("road") or {}).get("county") or {}).get("record_count")),
            "road_mandatory_population_percent": ((((row.get("gac") or {}).get("road") or {}).get("county") or {}).get("mandatory_population_percent")),
            "road_ng911_participant": ((((row.get("gac") or {}).get("road") or {}).get("metadata") or {}).get("ng911_upload")),
            "road_gac_public_opt_in": ((((row.get("gac") or {}).get("road") or {}).get("metadata") or {}).get("gac_open")),
            "road_submitted_at": ((((row.get("gac") or {}).get("road") or {}).get("metadata") or {}).get("submitted_at")),
        }.items()})
    return out.getvalue()


def _xlsx_col_name(index: int) -> str:
    out = ""
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out

def _xlsx_sheet_xml(rows: list[list]) -> str:
    xml_rows = []
    for r_idx, row in enumerate(rows, 1):
        cells = []
        for c_idx, value in enumerate(row, 1):
            ref = f"{_xlsx_col_name(c_idx)}{r_idx}"
            if isinstance(value, bool):
                cells.append(f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>')
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = html.escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", spreadsheet_cell(value)), quote=False)
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + '</sheetData></worksheet>'

def _mngac_xlsx_sheets(snapshot: dict) -> list[tuple[str, list[list]]]:
    data = snapshot.get("mngac")
    if not isinstance(data, dict):
        return []
    schema = _load_mngac_schema()
    specs = schema.get("fields") or []
    sheets = []
    if data.get("counties") and data.get("fields"):
        county_rows = [[
            "County","County code","Parcel records","Fields with any values","Standard fields",
            "All-field population percent","Mandatory population percent",
            "Mandatory fields 100% populated","Mandatory field count"
        ]]
        for name, county in sorted((data.get("counties") or {}).items()):
            county_rows.append([
                name,county.get("county_code"),county.get("record_count"),county.get("fields_with_values"),
                county.get("field_count"),county.get("field_population_percent"),county.get("mandatory_population_percent"),
                county.get("mandatory_fields_full"),county.get("mandatory_field_count"),
            ])
        field_rows = [[
            "Element","Field","Section","Inclusion","Data type","Counties with values",
            "Counties represented","Populated records","Record count","Statewide population percent",
            "Median county population percent"
        ]]
        for spec in specs:
            field = spec.get("field")
            stats = (data.get("fields") or {}).get(field) or {}
            field_rows.append([
                spec.get("label"),field,spec.get("section_name"),spec.get("inclusion"),spec.get("data_type"),
                stats.get("counties_with_values"),stats.get("counties_covered"),stats.get("populated"),
                stats.get("record_count"),stats.get("percent"),stats.get("county_median_percent"),
            ])
        detail_rows = [["County","Field","Element","Inclusion","Populated records","Record count","Population percent"]]
        for county_name, county in sorted((data.get("counties") or {}).items()):
            fields = county.get("fields") or {}
            for spec in specs:
                field = spec.get("field")
                stats = fields.get(field) or {}
                detail_rows.append([
                    county_name,field,spec.get("label"),spec.get("inclusion"),stats.get("populated"),
                    stats.get("record_count"),stats.get("percent"),
                ])
        sheets.extend([
            ("MNGAC Counties", county_rows),
            ("MNGAC Fields", field_rows),
            ("MNGAC Detail", detail_rows),
        ])
    elif isinstance(data.get("county"), dict):
        county = data.get("county") or {}
        field_rows = [["Field","Element","Section","Inclusion","Populated records","Record count","Population percent"]]
        for spec in specs:
            field = spec.get("field")
            stats = (county.get("fields") or {}).get(field) or {}
            field_rows.append([
                field,spec.get("label"),spec.get("section_name"),spec.get("inclusion"),stats.get("populated"),
                stats.get("record_count"),stats.get("percent"),
            ])
        sheets.append(("MNGAC Fields", field_rows))
    return sheets


def _gac_xlsx_sheets(snapshot: dict) -> list[tuple[str, list[list]]]:
    gac = snapshot.get("gac")
    if not isinstance(gac, dict) or not gac:
        return []

    standard_rows = [[
        "Standard","Name","Version","Standard fields","Mandatory fields","Population scope",
        "Counties represented","Record count","All-field population percent",
        "Mandatory population percent","NG911 participants","GAC public opt-ins"
    ]]
    county_rows = [[
        "Standard","County","Public records","All-field population percent",
        "Mandatory population percent","Fields with values","Standard fields",
        "NG911 participant","GAC public opt-in","Latest reported submission"
    ]]
    field_rows = [[
        "Standard","Element","Field","Section","Inclusion","Data type","Schema present",
        "Population scanned","Counties with values","Counties represented","Populated records",
        "Record count","Statewide population percent","Median county population percent"
    ]]
    detail_rows = [[
        "Standard","County","Field","Element","Inclusion","Population scanned",
        "Populated records","Record count","Population percent"
    ]]

    for standard_key in standard_keys():
        data = gac.get(standard_key)
        if not isinstance(data, dict):
            continue
        schema = load_gac_standard(standard_key)
        standard = data.get("standard") or schema.get("standard") or {}
        metadata_summary = data.get("metadata_summary") or {}
        standard_rows.append([
            standard_key, standard.get("short_name") or standard.get("name"),
            standard.get("version"), data.get("field_count") or len(schema.get("fields") or []),
            data.get("mandatory_field_count"), data.get("population_scope"),
            data.get("covered_counties"), data.get("record_count"),
            data.get("field_population_percent"), data.get("mandatory_population_percent"),
            metadata_summary.get("ng911_participants"), metadata_summary.get("gac_open_counties"),
        ])

        if isinstance(data.get("county"), dict) or data.get("metadata"):
            county_name = snapshot.get("county")
            county_items = [(county_name, data.get("county"), data.get("metadata") or {})]
        else:
            counties = data.get("counties") or {}
            metadata = data.get("county_metadata") or {}
            names = sorted(set(counties) | set(metadata))
            county_items = [(name, counties.get(name), metadata.get(name) or {}) for name in names]

        for county_name, county, metadata in county_items:
            county = county if isinstance(county, dict) else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            county_rows.append([
                standard_key, county_name, county.get("record_count"),
                county.get("field_population_percent"), county.get("mandatory_population_percent"),
                county.get("fields_with_values"), county.get("field_count"),
                metadata.get("ng911_upload"), metadata.get("gac_open"), metadata.get("submitted_at"),
            ])

        summaries = data.get("fields") or {}
        for spec in schema.get("fields") or []:
            field = str(spec.get("field") or "")
            stats = summaries.get(field) or {}
            field_rows.append([
                standard_key, spec.get("label"), field, spec.get("section_name"),
                spec.get("inclusion"), spec.get("data_type"),
                stats.get("present_in_source_schema"),
                stats.get("population_scanned"),
                stats.get("counties_with_values"), stats.get("counties_covered"),
                stats.get("populated"), stats.get("record_count"), stats.get("percent"),
                stats.get("county_median_percent"),
            ])

        for county_name, county, _metadata in county_items:
            county = county if isinstance(county, dict) else {}
            fields = county.get("fields") or {}
            for spec in schema.get("fields") or []:
                field = str(spec.get("field") or "")
                stats = fields.get(field) or {}
                detail_rows.append([
                    standard_key, county_name, field, spec.get("label"), spec.get("inclusion"),
                    field in fields, stats.get("populated"), stats.get("record_count"),
                    stats.get("percent"),
                ])

    return [
        ("GAC Standards", standard_rows),
        ("GAC Counties", county_rows),
        ("GAC Fields", field_rows),
        ("GAC Detail", detail_rows),
    ]


def _snapshot_xlsx(snapshot: dict) -> bytes:
    county_rows = [["County","Status","Actively monitored","Monitoring path","County-direct access","Statewide open access","County-direct source count","Parcel dataset fee","Fee product","Last county update","Catalog refresh date","Public data approved","Parcel data URL","Parcel viewer URL","Contact names","Contact source","Contact source URL","Contact verified"]]
    source_rows = [["County","Source","Status","Record count","Worker","Reporting","Stale source","Stale worker","Last successful check","Last checked"]]
    contact_rows = [["County","Name","Title","Department","Phone","Email","Contact source","Contact source URL","Verified"]]
    rows = snapshot.get("counties") if "counties" in snapshot else [snapshot]
    for row in rows:
        county = row.get("county") or ""
        parcel_access = row.get("parcel_access") or {}
        county_rows.append([
            county,row.get("status"),bool(row.get("actively_monitored")),row.get("monitoring_path_label"),
            parcel_access.get("county_direct_label"),parcel_access.get("statewide_open_label"),
            len(row.get("direct_sources") or []),parcel_access.get("parcel_dataset_fee"),parcel_access.get("fee_product"),
            row.get("last_county_update"),row.get("catalog_refresh_date"),bool(row.get("public_data_approved")),
            row.get("parcel_data_url"),row.get("parcel_viewer_url"),
            "; ".join(x.get("name","") for x in row.get("contacts",[]) if x.get("name")),
            row.get("contact_source"),row.get("contact_source_url"),row.get("contact_verified"),
        ])
        for source in row.get("direct_sources", []):
            if "sources" not in snapshot:
                source_rows.append([county,source.get("name"),source.get("status"),source.get("feature_count"),source.get("worker"),source.get("reporting"),bool(source.get("stale")),bool(source.get("worker_stale")),source.get("last_success_at"),source.get("checked_at")])
        for contact in row.get("contacts", []):
            contact_rows.append([county,contact.get("name"),contact.get("title"),contact.get("department"),contact.get("phone"),contact.get("email"),row.get("contact_source"),row.get("contact_source_url"),row.get("contact_verified")])
    if "sources" in snapshot:
        for source in snapshot.get("sources", []):
            source_rows.append([source.get("county"),source.get("name"),source.get("status"),source.get("feature_count"),source.get("worker"),source.get("reporting"),bool(source.get("stale")),bool(source.get("worker_stale")),source.get("last_success_at"),source.get("checked_at")])
    sheets=[("Counties",county_rows),("Sources",source_rows),("Contacts",contact_rows)]
    sheets.extend(_mngac_xlsx_sheets(snapshot))
    sheets.extend(_gac_xlsx_sheets(snapshot))
    profiles = {row["parcel_source_profile"]["county"]["slug"]: row["parcel_source_profile"] for row in rows if row.get("parcel_source_profile")}
    sheets.extend(county_profile_xlsx_sheets(profiles))
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>')
        zf.writestr("_rels/.rels",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{html.escape(name,quote=True)}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+'</Relationships>')
        for i,(_,data) in enumerate(sheets,1): zf.writestr(f"xl/worksheets/sheet{i}.xml",_xlsx_sheet_xml(data))
    return out.getvalue()
