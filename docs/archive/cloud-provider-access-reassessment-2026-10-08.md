# Cloud provider access reassessment — 2026-10-08

All four sources then assigned to the local profile returned HTTP 200 and
valid bounded responses from Google Cloud on October 8. The earlier failures
remain real operational evidence, but do not establish a permanent provider
ban on cloud/datacenter access. No execution-profile or scheduling change was
made by the initial investigation. The subsequent user-requested
[USDA connection](usda-cloud-connection-2026-10-08.md) validated both USDA
adapters in Cloud Run and moved their registry assignments to cloud. Rice
and Beltrami were later migrated after actual Cloud Run validation in the [county migration](county-cloud-migration-2026-10-08.md).

## Paired live results

The same standalone Python probe ran on GERTKEN-PC at
`2026-10-08T15:51:37Z` and in Google Cloud Build, us-central1, at
`2026-10-08T15:51:39Z`. Each environment made one request per source, without
retries, authenticated provider access, proxies, or disabled TLS validation.
Timeout was 20 seconds and response size was capped at 1 MiB. HTTP 429 would
stop the probe. No parcel features were downloaded.

| Source | Bounded request | Local | Google Cloud | Cloud response bytes |
| --- | --- | --- | --- | ---: |
| `usda-ssurgo-wfs` | WFS 1.1.0 GetCapabilities | 200, valid capabilities | 200, valid capabilities | 18,979 |
| `usda-ssurgo-mn-catalog` | SQL count of Minnesota survey catalog entries | 200, valid count response | 200, valid count response | 18 |
| `mn-beltrami-parcels-direct` | Configured MapServer layer 2 metadata | 200, valid polygon layer metadata | 200, valid polygon layer metadata | 9,978 |
| `mn-rice-parcels-direct` | Configured MapServer layer 1 metadata | 200, valid polygon layer metadata | 200, valid polygon layer metadata | 27,537 |

The probe used the currently configured provider URLs, including USDA's
`SDMDataAccess.sc.egov.usda.gov` host. It did not substitute a mirror or use
a different endpoint to overcome a failure. The catalog query was
`SELECT COUNT(*) AS survey_count FROM sacatalog WHERE areasymbol LIKE 'MN%'`.

Cloud runtime: Linux, Python 3.13.16, OpenSSL 3.5.7. Local control: Windows,
Python 3.14.6, OpenSSL 3.5.7. Cloud image was
`python:3.13-slim@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c`.
Cloud Build ID: `3389ca56-61b9-47d0-a3c0-bd7dc64f5c9d`.
The build completed successfully; the individual responses above, rather than
the process exit alone, establish source-level connectivity.
The no-source build created no deployed service, provider schedule, or aggregate
output. Its ordinary build/log audit records remain available to project operators.

## Earlier evidence and policy research

The October 4 Cloud Run staging execution `gis-data-watchtower-staging-j7zgl`
reported HTTP 403 for both USDA sources. Beltrami failed with connection
refused from both urllib and curl. These distinguish a refusal/error from a
documented policy: neither establishes a universal or permanent cloud ban.
The exact original Rice failure was not recovered in the bounded log review;
older documentation's general network/TLS explanation is not a substitute for
that missing source-level evidence.

[USDA's official web-service documentation](https://sdmdataaccess.nrcs.usda.gov/WebServiceHelp.aspx)
explicitly lists the configured WFS and REST POST endpoints and documents
programmatic access. No blanket cloud/datacenter prohibition was found in the
reviewed help. [USDA availability guidance](https://sdmdataaccess.nrcs.usda.gov/Help.aspx)
also documents nightly maintenance from midnight to 2 AM Mountain time. That
window does not explain the October 4 failures at approximately 17:55 UTC.

[Beltrami's official GIS page](https://www.beltramicountymn.gov/departments/gis/)
links its GIS data/download offerings.
[Rice's official GIS page](https://www.ricecountymn.gov/152/Geographic-Information-Systems)
points users to Minnesota Geospatial Commons. No explicit blanket cloud ban
was found in the reviewed official material. Absence of such a statement is
not permission for every monitoring operation. In particular, Rice's previously
recorded distribution/automation authorization ambiguity remains unresolved;
a successful metadata request does not resolve it. A subsequent rendered-page
review on October 8 found that the current Rice Commons About page labels the
dataset public, exposes direct REST/API links, and offers CSV, Shapefile,
GeoJSON and KML download options. No export was requested or downloaded.
The earlier secure-service/unavailable-download warning was not reproduced;
it must not be presented as a confirmed current authorization gate.
Human-facing property-search
restrictions must remain separate from official GIS service access.

### What remains ambiguous for Rice and Beltrami

Rice's earlier warning conflicted with its public item and accessible REST
metadata. Today's [official full-details page](https://gis.data.mn.gov/datasets/rice::tax-parcels-rice-county-minnesota/about)
and download choices provide stronger evidence of an intended public release.
The historical warning could have reflected portal/service availability or
configuration; its cause is unknown. The reviewed item license contains
as-is, accuracy, warranty, liability and legal/engineering/surveying-use
limitations, not a cloud or automation prohibition. What still needs an
operational assessment is use of the exact REST operations at a bounded daily
cadence, their actual Cloud Run reliability, and any additional applicable
service policy. No account, authorization gate or license acceptance was
bypassed. A published download option does not prove that an export completes.

Beltrami's [official Tax Parcels item](https://www.arcgis.com/sharing/rest/content/items/0a8f80d07f3044bab1395c59674dc4ad?f=pjson)
is public and points to the same county MapServer/2 already advertised through
its GIS download Hub. Its disclaimer concerns fitness, accuracy and liability;
the reviewed text contains no cloud or automation prohibition. There is no
Rice-style contradictory current download notice established for Beltrami.
Its unresolved cloud issue is primarily operational: why October 4 refused
the Cloud Run connection while October 8 accepted Cloud Build, and whether
the actual worker remains reliable over time. Neither county is established
to have a permanent cloud restriction. The user subsequently authorized their migration, and both full Cloud Run adapters passed; see the [county migration](county-cloud-migration-2026-10-08.md).

## Operational conclusion

Current evidence supports testing these sources as cloud candidates; it does
not justify describing them as permanently cloud-inaccessible. Cloud Build
uses a different runtime and egress path from the actual Cloud Run worker,
and this small probe did not execute each complete Watchtower adapter.

Before reassignment, validate the actual candidate Cloud Run image and adapter
operations through an explicitly authorized isolated staging check, without
saving to the authoritative aggregate. Then assess reliability over separately
authorized daily observations, compare with local results, and preserve
backoff/compliance controls. Resolve any outstanding source terms first.
The initial recommendation was to retain local assignments until validation
and any required configuration approval. The subsequent USDA connection
completed that scoped adapter/configuration step; the broader multi-day
reliability and scheduling gate remains incomplete.
