# GIS Data Watchtower v0.3.8 (coordinated release)

**Deployed to all four surfaces October 24, 2026 (about 10:30 PM
America/Chicago).** The owner approved merging the October 24 audit fixes and
deploying the result to the public and private dashboards and the provider and
public-publisher jobs.

## Scope

Audit fixes merged October 24 (squash commits on `main`):

| PR | Change | Finding | Commit |
| --- | --- | --- | --- |
| [#145](https://github.com/clearparcel/GIS-Data-Watchtower/pull/145) | Reject duplicate or missing source IDs before any check | WT-A01 | `5e04e72` |
| [#146](https://github.com/clearparcel/GIS-Data-Watchtower/pull/146) | Keep execution profile and monitoring decision in source exports | WT-A04 | `31e860d` |
| [#147](https://github.com/clearparcel/GIS-Data-Watchtower/pull/147) | Future check times are not current; contradictory totals are rejected | WT-A05, WT-A06 | `9ee4679` |
| [#148](https://github.com/clearparcel/GIS-Data-Watchtower/pull/148) | Detect MN GAC field-name drift since the schema audit | WT-A07 | `e080b11` |
| [#149](https://github.com/clearparcel/GIS-Data-Watchtower/pull/149) | Current release pointers in README and deployment docs | WT-A09 | `2db8d1e` |
| [#150](https://github.com/clearparcel/GIS-Data-Watchtower/pull/150) | Provider-run alerting proposal (documentation only) | — | `003ccf5` |

WT-A02 and WT-A03 were already fixed on `main` (#140). WT-A08 (retention) and
WT-A10 (dashboard service-account scope) await owner decisions and are not
part of this release.

## Why the jobs are included

#145 and #147 change worker behavior: the provider job refuses a registry with
duplicate or missing source IDs before claiming the dispatch slot, and
aggregate freshness treats far-future check times as stale. #148 adds the
public `gac_standard_field_names` field, which the publisher must emit for the
dashboards to compare field names.

## Deployment boundaries

- Job images only. Schedules, the 23-hour dispatch spacing guard, execution
  profiles and provider cadence are unchanged; no job is run by hand.
- Before the provider job was switched, the private source registry was
  checked with `validate_source_registry` for blank, padded or
  case-insensitively duplicate IDs.

## Source and checks

- Deployed source: merged `main` **`2a688d66cbcc54018498d050ea289cf5ecf99da9`**
  (#151). Each PR passed all seven required checks (six test jobs and
  security) on an up-to-date branch before merging.
- Local release validation in a clean worktree: 778 tests, 3 platform skips,
  required Node 24 behavior tests; compile, status sync and `git diff --check`
  passed.
- Live version preflight passed: v0.3.7 to v0.3.8.
- Registry check passed: the provider job's private registry (35 entries) has
  no blank, padded or duplicate IDs. It was read in memory only.
- The published snapshot passed v0.3.8 snapshot validation, including the new
  totals check, before the dashboards were switched.

## Build

Cloud Build **`a05785e2-2aad-4d92-8193-aa9195c46351`** passed all 27 steps
from a committed-only archive of `2a688d6`, with the v0.3.7 build steps plus
in-image tests for source-registry identity, aggregate guards and county
profile exports. Both images report `0.3.8` / full SHA / `production`. The
build source upload was removed afterwards.

| Surface | Image | Revision | Predecessor (rollback) |
| --- | --- | --- | --- |
| Public dashboard | `watchtower@sha256:978fea1f…6d7b2f98` | `gis-data-watchtower-public-00043-cax`, 100% | `00041-ham` (v0.3.7) |
| Private dashboard | `dashboard@sha256:dbda0476…3c889c83` | `gis-data-watchtower-dashboard-00045-vin`, 100% | `00043-nem` (v0.3.7) |
| Provider job | `watchtower@sha256:978fea1f…6d7b2f98` | — | v0.3.6 `72d1932c…2f2d422d` |
| Publisher job | `watchtower@sha256:978fea1f…6d7b2f98` | — | v0.3.6 `72d1932c…2f2d422d` |

## Rollout and acceptance

- Both dashboards were deployed as zero-traffic candidates (tag `v038`);
  non-image settings, ingress, IAP and traffic were verified unchanged, then
  each was promoted to 100%.
- Public acceptance on the normal URL: overview, counties, Cass and Brown
  county pages, MN GAC, `/api/state`, JSON/CSV/XLSX exports and `/healthz`
  returned 200; the hash-based CSP and the security headers are present; the
  footer shows v0.3.8; the Cass STATE_PIN scan row and workbook agree; the four
  `/assets/` brand URLs are immutable-cacheable and an unknown asset is 404.
- WT-A04 confirmed live: `/parcel-sources.csv` now fills `execution_profile`
  (98 of 350 rows) and `monitoring_decision` (188 rows); both were empty under
  v0.3.7.
- Private: the revision is Ready and unauthenticated requests are redirected
  to Google sign-in by IAP. A signed-in owner check is pending.
- Jobs: only the image changed. Read-back non-image specification hashes are
  identical, every environment variable is unchanged (including
  `WATCHTOWER_MIN_DISPATCH_HOURS=23` and
  `WATCHTOWER_DISPATCH_TOLERANCE_MINUTES=0`), the execution profile stays
  `cloud`, and both schedulers are unchanged (daily 05:00 and every 10 minutes,
  America/Chicago). No job was executed by hand and no provider was polled.
- The first scheduled v0.3.8 publisher run succeeded; its snapshot passes
  v0.3.8 validation and is served by the public site, and 21 of its 33 sources
  carry `gac_standard_field_names`.
- No error logs on the new revisions or the publisher job.
- The first v0.3.8 provider run is the October 25 05:00 schedule. The two
  previous scheduled provider runs (October 23 and 24, on v0.3.6) ended
  `EXECUTION_FAILED`; that predates this release.

## Rollback

Dashboards: restore traffic to `gis-data-watchtower-public-00041-ham` and
`gis-data-watchtower-dashboard-00043-nem` (v0.3.7). Jobs: restore the v0.3.6
image `watchtower@sha256:72d1932c554fb76b0721e6734bf8f0d6e26835d894930db8bd51319c2f2d422d`
on the provider and publisher jobs. Rollback was prepared, not exercised.
