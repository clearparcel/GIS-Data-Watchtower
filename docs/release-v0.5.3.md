# GIS Data Watchtower v0.5.3 candidate

This patch candidate contains the November 12, 2026 repository review fixes
(PRs #239 through #248, merged via #239 and #249):

- A `not-appropriate` county parcel decision now blocks every county-direct
  parcel source, not only editor-enrolled ones (F01).
- OGC `ExceptionReport`/`ServiceExceptionReport` capabilities responses are
  source errors; empty capabilities are warnings; WMS layer names come only
  from `Layer/Name` (F02, F09).
- The modern `gac_completeness` parcel result counts toward county coverage
  and status (F04).
- Enabled registry sources must have a name, URL and adapter or kind, or the
  run stops before any provider request (F05).
- The password-free loopback dashboard accepts only a local `Host` header (F06).
- Editor upload and retry scans wait at most 60% of the request deadline and
  finish in the background (F07).
- Editor validation highlights the failing monitoring method (F10).
- The public page reloads when county reporting or health changes, not only
  when content changes (F03).
- County PDFs show the cache warning on every page, monitoring status and
  per-standard observation dates (F08).
- Release, alerting and readiness documentation reflects the current state
  (F11 documentation, F12).

Deployment notes: after deployment, county-direct parcel sources in the 18
`not-appropriate` counties are skipped, and each WMS source may report one
schema-change warning as its layer inventory is re-read.

The candidate was validated locally with the repository's required test,
compile, status-sync and diff checks. It has not been deployed. Hosted CI,
staging and production promotion evidence will be recorded after those steps
are completed.
