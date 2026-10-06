# Minnesota county parcel-data access audit

Last updated: **2026-10-05**

## Purpose

GIS Data Watchtower is auditing the Minnesota counties that are currently shown as `needs-source` / "Direct source not yet identified."

That existing status is **registry-derived**, not a completed research conclusion. It currently means that Watchtower has no county-specific source configured for direct monitoring while a county/catalog record exists. It does **not** mean that a thorough search proved that no parcel dataset is available.

The audit will replace that ambiguous state with evidence-backed parcel-data access classifications.

## Scope: parcel data itself

This review is intentionally limited to access to the **parcel dataset itself**.

A county is **not** classified as fee-based merely because it charges for:

- staff time or custom GIS analysis;
- custom exports or special file preparation;
- printed maps;
- plats, deeds, recorded documents, or other land-record documents;
- subscriptions or services associated with parcel information;
- custom coordinate conversion, mailing lists, or consulting;
- third-party viewer features.

The public label **Fee-based parcel data** is used only when an official county source establishes that obtaining the parcel dataset itself requires payment.

## Evidence priority

For every county, use this order:

1. Official county government website.
2. Official county GIS / mapping / assessor / land-records page.
3. Official county open-data/download portal or ArcGIS Hub/REST service clearly owned or linked by the county.
4. Official county fee schedule, GIS data policy, data request form, resolution, or ordinance.
5. A county-authorized third-party parcel/GIS portal, when linked from the official county site.
6. MnGeo / Minnesota Geospatial Information Office as corroborating statewide context.

Search engines may be used to discover candidate pages, but a search-result snippet is not sufficient evidence for the final classification.

The MnGeo county open-data status layer is useful context, but it does **not** by itself determine whether parcel data specifically is free, fee-based, viewer-only, or restricted.

## Public classifications

The audit should use these parcel-specific classifications:

### Free parcel data

Use when an official source provides a parcel dataset for download or machine-readable access at no charge.

### Fee-based parcel data

Use only when an official county policy, fee schedule, order page, or equivalent evidence states that the parcel dataset itself is sold or supplied for a fee.

### Parcel viewer only

Use when public parcel information can be viewed interactively, but no free parcel dataset download or machine-readable county source is verified.

### Parcel data by request / restricted

Use when the parcel dataset appears obtainable only by request, approval, agreement, restricted access, or other non-public-download process and a specific dataset fee is not established.

### Statewide parcel coverage only

Use when parcel information is available through a statewide source such as MnGeo, but no county-direct parcel dataset access method has been verified.

### No direct parcel dataset verified

Use only after the defined official-source review is complete and no direct county parcel dataset, parcel download, fee-based parcel dataset, or request path can be verified.

This is the appropriate researched replacement for the current ambiguous "Direct source not yet identified" wording.

## Audit population

The current production aggregate places **35 counties** in the registry-derived `needs-source` category:

1. Blue Earth
2. Brown
3. Cottonwood
4. Dodge
5. Faribault
6. Freeborn
7. Goodhue
8. Hubbard
9. Jackson
10. Kanabec
11. Kandiyohi
12. Kittson
13. Lac qui Parle
14. Lake of the Woods
15. Le Sueur
16. Lincoln
17. Mahnomen
18. Marshall
19. Martin
20. Meeker
21. Murray
22. Nicollet
23. Nobles
24. Norman
25. Pennington
26. Pine
27. Red Lake
28. Redwood
29. Rock
30. Roseau
31. Sibley
32. Todd
33. Wadena
34. Watonwan
35. Winona

## Current audit state

The 35-county parcel-data access audit is **complete as of 2026-10-05**. Every stored county record has research_complete=true, parcel-specific evidence, and a completed official-source review log. Research conclusions remain separate from Watchtower monitoring observations and health.

### Results

- **17 Free parcel data**
- **7 Fee-based parcel data**
- **11 Parcel viewer only**
- **0 Parcel data by request / restricted**
- **0 Statewide parcel coverage only**
- **0 No direct parcel dataset verified**

The review identified **17 county-direct machine-readable parcel sources**. One bounded validation request from GERTKEN-PC returned HTTP 200 for all 17 sources. This confirms reachability only; it does not add those sources to the deployment registry and does not enable provider polling.

### County summary

