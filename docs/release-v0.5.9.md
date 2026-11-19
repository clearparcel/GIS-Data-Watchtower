# GIS Data Watchtower v0.5.9

Deployed November 19, 2026. Built from merged source commit
`ddc1c390d290f8b5872e05f43484c8f4ab32d16f`, merged through PR #283.

This patch release contains the fixes from the fifth review of v0.5.8
(`395e3cf`), merged through PR #282:

- **Publication integrity:**
  - A stored source or worker record with an unreadable or future time no
    longer stalls the fleet: the publisher keeps its last published version and
    reports it under `clock_quarantine` (V01).
  - A stored future heartbeat no longer blocks retiring an inactive worker (V02).
  - A zero-attempt deferral never reinstates a retired source (V03).
  - An unreadable source `checked_at` is refused at the private write, and a
    rebuilt deferral keeps the published measurement (V04).
  - Last success and availability times no longer depend on report arrival
    order (V05).
  - A worker name with surrounding whitespace is refused consistently (V06).
- **Provider checks:**
  - Participation rows without a county identifier or with an unreadable flag
    fail the check and keep the last valid measurement (V07).
  - The grouped-total check counts every returned group (V08).
  - Recognized completeness settings are validated before any request (V09).
  - Layer URLs with a query string build child requests from the parsed path
    (V10).
  - Extents in different spatial references are an informational change, and
    impossible bounds are unmeasured (V11).
- **Operations:** the weekly digest reads ISO catalog acquisition dates (V12)
  and refuses a future-dated aggregate (V13).

Deployment notes:

- **Private registry:** no `gac_completeness` or `mngac_completeness` object
  has an invalid recognized field.
- **Stored aggregate:** no source `worker` carries surrounding whitespace.

## Validation and promotion

- PRs #282 and #283 passed all six Windows/Linux Python combinations, CodeQL and
  the security check.
- Before rollout, the private registry passed the v0.5.9 checks (35 sources):
  all three completeness settings objects pass the new settings validation, and
  full registry validation passed with the new code. No registry change was
  needed. No stored worker name or source `worker` value in the aggregate
  carries surrounding whitespace, and its county catalog names all 87 Minnesota
  counties once. The coverage counts predicted from the current aggregate
  (87 counties, 67 actively checked) matched the live dashboard.
- The release-version preflight confirmed the live v0.5.8 and the v0.5.9
  candidate. The immutable image passed 418 installed-image tests (6 skipped),
  and its installed identity and source hashes matched the reviewed commit.
- The staging county services were updated first, with runtime settings, access
  controls and IAM preserved. Synthetic staging-storage validation passed, and
  the synthetic objects were removed afterward.
- Production candidate revisions were verified ready with no traffic before
  promotion. The public dashboard, internal dashboard, county editor, regular
  cloud worker, public publisher and weekly digest job now use v0.5.9. The
  public site displays v0.5.9, and its health, county directory, county page and
  export checks passed.
- All 25 source observations and the worker provenance matched the pre-release
  aggregate, and 87 county profiles remain available (67 actively checked).
  Runtime settings, IAM and scheduler configuration were unchanged.
- The first scheduled publisher run on v0.5.9 published successfully with no
  refusal or clock quarantine.
- No provider job or publisher run was started manually, and no schedule was
  changed. Previous revisions and images (v0.5.8) remain the rollback targets.
  Detailed deployment identifiers remain in the private deployment record.
