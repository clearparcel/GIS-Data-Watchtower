# GIS Data Watchtower v0.5.6

Deployed November 18, 2026. Built from merged source commit
`9979b638c1df9e9a7d56331c39221298b3f4da63`, merged through PR #272.

This patch release contains the fixes from the Codex follow-up review of v0.5.5
(`f8f0997`), merged through PRs #266 to #271:

- **#266, provider controls:**
  - `enabled` must be a JSON boolean; any other value fails closed.
  - A long, zero-padded `Retry-After` keeps its full delay.
  - `feature_count_change_percent` and `extent_shift_percent` must be finite.
  - The layer-name guard follows the canonical adapter, and `arcgis_service`
    needs `discover_parcel_layer` to use `expected_layer_name`.
  - A `cloud-job` with no eligible source claims no provider-run slot.
- **#267, change detection:** each field keeps its last valid baseline across
  partial and rate-limited checks; the Minnesota county catalog must name every
  county once; malformed ArcGIS responses are unavailable rather than zero.
- **#268, freshness and digest:** a county with an unknown check or report time
  counts as check overdue; the weekly digest lists missing workers and refuses
  an empty aggregate.
- **#269, publication:** the publisher refuses invalid or disagreeing counts,
  padded approval values publish, and year-boundary dates read as unknown.
- **#270:** the private dashboard drops cached history after a confirmed hosted
  removal.
- **#271:** the county editor's early rejections reach the client before the
  connection closes. Finding F16 is accepted as designed
  ([ADR 0001](adr/0001-status-read-reconciles-county-enrollment.md)).

Deployment notes:

- **Private registry:** must pass the v0.5.6 checks before rollout: JSON-boolean
  `enabled`, finite change thresholds, `expected_layer_name` on a service only
  with `discover_parcel_layer`, and catalog county names that all resolve to
  Minnesota counties.
- **Coverage counts:** a county whose check or report time is unknown now shows
  as check overdue instead of actively checked.

## Validation and promotion

- PRs #266 to #272 passed all six Windows/Linux Python combinations, CodeQL and
  the security check.
- Before rollout, the private registry passed the v0.5.6 checks (35 sources), and
  the stored county catalog's 87 county keys all resolved to Minnesota counties.
  The coverage counts predicted from the current aggregate (87 counties, 67
  actively checked) matched the live dashboard.
- The release-version preflight confirmed the live v0.5.5 and the v0.5.6
  candidate. The immutable image passed 316 installed-image tests, and its
  installed identity and source hashes matched the reviewed commit.
- The staging county services were updated first, with runtime settings, access
  controls and IAM preserved. Synthetic staging-storage validation passed, and
  the synthetic objects were removed afterward.
- Production candidate revisions were verified ready with no traffic before
  promotion. The public dashboard, internal dashboard, county editor, regular
  cloud worker and public publisher now use v0.5.6. The public site displays
  v0.5.6, and its health, county directory, county page and export checks passed.
- All 25 source observations and the worker provenance matched the pre-release
  aggregate, and 87 county profiles remain available. Runtime settings, IAM and
  scheduler configuration were unchanged.
- No provider job or publisher run was started manually, and no schedule was
  changed. The scanner and weekly digest images were outside this release; the
  weekly digest fix (#268) takes effect when that image is next updated.
  Previous revisions and images remain the rollback targets. Detailed deployment
  identifiers remain in the private deployment record.
