# WT-15 historical execution diagnosis

Investigated October 20, 2026. **Historical source-level causes identified;
formal recovery remains unverified.** This is a read-only diagnosis, not an
operational change or a declaration that the provider fleet is currently healthy.

## Evidence and correlation

The October 15–19 executions all ran v0.3.0 source
`4e4dbec082dbd966e7af1e18a12f03d0557295c2`, using the same immutable image and
configuration identity. The check, persistence and CLI source files match that
deployed source. Each execution had one task, one attempt and no job retries.

Five execution-scoped Cloud Logging queries recovered runtime headers, process
exits and final execution audits. Each header's run time and counts matched
exactly one original persisted worker-history entry. Source counts and the
deployed CLI's exit rules also agreed. Correlation therefore uses execution
labels, audit/image identity, process exit and the unique history record,
not timestamps alone. The history was downloaded at an explicit storage
generation. Observation cutoff: **2026-10-20T15:41:10Z**.

Exact execution IDs, storage generation, original diagnostics, source records,
history line numbers and SHA-256 evidence manifest remain in private local
evidence. No private deployment configuration is included here.

## Timeline and causes

| UTC run date | OK / warning / error | Exit | Supported explanation |
| --- | --- | --- | --- |
| October 15 | 33 / 0 / 0 | 0 | Recorded healthy baseline. |
| October 16 | 32 / 0 / 1 | 2 | FEMA flood-hazard transport failed with curl error 35, connection reset by peer, after two source attempts. |
| October 17 | 31 / 1 / 1 | 2 | Beltrami parcel query returned ArcGIS application error code 500 after two source attempts. Hennepin imagery also changed its capability fingerprint. |
| October 18 | 32 / 1 / 0 | 1 | Hennepin imagery's fingerprint returned to its prior value; the comparison emitted another change warning. |
| October 19 | 33 / 0 / 0 | 0 | All 33 source statuses were recorded OK. |

**VERIFIED_CAUSE — application outcome:** the two exit-2 executions reflect
recorded source failures under the deployed exit rules. The exit-1 execution
reflects a recorded change warning. These outcomes are not evidence of a
Watchtower process crash or a failed deployment.

**VERIFIED_CAUSE — warning mechanism:** Hennepin's stored fingerprint changed
on October 17 and changed back on October 18. The intermediate value is the
SHA-256 of `[]`. The deployed comparison code warns on both transitions.
This does not establish an imagery content change or explain why the derived
capability representation became empty.

**UNVERIFIED — upstream mechanism:** the saved errors establish the observed
FEMA transport reset and Beltrami query rejection, but do not identify the
underlying network/server cause. No provider request was made to reproduce them.
There is no evidence here supporting weaker TLS, shorter backoff, increased
cadence or forced successful exits.

## Later results and recovery limits

History records FEMA OK from October 17, Beltrami OK from October 18 and
Hennepin OK on October 19. Each first subsequent OK record has a positive
attempt count and elapsed time. This supports later successful recorded
results; it does not supply every field required for formal recovery proof.

All five captured stdout bodies fail full JSON parsing after their valid
headers. None reached the query's entry cap. The cause of incomplete or
disordered stdout is unverified; no missing JSON was repaired or invented.
Persisted history preserves per-run source summaries but omits `checked_at`,
`rate_limited` and `deferred`. It was not substituted for an original full
worker report.

The existing offline triage CLI therefore correctly returned **1** and retained
five `missing_worker_report` gaps, with zero recovery events and notifications
not attempted. Its empty unresolved-source list does **not** mean all sources
recovered: it cannot construct complete issue histories without the reports.

The downloaded history also contains an October 20 Todd timeout after two
source attempts (61,384 ms). This is contextual history outside the five
execution correlations, not a fresh provider probe. It is another reason not
to equate the October 19 all-OK result with current fleet health.

## Disposition and remaining work

Proposed disposition: retain the dated FEMA/Beltrami source failures and their
later recorded OK results; retain Hennepin as reversible fingerprint drift
with the upstream explanation unresolved. Preserve all existing operational
controls. Owner acceptance and assignment of a responsible operator remain
pending; permission to investigate is not an operational disposition.

This completes the bounded historical cause-attribution slice. It does not
close WT-15 or the operations work package. Remaining work includes:

- Complete original per-run evidence and source-timestamp/backoff recovery
  proof. A separate retention improvement could persist a compact report with
  execution identity and these fields; none was implemented or activated here.
- WT-02 matching against actual private authority records, prioritizing
  Aitkin/Morrison.
- Approved alert routing/delivery, actual GCS backup/restore and effective IAM
  assessment, plus five ordinary daily cycles after the applicable changes.
  Reading five historical runs does not meet that acceptance gate.

Production is unchanged: no provider polling, job execution, notification,
deployment, schedule, registry, IAM, credential or authoritative data write.
No application code change was justified by this evidence.

See the [triage runbook](operations-triage.md) for the receipt contract and
[monitoring-authority runbook](monitoring-authority-reconciliation.md) for the
next evidence-matching task.

## Candidate and validation record

Implementer: Codex. Branch: `codex/wt15-historical-diagnosis`, based on
`82845a74a9bda160102d0cdf0b021cf3eed984c4`. Changes are documentation only;
private evidence and diagnostic helpers are untracked. No new model review
has run for this diagnosis.

- Five execution/header/history/exit/image correlations passed local assertions.
  The three relevant runtime source files match the deployed job source.
- Strict local suite: 583 tests in 29.732 seconds, 3 platform skips, exit 0,
  with required Node 24 behavior tests enabled.
- Compilation, current-status synchronization and whitespace checks passed.
- The triage CLI's expected evidence-gap exit 1 is retained separately from
  both the successful test run and the historical provider-job exits.

Published CCE context was read at revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, record `gis-data-watchtower`,
SHA-256 `ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`.
It is historical `needs-review` material, updated October 13 with review due
October 14. Direct execution evidence and current owner instructions take
precedence.
