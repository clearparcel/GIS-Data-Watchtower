# Scheduled run evidence and delivery stage (disabled)

Implementer: Claude, October 20, 2026, on GERTKEN-PC.
Branch: `claude/run-evidence-20261020`, stacked on PR #115
(`claude/alert-delivery-candidate-20261020`, head `5bb3e3b`). Main remained
`1c3b3ed`; PRs #114 and #115 were open and unmerged.

Objective: close the evidence gap behind WT-15 and alert delivery. A provider
run's process exit code and original worker report were never persisted
together, so triage and delivery relied on operator-assembled inputs.

## Changes

- `clearparcel/datawatch/run_evidence.py`: minimized execution receipts in a
  bounded compare-and-swap object (`runs/receipts.json`, 30 per worker);
  registry-derived expected scope using the worker's own profile, enablement
  and hold-for-terms rules; an optional delivery stage over the receipts. It
  never raises into the job and never changes the exit code; failures are one
  structured log line.
- `clearparcel/datawatch/cli.py`: `cloud-job` records a receipt after success
  or failure when `WATCHTOWER_RUN_RECEIPTS=1`.
- `clearparcel/datawatch/cloud_job.py`: `job_storage` and `job_profile`
  helpers shared with the evidence stage (behavior unchanged).
- `clearparcel/datawatch/alert_delivery.py`: transport registry moved here
  from the CLI script.
- `tests/test_run_evidence.py`: 23 synthetic tests (no provider calls; the
  cloud job is patched).
- Runbook, configuration reference and STATUS updates.

## Bounded review

Claude (separate read-only reviewer context, local synthetic checkout) reviewed
the staged slice (tree `7b00322e`) and found: high, one overlapping or late
receipt made triage refuse every later delivery for about 30 runs; medium,
trimming re-keyed long incidents daily; medium, retried task attempts reused
the execution id; low, an empty expected scope and malformed stored times
caused repeated stage failures. Fixed: delivery uses a clean non-overlapping
history and reports exclusions; trimming keeps each unresolved incident's
opening receipt; ids include the task attempt; empty scope is skipped and
malformed rows are excluded. Regression tests cover each case.

The verification pass found that a protected old receipt still carried other
sources' history, so a reopened incident's recovery could reuse an old key
and be dropped (high), and that an overlapping run could re-key an open
incident once (low). Protected receipts are now reduced to the sources whose
incident they opened, and the history only moves forward in recording
order: an overlapping or late-recorded run is excluded permanently and, when
it is the current run, holds delivery with a warning.
A final pass found a far-future receipt could hold delivery indefinitely;
receipts with future ends, runs over 12 hours or reversed times are now
refused at recording and ignored if already stored.

## Not done

No environment variable, secret, job, schedule, policy or IAM binding was
changed and no message was sent. Activation steps and approvals are in the
runbook's remaining gates.

## Shared context

Memory `gis-data-watchtower` at published revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`
(historical `needs-review`; no conflicts).
