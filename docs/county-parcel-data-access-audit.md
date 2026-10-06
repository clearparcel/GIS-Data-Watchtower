# Minnesota county parcel-data access audit

Last updated: **2026-10-06**

## Purpose

GIS Data Watchtower completed a parcel-specific access audit for the 35 Minnesota counties that
were previously shown with the registry-derived needs-source status. That status meant only that
Watchtower had no county-specific parcel source configured; it was never evidence that an
exhaustive parcel-source search had failed.

The audit now separates three concepts that must not be conflated:

1. **County-direct parcel access** — how the county itself supplies parcel GIS data.
2. **Statewide open parcel access** — whether the county is represented in MnGeo Plan Parcels Open.
3. **Watchtower monitoring coverage** — whether Watchtower is actively observing the county through
   a county-specific source, MnGeo Plan Parcels Open, or both.

A county can therefore be fee-based directly from the county while still being freely available
through MnGeo. Winona County is an explicit example of this distinction.

## Scope: parcel data itself

This review is intentionally limited to access to the **parcel dataset itself**.

A county is not classified as fee-based merely because it charges for staff time, custom GIS
analysis, special exports, printed maps, plats, deeds, recorded documents, mailing lists,
unrelated subscriptions, or other services associated with parcel information.

**Fee-based parcel data** is used only when official county evidence establishes that obtaining
the county parcel dataset itself requires payment.

## Evidence priority

For every county, the audit reviewed official sources in this order:

1. Official county government website.
2. Official county GIS / mapping / assessor / land-records page.
3. Official county open-data/download page.
4. Official county ArcGIS Hub / ArcGIS Online / REST / FeatureServer endpoints.
5. Official county GIS data policy.
6. Official county fee schedule.
7. Official data request/order form.
8. County resolutions or ordinances governing GIS/parcel data.
9. County-authorized third-party GIS/parcel portals linked by the county.
10. MnGeo as corroborating statewide context and as the separate statewide-open-access dimension.

Search results may discover candidate sources, but search snippets are not final evidence.

## County-direct classifications

### Free parcel data

An official county or county-authorized source provides a parcel dataset download or
machine-readable parcel service at no charge.

### Fee-based parcel data

An official county fee schedule, data policy, order form, resolution, or equivalent states that
the county parcel dataset itself requires payment.

### Parcel viewer only

Public parcel information can be viewed interactively, but no county-authorized free parcel
dataset download or machine-readable parcel dataset access was verified.

### Parcel data by request / restricted

The county parcel dataset appears available only by request, approval, agreement, restricted
access, or another non-public-download procedure and a dataset fee is not established.

### No direct parcel dataset verified

After the full official-source review, no county-direct parcel dataset, parcel download,
fee-based parcel dataset, or parcel-data request path can be verified.

## Statewide open access is separate

MnGeo Plan Parcels Open is tracked independently from the county-direct classification. A county
record therefore carries a separate statewide_open_coverage object with whether the county is
represented, the MnGeo source, source URL, and verification date.

Among the 35 audited counties, **9** are represented in the current MnGeo Plan
Parcels Open observation:

Jackson, Lac qui Parle, Lake of the Woods, Marshall, Murray, Norman, Pennington, Red Lake, Winona.

This is why Winona is correctly represented as:

- **County-direct access:** Fee-based parcel data.
- **Statewide open access:** Available free through MnGeo Plan Parcels Open.
- **Watchtower monitoring path:** MnGeo Plan Parcels Open when the current statewide observation
  contains Winona County.

## Audit results

County-direct results for the 35 audited counties:

- **13 Free parcel data**
- **11 Fee-based parcel data**
- **11 Parcel viewer only**
- **0 Parcel data by request / restricted**
- **0 No direct parcel dataset verified**

The review identified **13 county-direct machine-readable parcel sources**. One bounded
validation request from GERTKEN-PC returned HTTP 200 for all 13 sources. This confirms
reachability only; it does not add those candidate sources to the deployment registry or enable
additional provider polling.

## Current Watchtower monitoring interpretation

The current production observation contains:

- **59 counties** represented in MnGeo Plan Parcels Open;
- **15 counties** with county-specific monitored sources;
- **13 counties** monitored through both paths;
- therefore **61 of 87 counties actively checked** after de-duplicating overlap.

A county is considered **actively checked** when Watchtower is observing its parcel data through
at least one active monitoring path. Being represented in the single statewide MnGeo parcel check
therefore counts as active county monitoring without creating a separate provider request for
each county.

