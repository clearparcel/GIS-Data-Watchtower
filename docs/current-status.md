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
- hybrid worker result aggregation.

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

## Not yet enabled

The staging Cloud Run Job is manually invoked. **No Cloud Scheduler automation is enabled yet.** A local production worker remains active while parallel validation continues.

The next release phase is automated local-worker publication to the shared aggregate, multi-day parallel validation, dashboard consumption of aggregate state, and only then scheduled cloud orchestration.
