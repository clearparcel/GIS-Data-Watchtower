# GIS Data Watchtower processing architecture

Last reviewed: **2026-10-05**

GIS Data Watchtower is cloud-neutral at the monitoring-engine layer and supports local, cloud, and hybrid execution.

## Components

### Monitoring engine

The Python monitoring engine:

1. selects sources from the configured execution profile;
2. performs bounded ArcGIS/OGC/API checks;
3. validates and compares observations;
4. records source health, changes, telemetry, and alerts; and
5. persists state/history through the configured storage boundary.

The engine must remain portable across Windows and Linux. It must not depend on workstation names, drive letters, interactive sessions, embedded secrets, or dashboard process state.

### Persistence

The supported persistence boundary consists of:

- current state;
- bounded/rotated history;
- alert artifacts;
- optional shared hybrid aggregate state; and
- snapshot/export output.

Local filesystem storage is the default. Google Cloud Storage is optional. Read/modify/write cloud artifacts use storage-generation preconditions; local aggregate publication uses lock-and-replace semantics so stale writers fail rather than silently overwriting newer observations.

### Hybrid aggregation

Cloud and local workers may own different source subsets. Each profiled worker publishes only its observations. The aggregate merger preserves observations from other workers and stamps worker provenance, last-report time, last-success time, counts, and telemetry.

Freshness is separate from source health: an otherwise healthy source can be overdue, and a freshly checked source can be unhealthy.

See [hybrid-aggregation.md](hybrid-aggregation.md) and [hybrid-execution.md](hybrid-execution.md).

### Dashboard and exports

The dashboard is a **consumer of persisted state**, not the authoritative scheduler.

The built-in private dashboard can display local or aggregate state and produce JSON, CSV, and Excel snapshots. ClearParcel also operates a separate read-only public renderer. It reads only the persisted aggregate, reduces it to an explicit public allowlist, and does not expose the private dashboard's provider connections or state-changing controls. HTML refreshes read saved state; they do not poll GIS providers.

Both static-site publication and the hosted public renderer omit detailed change payloads, fingerprints, tracked values, operational provider URLs, provenance details, worker telemetry, and other private diagnostics.

### Minnesota GAC completeness

For a standardized Minnesota parcel layer, the monitoring engine can calculate MN GAC parcel-field population summaries with bounded ArcGIS grouped-statistics requests. The stored observation contains record-weighted statewide field summaries plus per-county counts and percentages; it does not download or republish parcel rows. The private dashboard consumes that stored observation for the `/mngac` interactive county map, county-page field tables, and JSON/CSV/Excel exports.

The computation keeps **field population** separate from **standards compliance**. Conditional, If Available, and Optional fields may legitimately be blank, and counties absent from MnGeo Plan Parcels Open are represented as **No data**, not 0%.

See [mngac-completeness.md](mngac-completeness.md).

## Supported deployment patterns

### Local

A workstation or server runs ordinary unprofiled checks and stores state locally. This remains the simplest deployment.

### Cloud

A Cloud Run Job can execute a cloud profile and persist state in GCS. Secret/runtime source configuration is supplied outside the public repository.

### Hybrid

The validated ClearParcel staging pattern is:

```text
Cloud worker (cloud profile)
              \
               -> shared aggregate -> dashboard / exports
              /
Local worker (local profile)
```

This supports providers that permit cloud egress alongside providers that must remain local. It is not a mechanism for bypassing provider network restrictions.

## Current validated posture

As of 2026-10-05:

- the public package and container pass Windows/Linux CI;
- a private Cloud Run staging worker successfully checks 22 cloud-profile sources;
- a local worker successfully checks 4 provider-restricted sources;
- the unified aggregate has been validated at 26/26 healthy observations with no unassigned sources;
- the private hosted dashboard consumes the shared aggregate behind its authentication boundary;
- a separate read-only Google Cloud public dashboard consumes a sanitized projection of that same aggregate at `gis-watchtower.clear-parcel.com`;
- JSON, CSV, and Excel statewide exports contain the complete aggregate source set;
- Cloud Run startup/provisioning may take several minutes before the container reaches Started; see [google-cloud-deployment.md](google-cloud-deployment.md);
- Cloud Scheduler is intentionally not enabled for the staging deployment;
- the existing local production schedule remains authoritative while the multi-day parallel validation gate is open.

## Production migration gate

A production orchestration change should occur only after:

1. multiple parallel validation cycles retain the complete expected aggregate;
2. no unresolved status/count/schema parity differences remain;
3. worker/source freshness behaves correctly at the intended cadence;
4. concurrency protection preserves all writers under overlap;
5. dashboard and exports remain complete;
6. provider-use constraints remain satisfied; and
7. the operator explicitly approves any production scheduling change.

Cloud Run is a validated execution target, not a dependency of the core package.
