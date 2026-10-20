# Offline provider-run triage

Use this runbook for WT-15 before proposing operational changes. The receipt
tool reads saved evidence only. It cannot poll a provider, modify a registry,
change scheduling, publish state, or deliver notifications.

The [October 20 historical diagnosis](operations-diagnosis-2026-10-20.md)
correlates execution logs and persisted history for October 15–19. It identifies
the nonzero outcomes while preserving missing-report and recovery-proof gaps.

## Correlate private evidence

For each execution, retain its original receipt, image/source identity, worker
profile, start/completion times, process exit, and original per-run worker report.
The operator must establish that the report belongs to that execution. Matching
timestamps alone do not prove identity. Do not substitute a latest aggregate,
public snapshot, or saved state containing carried-forward sources. Concurrent
executions of the same worker require manual reconciliation.

Prepare a private JSON list using this synthetic shape:

```json
[
  {
    "execution_id": "synthetic-run-1",
    "worker": "cloud",
    "started_at": "2026-10-20T10:00:00Z",
    "completed_at": "2026-10-20T10:05:00Z",
    "exit_code": 2,
    "report": {
      "generated_at": "2026-10-20T10:00:01Z",
      "scope": {"type": "fleet"},
      "overall": "error",
      "counts": {"ok": 0, "warn": 0, "error": 1},
      "sources": {
        "synthetic-source": {
          "status": "error",
          "checked_at": "2026-10-20T10:01:00Z",
          "rate_limited": true
        }
      }
    }
  }
]
```

Omit `report` when unavailable; the receipt records an evidence gap. Do not invent
an empty successful report. Timestamps must include a timezone. `generated_at`
is the worker run's start time; individual checks can occur later in that run.

```text
python scripts/triage_provider_runs.py --input PRIVATE_EXECUTIONS.json --output NEW_PRIVATE_RECEIPT.json --as-of 2026-10-20T12:00:00Z
```

The output file must not exist. Keep inputs and receipts in private, untracked
storage; IDs and timestamps may expose operational details even though raw
diagnostics, URLs, credentials and parcel measurements are not copied. The
tool does not sanitize a receipt for public publication.

## Interpret results

| Process exit | Meaning under the matching Watchtower CLI version |
| --- | --- |
| 0 | Successful process status; source evidence still needs correlation |
| 1 | Deliberate source-warning status |
| 2 | Deliberate source error or empty-scope status |
| 3 | Watchtower/configuration/storage/unexpected tool failure |
| Other or missing | Unclassified; inspect execution and restricted logs |

An exit code alone does not identify a provider or establish a process crash.
The triage tool checks counts, overall status and exit agreement. It distinguishes
recorded rate limiting, deferred backoff, source error and source warning;
other exact causes require the original restricted diagnostics and human review.
An empty scope has no provider-level failure to attribute.

`evidence_complete` means the supplied records passed consistency checks.
It does not prove that all scheduled runs or configured sources were supplied,
that monitoring is approved, or that source data is current. The script returns
0 for complete evidence with no unresolved source issues, 1 for evidence gaps
or unresolved issues, and 2 for invalid input or output failure. These are
receipt-tool results, **not replacements for provider-job exit codes**.

Each source retains its check time and freshness independently of the report.
The default 36-hour threshold can be changed with `--max-age-hours`; this changes
only offline classification, never polling cadence. Missing/future check times
remain unknown. Historical receipts can be overdue without proving an ongoing
outage. Publication freshness and source data vintage are not inferred here.

A recovery event requires a later valid, non-deferred, non-rate-limited `ok`
check for the same worker and source. A missing source, another worker's success,
retained old observation, or inconsistent report cannot clear an earlier issue.
Recovery is bounded to the supplied sequence; it is not proof of current health.

## Operator dispositions and remaining gates

For each affected execution/source, record the private evidence reference,
diagnosed cause, stop/backoff state, owner disposition, responsible operator,
next ordinary scheduled check and subsequent recovery or continuing hold.
Never shorten Retry-After or force exit zero to hide a failure.

Synthetic failure/backoff/recovery tests validate receipt generation only.
Use the [offline alert-routing rehearsal](alert-routing.md) to prepare private
message candidates from the same original evidence and an explicit source
scope. It does not send or enable notifications.
Notification delivery remains `not_attempted`. Before activating routing, name
the recipient and escalation owner, approve the exact destination/message,
test delivery and recovery acknowledgement, and record a rollback procedure.
Keep source-age alerts distinct from failed attempts and publisher freshness.
Five ordinary scheduled cycles remain an operational acceptance requirement;
this tool does not create schedules or additional checks.

WT-02 is a separate authority reconciliation: join each active county-direct
source to a dated terms reference, approved scope/cadence and owner decision.
Prioritize unresolved Aitkin/Morrison evidence. A healthy source is not proof of
permission; missing approval is not proof of unlawful operation. Prepare holds
for approval rather than editing the registry. Existing data-driven
`hold-for-terms` exclusions remain authoritative.

The [isolated restore/CAS rehearsal](isolated-restore-rehearsal.md) covers the
synthetic local aggregate only. Actual backup/GCS restoration, effective IAM
assessment and any obsolete-binding removal remain operations tasks.
Restoration and notification delivery are not established by a triage receipt.
Production changes need their own reviewable change and approval.
