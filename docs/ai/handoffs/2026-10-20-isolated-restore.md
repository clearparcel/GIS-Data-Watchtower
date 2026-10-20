# Isolated aggregate restore — merged PR #105

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

## Accepted independent review

The owner requested a bounded CCE review before publication. One `gpt-6-luna`
medium worker reviewed the application/CLI/tests/runbook diff from base
`6a2f791d3fc1a7172ff7eef39f1ace3cc5f7fafe` to tested application head
`79b906978c4e46bcfc30e7756657e5b0294c4c00`, with supporting unchanged local
storage, aggregate publisher, locking and JSON parsing excerpts.

The review returned **no actionable P0-P2 findings** in recovery evidence,
storage isolation or concurrent publishing validation. No lead, specialist or
Astra review ran. The reviewer used supplied context only; it did not rerun
tests, inspect ancillary handoff/status changes or verify GCS, process termination
or production restoration. No application changes were needed. This follow-up
records the review in documentation only; the test results above remain evidence
from the implementation run, not newly executed checks.

The review does not authorize publication, merge or deployment.

## Limits and authority

The receipt measures local synthetic aggregate recovery only, with hashes of
the executed implementation files. It leaves GCS and production verification
false. It does not cover real backup provenance, all worker state/backoff/history
artifacts, IAM, process termination, network filesystems or live services.
No providers were polled; no cloud storage, notification destinations,
credentials, runtime scheduling or production configuration were changed.

PR #104 post-merge CI passed at the exact base above. The owner authorized
publication of this candidate and hosted CI on October 20. Publication preparation
changes documentation only; the application remains at the tested/reviewed head
above. The PR description and hosted checks record the exact published head and
CI outcome. All eight checks passed at `fb9ba642948b23401360d92d153ae3de8b9dc892`.
The owner then requested merge and deployment. PR #105 merged at
`cd2e071672740bebc10955720d8bd00d5fa89899`; post-merge CI
[39426148900](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39426148900)
passed. The required versioned deployment is tracked in
[v0.3.1 release preparation](../../release-v0.3.1.md).
Next operational work needs actual evidence and applicable explicit
approval: complete-backup/GCS rehearsal, alert delivery, IAM and five ordinary
daily cycles. WT-01 display deployment also remains open.

Shared published CCE context: `gis-data-watchtower`, revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`,
updated October 13/review due October 14, historical `needs-review`.
Current source and owner decisions outrank this historical context.
