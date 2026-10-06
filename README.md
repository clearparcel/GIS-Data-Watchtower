# GIS Data Watchtower

[![CI](https://github.com/clearparcel/GIS-Data-Watchtower/actions/workflows/watchtower-ci.yml/badge.svg)](https://github.com/clearparcel/GIS-Data-Watchtower/actions/workflows/watchtower-ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

GIS Data Watchtower is a lightweight Python monitor for public GIS services. It checks whether configured services are reachable, records meaningful changes over time, performs bounded parcel-data quality checks, and provides a plain-language dashboard without republishing source datasets.

ClearParcel also operates a read-only public dashboard at **https://gis-watchtower.clear-parcel.com**. The hosted view is deliberately sanitized and is separate from the private operational dashboard.

## What it monitors

- ArcGIS FeatureServer, MapServer, and ImageServer endpoints
- WMS/WFS capabilities
- selected public GIS catalogs and query APIs
- record-count and schema changes
- parcel-ID and attribute completeness signals
- Minnesota GAC parcel-field population statistics and interactive county comparison
- bounded geometry samples
- source response and processing history
- CSV, JSON, and Excel (`.xlsx`) snapshot exports

Watchtower is designed for **low-frequency, respectful monitoring**. It is not a bulk downloader or a scraper for human-facing property-search websites.

## Install

Python 3.12+:

```bash
python -m venv .venv
# activate the environment
python -m pip install -e .
```

For Google Cloud Storage support:

```bash
python -m pip install -e ".[gcs]"
```

## Configure

Start from `config/example_sources.json`. Runtime paths may be relative to the repository root or supplied through environment variables. See [`docs/configuration.md`](docs/configuration.md) for the supported top-level keys, source controls, storage options, dashboard settings, and environment overrides.

## Run

```bash
watchtower --config config/example_sources.json check
watchtower --config config/example_sources.json status
watchtower --config config/example_sources.json dashboard --host 127.0.0.1 --port 8765
```

The dashboard is intended to remain private by default. Wildcard/public binds fail closed unless authentication is configured.

## Responsible use

You are responsible for reviewing each provider's terms, licenses, rate limits, and redistribution restrictions before adding it. Watchtower respects HTTP 429 responses, bounds geometry sampling, prevents overlapping checks, and identifies itself with a project User-Agent.

See `docs/data-watchtower-provider-compliance.md` for the project's provider-use methodology. The public repository ships only provider-neutral example configuration; deployment-specific source registries remain private and are not evidence that any provider permits every possible use.

## Data and privacy

Watchtower stores derived monitoring observations in the configured local or cloud storage backend. Public/static outputs are intentionally sanitized and do not expose internal service fingerprints, tracked values, operational URLs, or raw parcel-owner records.

## County GIS contact provenance

Minnesota county contact information follows an explicit source-precedence rule. The official county government website is checked first. When that site provides additional or changed usable GIS, mapping, or land-records contact information, the county website is authoritative. When the official county site does not provide additional or changed usable contact information, Watchtower retains the Minnesota Geospatial Information Office (MnGeo) County GIS Contacts directory as the fallback. The dashboard and exports identify which source is in use and the verification date.

The baseline MnGeo directory and the official-county verification layer are stored separately so the fallback source is preserved rather than silently overwritten.

## Security

Do not report security vulnerabilities in public issues. See `SECURITY.md`.

## Development

```bash
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m compileall -q clearparcel tests
```

CI tests Windows and Ubuntu on Python 3.12, 3.13, and 3.14, plus a Linux container smoke test.

## Project documentation

- [`STATUS.md`](STATUS.md) — concise validated project/deployment status
- [`docs/current-status.md`](docs/current-status.md) — detailed current local/cloud/hybrid state
- [`docs/configuration.md`](docs/configuration.md) — supported configuration and environment variables
- [`docs/data-watchtower-processing-architecture.md`](docs/data-watchtower-processing-architecture.md) — processing/storage/dashboard boundaries
- [`docs/google-cloud-deployment.md`](docs/google-cloud-deployment.md) — optional Cloud Run/GCS execution deployment
- [`docs/public-dashboard-hosting.md`](docs/public-dashboard-hosting.md) — public Google Cloud serving architecture and security boundary
- [`docs/county-parcel-data-access-audit.md`](docs/county-parcel-data-access-audit.md) — parcel-specific county access audit scope, classifications, and current 35-county review population
- [`docs/hybrid-execution.md`](docs/hybrid-execution.md) and [`docs/hybrid-aggregation.md`](docs/hybrid-aggregation.md) — hybrid worker model
- [`docs/mngac-completeness.md`](docs/mngac-completeness.md) — Minnesota GAC field-population methodology, county map, and exports
- [`docs/data-watchtower-provider-compliance.md`](docs/data-watchtower-provider-compliance.md) — respectful-use methodology and known provider constraints
- [`docs/release-policy.md`](docs/release-policy.md) — versioning and release policy

## Cloud deployment

The base package remains cloud-neutral. Optional Google Cloud Storage support and a Cloud Run Job deployment path are documented in [`docs/google-cloud-deployment.md`](docs/google-cloud-deployment.md). Local filesystem storage remains the default.

## License

GIS Data Watchtower is licensed under the **MIT License**. See [`LICENSE`](LICENSE).