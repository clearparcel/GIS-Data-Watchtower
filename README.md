# GIS Data Watchtower

The current source prepares **v0.1.2**, fixing dashboard label encoding,
transparent branding, version display and unknown-health reporting, with a
restricted Cloud Build upload context. See the [October 10 review and release
record](docs/release-v0.1.2.md). Cloud deployment has not yet been verified;
the production record below remains the last confirmed deployment.

GIS Data Watchtower **v0.1.1** is deployed to production from merged code commit `8099ee1`. Production public revision `00011-b9c` serves the public dashboard, private dashboard revision `00019-c9l` preserves its audited IAP wrapper, and the sanitized publisher job uses the v0.1.1 image. The multi-day staging gate was explicitly waived by the user for this rollout and remains incomplete; provider scheduling is unchanged, and PostHog remains dormant pending a dedicated project ([Issue #50](https://github.com/clearparcel/GIS-Data-Watchtower/issues/50)). See [the release record](docs/release-v0.1.1.md).

The v0.1.1 release contains the review fixes and packaging/dashboard updates described in [its release record](docs/release-v0.1.1.md). The required staging gate did not pass before deployment; the user explicitly authorized the one-release exception.

[![CI](https://github.com/clearparcel/GIS-Data-Watchtower/actions/workflows/watchtower-ci.yml/badge.svg)](https://github.com/clearparcel/GIS-Data-Watchtower/actions/workflows/watchtower-ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

GIS Data Watchtower is a lightweight Python monitor for public GIS services. It checks whether configured services are reachable, records meaningful changes over time, performs bounded parcel-data quality checks, and provides a plain-language dashboard without republishing source datasets.

Development supports [synthetic cloud setup and offline public replay](docs/codex-cloud-development.md).
[Cloud-only receipts and explicit worker retirement](docs/hybrid-aggregation.md#observation-receipts)
prepare operational activation while preserving source observations and concurrency controls.
See [current status](docs/current-status.md) for the remaining runtime and deployment gates.

ClearParcel also operates a read-only public dashboard at **https://gis-watchtower.clear-parcel.com**. The hosted view is deliberately sanitized and is separate from the private operational dashboard.

## What it monitors

- ArcGIS FeatureServer, MapServer, and ImageServer endpoints
- WMS/WFS capabilities
- selected public GIS catalogs and query APIs
- record-count and schema changes
- parcel-ID and attribute completeness signals
- Minnesota GAC Parcel, Address Point, and Road Centerline field-population statistics with interactive county comparison
- evidence-backed Minnesota county-direct parcel access plus separate MnGeo statewide open coverage and active-monitoring paths
- bounded geometry samples
- source response and processing history
- CSV, JSON, and Excel (`.xlsx`) snapshot exports
- County parcel profiles in `/county-profiles.csv` (all 87 counties) and `/parcel-sources.csv` (each category and source, including empty-category placeholders). JSON county records include `parcel_source_profile`; Excel adds `County Access` and `Parcel Sources` sheets. `/snapshot.csv` retains the monitored-source rows. Unknown counts/dates stay blank in spreadsheets, observed zero stays zero, and date/time fields retain ISO semantics.
- Both county maps open the same complete profile with click, Enter or Space. Escape closes the dialog and returns focus; overview refresh pauses while reading. Desktop and 390px layouts wrap long source/evidence values. Public publication reporting is Current, Overdue or Unknown using the `/healthz` threshold, separately from provider health and source reporting.
- Profile coverage includes all 87 counties. The current evidence has 16 fully reviewed category inventories and 15 complete composed profiles; blocked evidence and unresolved county-direct access remain explicit. Monitoring coverage is derived from current observations.

Public snapshots use typed projections for source metrics, completeness, workers,
counts and catalog facts; private diagnostics and arbitrary nested values are
omitted. Matching official statewide products retain one vetted inventory identity,
with current county observations joined by source ID. Export row counts derive
from the composed inventory and observations, including empty-category rows.
Rendered public exports reuse a single bounded cache for each sanitized snapshot
generation. When storage refresh fails, the dashboard serves the last-known
snapshot with a stale banner while `/healthz` remains unhealthy. CI supply-chain
evidence inventories the built runtime image's Python and Debian packages and
records its image ID as the artifact subject; constraints are labeled as
dependency input metadata.

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

Optional public PostHog analytics remain disabled unless both a dedicated
Watchtower project token and the explicit IP-discard confirmation setting are
configured. When enabled, Watchtower uses explicit anonymous events only:
autocapture, Session Replay, automatic pageview/pageleave capture, exception
capture, feature-flag requests, persistent browser identity, and explicit user
identification are disabled. Client-IP discard must be enabled and verified on
the dedicated PostHog project before production activation.

## County GIS contact provenance

Minnesota county contact information follows an explicit source-precedence rule. The official county government website is checked first. When that site provides additional or changed usable GIS, mapping, or land-records contact information, the county website is authoritative. When the official county site does not provide additional or changed usable contact information, Watchtower retains the Minnesota Geospatial Information Office (MnGeo) County GIS Contacts directory as the fallback. The dashboard and exports identify which source is in use and the verification date.

The baseline MnGeo directory and the official-county verification layer are stored separately so the fallback source is preserved rather than silently overwritten.

## Security

Do not report security vulnerabilities in public issues. See `SECURITY.md`.

## Development

For Linux or Codex Cloud development, use the constrained setup and synthetic
dashboard preview in [the cloud development guide](docs/codex-cloud-development.md).
The preview uses local invented data; operational provider workers retain their
existing execution profiles.

```bash
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m compileall -q clearparcel tests scripts
git diff --check
```

CI tests Windows and Ubuntu on Python 3.12, 3.13, and 3.14, plus a Linux container smoke test. Runtime Python dependencies are constrained in `constraints.txt`, the container base image is digest-pinned, and CI runs a pinned dependency audit, CodeQL analysis, and Trivy high/critical container scan. The Linux container lane also uploads CycloneDX SBOM, build provenance, and image-ID evidence.

## Project documentation

- [`STATUS.md`](STATUS.md) — concise validated project/deployment status
- [`docs/current-status.md`](docs/current-status.md) — current recorded local/cloud/hybrid state and historical evidence
- [`docs/configuration.md`](docs/configuration.md) — supported configuration and environment variables
- [`docs/data-watchtower-processing-architecture.md`](docs/data-watchtower-processing-architecture.md) — processing/storage/dashboard boundaries
- [`docs/google-cloud-deployment.md`](docs/google-cloud-deployment.md) — optional Cloud Run/GCS execution deployment
- [`docs/public-dashboard-hosting.md`](docs/public-dashboard-hosting.md) — public Google Cloud serving architecture and security boundary
- [`docs/county-parcel-data-access-audit.md`](docs/county-parcel-data-access-audit.md) — parcel-access audit, classifications, evidence methodology, and direct-source findings; offline county profiles cover all 87 counties; all category reviews have been attempted, while blocked and unresolved evidence remains explicit
- [`docs/hybrid-execution.md`](docs/hybrid-execution.md) and [`docs/hybrid-aggregation.md`](docs/hybrid-aggregation.md) — hybrid worker model
- [`docs/gac-standards.md`](docs/gac-standards.md) — shared Minnesota GAC Parcel, Address Point, and Road Centerline monitoring methodology
- [`docs/mngac-completeness.md`](docs/mngac-completeness.md) — parcel-specific Minnesota GAC field-population history, county map, and exports
- [`docs/data-watchtower-provider-compliance.md`](docs/data-watchtower-provider-compliance.md) — respectful-use methodology and known provider constraints
- [`docs/release-policy.md`](docs/release-policy.md) — versioning, release policy and the public footer's package version, baked source commit and build environment

## Cloud deployment

The base package remains cloud-neutral. Optional Google Cloud Storage support and a Cloud Run Job deployment path are documented in [`docs/google-cloud-deployment.md`](docs/google-cloud-deployment.md). Local filesystem storage remains the default.

## License

GIS Data Watchtower is licensed under the **MIT License**. See [`LICENSE`](LICENSE).

County map selections open a shared parcel-source profile with four independent source categories, source-specific counts and dates, access evidence, and research status. The overview supports monitoring-path and MN GAC completeness views. Unknown values remain unavailable; county research does not activate monitoring.

The latest recorded (2026-10-06) isolated county-profile [preview](https://gis-data-watchtower-public-v2-preview-237020802969.us-central1.run.app) served committed `5aac504` (revision `00007-zfh`) with dedicated sanitized storage/identity. The previous five-class release served `dfacd72` (`00005-c24`). The final typed-metric and statewide-identity fixes passed review; live all-87 JSON/CSV/XLSX parity and targeted desktop/mobile checks passed. Original Task 8 and Task 10 local folder absence were verified on 2026-10-06; the earlier automatic approval review cleanup denial remains recorded. See [deployment details](docs/google-cloud-deployment.md#four-class-code-only-preview-release-2026-10-06).

The shared public header is **Minnesota Open Data Watchtower** in the reviewed Task 9 source change, released to the existing preview by Task 10. The confirmed follow-up source uses <30%, 30% - 50%, 50% - 70%, >70% classes on both completeness maps, summary modes and individual fields, with exactly 30 in the second class, exactly 50 and 70 in the third class, and a separate No data class. This follow-up is deployed to existing preview `00007-zfh` from committed `5aac504`, and rendered acceptance passed; sanitized data and its real publication/source dates were preserved. Monitored entries cover all dataset/service types; parcel coverage counts unique counties across direct and statewide observations. One statewide entry can cover many counties. Internal project identities are unchanged.

The [October 6 repository review](docs/repository-review-2026-10-06.md) fixes transport, reporting and publisher cleanup behavior; that earlier release is merged and deployed. The subsequent [manual review corrections](docs/review-fixes-2026-10-06.md) address ordering, profile isolation, inventory retirement, local locking and capabilities URLs. Those follow-up fixes are merged in PR #44 (`284cf0c`) and deployed from `afa908d`; see the [October 7 release record](docs/release-2026-10-07.md). Current recorded deployment facts are maintained in [STATUS.md](STATUS.md).

### October 7 dashboard remediation

See [observation semantics, compact public APIs, and offline hybrid validation preparation](docs/watchtower-remediation-2026-10-07.md). The implementation does not activate provider scheduling or deploy services; five daily hybrid validation cycles and separate activation approval remain pending.
