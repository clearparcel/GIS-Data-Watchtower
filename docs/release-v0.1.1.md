# GIS Data Watchtower v0.1.1 release candidate

**Status:** candidate preparation; not tagged, merged, or deployed. The current
production runtime remains `v0.1.0.dev0` until all release gates pass.

## Candidate scope

- Report configured GAC failures in source health while retaining the most
  recent successful quality observation and its timestamp.
- Reject truncated or inconsistent ArcGIS completeness-statistics batches and
  calculate fully populated fields from exact counts.
- Preserve retirement tombstones against delayed reports from reassigned
  workers, persist rotated cloud history, and apply an absolute private HTTP
  request deadline.
- Improve county-map accessibility and public cache/export resilience, and
  clarify schema presence and publication health in the dashboard.
- Generate supply-chain evidence from the built runtime image, constrain local
  setup to the supported runtime, and make the CLI's packaged default
  configuration behavior explicit for wheel installs.
- Split dashboard projections, exports, routes, templates, GAC views, county
  views, and overview/source views into focused modules while retaining
  compatibility entry points.

## Validation and release gates

The required ResourceWarning-strict test suite, `compileall`, current-status
synchronization, and `git diff --check` must pass on the final candidate commit.
The full CI matrix has not yet run for this candidate.

Private staging validation remains required for the aggregation, cloud-history,
and provider-statistics changes. Issue #20's multi-day hybrid validation gate
is still open after the catalog source timed out during the recorded full
staging cycle. Do not change authoritative scheduling before that gate passes.

PostHog remains dormant pending the dedicated project and verified client-IP
discard in Issue #50. Provider terms in Issues #1 and #2 remain unresolved;
the candidate does not authorize expanded monitoring. Fifteen of 87 composed
county profiles currently meet all inventory-category completion criteria.

No release tag, merge, production write, deployment, analytics activation,
provider-term change, or scheduling change is part of this candidate preparation.