| County | Parcel-data access | Direct machine-readable source | Parcel dataset fee |
| --- | --- | --- | --- |
| Blue Earth | Free parcel data | Yes | — |
| Brown | Free parcel data | Yes | — |
| Cottonwood | Parcel viewer only | No | — |
| Dodge | Free parcel data | Yes | — |
| Faribault | Free parcel data | Yes | — |
| Freeborn | Parcel viewer only | No | — |
| Goodhue | Fee-based parcel data | No | $0.05 per parcel for public-request digital parcel data; compilation/service charges may apply |
| Hubbard | Free parcel data | Yes | — |
| Jackson | Fee-based parcel data | No | $100 for the full GIS parcel layer |
| Kanabec | Parcel viewer only | No | — |
| Kandiyohi | Free parcel data | Yes | — |
| Kittson | Parcel viewer only | No | — |
| Lac qui Parle | Free parcel data | Yes | — |
| Lake of the Woods | Parcel viewer only | No | — |
| Le Sueur | Fee-based parcel data | No | $0.05 per parcel or $50/hour, whichever is greater |
| Lincoln | Free parcel data | Yes | — |
| Mahnomen | Free parcel data | Yes | — |
| Marshall | Free parcel data | Yes | — |
| Martin | Parcel viewer only | No | — |
| Meeker | Free parcel data | Yes | — |
| Murray | Parcel viewer only | No | — |
| Nicollet | Fee-based parcel data | No | $0.05 per parcel ($5 minimum) or $500 for the entire county |
| Nobles | Fee-based parcel data | No | $0.05 per parcel ($25 minimum) or $500 for the county parcel shapefile |
| Norman | Free parcel data | Yes | — |
| Pennington | Parcel viewer only | No | — |
| Pine | Parcel viewer only | No | — |
| Red Lake | Free parcel data | Yes | — |
| Redwood | Fee-based parcel data | No | $800 for countywide parcel data or $0.10 per parcel |
| Rock | Parcel viewer only | No | — |
| Roseau | Free parcel data | Yes | — |
| Sibley | Free parcel data | Yes | — |
| Todd | Free parcel data | Yes | — |
| Wadena | Free parcel data | Yes | — |
| Watonwan | Parcel viewer only | No | — |
| Winona | Fee-based parcel data | No | $75 minimum plus per-parcel rate (rate tiers in county fee schedule) |

### Direct machine-readable sources

- Blue Earth — https://gis.blueearthcountymn.gov/server/rest/services/Planning/CityViewBase/MapServer/1
- Brown — https://gis.browncountymn.gov/server/rest/services/Hosted/Brown_County_Authoritative_Parcels/FeatureServer/0
- Dodge — https://maps.co.goodhue.mn.us/pdfs/DodgeCoOpenData/DodgeCoParcels.zip
- Faribault — https://services2.arcgis.com/fxB2C8mQfjMb1848/arcgis/rest/services/TaxParcelsGAC/FeatureServer
- Hubbard — https://gis.co.hubbard.mn.us/arcgis/rest/services/OpenData/Hubbard_County_Tax_Parcels/FeatureServer
- Kandiyohi — https://gis.kcmn.us/arcgis/rest/services/Kandiyohi/PublicMailingKandi/FeatureServer/0
- Lac qui Parle — https://services5.arcgis.com/D5NH3zpCRhpMEHEy/arcgis/rest/services/Tax_Parcels/FeatureServer
- Lincoln — https://services2.arcgis.com/4bzoopFK3ECP25Sn/arcgis/rest/services/Parcels/FeatureServer/0
- Mahnomen — https://services8.arcgis.com/eORKbx5CWReJmkoa/arcgis/rest/services/TaxParcels/FeatureServer
- Marshall — https://gis.co.marshall.mn.us/server/rest/services/Marshall/MarshallCountyMN_TaxParcels/FeatureServer
- Meeker — https://services2.arcgis.com/pHb2Lre5eSy5plfE/arcgis/rest/services/Parcels_hub/FeatureServer
- Norman — https://gismap.co.pennington.mn.us/arcgis/rest/services/Norman/LandRecords/MapServer/8
- Red Lake — https://gismap.redlakecounty.gov/arcgis/rest/services/RedLake/Public/MapServer/26
- Roseau — https://gis.co.roseau.mn.us/arcgis/rest/services/TaxParcels/FeatureServer/0
- Sibley — https://gis.sibleycounty.gov/arcgis/rest/services/AGOL/ParcelTaxData/FeatureServer/0
- Todd — https://gis.mytoddcounty.com/toddcounty/rest/services/PublicViewerServer/MapServer
- Wadena — https://gis.co.wadena.mn.us/arcgis/rest/services/LinkPublic/MapServer/0

Each of these records is marked candidate-low-frequency. That is a research/operations assessment, not a schedule. Watchtower must continue to use bounded read-only checks, honor rate limits and HTTP 429 responses, avoid raw-data redistribution unless permitted, and never scrape human-facing property-search pages.

### Fee interpretation

Fee-based parcel data is used only when official county evidence establishes that obtaining the parcel GIS dataset itself requires payment. Charges for staff time, custom analysis, custom exports, printed maps, plats, deeds, recorded documents, mailing lists, or unrelated subscriptions do not trigger the label.

When a county sells a packaged shapefile but also publishes a county-authorized no-charge machine-readable parcel service, this audit classifies the county as Free parcel data. The packaged-product fee remains evidence/context but is not treated as a mandatory fee for all parcel-data access.

## Structured research dataset and schema

Persistent research data: clearparcel/datawatch/minnesota_county_parcel_access.json

Schema/validation code: clearparcel/datawatch/parcel_access.py

Regression coverage: tests/test_parcel_access.py

Every county record captures the county, review date, classification, research-complete flag, official county and parcel/GIS URLs, download/service and viewer URLs where applicable, parcel fee evidence where applicable, evidence notes and source authority, direct-machine-readable-source flag, monitoring-suitability assessment, evidence items, and review logs for the required official-source areas.

## UI integration

Public v2 reads parcel-access research independently from monitoring status. The county index and county detail pages can therefore show an evidence-backed parcel-data access classification without changing Watchtower health, freshness, or monitored-source counts.

For counties without completed stored parcel-access research, neutral wording remains appropriate:

**No direct county parcel source currently monitored**

That statement describes current Watchtower coverage and does not imply that an exhaustive source search has failed.
