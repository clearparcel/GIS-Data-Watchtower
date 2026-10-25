# Provider-run alerting: separating tool failures from source errors (proposal)

**Status: proposal, not applied.** Drafted October 24, 2026 after the
October 24 audit. No alert policy, job setting or schedule has been changed.
Each step below needs owner approval before it touches the hosted project.

## Why

The provider job's exit code reports the *fleet* result
([exit codes](configuration.md#exit-codes)): 0 ok, 1 any warning, 2 any source
error or an empty run, 3 Watchtower itself failed, 4 refused by run spacing.
Cloud Run marks every non-zero exit as a failed execution, and the existing
policy that "emails the existing alert channel when a provider job execution
does not succeed" ([v0.3.3 record](release-v0.3.3.md)) fires on all of them.

From October 20 to 24, all five daily 05:00 runs exited 2. That is
consistent with the single county source error shown publicly at the time,
not with a crash. Under the current policy, each of those runs would trigger
a "provider job failed" notification for what may be one source condition
(mailbox receipt was not verified). The source-alert digest
([alert routing](alert-routing.md)) already reports that condition per source,
with incident keys and recovery. Meanwhile:

- a genuine Watchtower failure (exit 3) looks the same as a single county
  error in the inbox;
- a run that never starts, because the scheduler is paused, the job is
  deleted, or dispatch fails, sends nothing. None of the five current policies
  has an absent-run condition.

## Proposed changes

1. **Alert on tool failure only (exit 3).** Replace or narrow the
   execution-failure condition to a log-based condition on the provider job's
   own container exit, for example:

   ```text
   resource.type="cloud_run_job"
   resource.labels.job_name="<provider-job>"
   textPayload:"Container called exit(3)"
   ```

   Verify the exact system log text against one recorded exit-3 execution
   before relying on it. Exit 1 and 2 stay covered by the source-alert digest.
   Exit 4 is a deliberate refusal and is logged as a `WARNING` with
   `watchtower_dispatch_refused`, so it can get its own low-urgency condition
   if wanted.
2. **Alert when no provider run completes.** Add a metric-absence condition on
   `run.googleapis.com/job/completed_execution_count` for the provider job,
   with a 26-hour duration. That window covers one daily run plus the
   23-hour spacing guard and daylight-saving shifts. It fires when the
   scheduler, dispatch or job stops producing runs, independent of their
   outcome.
3. **Keep the job's exit codes unchanged.** They're part of the CLI contract,
   and `operations-triage.md` and the run receipts rely on them.
   Routing decides what is urgent; the job doesn't hide source errors.

## Acceptance before activation

- Draft both conditions with placeholders in the private owner notes, and
  have the owner approve the exact filters, durations and channel.
- Confirm the exit-3 filter matches a synthetic tool-failure execution, for
  example a one-off execution with an invalid `--config`. That makes no
  provider request.
- Confirm the absence condition opens in a test project or with a shortened
  duration, then restore the 26-hour duration.
- Record the change, its rollback (re-enable the original execution-failure
  condition), and the first ordinary run after activation in a release or
  status record.
