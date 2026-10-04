# Current project status

Last validated: **2026-10-04**

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
- concurrency-safe aggregate publishing (GCS generation preconditions, atomic local locking) with dashboard/export consumption of the unified aggregate state.

## CI

The project is tested on:

- Ubuntu / Python 3.12
- Ubuntu / Python 3.13
- Windows / Python 3.12
- Windows / Python 3.13

The Linux 3.13 job also smoke-tests the Docker image.

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

## Concurrency-safe aggregate publishing

The shared aggregate object is now written with compare-and-swap semantics: Google Cloud Storage generation preconditions for cloud deployments, and an atomic lock-and-replace with retry for local/shared-filesystem deployments. A competing writer reloads the latest aggregate, re-merges, and retries instead of overwriting another worker's observations. A normal profiled `watchtower check` run (for example, the `local` execution profile) can publish directly to the configured shared aggregate store when opted in via `aggregate_object` or `WATCHTOWER_AGGREGATE_OBJECT`; this does not require a separate one-off script.

The private dashboard and the CSV/JSON/Excel snapshot exports now read the unified aggregate state. They show worker provenance, each worker's and source's last-success time (America/Chicago primary, UTC secondary), and reporting freshness against configurable thresholds, while keeping unhealthy sources (bad data) distinct from stale reporting (a worker or source overdue for a check). See `docs/hybrid-aggregation.md` for details and regression-test coverage.

## Not yet enabled

The staging Cloud Run Job is manually invoked. **No Cloud Scheduler automation is enabled yet.** A local production worker remains active while parallel validation continues.

Automated local-worker publication to the shared aggregate and dashboard consumption of the aggregate state are implemented, as described above, but have not yet completed a multi-day parallel validation run. The next release phase is that validation, followed by scheduled cloud orchestration only once it passes.
