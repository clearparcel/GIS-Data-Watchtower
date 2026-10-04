# GIS Data Watchtower

GIS Data Watchtower is a lightweight Python monitor for public GIS services. It checks whether configured services are reachable, records meaningful changes over time, performs bounded parcel-data quality checks, and provides a plain-language dashboard without republishing source datasets.

## What it monitors

- ArcGIS FeatureServer, MapServer, and ImageServer endpoints
- WMS/WFS capabilities
- selected public GIS catalogs and query APIs
- record-count and schema changes
- parcel-ID and attribute completeness signals
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

## Configure

Start from `config/example_sources.json`. Runtime paths may be relative to the repository root or supplied with environment variables documented in `docs/data-watchtower-standalone-readiness.md`.

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

Watchtower stores derived monitoring observations locally. Public/static outputs are intentionally sanitized and do not expose internal service fingerprints, field inventories, operational URLs, or raw parcel-owner records.

## Security

Do not report security vulnerabilities in public issues. See `SECURITY.md`.

## Development

```bash
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m compileall -q clearparcel tests
```

CI tests Windows and Ubuntu on supported Python versions.

## Current status

See [`docs/current-status.md`](docs/current-status.md) for the latest validated local/cloud/hybrid deployment status.

## Cloud deployment

The base package remains cloud-neutral. Optional Google Cloud Storage support and a Cloud Run Job deployment path are documented in `docs/google-cloud-deployment.md`. Local filesystem storage remains the default.

## License

GIS Data Watchtower is licensed under the **MIT License**. See `LICENSE`.