This definition is intentionally different from county-direct source count, which remains a
separate metric.

## Outside-MnGeo county-direct monitoring evaluation

After separating county-direct policy from technical endpoint reachability, the 13 discovered parcel
endpoints outside the current MnGeo Plan Parcels Open footprint resolve as follows.

### Approved for bounded Watchtower monitoring

The following **9 counties** have county-direct sources that are consistent with the current
provider-compliance rules and passed a bounded local Watchtower-engine probe on 2026-10-06:

- Brown
- Dodge
- Hubbard
- Mahnomen
- Meeker
- Roseau
- Sibley
- Todd
- Wadena

The local probe performed only service/layer metadata and feature-count checks for ArcGIS sources.
Dodge was checked with HTTP HEAD metadata only; the parcel ZIP was not downloaded. All nine
returned **ok** with zero warnings and zero errors.

Cloud compatibility was then tested with isolated temporary Cloud Run jobs using the existing
staging image, staging service account, and network path. The eight ArcGIS candidates returned
**8 OK / 0 warnings / 0 errors**. A separate HEAD-only Dodge execution also succeeded and returned
the expected ETag, Last-Modified, Content-Length, and ZIP content type. Therefore all nine approved
outside-MnGeo candidates are suitable for the **cloud execution profile**; no local-only exception
is required for this group.

Dodge uses the http_file adapter, which tracks ETag, Last-Modified, Content-Length, and content
type without retrieving the archive body.

### Hold for terms clarification

The following **4 counties** expose technically reachable parcel services but are **not** approved
for unattended Watchtower monitoring under the current evidence:

- **Blue Earth** — official county pages state property-tax GIS data are available for purchase;
  request terms say use may be restricted by a license agreement.
- **Faribault** — the July 1, 2026 county fee schedule explicitly distinguishes no-charge online
  viewers from parcel GIS data requiring a request and payment.
- **Kandiyohi** — the county authorization/release form requires agreement and payment, restricts
  delivered files to the identified project, and restricts transmission without written consent.
- **Lincoln** — the county geospatial pricing schedule states that some data require a license
  agreement and prices parcel boundaries/attributes per parcel.

These four remain hold-for-terms even though their viewer/application services are publicly
reachable. Public technical reachability is not treated as permission to automate a county data
product that the county separately licenses or sells.

If the nine approved outside-MnGeo candidates are later added to the active registry, the current
61/87 monitoring footprint would rise to **70/87 counties**, assuming current MnGeo coverage and
existing county-direct sources remain unchanged. The four held counties could raise the ceiling to
74/87 only after terms are clarified.

## County summary

| County | County-direct access | MnGeo open coverage | Direct machine-readable source | County parcel dataset fee |
| --- | --- | --- | --- | --- |
| Blue Earth | Fee-based parcel data | No | No | $30 Basic Bundle for for-profit use; qualifying nonprofit 10%; qualifying government may receive at no cost |
| Brown | Free parcel data | No | Yes | — |
| Cottonwood | Parcel viewer only | No | No | — |
| Dodge | Free parcel data | No | Yes | — |
| Faribault | Fee-based parcel data | No | No | $500 entire county or $100 per township |
| Freeborn | Parcel viewer only | No | No | — |
| Goodhue | Fee-based parcel data | No | No | $0.05 per parcel for public-request digital parcel data; compilation/service charges may apply |
| Hubbard | Free parcel data | No | Yes | — |
| Jackson | Fee-based parcel data | Yes | No | $100 for the full GIS parcel layer |
| Kanabec | Parcel viewer only | No | No | — |
| Kandiyohi | Fee-based parcel data | No | No | $1,280 entire parcel layer; area of interest = features × $0.05 + $75 labor |
| Kittson | Parcel viewer only | No | No | — |
| Lac qui Parle | Free parcel data | Yes | Yes | — |
| Lake of the Woods | Parcel viewer only | Yes | No | — |
| Le Sueur | Fee-based parcel data | No | No | $0.05 per parcel or $50/hour, whichever is greater |
| Lincoln | Fee-based parcel data | No | No | $0.05 per parcel plus $25 data-delivery charge for staff-serviced requests |
| Mahnomen | Free parcel data | No | Yes | — |
| Marshall | Free parcel data | Yes | Yes | — |
| Martin | Parcel viewer only | No | No | — |
| Meeker | Free parcel data | No | Yes | — |
| Murray | Parcel viewer only | Yes | No | — |
| Nicollet | Fee-based parcel data | No | No | $0.05 per parcel ($5 minimum) or $500 for the entire county |
| Nobles | Fee-based parcel data | No | No | $0.05 per parcel ($25 minimum) or $500 for the county parcel shapefile |
| Norman | Free parcel data | Yes | Yes | — |
| Pennington | Parcel viewer only | Yes | No | — |
| Pine | Parcel viewer only | No | No | — |
| Red Lake | Free parcel data | Yes | Yes | — |
| Redwood | Fee-based parcel data | No | No | $800 for countywide parcel data or $0.10 per parcel |
| Rock | Parcel viewer only | No | No | — |
| Roseau | Free parcel data | No | Yes | — |
| Sibley | Free parcel data | No | Yes | — |
| Todd | Free parcel data | No | Yes | — |
| Wadena | Free parcel data | No | Yes | — |
| Watonwan | Parcel viewer only | No | No | — |
| Winona | Fee-based parcel data | Yes | No | $75 minimum plus per-parcel rate (rate tiers in county fee schedule) |

