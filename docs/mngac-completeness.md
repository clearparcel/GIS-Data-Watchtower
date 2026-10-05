# Minnesota GAC parcel-field completeness

Last reviewed: **2026-10-05**

GIS Data Watchtower can measure how extensively fields from the **Minnesota Geospatial Advisory Council (GAC) Parcel Data Standard** are populated in a standardized statewide parcel layer.

The feature is designed around the official **MN GAC Parcel Data Standard v1.1.3** (published 2023-10-27):

https://mn.gov/mngeo/assets/MN_GAC_Parcel_Data_Standard_tcm1235-753537.pdf

The standard currently defines **91 parcel-transfer fields** in six sections and four inclusion categories:

- **Mandatory**
- **Conditional**
- **If Available**
- **Optional**

## What the percentage means

A field's population percentage is:

`records containing a value / parcel records represented × 100`

This is a **data-population statistic, not a standards-compliance score**.

That distinction matters:

- a Conditional field may correctly be blank when its condition does not apply;
- an If Available field is required only when the source organization has the data;
- an Optional field may legitimately be blank;
- only the standard's Mandatory category is expected without those qualifications.

The dashboard therefore displays the standard inclusion category beside every field and presents Mandatory-field population separately.

## Current statewide source

The validated ClearParcel deployment calculates these statistics from MnGeo's standardized **Plan Parcels Open** parcel layer:

https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_mngeo/plan_parcels_open/FeatureServer/1

This source already uses the GAC transfer-schema field names, which gives counties one consistent comparison basis.

Counties that are not represented in the current MnGeo open parcel layer are displayed as **No data**. Watchtower never converts absence from the statewide open layer into a false 0% completeness value.

The number of represented counties is derived from each stored observation rather than hard-coded.

## Provider-friendly calculation

The monitor does not download all parcel records.

When `mngac_completeness` is enabled for a compatible ArcGIS layer, Watchtower sends a bounded ArcGIS grouped-statistics request that:

1. groups by `CO_NAME` and `CO_CODE`;
2. counts parcel records;
3. calculates populated-row counts for the standard fields; and
4. returns one summary row per represented county.

For the current 91-field MnGeo layer, Watchtower uses **eight bounded grouped-statistics requests** at the default batch size of 12 fields. This avoids one request per field or county while keeping each ArcGIS statistics expression set reasonably small.

The normal source cadence still controls how often these requests occur.

## Population rules

Watchtower uses the standard's data representation when deciding whether a field is populated:

- text: `NULL` or an empty string is unpopulated;
- numeric/date fields: `NULL` is unpopulated;
- the tax/value fields whose standard descriptions define `0` as **No value** and `-9999` as **No data** treat both values as unpopulated;
- other numeric values, including `0`, remain values unless the standard explicitly defines them otherwise.

The stored observation includes the calculation method so exports retain this provenance.

## County pages

When a county is represented in the statewide source, its dashboard page shows:

- parcel-record count used as the denominator;
- number of standard fields containing at least one value;
- population across all 91 fields;
- population across Mandatory fields;
- number of Mandatory fields populated for 100% of county records;
- all 91 fields with populated count, record count, percentage, section, and inclusion category.

County tables can be filtered by field name and inclusion category.

## Statewide MNGAC page

`/mngac` provides:

- an interactive Minnesota county map;
- selectable statistics for every standard field;
- all-field population and Mandatory-field views;
- a fields-with-any-values view;
- persistent click/keyboard county selection;
- exact selected-county counts and percentages;
- explicit No data counties;
- a statewide 91-field table with record-weighted population and median county population.

The map uses a simplified, packaged snapshot of official MnGeo county boundaries:

https://feat.gisdata.mn.gov/arcgis/rest/services/MnGeo/mn_counties/FeatureServer/0

Map geometry is presentation-only; it is not used to derive parcel statistics.

## Exports

MNGAC information is included in:

- county JSON snapshots;
- county CSV summary columns;
- statewide JSON;
- Excel sheets:
  - `MNGAC Counties`
  - `MNGAC Fields`
  - `MNGAC Detail`

County-specific Excel exports include an `MNGAC Fields` sheet.

## Configuration

A compatible ArcGIS layer can enable the scan with:

```json
"mngac_completeness": {
  "timeout_seconds": 90,
  "batch_size": 12
}
```

The default batch size is 12. On the current 91-field MnGeo statewide parcel layer this produces eight grouped-statistics requests. Batch size is capped at 20 so a configuration mistake cannot turn the scan into one oversized statistics expression set.

The source must contain `CO_NAME`, `CO_CODE`, an object-id field, and at least some standard GAC fields. Missing standard fields remain explicitly identified in the observation.
