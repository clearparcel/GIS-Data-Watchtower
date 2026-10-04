# GIS Data Watchtower provider-use compliance review

Reviewed: 2026-10-04

This document records an operational terms-of-use review. It is not legal advice. Re-review provider terms before public launch and periodically afterward.

## Current polling behavior

The dashboard's 30-second HTML refresh reads locally saved Watchtower state. It does **not** query external providers.

External provider requests occur only when `check_sources` runs, currently through the CLI or the dashboard's **Check data now** action. No automatic high-frequency provider polling is required by the dashboard.

A direct county deep-QA check generally makes approximately 8–11 HTTP requests: service/layer metadata, count/statistics queries, bounded duplicate/completeness checks, and one geometry sample capped at 250 records.

## Operating rules

1. Do not scrape human-facing property-search pages.
2. Prefer documented public APIs, OGC services, ArcGIS REST services explicitly published as open/public data, and MnGeo opt-in datasets.
3. Do not bypass authentication, referrer restrictions, rate limits, robots controls, or provider access controls.
4. Treat HTTP 429 as a stop signal; do not immediately retry through a fallback transport.
5. Keep full deep-QA polling conservative. Until provider-specific permission says otherwise, target no more than four full checks/day/source in unattended production; daily is preferred for county parcel QA because source data typically changes much less frequently.
6. Keep geometry retrieval bounded. Current default: 250 features/check.
7. Do not redistribute raw provider records through Watchtower snapshots unless the provider's redistribution terms permit it.
8. Preserve provider attribution/disclaimers where required.
9. Public Watchtower should expose derived health/metadata, not republish parcel owner/assessment records by default.
10. Re-review terms when adding a source, materially increasing frequency, or moving from private monitoring to public redistribution.

## Provider review

### MnGeo / Minnesota DNR services — LOW RISK

Watchtower uses published ArcGIS REST, WMS, imagery, and statewide open-data services. MnGeo explicitly documents WMS use in GIS software and web applications. Its statewide open parcel dataset is an opt-in public compilation. The 2026 MnGeo report states that public inclusion depends on county opt-in.

Operational decision: automated low-frequency metadata/query monitoring is consistent with the documented purpose. Keep attribution and dataset limitations. Do not assume a county's direct endpoint inherits MnGeo's public redistribution permission.

### FEMA NFHL — LOW RISK

FEMA publishes public ArcGIS/OGC GIS services for direct GIS access. Watchtower performs read-only metadata/query checks.

Operational decision: allowed as low-frequency public-service access. Do not bypass access controls; stop/back off on provider throttling.

### USDA NRCS Soil Data Access — LOW RISK WITH LOAD CONTROLS

Soil Data Access is expressly a suite of web services for real-time spatial/tabular requests. Documentation specifies query/result constraints, including a 100,000-row maximum for post.rest and constrained WFS spatial extents.

Operational decision: current metadata/catalog use is appropriate. Keep queries bounded and honor service errors/timeouts. User-Agent must identify Watchtower/contact site.

### Scott County — LOW RISK

Scott County states that its authoritative GIS data are free of charge and that users have unrestricted access to online map services.

Operational decision: direct REST monitoring is consistent with the published open-data purpose.

### Olmsted County — LOW RISK

The monitored service is explicitly published under `AGOL_Open_Data/Parcels`, supports public query operations, and Olmsted directs users to its ArcGIS Online Open Data resources.

Operational decision: direct REST monitoring is consistent with the service's published purpose.

### Ramsey County — LOW RISK / ATTRIBUTION

Ramsey County has documented a free/open GIS initiative and public GIS files without cost or license.

Operational decision: low-frequency monitoring is consistent with open-data publication. Preserve county attribution and disclaimers.

### Waseca County — LOW RISK FOR GIS SERVICE; DO NOT SCRAPE PROPERTY PORTAL

Waseca's GIS page states that the county adopted a formal Free & Open GIS-data sharing policy. Separately, its property-information website prohibits applications designed to mine/gather/extract data.

Operational decision: Watchtower may monitor the published GIS FeatureServer, but must not automate the property-information search website. Do not conflate the two systems.

