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
