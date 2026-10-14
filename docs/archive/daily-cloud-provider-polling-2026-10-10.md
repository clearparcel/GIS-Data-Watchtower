# Daily Google Cloud provider polling

On October 10, 2026, the user explicitly requested daily Google Cloud provider
polling after approving removal of the legacy GERTKEN-PC daily poller.

## Schedule and execution boundary

- Scheduler: `gis-watchtower-daily-providers`, project `<project-id>`,
  region `us-central1`.
- Schedule: `0 5 * * *`, timezone `America/Chicago`: **5:00 AM Central every day**.
  The timezone follows daylight saving changes; the first scheduled run is
  October 11 at 5:00 AM CDT (10:00 UTC).
- Target: the existing `gis-data-watchtower-staging` Cloud Run Job. Its name
  retains the historical staging label, but it already supplies the private
  aggregate consumed by the production public publisher. No image or storage
  pipeline replacement was needed.
- Authentication: the existing scheduler service account uses OAuth to invoke
  the Cloud Run Jobs v2 `:run` endpoint. Only `roles/run.invoker` on this worker
  job was added; no secret/storage/admin permissions or credentials were added.
- One task per execution, 900-second task timeout, Cloud Run task retries zero.
  Scheduler trigger retries are also zero, with a 60-second API attempt deadline.
  Existing bounded adapter retries and provider stop/backoff controls remain.
- Secret Manager registry version 12 contains 35 sources, all assigned to
  `cloud`. The four county-direct terms holds remain excluded. No provider
  endpoint, source assignment, registry version or compliance rule changed.
- The existing ten-minute sanitized publisher remains separate from provider
  polling. It reads the worker's generation-protected shared aggregate and
  publishes only the approved public projection.

## Activation validation

One manual dispatch through the new Scheduler created
`gis-data-watchtower-staging-27qxp`. This checks the actual
scheduled authentication path. Scheduler logs confirm HTTP 200. Cloud Run
completed successfully at 22:31:43 CDT after provisioning and bounded checks.
The saved report is timestamped **October 10, 22:30:03 CDT**:

- 35/35 sources OK, zero warnings, zero errors; all 35 aggregate observations
  have cloud provenance and the new report time.
- Rice: 28,265 parcels; Beltrami: 41,646 parcels. USDA sources also passed their
  configured adapters. Provider registry and compliance controls were unchanged.
- The worker state and shared aggregate contain the exact configured inventory.
  Individual worker records carry `checked_at`; aggregate merging adds
  `last_report_at` and `last_success_at`. These distinct formats were validated
  against their actual contracts.
- The automatically scheduled publisher execution
  `gis-data-watchtower-public-publisher-vmvmf` completed successfully at
  22:35:47 CDT. Its public snapshot was published at **22:35:40 CDT** and exactly
  matched the sanitized aggregate's source inventory, source results, worker
  records and report time. The live `/api/state` and `/api/summary` reflected
  35 healthy sources and the new clocks; `/healthz` returned HTTP 200.
- The live summary retained derived unique parcel monitoring coverage of
  70/87 counties: 59 statewide, 24 county-direct, 13 overlaps. MN GAC parcel,
  address and road observations all have fresh October 10 observation times.
- Required offline validation passed: 340 tests with ResourceWarning treated
  as an error, compileall, generated status synchronization and diff checks.

The previously documented five-day activation study remains incomplete. The
user's current explicit request authorizes activation now; it does not establish
that the study passed. Retained historical local-worker records are not evidence
of an active local poller. No aggregate worker-history retirement was performed.

## Operation and rollback

Cloud Scheduler reports whether the API accepted dispatch, not whether every
provider check passed. Inspect the Cloud Run execution and saved source-level
report/aggregate after each run. The CLI returns 1 for warning reports and 2 for
error reports even when results are saved; zero exit status alone is not an
end-to-end acceptance check. Publication freshness and provider observation
freshness remain different clocks.

To stop future provider launches without affecting public publication:

```text
gcloud scheduler jobs pause gis-watchtower-daily-providers --project=<project-id> --location=us-central1
```

Pause does not stop an already-dispatched execution. Inspect it separately before
canceling. Removal of this scheduler and the one job-scoped invocation binding
can reverse the configuration change under an approved rollback. Do not
automatically restore the retired local task, change provider controls or erase
historical worker observations.
