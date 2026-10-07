# GIS Data Watchtower processing architecture

Last reviewed: **2026-10-06**

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

Reporting freshness prefers last_report_at, then checked_at, then legacy last_success_at. A fresh failed report is current and unhealthy; historical source success remains separate. Worker last_success_at records successful report publication even when sources fail.

See [hybrid-aggregation.md](hybrid-aggregation.md) and [hybrid-execution.md](hybrid-execution.md).

### Dashboard and exports

The dashboard is a **consumer of persisted state**, not the authoritative scheduler.

The built-in private dashboard can display local or aggregate state and produce JSON, CSV, and Excel snapshots. ClearParcel also operates a separate read-only public renderer. It reads only the sanitized public aggregate produced by a separate allowlist publisher, and does not expose the private dashboard's provider connections or state-changing controls. HTML refreshes read saved state; they do not poll GIS providers.

Typed anonymous-state projection lives in `public_projection.py`, shared by
publication and public rendering. Snapshot CSV and Excel builders live in
`dashboard_exports.py`; the dashboard module re-exports their existing helper
names for compatibility. Private/public page shells and the refresh script live
in `dashboard_templates.py`, with their dashboard helper names also preserved.
The shared snapshot JSON, CSV, and Excel routes use `dashboard_routes.py`;
private authentication and public cache behavior stay in their respective
servers. GAC standard and county renderers live in `dashboard_gac.py`. County
index and detail views live in `dashboard_counties.py`, and the overview and
source detail views live in `dashboard_views.py`. `dashboard.py` preserves their
compatibility wrappers and shared county profile and state helpers.

Both static-site publication and the hosted public renderer omit detailed change payloads, fingerprints, tracked values, operational provider URLs, provenance details, worker telemetry, and other private diagnostics.

### Minnesota GAC completeness

For a standardized Minnesota parcel layer, the monitoring engine can calculate MN GAC parcel-field population summaries with bounded ArcGIS grouped-statistics requests. The stored observation contains record-weighted statewide field summaries plus per-county counts and percentages; it does not download or republish parcel rows. The private dashboard consumes that stored observation for the `/mngac` interactive county map, county-page field tables, and JSON/CSV/Excel exports.

Configured GAC query failures affect source health even when layer metadata is
available. Truncated grouped statistics and inconsistent batch denominators
are rejected. The latest failed check is reported separately, while the most
recent successful quality observation remains available with its own timestamp.

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

Latest recorded validation on 2026-10-06 passed 31 cloud and four local sources (35 healthy aggregate observations with provenance). Earlier 22-cloud/26-total evidence is historical. The public service reads the sanitized object; provider polling remains separate from the 10-minute publisher cadence. Authoritative cloud provider scheduling remains disabled pending the multi-day gate. See [current status](current-status.md) and [deployment evidence](google-cloud-deployment.md).

Repository-review transport, reporting and publisher changes are not deployed. Redirects remain disabled by default; protected hops bind validated addresses while retaining original Host/TLS identity and reject effective proxies. HTTP 429 stops source requests/retries, including optional QA. Overall provider deadlines and bounded public socket deadlines limit stalled I/O; they do not cancel CPU computation. Publisher invocations use unique temporary directories, cleaned on success/failure; both storage clients share process ADC. See [configuration](configuration.md), [public hosting](public-dashboard-hosting.md) and [review limitations](repository-review-2026-10-06.md).

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
