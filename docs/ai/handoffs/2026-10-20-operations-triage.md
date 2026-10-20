# WT-15 offline operations triage — merged, undeployed

Subsequent status: the tool is included in the deployed v0.3.2 application.
The [October 20 diagnosis](../../operations-diagnosis-2026-10-20.md) correlates
the original execution headers/audits with persisted history and identifies
the dated source failures. Full reports and formal recovery remain unverified.
The isolated synthetic restore rehearsal also merged subsequently in PR #105.
The candidate record below retains its original scope and remaining gates.

Merge update, October 20: the owner authorized merging
[PR #103](https://github.com/clearparcel/GIS-Data-Watchtower/pull/103) after
hosted CI passed. Merge commit:
`464a767a303d45e5109820b92860dad5278dd17b`. Deployment remains separately gated.
[Post-merge hosted CI](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39419369427)
also passed on that exact commit.
The candidate record below preserves its original validation/review scope.

Implementer: Codex, October 20, 2026. Branch:
`codex/wt-operations-triage`; base:
`5af87ef0e234c29d987c5443310b8086bfb3bc6c` (merged WT-01 PR #102).
This handoff is part of the candidate diff; use the branch commit as its head.

## Scope and acceptance

The owner authorized WT-01 merge and proceeding to the next implementation step.
This first operations slice supplies offline execution/report triage and a
runbook. It does not close the entire operations work package.

- Preserve CLI source-warning/source-error/tool-failure distinctions.
- Mark missing reports, mismatched counts/exits, wrong worker/time provenance
  and contradictory backoff success as evidence gaps.
- Keep source check age separate from report age. Retained observations and
  another worker's success cannot clear a source issue.
- Record synthetic failure/backoff/recovery evidence without sending messages.
- Preserve original evidence and existing receipts; no network or operational
  configuration dependency is introduced.

Implementation: `operations_triage.py`, `scripts/triage_provider_runs.py`,
13 synthetic/CLI tests, operations runbook and synchronized status/index docs.
WT-01 documentation now records the authorized merge and successful main CI.

## Validation

After review correction, local strict suite: **554 tests, 3 platform skips, 28.202 seconds, exit 0**,
Python 3.14.6, Node 24.19.0, `WATCHTOWER_REQUIRE_NODE=1`.
Compilation, status-sync check and `git diff --check` passed.
The first focused run hit a Windows sandbox tempfile access error; the rerun
with working filesystem permissions passed. Raw logs remain private.

The synthetic sequence proves rate-limit failure, deferred backoff and supported
recovery receipt generation. CLI tests prove existing evidence/receipts cannot
be overwritten. Tests cover stale/future observations, mismatched exits/counts,
missing sources/reports, worker isolation, ambiguous execution windows and
omission of raw diagnostics/credentials/measurements.

Existing historical October 15–19 execution receipts were read locally and
normalized into a private receipt. Their process outcomes are 0/2/2/1/0.
All five lack original per-source worker reports in the supplied evidence;
the tool returns 1 and retains those gaps. No new provider check was run.
These historical outcomes do not establish current production health.

## Accepted independent review and correction

The owner accepted a bounded CCE review of application/script/tests/runbook
changes from `5af87ef0e234c29d987c5443310b8086bfb3bc6c` to
`56a7b657209e4fb3d6f4f7cc2061baded8370bd7`. CCE ran a `gpt-6-luna`
medium worker and `gpt-6.1-sol` medium lead synthesis. No specialist or Astra
review ran. The worker reported uncertainty; the lead found one concrete P2.

**Fixed:** report validity was captured before validating individual sources.
An invalid sibling source could therefore coexist with a recovery event that
cleared an earlier issue. Validation now completes for every source before any
issue-history change. A regression reproduced four failures on the reviewed
application (valid/invalid source order and success/error outcomes) and passes
with the fix. Valid recovery remains covered by the existing sequence test.

The reviewers did not run tests, inspect production, or independently verify
the runtime schema or ancillary documentation changes. The correction has
root-run regression/full-suite validation; it has not received another
independent model review. Review does not authorize merge or deployment.
The tested application/fix commit is
`9c20701f62429207b2f2a3d788519299cd60e269`. The owner authorized PR
publication and hosted CI on October 20. The PR description and checks record
the exact published head and hosted outcome; the publication-preparation
commit changes documentation only.

## Shared context and remaining gates

Published CCE record `gis-data-watchtower`, revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`,
updated October 13, review due October 14: historical `needs-review` context.
Current source and owner instructions take precedence.

Next: correlate restricted source reports and log/image identity for the dated
nonzero executions; record exact cause and owner disposition. Reconcile WT-02
authority separately. Alert recipients/delivery, isolated restore/CAS rehearsal,
inherited IAM assessment and five ordinary daily cycles remain open.
No production changes, deployment, scheduling, provider polling, notifications,
credential changes, CRM work or memory publication were performed or authorized.
Merge authority applied only to WT-01 PR #102.
