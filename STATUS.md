# Project status

Last validated: **2026-10-04**

GIS Data Watchtower is public, MIT-licensed, and supports local, cloud, and hybrid execution.

## Validated capabilities

- Windows and Ubuntu CI on Python 3.12 and 3.13
- ArcGIS/WMS/WFS and catalog/API monitoring adapters
- bounded provider-friendly polling and HTTP 429 handling
- plain-language dashboard with county pages
- CSV, JSON, and native Excel (`.xlsx`) snapshot exports
- local filesystem and optional Google Cloud Storage persistence
- Cloud Run Job container deployment
- source execution profiles (`cloud`, `local`, `any`)
- hybrid worker aggregation with per-source worker provenance

## ClearParcel staging validation

A private ClearParcel staging deployment has validated the hybrid architecture against a 26-source production registry:

- **22 cloud-profile sources:** 22 OK / 0 warning / 0 error
- **4 local-profile sources:** 4 OK / 0 warning / 0 error
- **aggregate:** 26 OK / 0 warning / 0 error
- all 26 aggregate observations have worker provenance
- cloud/local parity was exact for the sources accepted from both environments: status, feature counts, and schema hashes matched

The four local-profile sources are kept local because their providers' network/TLS behavior does not support the Google Cloud egress path used in staging. Watchtower does not bypass those restrictions.

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

The shared aggregate store now uses compare-and-swap writes: Google Cloud Storage deployments use object-generation preconditions, and local/shared-filesystem deployments use an atomic lock-and-replace with retry. A normal profiled `watchtower check` run can publish directly to the configured shared aggregate store (opt-in via `aggregate_object` / `WATCHTOWER_AGGREGATE_OBJECT`); no separate script is required. The dashboard and the CSV/JSON/Excel exports now read the unified aggregate state and show worker provenance, last-success time, and reporting freshness, with unhealthy sources tracked separately from stale/overdue reporting. See `docs/hybrid-aggregation.md` for the safety model and regression-test coverage. This closes the "automated local-worker publication" and "dashboard consumption of aggregate state" items noted below as the prior next step; it has not yet been exercised in a multi-day parallel staging run.

## Not yet enabled

- No Cloud Scheduler trigger has been enabled for the staging job.
- The existing local production schedule has not been retired.
- The hybrid staging deployment is not yet the authoritative production scheduler.

## Next validation gate

Run the hybrid system automatically in parallel for several days using the new concurrency-safe publishing path, verify aggregate freshness and failure/recovery behavior under real concurrent writes, then decide whether Cloud Scheduler should become the primary orchestration mechanism while retaining the local worker for provider-restricted sources.
