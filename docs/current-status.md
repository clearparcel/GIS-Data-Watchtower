# Current project status

Last validated: **2026-10-06**

## Release status

GIS Data Watchtower is a public MIT-licensed repository. The public repository contains provider-neutral example configuration only; deployment-specific source registries and credentials remain private.

Base functionality includes:

- provider-friendly GIS service monitoring and bounded QA;
- plain-language dashboard and county views;
- CSV, JSON, and native Excel (`.xlsx`) snapshot exports;
- Windows and Linux support;
- local filesystem and optional Google Cloud Storage backends;
- Cloud Run Job-compatible container deployment;
- hybrid source execution profiles;
- hybrid worker result aggregation;
- concurrency-safe aggregate publishing (GCS generation preconditions, atomic local locking) with dashboard/export consumption of the unified aggregate state;
- MN GAC parcel-field completeness statistics, county-level field tables, and an interactive Minnesota county map driven by the stored statewide observation.

## CI

The project is tested on:

- Ubuntu 24.04 / Python 3.12
- Ubuntu 24.04 / Python 3.13
- Ubuntu 24.04 / Python 3.14
- Windows / Python 3.12
- Windows / Python 3.13
- Windows / Python 3.14

The Linux 3.14 matrix leg also smoke-tests the Docker image.

## County parcel-data access audit

The parcel-specific access audit for all **35** registry-derived `needs-source` counties is complete. County-direct results are **13 Free parcel data**, **11 Fee-based parcel data**, and **11 Parcel viewer only**; Blue Earth, Faribault, Kandiyohi, and Lincoln remain `hold-for-terms`. The nine approved county-direct sources outside current MnGeo coverage are now included in **private staging registry version 7**, all assigned to the cloud profile. The 2026-10-06 hybrid staging cycle used image `473157b`: **31/31 cloud sources OK**, **4/4 local sources OK**, and a generation-protected merge produced a **35/35 OK** aggregate with cloud/local worker provenance intact. Against that aggregate, the county model is **70/87 actively checked** (59 MnGeo, 24 county-direct, 13 overlapping). Both local dashboard rendering and the deployed public v2 preview revision `00002-bn8` were verified to display **70/87**, including the subtext `59 via MnGeo open parcels · 24 via county-direct sources · overlap counted once`. The existing sanitized publisher has propagated the 35-source aggregate to the public data bucket, but the production UI service was not replaced and authoritative GIS-provider scheduling remains disabled. Full evidence and methodology are documented in `docs/county-parcel-data-access-audit.md`.

## Hosted public dashboard

The shareable read-only dashboard is hosted at **https://gis-watchtower.clear-parcel.com**. Public traffic terminates on a Google Cloud external Application Load Balancer and is routed through a serverless NEG to the dedicated `gis-data-watchtower-public` Cloud Run service. The service reads only the sanitized production object at `gs://clearparcel-watchtower-dark-bit-503017-j7/production/aggregate-state.json`; its service account has no read access to the unified staging aggregate.

The `gis-data-watchtower-public-publisher` Cloud Run Job reads only the unified source aggregate, applies the public allowlist and forbidden-field validation, and writes only that production object. `gis-watchtower-public-publish` invokes the publisher every **10 minutes** using a separate scheduler identity. This is a publication schedule only and performs no provider checks. The final least-privilege publisher execution completed successfully in about **3m6s**.

The public rendering path strips operational provider URLs, raw change payloads, tracked values, schema/observation fingerprints, provenance, and worker telemetry. It preserves derived health/freshness summaries, county views, MN GAC completeness, the interactive county map, public catalog/contact references, and JSON/CSV/Excel exports. The private operational dashboard remains separate and is not made anonymously accessible.

