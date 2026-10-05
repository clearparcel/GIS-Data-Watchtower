# Hybrid aggregation

Hybrid deployments may run different source sets from cloud and local workers. Each worker produces a partial result. The aggregation layer merges only the observations present in that partial result and preserves observations produced by other workers.

Each merged source records its worker provenance, last report time, and last successful observation time. Aggregate state also records per-worker check time, last-success time, counts, and telemetry.

## Safe concurrent publishing

Shared aggregate writes use compare-and-swap semantics. Google Cloud Storage deployments use object-generation preconditions. Local/shared-filesystem deployments use a short-lived lock plus an atomic replacement and verify that the object has not changed since it was read. A conflicting writer reloads the latest aggregate, merges again, and retries. This prevents a cloud and local worker finishing at nearly the same time from silently deleting one another's observations.

Set `WATCHTOWER_AGGREGATE_OBJECT` (or deployment-specific `aggregate_object`) to opt into publishing. Storage remains cloud-neutral: local filesystem is the default backend and GCS is optional.

A normal profiled check can publish directly. For example, a deployment configured with shared aggregate storage can run the local execution profile through the standard `check` command; no copy/merge/upload wrapper is required. Provider-specific source assignment remains private deployment configuration.

## Freshness

Freshness is deliberately separate from source health. A source can be healthy but stale because it has not been checked recently; a source can also be freshly checked and unhealthy. Deployments may set `worker_stale_minutes` and `source_stale_minutes` in configuration. The dashboard uses 1560 minutes (26 hours) for either threshold when no override is supplied, which allows for the project's documented daily check cadence plus a margin before flagging a source or worker as overdue. Deployments that check more frequently (for example, a tighter hybrid schedule) should set lower thresholds to get an earlier staleness signal.

The private dashboard prefers `aggregate_state_file` when configured, otherwise it reads the ordinary local state file. Timestamps are shown in America/Chicago time first with UTC second. Unified statewide JSON, CSV, and Excel exports are generated from the aggregate source set and include worker and freshness metadata. The statewide CSV is source-oriented so non-county sources are not lost; county-specific exports retain their county-oriented shape.

Aggregation never bypasses provider restrictions. Sources that are unsuitable for cloud execution must remain assigned to an appropriate local profile. Do not disable TLS verification or work around provider access controls.

## Deployment validation

As of 2026-10-05, the hardened aggregation path has been validated with a real hybrid staging cycle containing 26 sources: 22 refreshed by the cloud worker and 4 refreshed by the local worker. The resulting aggregate reported 26 healthy sources, 0 unassigned observations, complete JSON/CSV/Excel exports, per-source worker provenance, and per-worker telemetry. The remaining release gate is multi-day parallel observation; production scheduling changes still require explicit approval.
