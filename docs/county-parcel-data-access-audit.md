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

### Four-category inventory review, 2026-10-06

The original 35 counties were reviewed using bounded official county landing pages, parcel
service metadata, the [official MnGeo parcel source table](https://mn.gov/mngeo/gis-data-and-maps/info-by-topic/land-ownership/property.jsp),
the current state-hosted service directory, and county-specific Commons publishing-account
metadata searches plus all 87 returned official state-organization parcel-search records. Search responses were read; snippets were only discovery. All 52 previously unreviewed counties now have actual category reviews, including the exact final eight Swift–Yellow Medicine counties listed below. No county record retains pending categories; unresolved evidence remains blocked/unknown.

| Category | Reviewed across 87 county reviews | Blocked / unresolved | Pending |
| --- | ---: | ---: | ---: |
| MnGeo Plan Parcels Open | 87 (59 included, 28 excluded) | 0 | 0 |
| Distinct MnGeo public repository | 18 available | 69 | 0 |
| County-authorized parcel REST | 59 available | 28 | 0 |
| County parcel download | 52 available | 35 | 0 |

These counts are derived from stored category statuses: **216 reviewed**, **132 blocked**,
and **0 pending** category assessments across 87 county records. **16 counties have all
four categories complete** (Aitkin, Anoka, Carver, Dakota, Fillmore, Hennepin, Houston, Itasca, Lake, Morrison, Scott, Steele, Wabasha, Waseca, Washington, Wright);
Aitkin's county-direct pricing/policy assessment remains unresolved. County-direct
classification is separate from inventory completion; category keys alone do not finish research.

The official [Plan Parcels Open item metadata](https://www.arcgis.com/sharing/rest/content/items/69148d3959194a05a23964cc60f6517b?f=pjson)
explicitly lists 59 opted-in counties and supports the nine memberships within the original 35-county batch.
Current aggregate observations take precedence over this dated membership in composition.
The state service directory, organization-wide and account-scoped searches did not establish a distinct county
dataset for the original 35-county batch, but do not prove repository-wide absence. Those original-batch findings remain
**unknown**, rather than negative. Generic county catalog links and statewide parcels were
not counted as distinct repository evidence.

HTTP 403 blocked Blue Earth county policy pages and Nobles' county page; Faribault's fee PDF
also denied a subsequent policy-document read. Those denials were not bypassed. Initial linked Hub HTML was an application shell. Follow-up rendered official catalog pages
and county/ArcGIS item metadata verified downloadable parcels for Hubbard, Lac qui Parle
and Meeker, alongside Dodge. Brown, Sibley, Faribault and Goodhue catalogs were also read;
unresolved parcel-download permission/product scope remains blocked rather than absent.
Viewer/property-search data and parcel features were not retrieved; Dodge's ZIP was checked
with HEAD only. Dated access evidence remains retained when current category review is blocked.

Brown's [2025-effective fee schedule](https://www.browncountymn.gov/DocumentCenter/View/502/Fee-Schedule-PDF)
explicitly prices the requested **complete parcel Shapefile dataset at $697** and requires a
signed data disclosure. This is a dataset product charge, separate from labor. Its
[Maps & GIS page](https://www.browncountymn.gov/383/Maps-GIS) also advertises Open-Source GIS
Data Hub, and parcel REST metadata remains public. The requested product is therefore fee-based;
the fee does not prove every access route costs money. Brown is now held in the **research
assessment** pending route-specific permission reconciliation. No runtime registry, scheduling,
service or configuration changed, and observed monitoring coverage remains independent.

### Aitkin–Clay batch, 2026-10-06

This exact 12-county batch adds **34 reviewed / 14 blocked** category assessments; the other 75
records are unchanged by this batch. Evidence comes from actual official county pages,
rendered county-linked Hub catalog/About pages, item metadata, bounded REST metadata and
file HEAD checks. All new source monitoring decisions are **not-assessed**. Published
products and public links do not activate monitoring.

Archive verification must use HEAD only. Do not click or open parcel archive/download
links with web or browser tools; inspect the official landing-page advertisement and use
bounded HEAD metadata instead. During this batch, an unintended web-tool click on Benton's
Parcels ZIP link attempted archive retrieval and violated that constraint. The tool returned
an unsupported-content-type error; no archive body or file was delivered or retained.
Whether the tool fetched bytes internally before rejecting the content type is unknown.
Subsequent archive checks used HEAD only. This records the failed attempt and containment,
without asserting that no request occurred.

| County | Dated statewide membership | Distinct repository | County REST | County download | County-direct classification |
| --- | --- | --- | --- | --- | --- |
| Aitkin | Included | Available | Available | Advertised | Unresolved product/policy scope |
| Anoka | Included | Available | Available | Advertised | Free parcel data |
| Becker | Included | Unknown | Unknown | Advertised | Free parcel data |
| Beltrami | Excluded | Unknown | Available | Advertised | Free parcel data |
| Benton | Included | Unknown | Available | Unknown: ZIP 404 | Free parcel data via REST |
| Big Stone | Included | Unknown | Unknown: 403 | Advertised | Unresolved county policy read |
| Carlton | Included | Unknown | Available | Advertised | Free parcel data |
| Carver | Included | Available | Available | Advertised | Free parcel data |
| Cass | Included | Unknown | Unknown | Advertised | Unresolved county policy read |
| Chippewa | Included | Unknown | Available | Advertised | Free parcel data |
| Chisago | Included | Unknown | Unknown | Advertised | Free parcel data |
| Clay | Included | Unknown | Available | Advertised | Free parcel data |

Aitkin's [distinct Commons parcel item](https://gis.data.mn.gov/datasets/3cd285cbb13a43478d42e2ade3915403_0/about)
identifies county ParcelTaxData/0. Its 2026-02-23 metadata refers users to current distribution
procedures and prices without stating an actual parcel dataset fee. The public product and
requested-product ambiguity are both retained; no fee-based conclusion is invented.

The [official metropolitan parcel repository item](https://www.arcgis.com/sharing/rest/content/items/136b28bd0d874076b702ca55b9aafffc?f=pjson)
explicitly distributes individual county sublayers/feature classes. Actual service/layer
metadata verified Anoka County Parcels/0 and Carver County Parcels/1 as distinct repository
resources, independently of statewide membership. The other nine repository categories
remain unknown after bounded metadata searches, not absent.

[Anoka's current county-linked Hub](https://acgis-anokacounty.hub.arcgis.com/) states GIS data
are offered without cost or license and links a verified public parcel product. Its older
FTP delivery page requires authentication and disclaimer acceptance; that route was not
traversed and credentials were not retained. The $50/hour custom processing charge is not
a parcel dataset fee. [Carlton's FAQ](https://www.carltoncountymn.gov/DocumentCenter/View/64/Geographic-Information-Services-FAQ-PDF?bidId=)
separates free selected datasets from custom maps; its exact parcel download/REST item was
verified. Carver's county resolution separates no-cost published data from special requests;
Clay's official Hub advertises its free/open resolution and downloadable parcel product.

Beltrami's county download is independent of its exclusion from the dated statewide release.
Benton's county page links public Benton_Co_Data item b5240c2d09744e7cb999cf066ffc9c06;
its actual FeatureServer/0 metadata identifies Benton Parcels polygons with Query/Extract.
This usable REST route is separate from its linked ZIP, which returned 404 on HEAD.
Cass's official county directory advertises CASS_PARCELS_20260921.zip (HEAD 200), replacing an
older discovery URL, but its county policy landing read returned 403. Big Stone's county
homepage/REST metadata also returned 403; its advertised downloadable county Hub item was
read separately. No denial was bypassed. Becker's legacy county URL failed TLS/web reads;
the final official .gov download page was read without bypassing TLS or browser verification.
Chisago's official GIS page was initially read, then later denied 403; the county-linked Data
Download catalog advertises its exact parcel ZIP (HEAD 200). Parcel records/property-search
applications were not read.

Exact vetted Aitkin and Beltrami public dataset identities retain monitored IDs across shared
REST/Hub/download representations; no other join is inferred from county name or generic
catalog. Current runtime coverage still overrides dated research membership.

Across all stored records, **82** county-direct classifications are complete: **58 free**,
**13 fee-based**, **11 viewer-only**. The remaining 5 county-direct classifications are unresolved (Aitkin, Big Stone, Cass, Koochiching, Rice). These research totals do not change active monitoring coverage.

### Clearwater–Houston inventory batch, 2026-10-06

The exact nine counties are Clearwater, Cook, Crow Wing, Dakota, Douglas, Fillmore,
Grant, Hennepin and Houston. This batch adds **30 reviewed / 6 blocked** category
assessments; the other 78 county records are unchanged. All nine county-direct conclusions
cover a verified public parcel product and are free; publication does not activate polling.

| County | Statewide dated membership | Distinct repository | County REST | County download |
| --- | --- | --- | --- | --- |
| Clearwater | Included | Unresolved | Unresolved | County ESRI Shapefile ZIP |
| Cook | Included | Unresolved | Tax Parcel Layer (Current), layer 0 | County Hub parcel download |
| Crow Wing | Included | Unresolved | TaxParcels_public, layer 0 | County Hub parcel download |
| Dakota | Included | County-specific MetroGIS polygon layer 2 | Tax Parcels, layer 71 | CAD / File Geodatabase / Shapefile / GeoPackage advertised |
| Douglas | Included | Unresolved | Open Data Parcels, layer 0 | County Hub parcel download |
| Fillmore | Included | Distinct Commons county parcel item | County Parcels, layer 0 | Commons public parcel download |
| Grant | Included | Unresolved | TaxParcels_public, layer 1 | County Hub parcel download |
| Hennepin | Included | County-specific MetroGIS polygon layer 3 | County Parcels, layer 1 | County Hub parcel download |
| Houston | Included | Distinct Commons county parcel item | HoustonParcels, layer 0 | Commons public parcel download |

Final official pages, item identities, checked date and metadata URLs are retained in the
[research inventory](../clearparcel/datawatch/minnesota_county_parcel_access.json).
Rendered county Hubs/About pages and Commons catalog results were reviewed; shell HTML
and catalog discovery were not used as final proof. Cook's July 2026 fee schedule prices
requested assessor electronic query results, mailing labels and paper outputs; it does not
establish a fee on the separately advertised public parcel geometry layer. Dakota's current
policy provides free standard GIS data; its $41.13 half-hour charge covers special services.
Those fees are not county parcel dataset fees. Fillmore/Houston public county-owned items
and rendered Commons downloads establish dataset access beyond Beacon viewing.

All eight resolved county REST layers report **esriGeometryPolygon**. Dakota item narrative
calls its data lines, but exact REST geometry and the existing observation both identify
polygons; that discrepancy is recorded without changing the product identity. MetroGIS
county polygon layers remain separate products and cannot borrow county-direct counts.
Dakota REST/download share only the exact verified `mn-dakota-parcels-direct` observation.
The newly verified Douglas product did not match its runtime source, so its published
inventory receives no inferred count or health join.

Clearwater advertises ESRI Shapefile format; its current `Parcel.zip` passed bounded HEAD
with ZIP type and no body read. The older catalog `Parcel_Clearwater.zip` returned 404.
Legacy Douglas GIS download navigation and relative Fillmore/Houston departmental links
returned 404; useful current official About/canonical county routes were resolved separately.
No parcel features, property-search pages or archive bodies were read. Five scoped rendered
Commons searches show statewide/derived resources but do not prove repository-wide absence;
those distinct repository categories remain unknown. Clearwater's published download does
not establish an authorized REST layer. No runtime registry, configuration, scheduling,
provider polling, deployment or production writes occurred; all five existing research holds
remain unchanged. Earlier staging results elsewhere in this document remain historical observations.

### Olmsted–Scott inventory batch, 2026-10-06

The exact nine counties are Olmsted, Otter Tail, Pipestone, Polk, Pope, Ramsey,
Renville, Rice and Scott. This batch adds **25 reviewed / 11 blocked** category
assessments; the other 78 county records are unchanged. Eight county-direct
classifications are free for the advertised public product; Rice's current
county download/product-policy scope remains unresolved, so its classification
and legacy research completion remain unset. All nine statewide memberships
are supported by the dated official publication, separate from current observations.

| County | Distinct county Commons repository | County REST | County download |
| --- | --- | --- | --- |
| Olmsted | Unknown | Blocked (403) | Advertised free; agreement gate unaccepted |
| Otter Tail | Unknown | ParcelView layer 25, polygon | Hub Parcels, same layer 25 |
| Pipestone | Unknown | TaxParcels layer 0, polygon | Hub Tax Parcels, same layer 0 |
| Polk | Unknown | TaxParcels layer 0, polygon | Current Hub Tax Parcels, same layer 0 |
| Pope | Unknown | TaxParcels layer 0, polygon | Hub Tax Parcels, same layer 0 |
| Ramsey | Metro county polygon sublayer 4 | Blocked (403) | Current Attributed Parcels Hub product |
| Renville | Unknown | TaxParcels layer 0, polygon | Hub Tax Parcels, same layer 0 |
| Rice | Current county-owned Tax Parcels item | TaxParcels MapServer layer 1, polygon | Blocked; current Commons page says unavailable |
| Scott | Metro county polygon sublayer 5 | Parcels layer 0, polygon | County-authorized free Hub Parcels |

Official county pages or the explicit [MnGeo county parcel source table](https://mn.gov/mngeo/gis-data-and-maps/info-by-topic/land-ownership/property.jsp)
establish product delegation. Linked county Hub About pages were rendered and their
public item metadata and exact layer identities inspected; no viewer or feature table
was opened. All seven accessible exact REST layers identify **esriGeometryPolygon**.
Ramsey's public item describes parcel polygons, but its direct metadata returned 403.
Olmsted's cached official REST page identifies polygon geometry; that is dated cached
evidence and does not establish current metadata success. No archive was opened or
retrieved, and no terms gate was accepted.

[Olmsted Data Catalog](https://webapp.co.olmsted.mn.us/shoppingcart/site/Planning/GIS/DataCatalog/categories.aspx?CTypeid=4)
explicitly lists countywide Parcel Boundaries and cites adopted Resolution 19-248,
allowing public geospatial downloads at no cost subject to accepting its disclaimer.
The linked terms were read; they address as-is use, derivative-product responsibility
and liability. Addressing, mailing-list and subscriber-map fees do not establish parcel
dataset pricing. The download is advertised independently of the unaccepted gate and
blocked current REST access; discovery grants no unattended-use authorization.

Otter Tail's current public Parcels item now references **layer 25**, distinct from the
older discovery layer 8. Polk's current item references **TaxParcels/FeatureServer/0**;
its older item instead references **TaxParcels_public/FeatureServer/1**. The latter was
also inspected as polygon metadata but cannot supply current-product observation facts.
Neither county product gains an inferred identity join. Pope's assessor report/payment
processing fees and Renville's Landshark document subscription are separate from parcel
dataset fees. County as-is/no-warranty item terms were inspected; generic Hub
"No License Provided" labels do not themselves establish an automation prohibition.

Ramsey's current [Attributed Parcels item](https://www.arcgis.com/sharing/rest/content/items/3115ff609037465796604556843420be?f=pjson)
and rendered About advertise the county-native parcel product with unrestricted item
terms and a request to verify source/currentness. [MetroGIS](https://metrogis.org/how-do-i-get/parcel-data/)
corroborates native county geospatial publication without fee/licensure, including Ramsey
and Scott. Scott's county GIS page explicitly provides authoritative Parcels downloads
free through its linked Hub; item terms contain reference-only, liability and indemnity
language. Regional seven-county parcel compilations remain separate products.

Rice's old MnGeo-linked item is inaccessible. A rendered Commons search and current
[Tax Parcels item](https://www.arcgis.com/sharing/rest/content/items/d79e1a5432e44980877703f5371a1a70?f=pjson)
resolve a distinct county-owned repository product and exact county MapServer/1. Direct
bounded metadata succeeds, but its current Commons About reports a secure-service
authorization requirement and unavailable downloads. The county Maps page direct read
returned 403; current county homepage and item disclaimer were reviewed. No denial or
authorization gate was bypassed. Prior discovery of a FGDB archive does not resolve the
current download/product-policy scope, and technical REST access does not finish Rice's
legacy county-direct classification or authorize polling.

All nine scoped Commons catalogs were rendered. Rice's current county-owned item is a
distinct repository product. Subsequent review of the already-fetched official metropolitan
item and service metadata establishes separately identified Ramsey/4 and Scott/5 county
polygon sublayers. Like Anoka, Carver, Dakota, Hennepin and Washington, these are distinct
county repository resources even though their provenance is regional. The other six
repository categories remain unknown; bounded searches do not prove exhaustive absence.
Native county products and their observed identities remain independent.

Exact vetted public identities are retained only for Pipestone, Rice, Ramsey and Scott.
Rice's repository/REST and Pipestone/Scott REST/download share their same observation;
Ramsey's advertised download can retain historical source facts while current REST remains
blocked. Olmsted's newly inspected source did not match its observed product and receives
no inferred count/health join. All eight existing research holds remain unchanged. No
provider/configuration/scheduling/deployment or production writes occurred.

### Historical original 35 county-direct results

County-direct results for the original 35 audited counties:

- **12 Free parcel data**
- **12 Fee-based parcel data**
- **11 Parcel viewer only**
- **0 Parcel data by request / restricted**
- **0 No direct parcel dataset verified**

The earlier review identified **13 county-direct machine-readable parcel candidates**. Its bounded
validation request from GERTKEN-PC returned HTTP 200 for all 13 candidates. After the Brown
product-policy correction, **12** retain a usable direct-source research assessment. This confirms
reachability only; it does not add those candidate sources to the deployment registry or enable
additional provider polling.

## Current Watchtower monitoring interpretation

The earlier production observation documented before the staging expansion contained:

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

### Historical staging evaluation

The following **9 counties** passed a bounded local Watchtower-engine probe on 2026-10-06
and were accepted in the earlier staging evaluation. Brown's subsequent research policy hold
supersedes that earlier approval assessment; technical probe results remain historical evidence:

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

The following **11 counties** retain research holds pending terms clarification. Advertised
free products and historical runtime observations remain separate from these research decisions:

- **Blue Earth** — official county pages state property-tax GIS data are available for purchase;
  request terms say use may be restricted by a license agreement.
- **Brown** — requested complete parcel Shapefile product costs $697 with signed disclosure;
  reconcile its separately advertised Open-Source GIS Data Hub/public REST permission scope.
- **Faribault** — the July 1, 2026 county fee schedule explicitly distinguishes no-charge online
  viewers from parcel GIS data requiring a request and payment.
- **Kandiyohi** — the county authorization/release form requires agreement and payment, restricts
  delivered files to the identified project, and restricts transmission without written consent.
- **Lincoln** — the county geospatial pricing schedule states that some data require a license
  agreement and prices parcel boundaries/attributes per parcel.
- **Lake** — prior review retained a research hold for its advertised free product pending licensing clarification.
- **Lyon** — prior review retained a research hold for its advertised free product pending licensing clarification.
- **McLeod** — prior review retained a research hold for its advertised free product pending licensing clarification.

- **Stevens** — free county parcel product retained; general/visual-only use terms excluding financial or decision-making uses need clarification.
- **Swift** — 2026 parcel dataset pricing is separate from free interactive viewing; public-layer permission scope needs clarification.
- **Wilkin** — fee-exempt self-service parcel download retained; signed waiver/distribution statement applicability needs clarification.

The original four holds, Brown, Lake, Lyon, McLeod and Stevens remain unchanged. All holds are retained research decisions; their licensing text is not reinterpreted here as an express
ban on metadata-only monitoring. Public technical reachability is not treated as permission to automate a county data
product that the county separately licenses or sells.

The nine candidates from the earlier evaluation were added to **private staging registry version 7**
on 2026-10-06, all assigned to the cloud execution profile. Staging image `473157b` completed
**31/31 cloud checks OK** and the local profile completed **4/4 OK**. A generation-matched merge
produced a **35/35 OK** hybrid aggregate with worker provenance `cloud=31` and `local=4`.

Against that aggregate, the county model resolves to **70/87 actively checked counties**:
59 through MnGeo Plan Parcels Open, 24 through county-direct sources, and 13 through both paths.
The separate public v2 preview revision `00002-bn8` was queried directly and confirmed to render
the KPI **70/87** with those component counts. This observed coverage is separate from the
research policy holds. Brown's runtime observation remains represented; the four previously
unmonitored held counties require terms clarification before activation.

This staging activation does not enable authoritative provider scheduling. No GIS-provider Cloud
Scheduler job was created or enabled, and the production UI service was not replaced.

## Historical original 35 county summary

| County | County-direct access | MnGeo open coverage | Direct machine-readable source | County parcel dataset fee |
| --- | --- | --- | --- | --- |
| Blue Earth | Fee-based parcel data | No | No | $30 Basic Bundle for for-profit use; qualifying nonprofit 10%; qualifying government may receive at no cost |
| Brown | Fee-based parcel data (requested Shapefile product; open-route scope unresolved) | No | No (held; REST metadata available) | $697 complete parcel dataset; signed disclosure; 2025-effective schedule |
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

## Historical original 35 machine-readable sources discovered

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

These were historical candidate-low-frequency assessments; Brown now retains a research terms
hold. This is a research/operations assessment, not a
production schedule. Watchtower must continue to use bounded read-only checks, honor rate limits
and HTTP 429 responses, avoid raw-data redistribution unless permitted, and never scrape
human-facing property-search pages.

## Structured research dataset and schema

Persistent research data:

clearparcel/datawatch/minnesota_county_parcel_access.json

Schema/validation code:

clearparcel/datawatch/parcel_access.py

The schema is version 3. Its four source-inventory categories retain independent review status,
availability, checked date, evidence and explicit public source identities. Each county record captures county and review date,
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

For records without a completed county-direct assessment, the neutral research label is:

**County-direct parcel access not yet researched**

That statement is deliberately separate from whether Watchtower is already monitoring the county
through MnGeo.


### Isanti–Mower inventory batch, 2026-10-06

Exact counties: Isanti, Itasca, Koochiching, Lake, Lyon, McLeod, Mille Lacs,
Morrison and Mower. Actual official reviews add **28 reviewed / 8 blocked**
category assessments; all nine have dated statewide inclusion evidence. Other 78
county records are unchanged. Eight county-direct classifications are complete;
Koochiching's current download/product-policy scope remains unresolved.

| County | Distinct Commons repository | County-authorized REST | Published parcel download |
| --- | --- | --- | --- |
| Isanti | Unknown | TaxParcels_Public/0 polygon | County Hub product |
| Itasca | Tax Parcels county product | ParcelModel/8 polygon | Delegated Commons GeoPackage and ZIP |
| Koochiching | Unknown | Tax_Parcels/0 polygon; unmatched observation | Unknown; old ZIP is discovery only |
| Lake | Tax Parcels county product | Delegated county-specific state service/0 polygon | Commons GeoPackage and ZIP |
| Lyon | Unknown | Parcels/0 polygon | County Hub product |
| McLeod | Unknown | Unknown | Advertised parcel Shapefile; terms gate untouched |
| Mille Lacs | Unknown | AGO_Parcels_and_Lots/3 polygon | County File Geodatabase item |
| Morrison | Tax Parcels county product | MorrisonParcelsQ2/0 polygon | County-linked Commons product |
| Mower | Unknown | Open_Data/4 polygon | Current county Hub product |

[Itasca's adopted resolution 2015-74](https://metrogis.org/media/ttvdxaqg/itascacountyresolution_2015_12_09.pdf)
authorizes electronic county GIS distribution without charge or licensure and directs
county/Commons distribution. The current county Maps page corroborates that route;
the older signed-license/fee document is retained as superseded historical practice.
County-hosted ParcelModel and the delegated Commons parcel product remain distinct.

[Lake's county GIS Data policy](https://www.co.lake.mn.us/gis/gis-data/) advertises
free transmission and explicitly delegates public GIS data to Commons, but its
disclaimer and the parcel item's license restrict third-party use. [McLeod's GIS Data
page](https://www.mcleodcountymn.gov/departments/public_works/gis_(mapping___surveying)/gis_data.php)
advertises parcel Shapefiles with internal-purpose and third-party disclosure/use
restrictions. Lyon's published parcel item says reference use only, no redistribution.
These three new research-only **hold-for-terms** decisions retain free product
availability separately. Lyon's conservative hold reflects licensing uncertainty,
not a claim that its terms expressly prohibit bounded metadata monitoring. Brown and
the original four holds remain unchanged; runtime configuration is untouched.

[Morrison's GIS Fees page](https://morrisoncountymn.gov/292/GIS-Fees) labels its
parcel map layer open; Tax/CAMA data, imagery, Beacon subscriptions, labels and
labor fees describe separate outputs. Its Commons/REST/download share the vetted
existing observation identity. Koochiching's newly found service is unmatched and
borrows no count or health. Mille Lacs' File Geodatabase download is not presumed
identical to its separate REST layer. Mower's current published parcel item replaces
an inaccessible old catalog lead.

Six distinct-repository categories, McLeod REST and Koochiching download remain
unknown after actual county/MnGeo/Commons reviews. Scoped searches cannot prove
repository-wide absence. Isanti and Lyon county-home/GIS requests returned 403;
MnGeo-linked official county Hubs supplied final metadata instead. No property search or viewer data/table interaction was
performed; no terms gate was accepted. Dataset About metadata,
public item and layer metadata were read; no external parcel archives were opened,
clicked or retrieved. Advertised downloads establish product publication, not body
integrity or unattended authority. GeoPackage, Shapefile and File Geodatabase facts
are retained only where official publication states them; ZIP interior formats and
REST export formats are not inferred. Typed stable geometry/file projection is documented below.


### Sherburne–Stevens inventory batch, 2026-10-06

Exact counties: Sherburne, St. Louis, Stearns, Steele and Stevens. Actual official
reviews add **15 reviewed / 5 blocked** category assessments. All five have dated
statewide inclusion evidence and published county-authorized parcel downloads; the
other 82 county records are unchanged. These five county-direct classifications
are free parcel data, independently of unattended monitoring permission.

| County | Distinct Commons repository | County-authorized REST | Published parcel download |
| --- | --- | --- | --- |
| Sherburne | Unknown | OpenData/Parcels FeatureServer/0 polygon | County Parcels Hub product |
| St. Louis | Unknown | Open_Data MapServer/7 polygon | Native Tax Parcels Hub product |
| Stearns | Unknown | Unknown | Official parcel compressed ZIP; HEAD only |
| Steele | Distinct Tax Parcels county product | County Tax_Parcels MapServer/0 polygon | Delegated Commons parcel product |
| Stevens | Unknown | July_2026_Parcels FeatureServer/0 polygon | County July 2026 Parcels Hub product |

[Sherburne GIS Applications](https://www.co.sherburne.mn.us/841/GIS-Applications)
authorizes its open-data Hub for downloads/services; the current public Parcels
About page resolves its county polygon layer. Assessor CAMA subscription charges
are a separate product. [St. Louis Data - Geospatial](https://www.stlouiscountymn.gov/departments-a-z/economic-community-development/enterprise-gis/data-geospatial)
explicitly provides free parcel data. Its native Tax Parcels product uses the
exact vetted existing observation identity; the separate State Standard product
/6 receives none. Existing optional null-geometry QA remains unchanged.

The [Stearns county Hub](https://stearns-county-gis-stearns.hub.arcgis.com/)
explicitly lists its parcel ZIP as free without a license agreement. Bounded HEAD
returned 200/ZIP; no archive body was read and the interior format is unknown.
The page's imagery/LiDAR and Beacon fees are separate products. No authorized
parcel REST layer was established from its public distribution page; viewer
backends were not investigated.

[Steele GIS](https://www.steelecountymn.gov/departments/gis_geographic_information_systems/index.php)
delegates datasets to Commons. MnGeo's distinct Tax Parcels item, its rendered
About page and current county layer metadata establish repository, REST and
download independently of statewide inclusion. Linked resolution and fee-schedule PDF returned 404; the current fee landing
mentions potential requested-data charges without an actual parcel dataset price.
Current public parcel distribution and disclaimers were reviewed.
[Stevens GIS Open Data](https://www.stevenscountymn.gov/993/GIS-Open-Data)
advertises free GIS products in Shapefile, CSV and KML with zipped metadata; its
July 2026 Parcels About identifies the current polygon layer and download. These
county-wide format statements do not prove a particular archive's interior.
Its linked resolution returned a redirect loop. The item restricts use to
general/visual purposes, excluding financial or decision-making purposes.

Stevens receives a research-only **hold-for-terms** pending clarification of its
general/visual-only terms excluding financial or decision-making uses. Free
availability and its completed county-direct classification remain verified.
This is licensing uncertainty, not an established prohibition on bounded metadata
monitoring. The other four decisions remain **not-assessed**; no provider is activated.
Four distinct-repository categories remain unknown after actual rendered scoped
Commons/state metadata reviews; bounded searches do not prove exhaustive absence.
The eight existing holds remain, for **nine research holds total**. Typed stable geometry/file projection is documented below. No parcel features, property-search pages,
archives or download bodies were retrieved; no agreement gates were accepted.


### Swift–Yellow Medicine inventory batch, 2026-10-06

The exact eight counties are Swift, Traverse, Wabasha, Waseca, Washington, Wilkin, Wright,
and Yellow Medicine. This batch adds **27 reviewed / 5 blocked** assessments. The official
statewide item includes seven; Swift is excluded from that dated publication. Current
runtime coverage remains authoritative.

[Swift 2026 fees](https://swiftcounty.gov/uploads/dm/48672/2026_Licenses_Fees_and_Service_Charges)
explicitly price GIS parcel data: $0.03 per parcel without tax information, $0.04 with tax
information, $450 for the full layer with tax information; government agencies are exempt.
Its county GIS and Interactive Maps pages separately authorize free viewing. Public
staff-owned Swift_Parcels polygon metadata does not establish free downloadable delivery.
Swift is fee-based with a research hold pending clarification of the fee/public-service scope;
this is not an assertion that metadata-only monitoring is prohibited.

[Wilkin policy](https://wilkincounty.gov/vertical/sites/%7B6E7AB7CB-4769-4357-B6C8-90E546FFE488%7D/uploads/GIS_data_policy_12-17-19.pdf)
explicitly exempts self-service open-portal users from fees. Rendered county Tax Parcels About
advertises a public downloadable polygon product. Its free route is retained separately from
priced requested GIS/Tax Parcel packages ($3,000 plus contractor fees; individual parcels
$0.50 each, minimum $20 plus contractor fee). Recipients must sign waiver/release and distribution
liability statements; applicability to self-service access needs clarification, so Wilkin is
free with a research hold. Requested delivery formats are Shapefile/geodatabase; these are not
asserted as a particular Hub export format. No agreement was accepted or data downloaded.

Wabasha has a distinct state-hosted county parcel product. Official metadata identifies the
county publisher, countywide polygons, and no access/use restrictions beyond verification of
source/currentness. Rendered Commons About advertises GeoPackage and a separate ZIP data
product. Its county GIS landing returned 503; final official published product metadata remains
available. Waseca's county-owned Commons About explicitly describes parcel polygons shared to
Commons and advertises Download. Wright's county Hub and Commons resolve the same parcel
product. Traverse and Yellow Medicine have MnGeo-delegated county Hub parcel downloads;
public as-is/no-warranty/liability disclaimers remain separate from unattended-use permission.

[Washington Survey Division](https://www.co.washington.mn.us/surveyor) and its Maps page provide
free parcel data through GeoCommons. The official Metropolitan 7-County Parcel Polygons item
states individual county sublayers/feature classes, no fees/license and public-domain terms.
The verified Washington County Parcels subdataset is **FeatureServer/6**, distinct from the
statewide compilation and from the regional aggregate. Its advertised FGDB package contains
all seven counties; no native Washington-only archive or product counts/dates are inferred.
This verified county-specific regional subdataset qualifies as a distinct repository resource.

All eight bounded layer metadata reads report **esriGeometryPolygon**. No feature queries,
archive bodies, viewer scraping, private registry reads or source activation occurred.
Rendered scoped Commons searches for Swift, Traverse, Wilkin and Yellow Medicine did not
establish distinct repository products; these remain unknown, without claiming exhaustive
absence. Swift download remains unknown. Exact vetted public observed IDs are retained only
for Swift, Waseca and Wabasha; Wabasha/Waseca shared repository/REST/download representations
reuse the same observation identity. Discovery and the two new holds change research only.


### Stable source evidence projection and repository reconciliation, 2026-10-06

Optional source `geometry_type` and `file_type` now preserve verified stable facts
from the county-specific official evidence and bounded metadata reviews above.
The profile uses validated current live metadata first and falls back to these
scalars. Unknown facts remain null; parcel names and unspecified export formats
do not establish geometry or MIME. Supported ZIP containers retain their offered
file type without claims about contents. Washington's regional FGDB package
contains point and polygon products, so its download geometry remains null while
its exact county polygon sublayer is retained. Mille Lacs' separate FGDB geometry
and MIME remain unknown; original Task 4a service findings without retained exact
geometry facts remain null. No provider metadata reads were repeated to fill gaps.

The already-reviewed official metropolitan item and service/About evidence identify
Ramsey County Parcels/4 and Scott County Parcels/5 as `esriGeometryPolygon` county
resources, distributed freely without fee or license, public domain under Chapter 13.
Their repository categories are now reviewed/available, matching the same contract
used for the other five metropolitan counties. County-native classifications,
monitoring decisions and the eleven holds are unchanged; regional products have no
native monitored-source IDs, counts or provider dates. Scott now has all four
categories reviewed; Ramsey's native REST category remains unresolved.

Repository county acquisition and catalog refresh dates require a unique, exact
catalog data reference to an evidence-backed approved dataset/item, selected layer
or offered file. Sources with a selected layer require that same layer in the vetted
REST URL or dataset layer suffix; shared regional maps/items and unqualified archives
cannot supply county subdataset dates. County/Hub/search landing links cannot join dataset dates. Unmatched
or ambiguous repository products retain null dates. Statewide county contribution
dates retain their separate catalog association. Catalog checks, counts and health
are never borrowed as dataset observations. Regression tests cover two products in
one county, shared generic links, separate native/regional identities, safe live
precedence and unknown operational facts for unmonitored products.


## Local profile/browser acceptance (2026-10-06)

All 87 county profiles were exercised through both maps with actual Chrome
Browser/CUA keyboard interactions in a sanitized local fixture; representative
pointer clicks opened Brown and Winona. All summary modes and three representative
MN GAC field selections retained the full four groups. Desktop and 390px layout,
long source/evidence values, focus containment/return, internal scrolling and
refresh pause/resume passed. CSV and decoded Excel cells matched across all county
and source rows, and all county JSON detail profiles matched the statewide JSON.
These synthetic observations validate behavior, not new provider observations or
live coverage. No external county archives or download endpoints were opened.

The dashboard now labels its conservative derived result as 15 complete county
profiles; 16 inventories have all four category reviews complete, with Aitkin's
county-direct assessment still unresolved. Publication reporting is independently
labeled Current/Overdue/Unknown using the publication health threshold; an overdue
publication fails `/healthz` without removing county profiles or altering source
check times. Task 8 preview release and final review remain pending. The historical
Benton unsupported archive-open incident above remains part of the audit.