### Beltrami County — MODERATE / KEEP TO OPEN GIS ENDPOINT

Beltrami's human-facing property portal prohibits automated mining/gathering/extraction. Watchtower instead uses a service named `BeltramiOpenData`.

Operational decision: keep monitoring limited to the explicitly published GIS REST endpoint; do not automate the property portal. Before public redistribution beyond derived metrics, obtain/record the GIS endpoint's specific license/disclaimer.

### Dakota County — LOW/MODERATE; DISCLAIMER MUST FOLLOW REDISTRIBUTED DATA

Dakota's ArcGIS services state that GIS data are public under the Minnesota Government Data Practices Act and are provided as-is. The service says that if GIS data or a portion is transmitted to another user, the county disclaimer and accompanying metadata must also be provided.

Operational decision: read-only monitoring is acceptable. Watchtower public pages should publish derived status/counts rather than raw Dakota records. If raw data or a portion is ever redistributed, include the required disclaimer and metadata.

### Aitkin County — MODERATE/HIGH FOR REDISTRIBUTION

Aitkin publicly exposes GIS mapping and MnGeo lists downloadable Aitkin parcel data. However, an Aitkin ArcGIS parcel item's metadata says the dataset should not be distributed to other parties without consent of the County GIS Coordinator.

Operational decision: private read-only monitoring can remain low-frequency, but Watchtower must not redistribute Aitkin parcel records. Before a public Watchtower relies on the direct endpoint for anything beyond derived status/metadata, request clarification/consent or switch public-facing derivations to the MnGeo opt-in public parcel compilation.

### Morrison County — MODERATE; CONFIRM DIRECT API AUTOMATION

Morrison's LandShark terms strictly prohibit scraping/harvesting human-readable output with bots. MnGeo separately lists downloadable Morrison parcel data, and Watchtower uses a direct ArcGIS FeatureServer rather than LandShark.

Operational decision: do not automate LandShark. The FeatureServer distinction makes current API monitoring materially different from prohibited screen scraping, but provider-specific confirmation is advisable before unattended frequent QA or public redistribution. Until confirmed, keep Morrison checks conservative and derived-only.

### St. Louis County — LOW/MODERATE

St. Louis County publishes GIS/open-data infrastructure and an as-is GIS disclaimer. No automation prohibition was found in the reviewed GIS disclaimer/website terms.

Operational decision: low-frequency read-only REST monitoring is acceptable; preserve disclaimer/attribution for public presentation.

### Douglas, Swift, Rice, Pipestone, Koochiching — MODERATE PENDING SOURCE-SPECIFIC TERMS

Public machine-readable GIS endpoints were identified, and MnGeo identifies downloadable parcel data for several of these counties. The review did not locate explicit API polling/rate terms for every direct endpoint.

Operational decision: retain low-frequency read-only monitoring, no raw-data redistribution, bounded geometry samples, and provider throttling compliance. Record explicit county terms when found or obtain confirmation before substantially increasing frequency.

### Hennepin County imagery — MODERATE / METADATA-ONLY

Watchtower checks a publicly reachable county imagery MapServer. No explicit automated-polling terms were located in this review.

Operational decision: keep this source metadata-only and low-frequency. No image-tile crawling or bulk imagery retrieval.

## Public-launch requirements

Before making Watchtower public:

- display source/provider attribution;
- include provider-specific disclaimers where required;
- keep raw owner/assessment records out of public snapshots by default;
- document that county parcel boundaries are approximate and not legal surveys;
- resolve Aitkin direct-endpoint redistribution language;
- seek clarification for Morrison direct API automation if retained;
- record source-specific license/use-constraint metadata in the source registry;
- publish Watchtower's own respectful-use policy and contact information.

## Recommended cadence

- MnGeo statewide metadata/open-data services: every 6–24 hours.
- Direct county parcel deep QA: daily by default; maximum unattended target 4/day unless provider guidance supports more.
- FEMA/USDA metadata availability: every 6–24 hours.
- Imagery/LiDAR service availability: daily.
- Manual development checks: occasional, non-concurrent, and never looped at high frequency.

Parcel datasets are generally not changing minute-to-minute, so higher-frequency deep QA provides little operational value while increasing provider load.
