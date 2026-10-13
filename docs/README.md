# GIS Data Watchtower documentation

Choose the path that matches what you want to do. For the live dashboard and a concise introduction, start with the [project README](../README.md).

## Visitors, county staff, and GIS researchers

| Guide | Start here when you want to… |
| --- | --- |
| [Public user guide](user-guide.md) | Navigate the live dashboard with screenshots, interpret county results, and export findings |
| [MN GAC standards methodology](gac-standards.md) | Understand parcel, address-point, and road-centerline field-population methodology |
| [Parcel field population](mngac-completeness.md) | Understand the 91-field parcel comparison, Mandatory fields, and missing-value rules |
| [County parcel access audit](county-parcel-data-access-audit.md) | Understand direct access, MnGeo open coverage, unresolved access, and provenance |
| [County-direct schema audit](county-direct-gac-schema-audit.md) | Review source-specific field-name evidence and direct/statewide overlap |
| [Provider-use compliance](data-watchtower-provider-compliance.md) | Understand provider restrictions, attribution, and conservative checking |
| [Current project status](../STATUS.md) | See what is deployed, validated, and still under observation |

## Developers and contributors

| Guide | Purpose |
| --- | --- |
| [Contributing](../CONTRIBUTING.md) | Pull requests, testing, provider-use guardrails, and reporting |
| [Configuration reference](configuration.md) | Source definitions, storage, supported options, and environment overrides |
| [Processing architecture](data-watchtower-processing-architecture.md) | Data flow and separation of collector, saved observations, and dashboard |
| [Cloud/offline development](codex-cloud-development.md) | Safe synthetic development without contacting production GIS providers |
| [Hybrid execution](hybrid-execution.md) | Local and cloud execution profiles |
| [Hybrid aggregation](hybrid-aggregation.md) | Worker receipts, safe concurrency, and aggregate publication |

## Operators and maintainers

| Guide | Purpose |
| --- | --- |
| [Google Cloud deployment](google-cloud-deployment.md) | Optional Cloud Run and storage deployment |
| [Public dashboard hosting](public-dashboard-hosting.md) | Anonymous sanitized service, access boundaries, publication, and freshness |
| [Release policy](release-policy.md) | Versioning, evidence, and rollback expectations |
| [Current v0.2.3 release](release-v0.2.3.md) | Branding update, immutable images, public/private acceptance, and rollback details |
| [Current status](current-status.md) | Generated companion to authoritative [STATUS.md](../STATUS.md); do not edit directly |
| [Private vulnerability reporting](../SECURITY.md) | Safe reporting and security expectations |

## Historical engineering and release records

This repository retains dated engineering notes, reviews, incident investigations, and release evidence under the docs directory. They are valuable for traceability but **are not automatically the current operational state**.

Examples include [the October 11 county-percentage release](release-county-percentage-fix-2026-10-11.md), [the original v0.2.0 release](release-v0.2.0.md), and [the October 10 final review](final-review-2026-10-10.md). Superseded plans and specifications remain under the [superpowers directory](superpowers/). Always reconcile dated documents against [STATUS.md](../STATUS.md) and the current branch before acting on an older instruction.

**Safety:** Public documentation must not contain private source registries, credentials, raw parcel-owner records, nonpublic service endpoints, or authenticated dashboard screenshots.
