# Offline alert-routing rehearsal

This tool prepares private email message candidates from saved,
operator-correlated worker reports. It does not send email, configure a channel,
run a provider, alter a schedule, or establish delivery acceptance.

Keep the input, recipient, escalation owner and output private and untracked.
Only synthetic examples belong in public Git. An input object contains:

- `executions`: the original evidence list described in
  [the operations triage runbook](operations-triage.md).
- `expected_sources`: explicit `worker` / `source_id` pairs for this review,
  for example `[{"worker": "cloud", "source_id": "synthetic-source"}]`.
- `routing`: `channel: "email"`, `recipient`, `escalation_owner`, and
  `runbook_ref`. A synthetic recipient is `operator@example.invalid`.

```text
python scripts/preview_alert_routing.py --input PRIVATE_REHEARSAL.json --output NEW_PRIVATE_PREVIEW.json --as-of 2026-10-20T12:00:00Z
```

The output file must not exist. Exit 0 means the supplied evidence and draft
route have no identified gaps, even if they contain failure messages. Exit 1
means evidence or routing gaps; exit 2 means invalid input/output. None means
that a notification was delivered or monitoring was authorized.

## Classification and operator action

| Preview | Meaning and action |
| --- | --- |
| Source failure/warning | Inspect the original execution/report; a nonzero process exit alone does not identify a provider outage. |
| Rate limit/backoff | Preserve Retry-After and current stop/backoff controls. Do not trigger an extra provider check. |
| Check overdue | Latest check is older than 36 hours by default; investigate the ordinary scheduler and worker evidence. This is not data vintage or proof of an outage. |
| Evidence gap | Latest worker report is missing, inconsistent, partial, or missing an expected source; investigate before claiming health. |
| Recovered | The latest valid, fresh check for the same worker/source follows a supported failure. Match the incident and acknowledge recovery after delivery has been verified. |

The cutoff must be explicit and timezone-aware. `--max-age-hours` changes only
offline classification. A retained check under backoff stays old even if a
newer worker report exists. A stale recovery is not emitted as current health.
The latest full-fleet report must cover each expected pair; the tool never
falls back to an old successful run when newer evidence is missing.

Rehearse source errors, warnings, rate limits/backoff, overdue checks, missing
reports/sources, malformed reports, and fresh versus stale recoveries. The
expected scope must be reviewed against configuration; this tool cannot prove
the supplied inventory or history is exhaustive.

## Deduplication and delivery gates

The preview emits deterministic `event_key` values. Repeated failures within
the supplied unresolved incident share a key; a recovery followed by a new
failure starts a new key. Overdue keys bind the last check time. Retain the
complete relevant incident history: truncating it can change incident keys.
Different conditions (for example failure and overdue) deliberately have
different keys.

These are candidate keys, not durable delivery deduplication. Before enabling
delivery, an implementation must persist accepted/sent/acknowledged state,
handle retries without duplicate sends, and define a repeat/reminder policy.
There is no delivery transport or ledger in this candidate.

Before a delivery test:

1. Review the exact private destination, escalation owner, scope, threshold,
   subject, structured source/worker/time fields and fixed message text.
2. Approve the specific synthetic test messages and destination. A draft
   recipient selection alone does not authorize sending.
3. Test authorized delivery through the chosen channel; retain independent
   receipt and operator acknowledgement for both failure and recovery.
4. Prepare a separate configuration/activation diff, transport credentials
   handling, delivery retry policy and rollback procedure. Rollback disables
   only the new notification route and preserves provider controls/evidence.
5. After approved activation, observe five ordinary daily cycles without
   increasing provider cadence. No automation is created by this runbook.

Existing hosted notification policies and real delivery are not inspected by
this offline rehearsal. Source-age, provider attempts, public publication
freshness and source data vintage remain separate. The receipt always retains
`notification_delivery: "not_attempted"`, `activation_authorized: false` and
`delivery_acceptance_complete: false`.
