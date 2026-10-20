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
| [Offline operations triage](operations-triage.md) | Correlate saved run evidence, distinguish status exits, and prepare source-failure/recovery review |
| [Processing architecture](data-watchtower-processing-architecture.md) | Data flow and separation of collector, saved observations, and dashboard |
| [Cloud/offline development](codex-cloud-development.md) | Safe synthetic development without contacting production GIS providers |
| [Hybrid execution](hybrid-execution.md) | Local and cloud execution profiles |
| [Hybrid aggregation](hybrid-aggregation.md) | Worker receipts, safe concurrency, and aggregate publication |
| [Shared AI workflow](ai/WORKFLOW.md) | How Codex and Claude implement, review, and hand off work ([handoff template](ai/HANDOFF-TEMPLATE.md)) |
| [Standalone readiness](data-watchtower-standalone-readiness.md) | What the open-source package needs to run outside ClearParcel's deployment |

## Operators and maintainers

| Guide | Purpose |
| --- | --- |
| [Google Cloud deployment](google-cloud-deployment.md) | Optional Cloud Run and storage deployment |
| [Public dashboard hosting](public-dashboard-hosting.md) | Anonymous sanitized service, access boundaries, publication, and freshness |
| [Release policy](release-policy.md) | Versioning, evidence, and rollback expectations |
| [Current v0.3.0 release](release-v0.3.0.md) | Deployment evidence, review stack contents, operator compatibility notes and rollback |
| [v0.2.3 release](release-v0.2.3.md) | Rollback baseline for v0.3.0 services; branding update |
| [v0.2.2 release](release-v0.2.2.md) | Rollback baseline for the v0.3.0 job images |
| [Current status](current-status.md) | Generated companion to authoritative [STATUS.md](../STATUS.md); do not edit directly |
| [Private vulnerability reporting](../SECURITY.md) | Safe reporting and security expectations |

## Historical engineering and release records

Dated notes, reviews, incident investigations and release evidence live in `docs/archive/`. They are kept for traceability but **are not the current operational state**: reconcile anything here against [STATUS.md](../STATUS.md) and the current branch before acting on it. Archived deployment notes use placeholders such as `<project-id>` instead of private deployment identifiers.

### Status and release records

- [Versioned public UI release — October 7, 2026](archive/public-ui-release-2026-10-07.md)
- [Application release — 2026-10-06](archive/release-2026-10-06.md)
- [Follow-up application release — 2026-10-07](archive/release-2026-10-07.md)
- [GIS Data Watchtower v0.2.0 — County percentage clarity deployment](archive/release-county-percentage-fix-2026-10-11.md)
- [Address/Road GAC and Watchtower hardening release — 2026-10-07](archive/release-gac-address-road-2026-10-07.md)
- [GIS Data Watchtower v0.1.1 release record](archive/release-v0.1.1.md)
- [GIS Data Watchtower v0.1.2 review and release](archive/release-v0.1.2.md)
- [GIS Data Watchtower v0.2.0](archive/release-v0.2.0.md)
- [GIS Data Watchtower v0.2.1 — Production release](archive/release-v0.2.1.md)
- [Historical status and release evidence (through 2026-10-06)](archive/status-history-2026-10-06.md)
- [Alternate status snapshot (through 2026-10-06)](archive/status-history-2026-10-06-alt.md)
- [Status log, October 2026 (archived)](archive/status-log-2026-10.md)

### Reviews and remediation

- [Browser feedback changes — October 7, 2026](archive/browser-feedback-2026-10-07.md)
- [Codex Cloud readiness review — 2026-10-08](archive/codex-cloud-readiness-review-2026-10-08.md)
- [County Percentage and Repository QA — 2026-10-11](archive/county-percentage-audit-2026-10-11.md)
- [Final Watchtower UI, repository and operational review](archive/final-review-2026-10-10.md)
- [Repository review — 2026-10-06](archive/repository-review-2026-10-06.md)
- [GIS Data Watchtower repository review — 2026-10-11](archive/repository-review-2026-10-11.md)
- [Manual review follow-up fixes](archive/review-fixes-2026-10-06.md)
- [October 7 review remediation](archive/watchtower-remediation-2026-10-07.md)

### Migration, deployment and investigation notes

- [Cloud provider access reassessment — 2026-10-08](archive/cloud-provider-access-reassessment-2026-10-08.md)
- [Rice and Beltrami cloud migration — 2026-10-08](archive/county-cloud-migration-2026-10-08.md)
- [Daily Google Cloud provider polling](archive/daily-cloud-provider-polling-2026-10-10.md)
- [MN GAC county-results publication](archive/mngac-county-publication-2026-10-10.md)
- [USDA Google Cloud connection — 2026-10-08](archive/usda-cloud-connection-2026-10-08.md)

### Superseded plans and specifications

- [County Parcel-Source Profiles Implementation Plan](archive/superpowers/plans/2026-10-06-county-parcel-source-profiles.md)
- [Four-class percentage feedback](archive/superpowers/plans/2026-10-06-four-class-percentage-feedback.md)
- [Repository security and maintenance review](archive/superpowers/plans/2026-10-06-repository-review.md)
- [Watchtower Review Remediation Implementation Plan](archive/superpowers/plans/2026-10-07-watchtower-remediation.md)
- [Minnesota county parcel-source profiles](archive/superpowers/specs/2026-10-06-county-parcel-source-profiles-design.md)

**Safety:** Public documentation must not contain private source registries, credentials, raw parcel-owner records, nonpublic service endpoints, or authenticated dashboard screenshots.
