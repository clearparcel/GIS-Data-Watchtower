# Project status

Last validated: **2026-10-06**

GIS Data Watchtower is public, MIT-licensed, and supports local, cloud, and hybrid execution.

## Validated capabilities

- Windows and Ubuntu CI on Python 3.12, 3.13, and 3.14
- ArcGIS/WMS/WFS and catalog/API monitoring adapters
- bounded provider-friendly polling and HTTP 429 handling
- plain-language dashboard with county pages
- CSV, JSON, and native Excel (`.xlsx`) snapshot exports
- local filesystem and optional Google Cloud Storage persistence
- Cloud Run Job container deployment
- source execution profiles (`cloud`, `local`, `any`)
- hybrid worker aggregation with per-source worker provenance
- MN GAC parcel-field completeness analysis with county pages, interactive Minnesota county map, and JSON/CSV/Excel exports

## ClearParcel staging validation

A private ClearParcel staging deployment has validated the hybrid architecture against a 26-source production registry:

- **22 cloud-profile sources:** 22 OK / 0 warning / 0 error
- **4 local-profile sources:** 4 OK / 0 warning / 0 error
- **aggregate:** 26 OK / 0 warning / 0 error
- all 26 aggregate observations have worker provenance
- cloud/local parity was exact for the sources accepted from both environments: status, feature counts, and schema hashes matched

The four local-profile sources are kept local because their providers' network/TLS behavior does not support the Google Cloud egress path used in staging. Watchtower does not bypass those restrictions.

The hardened post-security-review build was revalidated end-to-end on 2026-10-05: the Cloud Run worker completed **22/22 cloud sources OK**, the local worker completed **4/4 local-only sources OK**, and the resulting aggregate remained **26/26 OK** with **0 unassigned observations**. JSON, CSV, and Excel exports each represented all 26 monitored sources.

The same staging architecture also validated the MN GAC completeness feature against MnGeo Plan Parcels Open. The 2026-10-05 observation represented **59 of 87 counties**, **2,710,201 parcel records**, and all **91 standard fields** using **8 bounded grouped-statistics queries**. The other 28 counties are reported as **No data**, not 0%. The observed record-weighted all-field population was **42.92%** and Mandatory-field population was **78.37%**; these are descriptive population statistics, not compliance grades. The full cloud retry after this feature was enabled returned **22/22 OK**, preserving the **26/26** hybrid aggregate.

## County parcel-data access audit

The 35-county parcel-specific access audit is complete. After reconciling public technical endpoints against official county distribution/fee policies, county-direct results are **13 Free parcel data**, **11 Fee-based parcel data**, and **11 Parcel viewer only**. Blue Earth, Faribault, Kandiyohi, and Lincoln remain held for terms clarification despite reachable parcel services. The nine approved county-direct sources outside current MnGeo coverage (Brown, Dodge, Hubbard, Mahnomen, Meeker, Roseau, Sibley, Todd, and Wadena) are now present in **private staging registry version 7** as cloud-profile sources. On 2026-10-06 the hardened staging image `473157b` completed **31/31 cloud checks OK**; the local profile completed **4/4 OK**; the merged staging aggregate completed **35/35 OK**. The staging county-monitoring model now resolves to **70/87 actively checked counties**: 59 through MnGeo Plan Parcels Open, 24 through county-direct sources, with 13 overlaps counted once. The separate public v2 preview was updated to revision `00002-bn8` and its rendered KPI was verified at **70/87**. No authoritative GIS-provider scheduler was enabled and the production UI service was not replaced. See `docs/county-parcel-data-access-audit.md`.

## Public dashboard hosting

A separate read-only Cloud Run service serves the shareable dashboard at **https://gis-watchtower.clear-parcel.com** through a Google Cloud external Application Load Balancer. The dashboard now reads only the sanitized production object at `gs://clearparcel-watchtower-dark-bit-503017-j7/production/aggregate-state.json`; its service account no longer has access to the unified staging aggregate, private provider registry, or provider credentials.

A dedicated Cloud Run publisher job reads only the unified aggregate object, applies the public allowlist and fail-closed forbidden-field validation, then writes only the production aggregate object. A separate least-privilege scheduler identity invokes that job every **10 minutes**. The final least-privilege publisher execution completed successfully in about **3m6s**. This publication schedule performs no GIS-provider polling and does not replace the multi-day validation gate for the authoritative monitoring schedule.

The public renderer removes operational provider URLs, raw change payloads, tracked values, fingerprints, provenance details, and worker telemetry before rendering or exporting state. The existing private operational dashboard remains separate. Cloudflare is used only for authoritative DNS for the hostname; the record is DNS-only and application traffic is served by Google Cloud. Cloud Armor applies a conservative 120 requests/minute/IP throttle, load-balancer request logging is enabled at full sampling, and Cloud Monitoring checks `/healthz` every minute with availability and Cloud Run 5xx alert policies. Public snapshots carry their own publication timestamp; `/healthz` is designed to fail if publication age exceeds 30 minutes.

## Staging architecture

```text
Cloud Run Job (cloud profile, 22)
              \
               -> aggregate state -> dashboard/exports
              /
Local worker (local profile, 4)
```

The cloud worker persists its staging artifacts in Google Cloud Storage. Private production configuration is supplied through Secret Manager and is not included in this public repository or its container image.

## Concurrency-safe aggregate publishing

The shared aggregate store now uses compare-and-swap writes: Google Cloud Storage deployments use object-generation preconditions, and local/shared-filesystem deployments use an atomic lock-and-replace with retry. Ordinary cloud-job state, history, and alert artifacts also use version preconditions so a stale execution fails closed instead of overwriting a newer object. A normal profiled `watchtower check` run can publish directly to the configured shared aggregate store (opt-in via `aggregate_object` / `WATCHTOWER_AGGREGATE_OBJECT`); no separate script is required. The dashboard and the CSV/JSON/Excel exports read the unified aggregate state and show worker provenance, last-success time, and reporting freshness, with unhealthy sources tracked separately from stale/overdue reporting. See `docs/hybrid-aggregation.md` for the safety model and regression-test coverage.

A single hardened hybrid staging cycle has now been completed successfully. The remaining validation gate is multi-day parallel observation, not basic Cloud Run or aggregate correctness.

## Not yet enabled

- No Cloud Scheduler trigger has been enabled for the GIS-provider staging/check job. The only enabled Cloud Scheduler job is the 10-minute sanitized public-publication job, which performs no provider polling.
- The existing local production monitoring schedule has not been retired.
- The hybrid staging deployment is not yet the authoritative production monitoring scheduler.

## Cloud Run startup behavior

Cloud Run Job provisioning can remain in **Waiting for execution to start** for several minutes after the image is imported and resources are provisioned. In the validated staging environment, successful executions have taken approximately **2m30s to 4m15s** to reach the Started condition. This delay is a Cloud Run scheduling/provisioning interval, not evidence that Watchtower itself has failed.

Operationally, do not cancel an execution solely because Started is still Unknown during the first five minutes. Inspect the execution conditions if the delay exceeds roughly 5–7 minutes, investigate further by 7–10 minutes, and treat an explicit Failed condition as the real failure signal. The configured 15-minute task timeout remains the final execution bound.

## Next validation gate

Run the hybrid system in parallel for several days using the concurrency-safe publishing path, verify aggregate freshness and failure/recovery behavior over multiple real runs, then decide whether Cloud Scheduler should become the primary orchestration mechanism while retaining the local worker for provider-restricted sources.
