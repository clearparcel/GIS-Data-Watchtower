# GIS Data Watchtower processing architecture

## Current deployment

GERTKEN-PC is the authoritative Watchtower processor during the development and validation phase.

The machine performs:

1. source collection and ArcGIS/OGC queries;
2. Watchtower change and QA analysis;
3. local state/history persistence;
4. snapshot generation; and
5. private LAN dashboard serving.

Remote GIS providers still perform query operations that their APIs expose, such as feature counts and server-side statistics. Watchtower interprets and persists the results.

## Portability boundary

New Watchtower processing code should remain portable across Windows and Linux.

### Processing engine

The collection/QA layer must not depend on:

- Windows drive letters;
- Windows Task Scheduler;
- interactive desktop sessions;
- GERTKEN-PC host names;
- local-only secrets; or
- dashboard HTTP state.

Configuration and state locations should be supplied through CLI arguments, configuration, or environment variables.

### Persistence

The current JSON/JSONL state implementation is the local development backend.

The intended boundary is:

- current-state store;
- append-only observation/history store;
- snapshot/export store.

A future hosted implementation can map those roles to object storage and/or a database without rewriting source adapters.

### Dashboard

The dashboard is a consumer of Watchtower state. It should not be the scheduler or authoritative processor.

This separation permits:

- GERTKEN-PC processing + LAN dashboard today;
- scheduled cloud processing + hosted dashboard later;
- static/public dashboard exports without exposing operational state.

## Production migration candidates

### Google Cloud Run — leading target

Strong fit when Watchtower becomes scheduled production infrastructure:

- containerized Python runtime;
- scheduled execution through Cloud Scheduler / job orchestration;
- no requirement to keep a workstation online;
- natural fit with existing ClearParcel Google Cloud infrastructure;
- processing and dashboard can be deployed separately.

Before migration, measure real Watchtower runtime, memory, outbound request volume, history growth, and geometry-QA cost.

### Cloudflare

Potential fit for dashboard/static delivery and lightweight orchestration. Heavy GIS geometry processing should be evaluated against runtime/memory limits before selecting it as the primary processor.

### Small VPS/container host

Viable fallback when predictable always-on execution and filesystem/database control are more important than serverless operation. Carries more patching and operational responsibility.

## Migration gates

Do not migrate merely because the code can run in the cloud. Migrate when:

1. source coverage and QA behavior are stable;
2. processing runtime is measured;
3. history/storage requirements are understood;
4. secrets/configuration are externalized;
5. processing can run unattended;
6. state persistence has a cloud-capable implementation;
7. dashboard authentication/exposure requirements are defined; and
8. estimated hosted cost is justified by 24/7 availability.

## Current decision

Continue processing on GERTKEN-PC while building to the portability boundary above. Treat Google Cloud Run as the leading long-term option, not a hard dependency.
