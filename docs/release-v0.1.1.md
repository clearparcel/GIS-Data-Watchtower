# GIS Data Watchtower v0.1.1 release candidate

**Status:** merged as `main` commit
`8099ee18ec48714b33a9e998b414ea9ee0cf7d8e`; not tagged or deployed to
production. The production runtime remains `v0.1.0.dev0` until all release
gates pass.

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
synchronization, and `git diff --check` passed on the candidate commit. GitHub
CI also passed all six Windows/Linux Python 3.12/3.13/3.14 test lanes and the
security job; CodeQL passed on PR #51 on 2026-10-07.

Cloud Build `f3179e48-57fe-4e27-9567-a36994d825a1` built the merged source as
preview image digest
`sha256:354da814dc0dc24137e4818e57761769ab13320cda9311d6088cb7662803eec1`.
That image now serves 100% of isolated preview service revision
`gis-data-watchtower-public-v2-preview-00017-s8b`; the preview returned HTTP
200 and rendered v0.1.1 / `8099ee1`, 70/87 parcel coverage, 42.92% all-field
population, and 78.37% Mandatory-field population. The existing staging provider
job uses the same candidate image, but has not been executed since the update;
its latest execution remains `gis-data-watchtower-staging-p9m94`.

Private staging validation remains required for the aggregation, cloud-history,
and provider-statistics changes. Issue #20's multi-day hybrid validation gate
is still open after the catalog source timed out during the October 7 full
staging cycle. Its same-day read-only retest did not count as another daily
cycle. Continue at the next normal daily window. Do not change authoritative
scheduling before that gate passes.

PostHog remains dormant pending the dedicated project and verified client-IP
discard in Issue #50. Provider terms in Issues #1 and #2 remain unresolved;
the candidate does not authorize expanded monitoring. Fifteen of 87 composed
county profiles currently meet all inventory-category completion criteria.

Production public/private services remain on their existing release. No release
tag, production deployment, analytics activation, provider-term change, or
scheduling change has occurred for v0.1.1.