Cloudflare remains authoritative for the parent DNS zone, but the Watchtower record is DNS-only; dashboard content and TLS termination are handled by Google Cloud. Cloud Armor is attached with a conservative **120 requests/minute/IP** throttle, load-balancer logging is enabled at full sampling, and Cloud Monitoring runs a one-minute HTTPS `/healthz` check plus availability and Cloud Run 5xx alert policies. Public publications are timestamped independently of source-data observation time, and `/healthz` fails once the production snapshot is more than **30 minutes** old.

## Validated cloud staging

A private Google Cloud staging deployment has been validated in `us-central1`.

The cloud execution profile currently handles **22 sources**. Against the corresponding local observations, validation found:

- 0 status differences;
- 0 feature-count differences;
- 0 schema-hash differences.

Four deployment-specific sources remain local-only because their providers do not accept the same Google Cloud egress path or TLS environment. Watchtower does not bypass those restrictions.

## Validated hybrid aggregation

The aggregate state was validated with:

- **26 total sources**
- **26 OK**
- **0 warnings**
- **0 errors**
- **22 cloud observations**
- **4 local observations**

Worker provenance, check timestamps, counts, and telemetry are retained in the aggregate state.

The hardened post-security-review build was revalidated on 2026-10-05. The Cloud Run worker completed **22/22 cloud sources OK** and the local worker completed **4/4 local-only sources OK**. The resulting aggregate remained **26/26 OK**, with **0 unassigned observations**; JSON, CSV, and Excel exports each represented all 26 sources.

### Validated MN GAC completeness observation

The current MN GAC feature was validated against MnGeo Plan Parcels Open on 2026-10-05:

- **59/87 counties represented** in the statewide open parcel layer;
- **28 counties explicitly reported as No data**, rather than 0%;
- **2,710,201 parcel records** in the denominator;
- **91/91 standard fields present** in the MnGeo source schema;
- **8 bounded grouped-statistics queries** at the default 12-field batch size;
- **42.92%** record-weighted population across all 91 fields;
- **78.37%** record-weighted population across the standard's Mandatory fields.

These percentages describe field population only. They are not pass/fail standards-compliance scores because Conditional, If Available, and Optional fields may legitimately be blank. The interactive county map, county field tables, JSON/CSV output, and Excel MN GAC sheets were validated against the stored observation.

## Concurrency-safe aggregate publishing

The shared aggregate object is now written with compare-and-swap semantics: Google Cloud Storage generation preconditions for cloud deployments, and an atomic lock-and-replace with retry for local/shared-filesystem deployments. A competing writer reloads the latest aggregate, re-merges, and retries instead of overwriting another worker's observations. A normal profiled `watchtower check` run (for example, the `local` execution profile) can publish directly to the configured shared aggregate store when opted in via `aggregate_object` or `WATCHTOWER_AGGREGATE_OBJECT`; this does not require a separate one-off script.

The private dashboard and the CSV/JSON/Excel snapshot exports now read the unified aggregate state. They show worker provenance, each worker's and source's last-success time (America/Chicago primary, UTC secondary), and reporting freshness against configurable thresholds, while keeping unhealthy sources (bad data) distinct from stale reporting (a worker or source overdue for a check). See `docs/hybrid-aggregation.md` for details and regression-test coverage.

Cloud Run startup latency was also characterized during this validation. A Job can remain in **Waiting for execution to start** for several minutes even after its image and resources are ready. Successful staging executions have taken roughly **2m30s to 4m15s** to reach Started. Operators should not treat this state alone as a failure during the first five minutes; explicit Failed conditions and the 15-minute job timeout are the authoritative failure bounds.

## Not yet enabled

The GIS-provider staging Cloud Run Job remains manually invoked. **No Cloud Scheduler automation is enabled for provider polling/check execution.** The only Scheduler automation is the separate 10-minute sanitized public-publication job. A local production monitoring worker remains active while parallel validation continues.

Automated local-worker publication to the shared aggregate and dashboard consumption of the aggregate state are implemented and have completed a successful one-cycle hardened hybrid validation. They have not yet completed a multi-day parallel validation run. The next release phase is that longer observation window, followed by scheduled cloud orchestration only once it passes.
