# Alert routing: offline preview and disabled delivery candidate

The preview tool prepares private email message candidates from saved,
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

The preview keys alone are not durable delivery deduplication; the disabled
delivery candidate below adds the ledger.

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

## Delivery candidate — disabled by default

`clearparcel/datawatch/alert_delivery.py` reuses the preview unchanged and adds
a durable delivery ledger. Nothing is sent unless a private configuration sets
`"enabled": true`, names a transport, and the caller supplies that transport.
A missing or disabled configuration performs a read-only dry run: it reports
which event keys are new and writes no ledger.

```text
python scripts/deliver_alerts.py --ledger-root PRIVATE_LEDGER_DIR deliver --input PRIVATE_REHEARSAL.json --output NEW_PRIVATE_RECEIPT.json --as-of 2026-10-20T12:00:00Z
python scripts/deliver_alerts.py --ledger-root PRIVATE_LEDGER_DIR status
python scripts/deliver_alerts.py --ledger-root PRIVATE_LEDGER_DIR acknowledge --event-key KEY --by OPERATOR
python scripts/deliver_alerts.py --ledger-root PRIVATE_LEDGER_DIR reconcile --event-key KEY --resolution sent|requeue|abandon --by OPERATOR
```

With `WATCHTOWER_STORAGE=gcs` the ledger uses the existing generation-conditional
storage backend (object `alerts/delivery-ledger.json` by default) instead of
`--ledger-root`. The ledger is private evidence and is not part of the public
publication allowlist. Deliver exits 0 when nothing needs attention, 1 for
evidence/routing gaps or ambiguous, rejected or exhausted delivery, and 2 for
invalid input, storage conflicts or a refused transport.

### Ledger states

| State | Meaning |
| --- | --- |
| `queued` | Accepted: the event key was recorded once from a current preview. |
| `sending` | Claimed by one invocation through a compare-and-swap write. |
| `sent` | The transport confirmed a hand-off. This is not mailbox receipt. |
| `retry_wait` | The transport definitively did not hand off; a later invocation may retry. |
| `exhausted` | Rejected without retry, or retries used up. Operator attention required. |
| `ambiguous` | Outcome unknown (timeout, partial write, or a claim whose lease expired). |
| `expired` | Undelivered and no longer current after `max_queue_age_hours` (72), or abandoned by an operator. Unabandoned expiry needs operator attention. |
| `superseded` | Not yet delivered when a recovery for the same worker/source was accepted; never sent. |
| `acknowledged` | An operator recorded review of a sent, ambiguous or expired event. |

### Delivery rules

- **Idempotency.** The preview `event_key` is the ledger key. A known key is
  never queued again, so repeated runs of one unresolved source failure,
  replays of the same input, and an acknowledged but continuing incident send
  nothing new. Evidence-gap keys bind the latest execution, so a gap that
  persists across runs produces one alert per affected run.
- **Current evidence only.** Enabled delivery refuses an `--as-of` later than
  the delivery clock or older than `max_age_hours`, so replayed history is
  never presented as current.
- **Concurrency.** Claims and outcomes are compare-and-swap writes. Only the
  invocation whose claim write succeeds sends; competing invocations reload.
  A claim write that landed but reported a conflict is recognized on retry.
  Persistent conflicts stop the run without sending.
- **One digest per invocation.** All claimed events go in one message, bounded
  by `max_messages_per_digest` (default 25); the remainder stays queued.
- **Ambiguous outcomes are held.** A timeout, unexpected error, interrupted
  write, or claim older than `claim_lease_minutes` (default 15) becomes
  `ambiguous` and is not resent, unless a transport declares provider-side
  replay safety. An operator checks the destination and reconciles it as
  `sent`, `requeue` (accepting possible duplicate delivery), or `abandon`.
- **Bounded retries.** Only definitive non-delivery is retried, on a later
  invocation, never in a sleep loop: `max_attempts` (default 3), exponential
  backoff from `retry_base_minutes` (15) capped at `retry_cap_minutes` (360).
  A transport `Retry-After` is honored for the whole ledger: no event is sent
  before it passes. Retries never trigger a provider check.
- **Incident reopening.** Accepting a recovery marks earlier events for the
  same worker/source `resolved_by`; any of them not yet delivered become
  `superseded`, so a failure never arrives after its recovery. A later failure
  has a new preview key and is delivered as a new incident.
- **Repeat policy.** No automatic reminders. Unacknowledged sent events are
  listed by `status` for operator follow-up.
- **Routing gaps block sending.** Events queue but are not sent while any route
  field is missing.
- **Rollback.** Set `"enabled": false` (or omit the configuration). The ledger is
  retained and nothing is sent. On re-enablement, a queued event whose
  condition is still current is re-dated and delivered; one no longer current
  after `max_queue_age_hours` expires and is listed for operator attention.
  Provider controls, evidence and schedules are untouched.
- **Minimal content.** Digests carry fixed message text, worker/source IDs,
  times and the runbook reference, not recipients, owner names or provider
  diagnostics. Only short machine-style transport rejection reasons are stored.

### Transport candidate

`structured_log` writes one JSON log line per digest (`severity: ALERT`,
`jsonPayload.watchtower_alert_digest`) and refuses to run outside a Cloud Run
job. On Cloud Run the line becomes a Cloud Logging entry that a separately
approved log-based alerting policy could route to an email channel. Its `sent`
state means the line was handed to the platform log collector. Cloud Logging
removes duplicate insert IDs only at query time, so the transport is not
replay-safe. Log-based policies are rate-limited, which is why delivery sends
one digest per invocation.

Existing hosted notification routing was inspected read-only before choosing
this candidate. It alerts on infrastructure symptoms and does not evaluate
source-level failure, provider backoff, overdue checks, evidence gaps or
recovery. Wiring an automatic evidence source (original worker reports plus
execution receipts) into a scheduled run is not part of this candidate.
Activation details stay in the private owner draft.

### Remaining delivery gates

Synthetic tests with injected transports do not prove delivery. Before
activation: approve the exact digest and alert-policy text and destination,
approve a test delivery, add the evidence-assembly step, deploy through the
normal release process, verify receipt and operator acknowledgement for a
failure and a recovery, then observe five ordinary daily cycles without
increasing provider cadence.
