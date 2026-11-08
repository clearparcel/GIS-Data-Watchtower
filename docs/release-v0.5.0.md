# GIS Data Watchtower v0.5.0

Coordinated rollout: November 7, 2026 (Central time).
Source: `69619565646372aa3e7b346a2e9a3bbfc06901ec`, merged release PR #228.

This release includes the county editor improvements and source enrollment from
merged PRs #225–#227. Explicitly reviewed direct services and data files can join
regular cloud or local checks and publish their results through the existing
public snapshot. Service checks read details and one count; file checks read
update headers. County terms holds, stop decisions and provider backoff remain
in force, and permission evidence stays private.

The hosted editor offers the current regular cloud schedule. A local worker
choice requires explicit operator configuration and an active approved worker.

The editor adds section navigation, clear save/retry feedback, change review,
field validation and protection against losing unsaved edits. Internal dashboard
fixes preserve refresh preferences and show the correct count observation date.

## Validation and promotion

- 1,058 local tests passed with Node required. All six Windows/Linux Python
  combinations passed, including dependency checks, CodeQL, both container scans
  and supply-chain evidence. The [merged-source CI run](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/42441572969)
  passed for the deployed source. Independent feature and release reviews found
  no remaining concrete code issues after the reported findings were fixed.
- The visible-version preflight passed. The immutable installed image matched
  committed source hashes and passed 39 synthetic tests, including authenticated
  editor save through worker checks, aggregation and public publication. Its
  OS/Python inventories matched the scanned CI artifact.
- The private enrollment registry was initialized conditionally without enabling
  sources. Its scoped worker read passed under the actual worker identity, while
  reads of unrelated private records and attachments were denied. The temporary
  storage-only validation job was removed.
- Service candidates were prepared without traffic and compared with rollback
  baselines. The existing ingress policy restricted direct canary access; the
  normal public route was verified immediately after promotion. Live version,
  service IAM, authentication and unrelated runtime settings matched expectations.
- The regular worker received only its new private registry input alongside the
  image update. The public publisher completed successfully. Public source
  results and worker provenance matched the aggregate; county/source pages,
  summaries, JSON exports and publication health passed live checks.
- Existing schedules and provider-run spacing were preserved. No additional GIS
  provider run was executed. Previous revisions remain available for rollback.

The public dashboard, internal dashboard, county editor, regular cloud worker and
public publisher use this release. The scanner and digest jobs were outside the
application update. Private artifact, configuration and operational evidence is
retained with the deployment records.

## Verification scope

The owner provided a screenshot confirming the revised signed-in editor layout
and review controls. The assistant could not directly inspect that browser
session. The save-to-check-to-public flow was verified with installed-image
synthetic data; live operational checks verified the deployed wiring and saved
observations. An eligible source explicitly enrolled in the editor joins the
next regular worker run and then the public publisher.

The [source monitoring guide](county-source-monitoring.md) describes the private
registry input and exact-object worker permission required for activation.
Application rollout retains the existing provider schedule. Deployment evidence
and rollback configuration stay in the private release record.
