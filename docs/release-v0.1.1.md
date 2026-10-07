# GIS Data Watchtower v0.1.1 release record

**Status:** deployed to production on 2026-10-07 from merged code commit
`8099ee18ec48714b33a9e998b414ea9ee0cf7d8e`. The user explicitly authorized
waiving the multi-day staging gate for this rollout. That gate did not pass and
Issue #20 remains open.

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

## CI, staging state, and release decision

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

Private staging validation was not completed for the aggregation, cloud-history,
and provider-statistics changes. Issue #20 remains open after the catalog source
timed out during the October 7 full staging cycle; its same-day read-only retest
did not count as another daily cycle. The user explicitly authorized deployment
without that gate. This exception does not authorize a change to authoritative
provider scheduling.

PostHog remains dormant pending the dedicated project and verified client-IP
discard in Issue #50. Provider terms in Issues #1 and #2 remain unresolved;
the candidate does not authorize expanded monitoring. Fifteen of 87 composed
county profiles currently meet all inventory-category completion criteria.

## Production rollout — 2026-10-07

Cloud Build `1ca9bfa8-75c7-4139-a782-a3c133628ea8` built the production
universal image from the clean merged code commit with production build identity:

- Universal image: `sha256:3f3244054a202c55a464e06e85afea9f72dc750bc34d75cbbe872fde5495dfb6`.
- Private dashboard derivative: Cloud Build `8484cb0a-1794-4662-ae19-804136a533f5`,
  image `sha256:4fbc66103d968c289e03d48a07646a9c6ac69435cd7d46700c9b137c85dd9ed6`.
  It was derived from the universal image and preserved the deployed wrapper
  byte-for-byte; Cloud Build verified SHA-256
  `786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.

Production now serves public revision `gis-data-watchtower-public-00011-b9c`
and private dashboard revision `gis-data-watchtower-dashboard-00019-c9l`, both
Ready with 100% traffic. The publisher job uses the universal v0.1.1 digest,
retains its existing command, service account, environment variable names and
300-second timeout. It was not manually started; the existing
`gis-watchtower-public-publish` schedule remains enabled at
`3,13,23,33,43,53 * * * *`; no cloud GIS-provider job was created or run.

The first scheduled post-deployment publisher execution,
`gis-data-watchtower-public-publisher-8tr9h`, completed successfully at
`2026-10-07T21:54:08Z` on the v0.1.1 digest. It published the retained
35-source aggregate: 34 sources are OK and
`mn-parcel-county-catalog` remains in error from the known timeout. Fleet
status is therefore `error`; `/healthz` returned 200 because publication
freshness is reported separately from provider health. The published snapshot
time is `2026-10-07T21:54:04.658204Z`.

Production acceptance through `https://gis-watchtower.clear-parcel.com` returned
HTTP 200 for `/`, `/api/state`, and `/healthz`. The HTML identifies v0.1.1,
build `8099ee1`, and Production. The sanitized API contained 35 source entries;
anonymous access to the private dashboard still returned the Google IAP
redirect. Existing public ingress, service accounts, private dashboard
authentication boundary, analytics dormancy, provider policy and schedules were
preserved.

Rollback targets remain available: public revision `gis-data-watchtower-public-00010-75k`
on `sha256:20bdbbb967012dfee1b7de3b57ddd17ed3dbd5c197762e8d9c9d6beb3bdfb10f`,
private revision `gis-data-watchtower-dashboard-00018-vtw` on
`sha256:15459106816fc7ea71467fa97b46d38dcb25c45fbc04f695f3041a380b5fdcc3`,
and the publisher's prior universal image is the same public digest. No rollback
was required.
