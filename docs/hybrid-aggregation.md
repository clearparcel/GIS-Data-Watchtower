# Hybrid aggregation

Hybrid deployments may run different source sets from cloud and local workers. Each worker produces a partial result. The aggregation layer merges only the observations present in that partial result and preserves observations produced by other workers.

Each merged source records its worker provenance, and the aggregate state records per-worker check time, counts, and telemetry.

Cloud jobs can set `WATCHTOWER_AGGREGATE_OBJECT=aggregate-state.json` to maintain an aggregate object in the configured storage backend.

For local workers, use the `aggregate` CLI after a local profile run, or integrate the same `merge_states` function with the deployment scheduler.

Aggregation does not bypass provider restrictions: sources rejected from cloud should remain local-only.
