# Disabled alert delivery candidate

Implementer: Claude, October 20, 2026, on GERTKEN-PC.
Branch: `claude/alert-delivery-candidate-20261020`.
Base: `1c3b3ed62389c36c3d2e61db60715509cb430076` (merged PR #112).
PR #114 (status/handoff corrections) was still open and unmerged at start;
this branch does not depend on it.

Objective: turn the merged offline preview into a disabled-by-default delivery
candidate with durable accepted/sent/acknowledged state, idempotency,
ambiguous-outcome handling, bounded retries, incident reopening and rollback,
tested only with injected transports and synthetic evidence.

## Read-only inspection before choosing a transport

The repository had no notification transport. Hosted notification routing was
listed read-only (channel types, policy names and condition filters; no
addresses copied into Git). It alerts on infrastructure symptoms only and
does not evaluate source-level failure, provider backoff, overdue checks,
evidence gaps or recovery. Cloud Logging documentation states that insert-ID
duplicates are removed only at query time, and log-based alerting policies are
rate-limited. Consequences adopted in the design: one digest per invocation,
and ambiguous outcomes are held for operator reconciliation instead of resent.

## Changes

- `clearparcel/datawatch/alert_delivery.py`: ledger over the existing
  version-conditional storage backends (local file lock + hash CAS, or GCS
  generation preconditions); states `queued`, `sending`, `sent`,
  `retry_wait`, `exhausted`, `ambiguous`, `expired`, `superseded`,
  `acknowledged`;
  `acknowledge`, `reconcile`, `ledger_status`; a `structured_log` transport
  that refuses to run outside a Cloud Run job and is not replay-safe.
- `scripts/deliver_alerts.py`: `deliver` (dry run unless an enabled private
  configuration names a transport), `status`, `acknowledge`, `reconcile`.
- `tests/test_alert_delivery.py`: 44 synthetic tests.
- Runbook, README and STATUS/current-status updates.

The merged preview and triage logic are reused unchanged.

## Validation on GERTKEN-PC

Python 3.12.10, Node v24.19.0, `WATCHTOWER_REQUIRE_NODE=1`:

- `python -W error::ResourceWarning -m unittest discover -s tests -q`:
  637 tests passed; 3 skipped (two POSIX permission-bit tests and one POSIX
  directory-fsync test). Exact timing is recorded in the PR.
- `python -m compileall -q clearparcel tests scripts`: passed.
- `python scripts/sync_current_status.py --check`: passed.
- `git diff --check` (staged and unstaged): passed.

Synthetic coverage: source failure and warning; provider rate limit and
backoff; overdue checks; missing, partial and malformed reports; stale versus
fresh recovery; repeated incidents and replays; recovery resolution and
reopening; four concurrent invocations; an injected competing writer;
persistent storage conflicts; malformed ledgers; transport 429 with
`Retry-After`, exponential backoff and attempt exhaustion; definitive
rejection; ambiguous outcomes, reconciliation and requeue; replay-safe
transports; interrupted delivery and lease expiry; late outcomes after a sweep;
digest size limits; acknowledgement; routing gaps; rollback and stale-queue
expiry; CLI fail-closed behavior; diagnostic minimization.

## Bounded review

Claude (separate reviewer context, read-only, local synthetic checkout, no
network) reviewed the pinned diff `1c3b3ed..0cca217` (tree `1d07b8f5`).
Findings and fixes in the follow-up commit:

- High: a queued alert for a still-failing source could expire silently.
  Now re-dated while still current; stale expiry needs operator attention.
- Medium: a failure waiting to retry could arrive after its recovery. Now
  `superseded` when the recovery is accepted.
- Medium: transport `Retry-After` applied per event. Now ledger-wide.
- Medium: replayed old evidence could be delivered as current. Enabled
  delivery now requires `as_of` within `max_age_hours` before the clock.
- Low: a claim write that landed but reported a conflict stranded the claim.
  The retry now recognizes its own claim.
- Notes addressed: `--ledger-root` is used exactly; incomplete ledger records
  fail closed; owner labels and free-text rejection reasons stay out of
  digests and the ledger; runbook idempotency wording corrected for
  per-execution evidence-gap keys. Added generation-token storage,
  outcome-write failure and replay-safe attempt-limit tests.

A follow-up bounded review of the fix commit `ed8fee8` (tree `59e92489`)
confirmed those fixes and found four more, addressed in a third commit:
freshness is now judged at the delivery clock rather than `--as-of`; an
oversized `Retry-After` is treated as a definitive rejection instead of
overflowing or silencing delivery; `requeue` is refused once a recovery has
closed the incident, and ambiguous records are no longer superseded; and
`--as-of` may lead the clock by up to two minutes.

A final bounded verification of `e40453f` (tree `80e008e4`) confirmed those
four fixes and found two low-severity edge cases, fixed in a fourth commit:
a replay-safe transport no longer replays an ambiguous failure that a recovery
closed, and duration settings are bounded to 30 days so no computed delay can
overflow.

## Not done

No message was sent. No route, alert policy, IAM binding, schedule, job,
secret or production configuration changed, and no provider was polled.
Automatic evidence assembly for a scheduled run is not implemented. Live
delivery, acknowledgement, and five ordinary daily cycles remain open.

## Shared context

Memory `gis-data-watchtower` read at published revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`; the
published branch carried the same blob. It remains historical `needs-review`
(updated October 13, review due October 14) and does not establish current
state. No conflicts with current evidence.

## Next gate

Bounded independent review of the pinned diff, then publication as a PR.
Activation needs separate owner approvals for the exact digest and policy
text, a test delivery, the evidence-assembly change, deployment and the alert
policy. The private activation draft is kept outside public Git.
