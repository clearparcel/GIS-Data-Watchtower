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
| `superseded` | Queued or retrying when a recovery for the same worker/source was accepted; never sent. |
| `acknowledged` | An operator recorded review of a sent, ambiguous or expired event. |

### Delivery rules

- **Idempotency.** The preview `event_key` is the ledger key. A known key is
  never queued again, so repeated runs of one unresolved source failure,
  replays of the same input, and an acknowledged but continuing incident send
  nothing new. Evidence-gap keys bind the latest execution, so a gap that
  persists across runs produces one alert per affected run.
- **Current evidence only.** Enabled delivery judges freshness at the delivery
  clock, not at `--as-of`, and refuses an `--as-of` more than two minutes ahead
  of the clock or older than `max_age_hours`. Old evidence therefore appears as
  overdue, never as a fresh failure or recovery.
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
  before it passes. A `Retry-After` longer than `max_queue_age_hours` is
  treated as a definitive rejection (`exhausted`, operator attention).
  Retries never trigger a provider check.
- **Incident reopening.** Accepting a recovery marks earlier events for the
  same worker/source `resolved_by`; queued or retrying ones become
  `superseded`, so a failure never arrives after its recovery. Ambiguous ones
  stay for reconciliation, and `requeue` is refused once a recovery closed the
  incident. A later failure has a new preview key and is a new incident.
  Incident order follows provider check times (`checked_at`), not arrival
  order: a failure checked no later than an accepted recovery is recorded and
  superseded (a delayed caller cannot reopen a closed incident), and a
  recovery checked before an accepted failure is recorded and superseded
  rather than sent after it. Events without a check time keep the
  arrival-order behavior.
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

### Scheduled run evidence

With `WATCHTOWER_RUN_RECEIPTS=1`, every `cloud-job` run (including one that
fails with exit 3) appends an execution receipt to the private object
`runs/receipts.json` using the same compare-and-swap storage as the job. A
receipt holds the worker, the Cloud Run execution id, start and end times, the
process exit code and a minimized copy of the original worker report: per
source only status, check time, rate-limit and backoff flags. URLs,
diagnostics, values and telemetry are dropped. The execution id includes the
Cloud Run task index and attempt, so a retried attempt is its own receipt. The
newest 30 receipts per worker are kept. An older receipt that opened a
still-unresolved incident is kept too, reduced to just that incident's
sources, so a long incident keeps one event key without stitching other
sources' old states onto recent runs.

Delivery uses a clean history that only moves forward in recording order:
a receipt is used only if it starts after every receipt recorded before it
ends. A run that overlaps, or was recorded after a newer run (a manual run, an
extra task, a late append), is excluded permanently so incident keys never
shift, and receipts with malformed times are excluded too; exclusions are
counted in the log line. Receipts are refused at recording time, and ignored
if already stored, when they end in the future, run longer than 12 hours, or
end before they start, so one bad clock cannot hold delivery; keep the job's
task timeout under 12 hours so a genuine run always gets a receipt. When the
current run is out of order, delivery is held and a warning is logged instead
of risking a duplicate. A worker with no expected sources skips delivery.

If `WATCHTOWER_ALERT_DELIVERY_CONFIG` is also set, the delivery stage runs over
those receipts. The expected scope is derived from the registry with the
worker's own rules, so disabled, other-profile, hold-for-terms,
awaiting-permission and stop-requested sources are excluded automatically. The stage writes one structured log line per run
(`watchtower_alert_delivery` counts, or `watchtower_alert_pipeline_error` on a
failure). Neither stage polls a provider, changes the job's exit code, or
raises into the job; a failure is only logged.

### Synthetic delivery test

`watchtower alert-test --kind failure|recovery --confirm-test-send` sends one
real, clearly labeled test digest (subject prefixed `TEST - `) through the
configured transport for the reserved source `alert-delivery-test`. It never
polls a provider, reads no source registry, and records only in its own
`alerts/test-delivery-ledger.json`, leaving production receipts, ledger and
incident keys untouched. Routing comes from `WATCHTOWER_ALERT_DELIVERY_CONFIG`;
the transport is used even while `delivery.enabled` is false, which is why
the explicit confirmation flag is required. On Cloud Run it is run as a
one-off execution of the provider job with only the arguments overridden, so
the log-based alert policy sees it as that job.

### Remaining delivery gates

Synthetic tests with injected transports do not prove delivery. Before
activation: approve the exact digest and alert-policy text and destination,
approve setting the two environment variables on the provider job (first with
`delivery.enabled` false for a logged dry run), approve a test delivery, deploy
through the normal release process, verify receipt and operator
acknowledgement for a failure and a recovery, then observe five ordinary daily
cycles without increasing provider cadence.
