# Provider-run alerting: separating tool failures from source errors

**Status: approved by the owner on November 3, 2026; implemented, not yet
activated.** No alert policy, job setting or schedule has been changed. Each
activation step below needs owner approval before it touches the hosted
project. Tracked in [Apply the provider-run alerting proposal](https://github.com/clearparcel/GIS-Data-Watchtower/issues/180).

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
a "provider job failed" notification for what may be one source condition.
The source-alert digest ([alert routing](alert-routing.md)) already reports
that condition per source, with incident keys and recovery. Meanwhile:

- a genuine Watchtower failure (exit 3) looks the same as a single county
  error in the inbox;
- a run that never starts, because the scheduler is paused, the job is
  deleted, or dispatch fails, sends nothing. None of the five current policies
  has an absent-run condition.

## Design

The job's exit codes stay unchanged. They're part of the CLI contract, and
`operations-triage.md` and the run receipts rely on them. Routing decides what
is urgent; the job doesn't hide source errors.

Three policies, defined in code in
[`clearparcel/datawatch/alert_policies.py`](../clearparcel/datawatch/alert_policies.py):

| Policy | Condition | Notifies |
| --- | --- | --- |
| Provider tool failure | Log match: provider job, `textPayload:"Container called exit(3)"` | At most hourly |
| Provider run overdue | Log match: publisher job, `severity=ERROR` with `jsonPayload.watchtower_provider_run_overdue` or `jsonPayload.watchtower_provider_watchdog_error` | At most every 6 hours while open |
| Publisher absent | Metric absence: publisher `completed_execution_count` with `result="succeeded"`, 1 hour | Once per incident |

Exit 1 and 2 stay covered by the source-alert digest. Exit 4 is a deliberate
refusal logged as a `WARNING` with `watchtower_dispatch_refused`. The original
policy also caught platform failures that exit with other codes (a task
timeout, an out-of-memory kill, an argument error); once it is retired, those
are reported by the 26-hour overdue alert rather than immediately.

### Why the no-run alert is a watchdog, not a metric-absence condition

The original proposal used a 26-hour metric-absence condition on the provider
job's completed executions. Cloud Monitoring caps a metric-absence duration at
[23.5 hours](https://docs.cloud.google.com/monitoring/alerts/metric-absence),
which is shorter than one daily cycle, so such a condition would open every
day before the next run. Google's long-lookback PromQL alerting could express
26 hours but was a preview feature as of July 2026
([report](https://securitybrief.asia/story/google-cloud-adds-long-lookback-promql-alert-policies)),
so it is not used for the only "nothing ran" alarm.

Instead, the public publisher, which already runs every few minutes and
already reads the private aggregate, runs a **provider-run watchdog**
([`provider_watchdog.py`](../clearparcel/datawatch/provider_watchdog.py)).
When an expected worker's `last_report_at` (or `checked_at`) is older than
`WATCHTOWER_WORKER_STALE_MINUTES` (default 1560, that is 26 hours: one daily
run plus the 23-hour spacing guard and daylight-saving shifts), it writes one
`ERROR` line per overdue worker:

```json
{"severity":"ERROR","watchtower_provider_run_overdue":{"worker":"cloud","threshold_minutes":1560,"reason":"overdue","last_report_at":"…","age_minutes":1601}}
```

`reason` is `overdue`, `missing` (an expected worker is absent from the
aggregate), `no_report_time`, or `clock_skew`. The line carries no URLs,
diagnostics or telemetry. If the watchdog itself fails, it logs
`{"severity":"ERROR","watchtower_provider_watchdog_error":"watchdog_failed"}`,
which the same policy matches, so a broken watchdog never looks healthy. The watchdog never polls a provider, never changes
the publication result, and never raises. Because the watchdog lives in the
publisher, the **publisher absent** policy covers the case where the publisher
itself stops succeeding, or scheduling in the project stops; 1 hour fits well
under the 23.5-hour cap. It counts only successful runs, because a publisher
that fails before the watchdog runs (for example, on an unreadable aggregate)
would otherwise still look alive. Metric-absence conditions ignore deleted
resources, so deleting the publisher job is not detected by this policy.

Watchdog settings on the publisher job:

| Variable | Meaning | Default |
| --- | --- | --- |
| `WATCHTOWER_PROVIDER_WATCHDOG` | `0` turns the watchdog off | on |
| `WATCHTOWER_WATCHDOG_WORKERS` | Comma-separated workers that must report (an empty list falls back to the default) | every current (non-retired) worker in the aggregate |
| `WATCHTOWER_WORKER_STALE_MINUTES` | Staleness window, shared with the dashboards | `1560` |

Set `WATCHTOWER_WATCHDOG_WORKERS=cloud` in production so a historical worker
can never page and a missing cloud worker always does.

## Activation (each step needs owner approval)

Run from the authoritative machine, with deployment identifiers kept in the
private owner notes, never in this repository.

1. **Deploy** the publisher image that contains the watchdog, with
   `WATCHTOWER_WATCHDOG_WORKERS=cloud`. Confirm the next publications log no
   `watchtower_provider_run_overdue` line while the provider is current.
2. **Render** the policies into a private folder outside the repository:

   ```text
   python scripts/render_alert_policies.py --provider-job <provider-job> \
     --publisher-job <publisher-job> \
     --channel projects/<project>/notificationChannels/<id> --output-dir <private-folder>
   ```

   The owner approves the three rendered files: exact filters, durations and
   channel. In Metrics Explorer, confirm that the publisher's
   `completed_execution_count` series carries `result="succeeded"` for its
   normal runs; if the platform uses a different value, change the filter in
   `alert_policies.py` first.
3. **Verify the exit-3 text** against a synthetic tool failure: a one-off
   provider-job execution with an invalid `--config`, which makes no provider
   request. Confirm the system log line reads `Container called exit(3).`; if
   the platform wording differs, change the filter in `alert_policies.py`
   first.
4. **Create** the policies with
   `gcloud monitoring policies create --policy-from-file=<file>` for each file.
5. **Test the overdue alert** with a one-off publisher execution that sets
   `WATCHTOWER_WORKER_STALE_MINUTES=1`. The watchdog logs an overdue line for
   the cloud worker and the overdue policy should email within minutes. This
   makes no provider request; the snapshot it publishes is the ordinary one.
6. **Confirm the exit-3 policy** fires on the step 3 execution (or repeat it).
7. **Retire the old policy**: disable the original "provider job execution did
   not succeed" policy once steps 5 and 6 have both emailed.
8. **Record** the change, the first ordinary provider run after activation, and
   that the Monday after it produced no false alert, in `STATUS.md`.

The publisher-absent policy is not tested by stopping the publisher, because
that would halt public publication. Its filter is checked in review and by
`tests/test_alert_policies.py`.

## Rollback

Re-enable the original execution-failure policy, then disable or delete the
three new policies. To silence the watchdog without a deploy, set
`WATCHTOWER_PROVIDER_WATCHDOG=0` on the publisher job.
