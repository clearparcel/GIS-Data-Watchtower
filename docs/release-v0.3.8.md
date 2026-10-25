# GIS Data Watchtower v0.3.8 (coordinated release)

**Prepared October 25, 2026; deployment pending.** The owner approved merging
the October 24 audit fixes and deploying the result to all four surfaces: the
public and private dashboards and the provider and public-publisher jobs.

## Scope

Audit fixes merged October 25 (squash commits on `main`):

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
- Before the provider job is switched, the private source registry is checked
  with `validate_source_registry` for blank, padded or case-insensitively
  duplicate IDs.

## Rollback

Dashboards: restore traffic to `gis-data-watchtower-public-00041-ham` and
`gis-data-watchtower-dashboard-00043-nem` (v0.3.7). Jobs: restore the v0.3.6
image `72d1932c…2f2d422d` on the provider and publisher jobs.
