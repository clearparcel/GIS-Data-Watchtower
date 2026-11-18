# GIS Data Watchtower v0.5.4 candidate

This patch candidate contains PR #255:

- An ArcGIS layer source may set `expected_layer_name`. If the provider
  renumbers layers inside a service, the source fails with a clear
  "layer name mismatch" error before any count or completeness query. MnGeo
  swapped the Plan Parcels Open layers 0 and 1 in November 2026.
- The county catalog transfer-limit error now reports a real status and
  names a possible layer renumbering, instead of a garbled HTTP message.
- `opentelemetry-api` is constrained to 1.45.2 (CVE-2026-126360).

Deployment notes: `expected_layer_name` is optional, so existing registry
entries behave as before until it is added.

The candidate was validated with the repository's required test, compile,
current-status and diff checks, and CI passed on all six Windows/Linux Python
combinations, CodeQL and the security check.
