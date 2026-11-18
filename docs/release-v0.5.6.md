# GIS Data Watchtower v0.5.6

Candidate, not yet deployed. This patch release contains the fixes from the
Codex follow-up review of v0.5.5 (`f8f0997`), merged through PRs #266 to #271:

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
