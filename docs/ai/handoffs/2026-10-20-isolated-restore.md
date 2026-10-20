# Isolated aggregate restore — local candidate

Implementer: Codex, October 20, 2026. Branch `codex/wt-isolated-restore`.
Base: `6a2f791d3fc1a7172ff7eef39f1ace3cc5f7fafe`, the owner-approved PR #104
merge. The branch commit containing this handoff identifies the candidate.

## Scope and acceptance

The owner authorized merging PR #104 and proceeding to the next implementation
step. The operations plan calls for an isolated synthetic restoration and
concurrent-write rehearsal. Actual source approval records remain unavailable;
the prior bounded cloud-log read required operator reauthentication.

This slice adds `restore_rehearsal.py`, a standalone CLI, seven regression
tests, a runbook and synchronized status/index/handoff documentation.
It creates only fixed synthetic aggregates in an owned temporary directory and
uses the existing local backend and aggregate publisher. No production
configuration or backend environment selection is loaded.

Acceptance: exact restore from captured bytes; damaged-backup rejection before
write; occupied-destination and stale-token refusal; an observed real concurrent
CAS conflict followed by production publisher retry retaining both workers;
preserved observation clocks/provenance/tombstones; delayed-report protection;
unchanged backup/origin and removed scratch. Receipt output is exclusive-create.

## Validation

Focused suite: 7 tests passed, including fault injection disabling CAS,
removing retries and losing a worker update.

Full ResourceWarning-strict suite: **575 tests, 3 platform skips, 29.596 seconds,
exit 0**. Python 3.14.6, Node 24.19.0, `WATCHTOWER_REQUIRE_NODE=1`.
Compilation, generated-status synchronization and whitespace checks passed.
A standalone CLI execution passed all nine checks with exactly one real CAS
conflict; cleanup completed. The generated receipt/logs remain in ignored local
evidence. Tests and the CLI exercised local storage only.

No independent model review has run for this slice. Offer a bounded CCE review
of the pinned candidate for false-positive evidence, concurrency coverage and
storage isolation before publication.

## Limits and authority

The receipt measures local synthetic aggregate recovery only, with hashes of
the executed implementation files. It leaves GCS and production verification
false. It does not cover real backup provenance, all worker state/backoff/history
artifacts, IAM, process termination, network filesystems or live services.
No providers were polled; no cloud storage, notification destinations,
credentials, runtime scheduling or production configuration were changed.

PR #104 post-merge CI passed at the exact base above. This new candidate remains
local and unmerged; publication, merge and deployment outcomes must be recorded
separately. Next operational work needs actual evidence and applicable explicit
approval: complete-backup/GCS rehearsal, alert delivery, IAM and five ordinary
daily cycles. WT-01 display deployment also remains open.

Shared published CCE context: `gis-data-watchtower`, revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`,
updated October 13/review due October 14, historical `needs-review`.
Current source and owner decisions outrank this historical context.
