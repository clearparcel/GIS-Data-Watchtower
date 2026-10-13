# Codex and Claude shared development workflow

Use the existing project repository as the source of code, GitHub issues and pull requests as the work record, and the owner's approved published CCE catalog as shared project memory. Claude Code is the primary Claude coding interface. Claude web/Project Knowledge is an optional reader of manually refreshed Markdown snapshots.

## Start a task

Read the repository's `AGENTS.md`, applicable nested instructions, README, existing CI, and relevant current-status documents. `CLAUDE.md` imports `AGENTS.md` rather than keeping a second copy of common rules. Retrieve only relevant shared-memory IDs and record their exact Git revision, document hashes, freshness, and published/draft state. If memory is unavailable or contradicts current evidence, disclose the gap and verify the source; do not fill it with confident assistant recollection.

Record the task, base commit, working branch, affected files, acceptance criteria, and implementer. Use separate worktrees/branches for parallel work and disjoint tasks; never have two assistants edit the same live checkout. Parallel work does not grant new delegation, spending, production, or credential permissions.

## Implement and review

Either assistant may implement. Assign the other as reviewer for that task when the owner requests a review. The reviewer reads the same approved context plus a diff pinned to explicit base/head commits, existing instructions, and actual validation results. A bounded review may use a supplied diff with tools disabled; a deeper repository review needs its own authorized read scope. Do not infer broad tool authority from a review request.

Review concrete defects, regressions, security/data boundaries, missing behavior tests, and project-specific invariants. Findings include severity, file/line, impact, evidence, and a proposed correction. Report uncertainty and untested paths. The implementer fixes actionable findings and reruns the affected checks; a changed head invalidates the previous review of those changes.

Use ordinary pull requests and existing CI. AI findings supplement tests and human ownership; neither an acknowledgement nor an empty review proves a release is safe. Record which assistant actually reviewed the exact head. One task does not need reviews by both assistants merely for symmetry.

## Handoff record

Keep a task-specific file under `docs/ai/handoffs/` or use the equivalent issue/PR fields. Include:

- Objective and acceptance criteria.
- Repository, exact base/head SHAs, branch/worktree, implementer and requested reviewer.
- Shared-memory revision, IDs/hashes, freshness and known conflicts.
- Files/behavior changed and actual checks with results.
- Findings addressed, remaining risks, and the next concrete step.
- Separately granted scoped approvals, and any merge/deployment/publication gates.

Do not put raw chats, credentials, capabilities, personal/client/financial data, or private deployment evidence into repository handoffs. Public repositories receive public/synthetic context only; private shared memory remains in its approved private store.

## Review entry points

- Local Codex: open the project checkout in Codex, choose Code Review, and specify the task's pinned diff and shared-memory receipt.
- Local Claude Code: launch `claude` in the project's isolated checkout and ask it to review the explicit base/head diff using the same receipt. It reads the common rules through `CLAUDE.md`.
- Codex GitHub: after repository review integration is enabled, request `@codex review` on a PR. Integration availability and allowance must be verified; adding instruction files alone does not enable it.
- Claude GitHub: its official Action or hosted review is a separate optional activation requiring the authorized GitHub app/credentials and a chosen cost/trigger policy. This setup does not create unattended model jobs or new secrets.

Review requests consume the relevant provider allowance. Run them when they can add useful independent scrutiny; avoid duplicate unchanged reviews and automatic reply loops. For substantive ClearParcel changes, follow the existing owner guidance to offer an independent CCE review and wait for acceptance.

## Publish and refresh

Keep memory updates separate and reviewable with dated sources and conflict explanations. Only an explicitly approved publication makes a new CCE revision authoritative. Refresh consumers and record their actual consumed revision after publication. A persistent Claude session retains its imported snapshot, but it does not automatically follow future Git changes.

Merge, deploy, account access, credentials, authoritative datasets, and production configuration require the existing scoped owner authority. This workflow does not change those boundaries or existing CCE connection ownership/chat-continuity rules.
