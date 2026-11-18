# 0001. The editor's publication-status read may reconcile county enrollment

- Status: Accepted
- Date: 2026-11-18
- Decided by: the project owner
- Context: Codex follow-up review of v0.5.5 (finding F16, original finding 31)

## Context

The authenticated county editor exposes
`GET /api/counties/<county>/publication`. Besides reporting publication status,
the handler calls `_sync_monitoring`, which rewrites that county's entry in the
private enrollment object `county-directory/v1/monitoring/sources.json` from the
saved private draft and revision (`clearparcel/datawatch/county_admin.py`).

A GET that can change what a later worker checks is unusual. The review asked
for either moving reconciliation to the explicit retry/write path or recording
a decision that accepts it.

## Decision

Keep the reconciliation on the status read. It is an accepted, documented side
effect, not a defect.

The side effect is bounded:

- It only replays the operator's last durable private save. It never invents an
  enrollment, and a stale revision cannot override a newer save, because the
  enrollment object uses conditional, revision-checked writes.
- It is authenticated with the same editor credentials as a save.
- It makes no DNS or GIS-provider request. Workers still apply profile
  assignments, dispatch spacing, terms holds, county stop/decline decisions and
  provider 429 backoff before any check.
- It is idempotent: repeating it with an unchanged private save writes the same
  entry.

## Consequences

- An operator can finish a save whose enrollment sync failed by reopening or
  refreshing the county status, as well as with **Retry updates**. The runbook in
  `docs/county-source-monitoring.md` relies on this recovery path.
- Reviewers should not re-raise the GET-side write as a finding unless one of
  the bounds above changes. If the editor ever gains unauthenticated or
  cross-origin status reads, or the reconciliation starts doing more than
  replaying the saved private record, revisit this decision.
