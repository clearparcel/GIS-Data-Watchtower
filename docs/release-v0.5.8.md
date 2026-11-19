# GIS Data Watchtower v0.5.8

Candidate, not yet deployed. This patch release contains the fixes from the
fourth review of v0.5.7 (`754859e`), merged through PR #279:

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