## Direct machine-readable sources discovered

- Brown — https://gis.browncountymn.gov/server/rest/services/Hosted/Brown_County_Authoritative_Parcels/FeatureServer/0
- Dodge — https://maps.co.goodhue.mn.us/pdfs/DodgeCoOpenData/DodgeCoParcels.zip
- Hubbard — https://gis.co.hubbard.mn.us/arcgis/rest/services/OpenData/Hubbard_County_Tax_Parcels/FeatureServer
- Lac qui Parle — https://services5.arcgis.com/D5NH3zpCRhpMEHEy/arcgis/rest/services/Tax_Parcels/FeatureServer
- Mahnomen — https://services8.arcgis.com/eORKbx5CWReJmkoa/arcgis/rest/services/TaxParcels/FeatureServer
- Marshall — https://gis.co.marshall.mn.us/server/rest/services/Marshall/MarshallCountyMN_TaxParcels/FeatureServer
- Meeker — https://services2.arcgis.com/pHb2Lre5eSy5plfE/arcgis/rest/services/Parcels_hub/FeatureServer
- Norman — https://gismap.co.pennington.mn.us/arcgis/rest/services/Norman/LandRecords/MapServer/8
- Red Lake — https://gismap.redlakecounty.gov/arcgis/rest/services/RedLake/Public/MapServer/26
- Roseau — https://gis.co.roseau.mn.us/arcgis/rest/services/TaxParcels/FeatureServer/0
- Sibley — https://gis.sibleycounty.gov/arcgis/rest/services/AGOL/ParcelTaxData/FeatureServer/0
- Todd — https://gis.mytoddcounty.com/toddcounty/rest/services/PublicViewerServer/MapServer
- Wadena — https://gis.co.wadena.mn.us/arcgis/rest/services/LinkPublic/MapServer/0

Each is marked candidate-low-frequency. This is a research/operations assessment, not a
production schedule. Watchtower must continue to use bounded read-only checks, honor rate limits
and HTTP 429 responses, avoid raw-data redistribution unless permitted, and never scrape
human-facing property-search pages.

## Structured research dataset and schema

Persistent research data:

clearparcel/datawatch/minnesota_county_parcel_access.json

Schema/validation code:

clearparcel/datawatch/parcel_access.py

The schema is version 2. Each county record captures county and review date,
county_direct_classification, statewide_open_coverage, official county and parcel/GIS URLs,
download/service and viewer URLs where applicable, parcel fee evidence where applicable,
evidence notes and source authority, the county-direct machine-readable-source flag, monitoring
suitability, evidence items, and the complete official-source review log.

The research file remains separate from service-health observations. Runtime monitoring coverage
is derived from the current Watchtower state, not from the research classification.

## UI integration

Public v2 shows the dimensions separately:

- **Monitoring coverage** — actively checked, needs attention, failed, catalog-only, or not active.
- **Monitoring path** — county-direct source, MnGeo Plan Parcels Open, or both.
- **County-direct access** — the evidence-backed county classification.
- **Statewide open access** — current MnGeo Plan Parcels Open coverage.
- **County-direct sources** — number of county-specific sources actively checked.

For counties outside the completed 35-county direct-access audit, the neutral research label is:

**County-direct parcel access not yet researched**

That statement is deliberately separate from whether Watchtower is already monitoring the county
through MnGeo.
