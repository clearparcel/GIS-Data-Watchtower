# Public UI language and navigation

- Objective: implement the owner's seven requested UI changes: clearer county
  purpose and cards; four-column county list; plain metric/status language;
  readable public access updates; purposeful source links; expandable technical
  details; and an Overview focused on coverage, attention and check times.
- Base: `0059aaf025b6b7b93f3ecda702367ae059f057cd` (public v0.4.2 release record).
- Branch: `codex/simplify-public-ui`. Implementer: Codex.
- Shared context: current repository instructions and source were read. Published
  CCE memory and a live CCE connection were unavailable. The owner explicitly
  approved a task-specific exception for this cloud UI implementation and offline
  validation on November 7, 2026. It does not grant deployment authority.
- Scope: presentation modules, UI assertions, user guide, README and status.
  No observation, provider-permission, scheduling or export-schema change.
- Acceptance: recent check counts exclude overdue reports; county access and
  statewide availability remain separate; unknowns remain unknown; field names
  and calculations remain available; filters and refresh retain their behavior;
  phone layouts remain usable.
- A published directory update time is labeled **updated**, not **reviewed**,
  because it records publication rather than a source-research review.
- A statewide-only directory link does not establish a county download. Export
  summaries retain their existing vocabulary and machine-readable contracts.
- Local browser validation uses invented observations and county-directory data,
  with external requests blocked. No providers were polled.
- Independent review: no other assistant or CCE reviewer has reviewed this diff.
  The candidate requires review and the owner's separate merge/deployment approval.

## Validation

- `WATCHTOWER_REQUIRE_NODE=1 python -W error::ResourceWarning -m unittest discover -s tests -q`:
  1,016 tests passed, no skips (Python 3.13.15, Node 24.19.0; PDF test extras installed).
- Compilation of `clearparcel`, `tests` and `scripts`, generated status sync,
  dependency consistency and `git diff --check` passed.
- Chromium: all six routes (Overview, Counties, county profile, county fields,
  statewide completeness and source details) returned 200 at 1440, 390 and 320 px.
  County search/empty state, four-column table, field-code disclosure,
  required-field filtering, refresh pause, lazy county details and relocated
  comparisons passed. No JavaScript errors or horizontal page overflow.
- Added regression coverage for a recent source with an overdue worker, a
  statewide-only link, and paused/permission filter states. Existing tests retain
  the zero/unknown/unscanned, permission and export-contract checks.
- The exact implementation head and subsequent CI results are recorded in the PR.
