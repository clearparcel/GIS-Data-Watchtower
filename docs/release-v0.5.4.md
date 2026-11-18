# GIS Data Watchtower v0.5.4

Deployed November 18, 2026. Built from merged source commit
`95a454e11940dc03e0754a911b1fb27869a2b665`, merged through PR #256.

This patch release contains PR #255:

- An ArcGIS layer source may set `expected_layer_name`. If the provider
  renumbers layers inside a service, the source fails with a clear
  "layer name mismatch" error before any count or completeness query. MnGeo
  swapped the Plan Parcels Open layers 0 and 1 in November 2026.
- The county catalog transfer-limit error now reports a real status and
  names a possible layer renumbering, instead of a garbled HTTP message.
- `opentelemetry-api` is constrained to 1.45.2 (CVE-2026-126360).

Deployment notes: `expected_layer_name` is optional, so existing registry
entries behave as before until it is added. The MnGeo layer swap itself was
corrected in the private registry on November 17, separately from this
release; both statewide MnGeo sources recovered on the November 18 run.

## Validation and promotion

- PRs #255 and #256 passed all six Windows/Linux Python combinations, CodeQL
  and the security check. Local validation passed the required test, compile,
  current-status and diff checks.
- The release-version preflight confirmed the live v0.5.3 and the v0.5.4
  candidate. The immutable image passed 224 installed-image tests, and its
  installed identity and source hashes matched the reviewed commit.
- The private registry check passed before rollout.
- The staging county services were updated first, and their runtime settings,
  access controls and IAM were preserved. Synthetic staging-storage validation
  passed: audit replay, public privacy, bounded attachment metadata reads and
  hash-verified downloads. The synthetic objects were removed afterward.
- Production candidate revisions were verified ready with no traffic before
  promotion. The public dashboard, internal dashboard, county editor, regular
  cloud worker and public publisher now use v0.5.4. The public site returned
  HTTP 200 and displayed v0.5.4, and its health, county directory, county page
  and export checks passed.
- All 25 source observations and the worker provenance matched the
  pre-release aggregate, and 87 county profiles remain available. Runtime
  settings, IAM and scheduler configuration were unchanged. No production
  errors were logged after promotion.
- No provider job or publisher run was started manually, and no schedule was
  changed. The scanner and weekly digest images were outside this release.
  Previous revisions and images remain the rollback targets. Detailed
  deployment identifiers remain in the private deployment record.
