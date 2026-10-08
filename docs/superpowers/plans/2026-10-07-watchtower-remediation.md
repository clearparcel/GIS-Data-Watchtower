# Watchtower Review Remediation Implementation Plan

**Goal:** Restore trustworthy freshness, repair dashboard interaction/transfer costs, and add three diagnostic graphics.
**Architecture:** Existing Python HTML/SVG and CAS worker aggregation; read-only public summaries and lazy county fragments.
**Spec:** User-approved plan in this conversation, based on the attached October 7 review.

## Constraints

GERTKEN-PC only. Preserve dirty work. No provider runs, staging writes, deployment, merge, production writes, or scheduling activation. Private registries/receipts stay private. Existing provider terms, profile assignments, holds, cadence, authentication, analytics and CAS protections remain intact. Five distinct authorized daily hybrid validation cycles precede any scheduling decision.

## Tasks

- [x] 1. Data/provenance: catalog success-time retention and recovery; public GAC observation times; read-only validation receipts; candidate worker preparation and runbook.
- [x] 2. UI/performance: external Export popup; semantic scrollable mobile tables; persisted manual pause/map/county/filter/sort/focus; lazy revision-bound county fragments; compact summary polling; ETags/gzip.
- [x] 3. Graphics: parcel path composition; three-standard coverage/population comparison; six largest mandatory-field gaps per standard; research and road metadata clarification.
- [x] 4. Validation/docs: regression tests and browser QA; <=250 KiB decoded homepage and <=64 KiB summary; required suite/compile/status/diff checks; independent whole-branch review.

## Interfaces and acceptance

Catalog metadata: catalog_observed_at, catalog_retained, inferred legacy time label. Failures remain errors and preserve prior records/time; recovery replaces them. Public GAC observed_at/observation_status are typed allowlisted leaves.

Public GET /api/summary returns schema_version=1, content_revision, public_published_at and compact chart/map/freshness metadata. Revision excludes publication-only times and clock-based ages, includes sanitized observations and application/research identity. GET /api/county-profile?slug=...&revision=... returns escaped HTML; unknown slug=404, obsolete revision=409. Poll every 30 seconds while visible/unpaused. Publication-only change never reloads the full page. Dialog/evidence closure never cancels manual pause. Private pages retain timed reload with the shared pause/view-state repair.

Coverage categories are exclusive; reviewed baseline 46 statewide-only / 11 direct-only / 13 both / 17 neither. Standard comparison uses record-weighted and median county mandatory rates, actual denominator/version/scope/time. Gap bars sort unpopulated mandatory-field counts descending, field-name ties, top six; missing/unscanned/zero remain distinct. Roads' representation/opt-in discrepancy remains unresolved and explicitly labeled. Tables/downloads accompany graphics. Matrices and trends are deferred.

## Verification

Catalog success/timeout/recovery/no-prior/legacy; sanitizer boundaries; publication-only and observation changes; revision conflicts/404; ETags/gzip; fragment errors; pause/dialog/map/county/filter/focus restoration; chart overlap/zero/unscanned/exclusions/weighting. Desktop and 360/390/412-pixel browser QA. Run required unittest/compileall/diff checks and status-sync consistency. Record actual results without treating pending multi-day or deployment gates as completed.
