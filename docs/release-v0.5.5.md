# GIS Data Watchtower v0.5.5

Deployed November 18, 2026. Built from merged source commit
`f8f09973f40c8c630df9d59f18791d5b8643a106`, merged through PR #264.

This patch release contains the fixes from the November 18 review of
`ff9f9a7`, merged through PRs #258 to #263:

- **#258, dashboard filters and monitoring accuracy:**
  - The mobile filters hide rows again.
  - "Actively checked" now filters on check freshness, not health.
  - A failed check keeps the last usable observation as its comparison baseline.
  - A short county catalog is rejected.
  - A change configured at `error` severity fails the source.
  - Parcel sublayer schema changes and a missing expected WKID are reported.
- **#259, provider controls:** the registry check refuses these before any request:
  - malformed `execution_profiles`;
  - `expected_layer_name` on an adapter that ignores it;
  - a non-finite or over-hour `retry_delay_seconds`.

  Damaged stored backoffs become operator holds, and backoff merges compare instants. A check that selects no source does not claim the provider-run slot.
- **#260, publisher and coverage:**
  - A malformed private aggregate is never published.
  - An assigned source without its worker's report is not counted as current.
  - A county-direct source that the county's research decision blocks no longer counts as active coverage.
- **#261:** a restart right after a killed run waits up to five seconds for the run lock (Windows).
- **#262, Low cleanup:**
  - Exports keep a never-checked source's check time blank.
  - MnGeo approval values `yes`/`no` and `true`/`false` read the same way.
  - Catalog dates are read the same way in every view.
  - `watchtower status` exits 1 without a state file.
  - County REST links are validated by URL segment.
  - `WATCHTOWER_WORKDIR` is the parent of each run's directory.
  - Build provenance schema v2 names `image_config_digest`.
- **#263:** user-guide screenshots recaptured from v0.5.4.

Deployment notes:

- **Private registry:** must pass the stricter checks before rollout:
  - change severities are only `info`, `warn` or `error`;
  - `execution_profiles` are lists of `cloud`, `local` or `any`;
  - `expected_layer_name` appears only on `arcgis_layer` or `arcgis_service` sources;
  - `retry_delay_seconds` is at most 3600.
- **Coverage counts:** can drop where a stored county-direct observation belongs to a county whose decision now blocks it.
- **Scripts:**
  - A script that treated `watchtower status` exit 0 as healthy without a state file now sees exit 1.
  - A consumer of the provenance file's `image_digest` should read `image_config_digest`.

## Validation and promotion

- PRs #258 to #264 passed all six Windows/Linux Python combinations, CodeQL
  and the security check. Local validation passed the required test, compile,
  current-status and diff checks.
- The release-version preflight confirmed the live v0.5.4 and the v0.5.5
  candidate. The immutable image passed 268 installed-image tests, and its
  installed identity and source hashes matched the reviewed commit.
- The private registry passed the stricter v0.5.5 checks before rollout, and
  the coverage counts predicted from the current aggregate matched the live
  dashboard, so no coverage count dropped.
- The staging county services were updated first, and their runtime settings,
  access controls and IAM were preserved. Synthetic staging-storage validation
  passed: audit replay, public privacy, bounded attachment metadata reads and
  hash-verified downloads. The synthetic objects were removed afterward.
- Production candidate revisions were verified ready with no traffic before
  promotion. The public dashboard, internal dashboard, county editor, regular
  cloud worker and public publisher now use v0.5.5. The public site displayed
  v0.5.5, and its health, county directory, county page and export checks
  passed.
- All 25 source observations and the worker provenance matched the
  pre-release aggregate, and 87 county profiles remain available. Runtime
  settings, IAM and scheduler configuration were unchanged.
- No provider job or publisher run was started manually, and no schedule was
  changed. The scanner and weekly digest images were outside this release.
  Previous revisions and images remain the rollback targets. Detailed
  deployment identifiers remain in the private deployment record.
