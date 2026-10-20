# WT-02 monitoring-authority reconciliation — local candidate

Implementer: Codex, October 20, 2026. Branch:
`codex/wt-monitoring-authority`. Base:
`464a767a303d45e5109820b92860dad5278dd17b` (owner-authorized PR #103 merge).
The branch commit containing this handoff identifies the candidate head.

## Scope and acceptance

The owner authorized merging operations triage PR #103 and proceeding to the
next implementation step. This slice implements an offline evidence matcher,
CLI and runbook for county-direct parcel monitoring authority.

- Bind each supplied approval to the exact source and current research hashes,
  county and worker scope, dated terms/approval/reviewer references.
- Check current review dates and recorded combined minimum dispatch interval,
  including explicit evidence for subdaily exceptions.
- Preserve disabled sources and every current data-driven `hold-for-terms`
  exclusion; do not infer monitoring approval from healthy observations.
- Flag missing/stale/conflicting records, ambiguous worker assignments,
  mismatched endpoints/research, unknown IDs and unresolved scope.
- Never grant activation, rewrite research/registry data, poll providers or
  send notifications. Output always says live configuration is unverified.

Files: `monitoring_authority.py`, `reconcile_monitoring_authority.py`, 14 tests,
runbook and synchronized README/status/handoff documentation.

## Actual validation

Final ResourceWarning-strict suite: **568 tests, 3 platform skips, 28.342 seconds,
exit 0**. Python 3.14.6, Node 24.19.0, `WATCHTOWER_REQUIRE_NODE=1`.
Compilation, generated-status synchronization and whitespace checks passed.

Synthetic tests cover matching assertions without activation, stale/future
reviews, wrong county/profile/hash, cadence conflicts and subdaily exceptions,
duplicate/orphan evidence, missing scope, endpoint changes, disabled sources,
input immutability and exclusive output creation. A data-driven test compares
every current research hold to the existing runtime hold predicate. CLI tests
reject duplicate JSON fields and non-finite numbers before creating a receipt.

A standalone CLI run with a synthetic Aitkin-tagged source and no approval
evidence returned exit 1, `missing_approval`, incomplete reconciliation and
`activation_authorized: false`. Raw receipts/logs remain private.

The accepted PR #103 merge and post-merge CI succeeded at the exact base above.
This new candidate has not been published, hosted-tested or independently
model-reviewed. A bounded CCE review is recommended for evidence matching,
hold precedence and cadence scope.

## Evidence and limitations

A bounded read of existing historical execution logs was attempted for the
previous source-triage follow-up. It failed because the local cloud session
requires interactive reauthentication. No credentials/account configuration
were changed and no provider job was started. The original execution-only
receipts still cannot establish exact provider causes or recovery.

No real private source approval/cadence ledger was supplied to this new tool.
`documented` means input assertions match, not that the tool authenticated the
reviewer, verified official terms, inspected live schedules or granted access.
The operator must establish evidence provenance, full registry coverage and
combined spacing across every dispatch path. Wildcard/unassigned scope remains
unresolved. Statewide parcel rows without county scope require separate
classification rather than being silently accepted as county-direct approvals.

Published CCE context `gis-data-watchtower`, revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`,
updated October 13/review due October 14, remains historical `needs-review`
context. Current source and owner decisions take precedence.

Next: independently review this candidate if accepted, then supply and review
the actual private authority/cadence evidence, prioritizing Aitkin/Morrison.
Historical log diagnosis requires restored operator cloud authentication.
Notification delivery, isolated restore/CAS proof, IAM assessment and five
ordinary cycles remain open. No merge authority for this candidate, deployment,
production writes, source changes, schedule changes or notifications are granted.
