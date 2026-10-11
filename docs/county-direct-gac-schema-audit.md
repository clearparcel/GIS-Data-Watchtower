# County-direct coverage and MN GAC transfer schemas

Verified 2026-10-10 on GERTKEN-PC. County-direct inventory is the saved October 9 public observation; statewide membership was checked live at 21:11 CDT on October 10.

## Coverage

County-direct means a county-specific monitored product, including a county product hosted by the state. It does not mean the county is absent from MnGeo Open Parcels.

A bounded live grouped count query of the [official MnGeo Plan Parcels Open layer](https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_mngeo/plan_parcels_open/FeatureServer/1) returned 59 county groups and 2,710,201 parcel records, without exceeding the transfer limit. No parcel records or geometry were downloaded. Of 24 monitored direct counties, 13 also appear in the statewide layer; 11 do not. Unique monitoring coverage remains 59 + 24 - 13 = 70 counties. Runtime coverage remains derived from each saved observation, rather than this historical audit.

Olmsted has 75,579 statewide parcel records. The HTTP 403 on its separate direct endpoint concerns that endpoint only; it is not statewide absence.

## Direct feed schema evidence

The [MN GAC Parcel Data Standard v1.1.3](https://mn.gov/mngeo/assets/MN_GAC_Parcel_Data_Standard_tcm1235-753537.pdf) defines 91 fields, including seven Mandatory fields. Physical field names were compared case-insensitively in bounded metadata responses from 21 direct layers. Aliases and crosswalks were not applied. Ramsey and Olmsted returned HTTP 403; Dodge is download-only and was not inspected.

The [official FAQ](https://mn.gov/mngeo/assets/MN_GAC_Parcel_Data_Standard_FAQ_tcm1235-753538.pdf) identifies this as a transfer standard, not a prescription for internal storage. Missing names show a mismatch in the checked feed, not that a county never provides standardized exports. Full compliance also needs type, width, domain, order, conditional and value checks.

| Direct county | In MnGeo Open | Statewide records | Direct names / 91 | Mandatory names / 7 |
|---|---|---:|---:|---:|
| [Aitkin](https://gisweb.co.aitkin.mn.us/arcgis/rest/services/ParcelTaxData/FeatureServer/0?f=pjson) | Yes | 43,024 | 2 | 0 |
| [Beltrami](https://arcgis.co.beltrami.mn.us/arcgis/rest/services/BeltramiData/BeltramiOpenData/MapServer/2?f=pjson) | No | Absent | 20 | 1 |
| [Brown](https://gis.browncountymn.gov/server/rest/services/Hosted/Brown_County_Authoritative_Parcels/FeatureServer/0?f=pjson) | No | Absent | 0 | 0 |
| [Dakota](https://gis2.co.dakota.mn.us/arcgis/rest/services/DCGIS_OL_PropertyInformation/MapServer/71?f=pjson) | Yes | 154,315 | 13 | 0 |
| Dodge | No | Absent | Not assessed | Not assessed |
| [Douglas](https://services2.arcgis.com/8iQOd6RvhPL17pJd/arcgis/rest/services/Douglas_County_MN_Open_Data_Parcels/FeatureServer/0?f=pjson) | Yes | 33,624 | 0 | 0 |
| [Hubbard](https://gis.co.hubbard.mn.us/arcgis/rest/services/OpenData/Hubbard_County_Tax_Parcels/FeatureServer/0?f=pjson) | No | Absent | 2 | 0 |
| [Koochiching](https://gis.co.koochiching.mn.us/server/rest/services/Tax_Parcels/MapServer/0?f=pjson) | Yes | 55,291 | 3 | 0 |
| [Mahnomen](https://services8.arcgis.com/eORKbx5CWReJmkoa/arcgis/rest/services/TaxParcels/FeatureServer/0?f=pjson) | No | Absent | 8 | 0 |
| [Meeker](https://services2.arcgis.com/pHb2Lre5eSy5plfE/arcgis/rest/services/Parcels_hub/FeatureServer/0?f=pjson) | No | Absent | 2 | 0 |
| [Morrison](https://services1.arcgis.com/lQjrBHFnTgKBR9zX/arcgis/rest/services/MorrisonParcelsQ2/FeatureServer/0?f=pjson) | Yes | 30,117 | 0 | 0 |
| Olmsted | Yes | 75,579 | Not assessed | Not assessed |
| [Pipestone](https://gis.pcmn.us/arcgis/rest/services/AssessmentInformation/TaxParcels/FeatureServer/0?f=pjson) | Yes | 8,359 | 7 | 0 |
| Ramsey | Yes | 172,178 | Not assessed | Not assessed |
| [Rice](https://asr-arcgis01.ricecountymn.gov/arcgis/rest/services/Maps/TaxParcels/MapServer/1?f=pjson) | Yes | 28,166 | 52 | 5 |
| [Roseau](https://gis.co.roseau.mn.us/arcgis/rest/services/TaxParcels/FeatureServer/0?f=pjson) | No | Absent | 4 | 0 |
| [Scott](https://services.arcgis.com/DqIh9WAsIZcPlBEF/arcgis/rest/services/Parcels/FeatureServer/0?f=pjson) | Yes | 61,696 | 3 | 0 |
| [Sibley](https://gis.sibleycounty.gov/arcgis/rest/services/AGOL/ParcelTaxData/FeatureServer/0?f=pjson) | No | Absent | 8 | 0 |
| [St. Louis](https://gis.stlouiscountymn.gov/server2/rest/services/GeneralUse/Open_Data/MapServer/7?f=pjson) | Yes | 186,455 | 4 | 0 |
| [Swift](https://services3.arcgis.com/D3VRNSq5Pf3sYZAp/arcgis/rest/services/Swift_Parcels/FeatureServer/0?f=pjson) | No | Absent | 2 | 0 |
| [Todd](https://gis.mytoddcounty.com/toddcounty/rest/services/PublicViewerServer/MapServer/80?f=pjson) | No | Absent | 2 | 0 |
| [Wabasha](https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_co_wabasha/plan_parcelspolygon/FeatureServer/0?f=pjson) | Yes | 17,323 | 91 | 7 |
| [Wadena](https://gis.co.wadena.mn.us/arcgis/rest/services/LinkPublic/MapServer/0?f=pjson) | No | Absent | 6 | 0 |
| [Waseca](https://gis.wasecacounty.gov/arcgis/rest/services/Public/Cadastral/FeatureServer/0?f=pjson) | Yes | 12,327 | 4 | 0 |

Wabasha exposes all 91 names and seven mandatory names; its [county-published metadata](https://www.arcgis.com/sharing/rest/content/items/bf8ef9d0b3f1455c9af61ef6b60329e2/info/metadata/metadata.xml?format=default&output=html) declares v1.1.3 use. Rice exposes 52 names and five mandatory names, missing ACRES_POLY and EXP_DATE. Beltrami exposes 20 names and one mandatory name. None of these counts is a field-population percentage.

## Dashboard behavior

Pane A, full county profiles, parcel county MN GAC results, public direct-source pages and county JSON/CSV/XLSX expose the same offline evidence. The direct-feed card reports the audit date, exact source, matching names and missing mandatory names. A changed observed field count flags the audit for recheck. Unassessed feeds stay unassessed; even all 91 names do not imply full compliance. Statewide population metrics stay unavailable when no statewide county observation exists, without inventing zeroes or substituting direct-feed counts.

The packaged county_direct_gac_schema.json stores public, source-specific research only. It does not activate sources, change schedules, or affect runtime health. Matching requires the exact audited source ID and county. API content revisions include this evidence so cached county fragments cannot retain an older assessment after it changes.

This implementation is a local candidate. No production publication or provider configuration changed.

The map pane and Pane A use equal grid-row heights, including stacked layouts,
and stretch to the larger pane as county details load or change.
