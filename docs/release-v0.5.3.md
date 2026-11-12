# GIS Data Watchtower v0.5.3

Deployed November 12, 2026. Built from merged source commit
`963fef7fc4954f3704c96039bf81ee08616d8fe4`, merged through PR #250.

This patch release contains the November 12, 2026 repository review fixes
(PRs #239 through #248, merged via #239 and #249):

- A `not-appropriate` county parcel decision now blocks every county-direct
  parcel source, not only editor-enrolled ones (F01).
- OGC `ExceptionReport`/`ServiceExceptionReport` capabilities responses are
  source errors; empty capabilities are warnings; WMS layer names come only
  from `Layer/Name` (F02, F09).
- The modern `gac_completeness` parcel result counts toward county coverage
  and status (F04).
- Enabled registry sources must have a name, URL and adapter or kind, or the
  run stops before any provider request (F05).
- The password-free loopback dashboard accepts only a local `Host` header (F06).
- Editor upload and retry scans wait at most 60% of the request deadline and
  finish in the background (F07).
- Editor validation highlights the failing monitoring method (F10).
- The public page reloads when county reporting or health changes, not only
  when content changes (F03).
- County PDFs show the cache warning on every page, monitoring status and
  per-standard observation dates (F08).
- Release, alerting and readiness documentation reflects the current state
  (F11 documentation, F12).

Deployment notes: county-direct parcel sources in the 18 `not-appropriate`
counties are skipped. The private registry check found none currently enabled,
so no active check stopped. Each WMS source may report one schema-change warning
as its layer inventory is re-read.

## Validation and promotion

- Candidate PRs passed all six Windows/Linux Python combinations, CodeQL and the
  security check. Local validation passed 1,124 tests, compileall,
  current-status synchronization and diff checks.
- The release-version preflight confirmed the live v0.5.2 and the v0.5.3 candidate.
  The immutable image passed 209 installed-image tests, and its installed
  identity and source hashes matched the reviewed commit.
- The private registry passed the new required-field check before rollout.
- The staging county services were updated first, and their runtime settings,
  access controls and IAM were preserved. Synthetic staging-storage validation
  passed: audit replay, public privacy, bounded attachment metadata reads and
  hash-verified downloads. The synthetic objects were removed afterward. Staging
  browser access requires Google sign-in, so no authenticated staging
  walkthrough was performed.
- Production candidate revisions were verified ready with no traffic before
  promotion. The public dashboard, internal dashboard, county editor, regular
  cloud worker and public publisher now use v0.5.3. The public site returned
  HTTP 200 and displayed v0.5.3, and its health, county directory, county page
  and export checks passed.
- All 25 source observations and the worker provenance matched the
  pre-release aggregate, and 87 county profiles remain available. Runtime
  settings, IAM and scheduler configuration were unchanged. No production
  errors were logged after promotion.
- No provider job or publisher run was started manually, and no schedule was
  changed. The scanner and weekly digest images were outside this release.
  Previous revisions and images remain the rollback targets. Detailed
  deployment identifiers remain in the private deployment record.
