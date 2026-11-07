# Internal UI release preparation

- Authorization: owner requested deployment after reviewing the internal UI
  candidate. Deployment scope is the internal dashboard.
- Base: `1a4e80ea2fb513ffe6e72b7cd2afd3548a4a613b` (PR #222, stacked on #221).
- Branch: `codex/internal-ui-release`; prepared on the authoritative workstation
  in an isolated worktree. Existing dirty work is preserved.
- Candidate changes: version 0.4.3, current Debian zlib runtime package, a
  container package-install regression, and release/status documentation.
- Acceptance: full CI including enforced container scans; clean committed
  source; version preflight; immutable private-dashboard build; rollback
  capture; image-only service update; identity, authentication and read-only
  user-flow verification.
- No merge, promotion or production settings changes have occurred in this
  preparation. The user has authorized deployment; repository merge approval
  remains separate under AGENTS.md.
- Shared CCE memory was unavailable. No independent review has been requested.
  CI results and exact head will be recorded in the PR. Private deployment
  evidence must remain outside this public repository.

## Deployment update

The owner subsequently approved merge and continued deployment. PR #223 merged
as `81807110dca882a57fed7d7f3acf7449badc7946`, including #221 and #222. Its
[main CI run](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/42417111860)
passed. The public service, provider jobs and schedules were outside the rollout.

The internal service was promoted after image acceptance and comparison of the
candidate's non-image settings and IAM with the retained predecessor. The image
index was resolved to its Linux/amd64 manifest; installed source identity and
both OS/Python inventories matched the tested source and scanned CI components.
After promotion the expected revision held 100% traffic, settings/IAM were
unchanged, anonymous access still required Google sign-in, and the owner
confirmed the new signed-in UI.

Private evidence was saved on the authoritative workstation before and after
promotion. Its connection stopped responding during additional monitoring-data
and request-log reads, which remain unverified. The final combined private
receipt and temporary auth-log cleanup should be completed when that connection
is available. No rollback was needed. This public documentation follow-up does
not change application code or deployment settings.
