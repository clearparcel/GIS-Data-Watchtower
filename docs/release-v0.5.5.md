# GIS Data Watchtower v0.5.5 candidate

This patch candidate contains the fixes from the November 18 review of
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

The candidate was validated with the repository's required test, compile,
current-status and diff checks. Each merged PR passed CI on all six
Windows/Linux Python combinations, CodeQL and the security check.
