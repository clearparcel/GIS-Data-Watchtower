# Rice and Beltrami cloud migration — 2026-10-08

The user authorized moving Rice and Beltrami to Google Cloud after the public
policy/connectivity reassessment. Both complete adapters passed in the existing
Cloud Run staging worker, with saving disabled, before changing their profiles.

| Source | Cloud Run execution | Status / attempts | Parcel count / fields | Observation UTC |
| --- | --- | --- | --- | --- |
| Rice | `gis-data-watchtower-staging-z55r7` | OK / 1 | 28,265 / 88 | 2026-10-08T17:56:17.362814+00:00 |
| Beltrami | `gis-data-watchtower-staging-djmzk` | OK / 1 | 41,645 / 63 | 2026-10-08T17:56:17.074701+00:00 |

Both reported `esriGeometryPolygon`, with no source errors. Each execution used
the existing staging service account and image
`sha256:354da814dc0dc24137e4818e57761769ab13320cda9311d6088cb7662803eec1`.
Execution-only arguments were `--config /secrets/data_sources.json check
--source SOURCE_ID --no-save --json`. The actual argument arrays were verified.
No alternate endpoint, authentication bypass, proxy, or TLS relaxation was used.

Private staging registry version **12** changes only
`mn-rice-parcels-direct` and `mn-beltrami-parcels-direct` from local to cloud.
The saved configuration was read back and compared with the candidate, and a
pre-publication comparison checked for concurrent registry changes. All other
source/configuration values match version 11. The configured inventory is now
**35 cloud / 0 local**. The existing staging job mounts `latest`; no new job or
secret was created. Version 11 remains available for rollback. A scoped rollback
must restore just these two profiles in the then-current registry, preserving
any later unrelated changes, and publish through the normal approval boundary.

The no-save checks did not publish worker state. Read-only aggregate verification
still finds **31 cloud / 4 local observations**, with both counties retaining
their October 7 local timestamps. Configured execution assignments and observed
worker provenance are separate. The public dashboard continues to represent
saved observations; no new coverage count or freshness claim is warranted.
Cloud Scheduler still contains only the existing sanitized public publisher.
The authoritative GERTKEN-PC installation and scheduling are unchanged.

The [reassessment](cloud-provider-access-reassessment-2026-10-08.md) records the
prior connectivity and Rice portal ambiguity. This migration verifies both
adapters in actual Cloud Run and implements the user's scoped profile decision;
it does not prove multi-day reliability or authorize bulk parcel retrieval.

Before replacing local operational authority, complete the validation and
worker-retirement work identified in the [cloud readiness review](codex-cloud-readiness-review-2026-10-08.md).
Temporary private registry exports and diagnostic outputs were removed after
validation. Standard execution and Secret Manager audit records remain.
