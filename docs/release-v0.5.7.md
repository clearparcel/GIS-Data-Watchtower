# GIS Data Watchtower v0.5.7

Deployed November 18, 2026. Built from merged source commit
`206c4bed200c0648100f44c84bc86a7ceb436d83`, merged through PR #277.

This patch release contains the fixes from the Codex third review of v0.5.6
(`2310764`), merged through PRs #274 to #276:

- **#274, publication integrity:**
  - A source's measured values are ordered by provider check time, so
    overlapping workers cannot republish an older observation (T01).
  - The publisher refuses an aggregate dated more than five minutes ahead of
    its clock, and stored or published future times no longer block recovery
    (T02).
  - A mistyped source status is refused before publication (T03).
  - A worker's first filtered report records only its heartbeat (T10).
  - The public worker card reads "Last fully successful worker run" (T11).
- **#275, provider options and change detection:**
  - Request-producing options must be JSON booleans (T04).
  - The Minnesota county catalog must name all 87 counties once, checked per
    raw row; aliases are stored under the canonical name (T05).
  - Malformed statistics groups are unavailable rather than zero (T06).
  - Unmeasured parcel schemas report no change; tracked values keep a per-key
    baseline (T07).
  - An explicit `null` `extent_shift_percent` is refused (T08).
- **#276, operations:** the publisher watchdog default also expects workers
  that sources are assigned to (T09); the Windows lock test stops its owner
  gracefully (T12); the CRM terms client closes HTTP error responses (T13).

Deployment notes:

- **Private registry:** must pass the v0.5.7 checks before rollout: JSON-boolean
  `count`, `discover_parcel_layer`, `parcel_quality`, `geometry_sample`,
  `item_metadata` and `prefer_curl` when set, and no `null`
  `extent_shift_percent`.
- **County catalog:** the next MnGeo catalog check fails, keeping the last
  complete catalog, unless it names all 87 counties exactly once.

## Validation and promotion

- PRs #274 to #277 passed the repository CI checks before merge.
- Before rollout, the private registry passed the v0.5.7 checks (35 sources):
  every request option set was a JSON boolean, no `extent_shift_percent` was
  `null`, and full registry validation passed with the new code. No registry
  change was needed. The stored county catalog, re-validated row by row, named
  all 87 Minnesota counties once. The coverage counts predicted from the current
  aggregate (87 counties, 67 actively checked) matched the live dashboard.
- The release-version preflight confirmed the live v0.5.6 and the v0.5.7
  candidate. The immutable image passed 360 installed-image tests (6 skipped),
  and its installed identity and source hashes matched the reviewed commit.
- The staging county services were updated first, with runtime settings, access
  controls and IAM preserved. Synthetic staging-storage validation passed, and
  the synthetic objects were removed afterward.
- Production candidate revisions were verified ready with no traffic before
  promotion. The public dashboard, internal dashboard, county editor, regular
  cloud worker, public publisher and weekly digest job now use v0.5.7. The
  weekly digest was outside the v0.5.6 release, so its fix (#268) and the
  watchdog default (T09) are now live. The public site displays v0.5.7 and the
  worker card label "Last fully successful worker run", and its health, county
  directory, county page and export checks passed.
- All 25 source observations and the worker provenance matched the pre-release
  aggregate, and 87 county profiles remain available (67 actively checked).
  Runtime settings, IAM and scheduler configuration were unchanged.
- The first scheduled publisher run on v0.5.7 published successfully, with no
  future-clock refusal.
- No provider job or publisher run was started manually, and no schedule was
  changed. Previous revisions and images (v0.5.6) remain the rollback targets.
  Detailed deployment identifiers remain in the private deployment record.
