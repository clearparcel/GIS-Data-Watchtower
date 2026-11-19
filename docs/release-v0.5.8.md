# GIS Data Watchtower v0.5.8

Deployed November 18, 2026. Built from merged source commit
`f923be911b3add2a9d4b3bf3f9c2a82fb3271980`, merged through PR #280.

This patch release contains the fixes from the fourth review of v0.5.7
(`754859e`), merged through PR #279:

- **Publication integrity:**
  - A complete report no longer retires a source whose provider check is newer
    than the report, and a retired source returns only with a provider check
    after its retirement (Q01).
  - A source check or worker retirement more than five minutes ahead of the
    merging clock is refused at the private write (Q02).
  - A stored future heartbeat no longer blocks a valid worker retirement (Q03).
  - A same-worker deferred first check keeps the last measurement (Q04).
- **Provider options and quality checks:**
  - `gac_completeness` and `mngac_completeness` must be `true`, `false` or a
    settings object (Q05).
  - Parcel completeness groups by the canonical Minnesota county (Q06).
  - Conflicting, malformed or empty participation metadata, and grouped totals
    above the layer count, fail the check and keep the last valid measurement
    (Q07, Q08).
  - A layer response without a usable extent keeps the last valid bounds (Q09).
- **Operations:** a malformed source `worker` assignment is an explicit input
  error for the publisher and weekly digest, and the watchdog still alerts on
  valid overdue workers (Q10); the weekly digest refuses an invalid
  `schema_version` or `generated_at` (Q11).

Deployment notes:

- **Private registry:** must pass the v0.5.8 checks before rollout:
  `gac_completeness` and `mngac_completeness`, when set, are booleans or
  settings objects, not text.
- **Stored aggregate:** every source `worker` value is a plain worker name, and
  no source check time is in the future.

## Validation and promotion

- PRs #279 and #280 passed all six Windows/Linux Python combinations, CodeQL and
  the security check.
- Before rollout, the private registry passed the v0.5.8 checks (35 sources):
  no completeness setting is text, every request option is a JSON boolean, no
  `extent_shift_percent` is `null`, and full registry validation passed with
  the new code. No registry change was needed. The stored aggregate's 25 source
  `worker` values are plain names with no future check time, and its county
  catalog names all 87 Minnesota counties once. The coverage counts predicted
  from the current aggregate (87 counties, 67 actively checked) matched the live
  dashboard.
- The release-version preflight confirmed the live v0.5.7 and the v0.5.8
  candidate. The immutable image passed 388 installed-image tests (6 skipped),
  and its installed identity and source hashes matched the reviewed commit.
- The staging county services were updated first, with runtime settings, access
  controls and IAM preserved. Synthetic staging-storage validation passed, and
  the synthetic objects were removed afterward.
- Production candidate revisions were verified ready with no traffic before
  promotion. The public dashboard, internal dashboard, county editor, regular
  cloud worker, public publisher and weekly digest job now use v0.5.8. The
  public site displays v0.5.8, and its health, county directory, county page and
  export checks passed.
- All 25 source observations and the worker provenance matched the pre-release
  aggregate, and 87 county profiles remain available (67 actively checked).
  Runtime settings, IAM and scheduler configuration were unchanged.
- The first scheduled publisher run on v0.5.8 published successfully with no
  refusal.
- No provider job or publisher run was started manually, and no schedule was
  changed. Previous revisions and images (v0.5.7) remain the rollback targets.
  Detailed deployment identifiers remain in the private deployment record.
