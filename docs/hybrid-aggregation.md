# Hybrid aggregation

Hybrid deployments may run different source sets from cloud and local workers. Each worker produces a timestamped result. Reports require a valid `generated_at`; a report no newer than that worker's accepted heartbeat is ignored. Source observations newer than an incoming report remain intact, including shared IDs checked by another worker. Fleet time never moves backward.

A complete `scope.type=fleet` report retires omitted sources owned by that worker, provided their observation is not newer than the report. Filtered `scope.type=source` and legacy reports without scope remain additive. A filtered check does not establish a complete inventory; retirement occurs on the next complete report. Other workers' observations remain intact.

Retirement tombstones also apply across worker identities: an incoming source observation at or before `retired_at` is ignored, even when its worker has no newer heartbeat. This keeps the private aggregate and the public publisher's anti-resurrection check consistent when a source ID is reassigned or a delayed worker report arrives.

Each merged source records its worker provenance, last report time, and last successful observation time. Aggregate state also records per-worker check time, last-success time, counts, and telemetry.

## Safe concurrent publishing

Shared aggregate writes use compare-and-swap semantics. Google Cloud Storage deployments use object-generation preconditions. Local filesystem deployments use an OS-owned lock plus a unique temporary file and atomic replacement, verifying that the object has not changed since it was read. The lock file persists; the lock itself is released on descriptor closure or process termination. A conflicting writer reloads the latest aggregate, merges again, and retries. Aggregate scratch is unique per invocation and removed on success or failure. Custom storage backends must implement atomic conditional uploads; the base backend fails closed.

The local backend requires a filesystem that supports Windows byte locks or POSIX `flock` and atomic replacement. Verify these guarantees before using a network/shared filesystem. All writers of shared objects must use conditional uploads.

Cloud jobs persist the bounded two-generation history as `history.jsonl` and `history.jsonl.1`. The rotated archive has its own object generation precondition. A conflict on either history object fails the job rather than uploading stale history. Retention is intentionally limited to the active file and one archive; operators should export older history before raising the local rotation limit.

Set `WATCHTOWER_AGGREGATE_OBJECT` (or deployment-specific `aggregate_object`) to opt into publishing. Storage remains cloud-neutral: local filesystem is the default backend and GCS is optional.

A normal profiled check can publish directly. For example, a deployment configured with shared aggregate storage can run the local execution profile through the standard `check` command; no copy/merge/upload wrapper is required. Provider-specific source assignment remains private deployment configuration.

## Freshness

Freshness is deliberately separate from source health. Reporting freshness prefers `last_report_at`, then `checked_at`, with `last_success_at` as a legacy fallback. A recent failed check remains current while its health is unhealthy and its historical source success timestamp remains unchanged. The worker `last_success_at` is a successful report-publication heartbeat, including reports of source failures; it is not evidence that all providers succeeded. A source can be healthy but stale because it has not been checked recently; a source can also be freshly checked and unhealthy. Deployments may set `worker_stale_minutes` and `source_stale_minutes` in configuration. The dashboard uses 1560 minutes (26 hours) for either threshold when no override is supplied, which allows for the project's documented daily check cadence plus a margin before flagging a source or worker as overdue. Deployments that check more frequently (for example, a tighter hybrid schedule) should set lower thresholds to get an earlier staleness signal.

The private dashboard prefers `aggregate_state_file` when configured, otherwise it reads the ordinary local state file. Timestamps are shown in America/Chicago time first with UTC second. Unified statewide JSON, CSV, and Excel exports are generated from the aggregate source set and include worker and freshness metadata. The statewide CSV is source-oriented so non-county sources are not lost; county-specific exports retain their county-oriented shape.

Aggregation never bypasses provider restrictions. Sources that are unsuitable for cloud execution must remain assigned to an appropriate local profile. Do not disable TLS verification or work around provider access controls.

## Deployment validation

As of 2026-10-05, the hardened aggregation path had been validated with a real hybrid staging cycle containing 26 sources: 22 refreshed by the cloud worker and 4 refreshed by the local worker. The resulting aggregate reported 26 healthy sources, 0 unassigned observations, complete JSON/CSV/Excel exports, per-source worker provenance, and per-worker telemetry.

On 2026-10-06, the same path was validated after adding nine approved county-direct parcel sources to private staging. The cloud profile completed **31/31 OK**, the local profile completed **4/4 OK**, and a generation-protected merge produced **35/35 OK** with worker provenance preserved. The resulting county coverage model is **70/87 actively checked** (59 MnGeo, 24 county-direct, 13 overlap). The remaining release gate is multi-day parallel observation; authoritative provider scheduling changes still require explicit approval.

Public snapshot publication uses a unique temporary directory beneath the configured workdir for each invocation. Downloaded private aggregates and sanitized scratch files are removed on success and failure. The environment publisher constructs two GCS clients using the same process application default credentials; separate deployment service identities are configured outside this function.

Publication also uses destination compare-and-swap, retrying up to eight conflicts. Older fleet, worker or retained-source timestamps cannot replace the current public snapshot. An unchanged observation may be republished to renew publication freshness without implying a provider check. Skips return `published=false` and `reason=superseded`. Publication timestamps never move backward. See [follow-up fixes and upgrade procedure](review-fixes-2026-10-06.md).

## Observation receipts

[Offline hybrid receipts](watchtower-remediation-2026-10-07.md#hybrid-candidate-and-validation-preparation) compare already captured reports, aggregate, and sanitized snapshot. Catalog retained-payload time and GAC metric time survive public projection; publication-only updates remain distinct from provider observations. CAS and worker/source ordering behavior remain unchanged.

Receipts require reports and active worker entries only for execution profiles
with assigned sources. A cloud-only candidate needs no empty local report or
heartbeat. Its aggregate and public snapshot must contain exactly the active
worker inventory; inactive-profile reports and an empty candidate cannot pass. Runtime identity, complete
source inventory, provenance and observation checks still apply. A passing
receipt does not authorize activation or scheduling.

## Explicit worker retirement

Changing profile assignments does not remove a worker from retained state. Once
fresh observations have moved every source away from a worker, prepare an
offline retirement using a timestamp later than the aggregate and that worker's
retained clocks:

```text
watchtower worker-retire --base captured-aggregate.json --worker local --at 2026-10-09T12:00:00Z --output proposed-aggregate.json
```

Choose the actual reviewed retirement time; the example is not an operational
instruction. This command reads and writes local files only, without loading a
provider registry. It refuses retirement while any source observation belongs
to that worker. History is archived under `retired_workers`, and all source
observations remain intact. Retired workers no longer count as active or stale.
Older delayed reports are ignored; subsequent reports from the retired identity
are rejected. Reactivation requires a separately reviewed recovery procedure.

The `publish_worker_retirement` storage utility uses generation-protected CAS
and rechecks the latest source ownership after each conflict. Publish only under
explicit operational-write approval; never upload an offline proposal over a
newer aggregate. The public publisher retains sanitized retirement history and
rejects removal without a newer tombstone or resurrection of a retired worker.
No deployed aggregate has been retired as part of this repository change.
