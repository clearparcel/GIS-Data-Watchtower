# GIS Data Watchtower v0.5.9

Candidate, not yet deployed. This patch release contains the fixes from the
fifth review of v0.5.8 (`395e3cf`), merged through PR #282:

- **Publication integrity:**
  - A stored source or worker record with an unreadable or future time no
    longer stalls the fleet: the publisher keeps its last published version and
    reports it under `clock_quarantine` (V01).
  - A stored future heartbeat no longer blocks retiring an inactive worker (V02).
  - A zero-attempt deferral never reinstates a retired source (V03).
  - An unreadable source `checked_at` is refused at the private write, and a
    rebuilt deferral keeps the published measurement (V04).
  - Last success and availability times no longer depend on report arrival
    order (V05).
  - A worker name with surrounding whitespace is refused consistently (V06).
- **Provider checks:**
  - Participation rows without a county identifier or with an unreadable flag
    fail the check and keep the last valid measurement (V07).
  - The grouped-total check counts every returned group (V08).
  - Recognized completeness settings are validated before any request (V09).
  - Layer URLs with a query string build child requests from the parsed path
    (V10).
  - Extents in different spatial references are an informational change, and
    impossible bounds are unmeasured (V11).
- **Operations:** the weekly digest reads ISO catalog acquisition dates (V12)
  and refuses a future-dated aggregate (V13).

Deployment notes:

- **Private registry:** no `gac_completeness` or `mngac_completeness` object
  has an invalid recognized field.
- **Stored aggregate:** no source `worker` carries surrounding whitespace.
