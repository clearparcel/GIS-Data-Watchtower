# GIS Data Watchtower v0.3.7 (dashboard release)

**Prepared October 23, 2026 (America/Chicago); deployment pending.** The owner
approved merging the October 23 review fixes and deploying the result.

## Scope

- Review fixes merged October 23:
  [#131](https://github.com/clearparcel/GIS-Data-Watchtower/pull/131) through
  [#141](https://github.com/clearparcel/GIS-Data-Watchtower/pull/141), covering
  alert incident ordering, static-export boundaries, county-panel revisions,
  exact source history, public snapshot validation, parcel-quality
  predicates, statewide GAC projection, GAC route dispatch, LocalStorage
  confinement and hosted brand images.
- Surfaces: the public and private dashboards move from v0.3.6 to v0.3.7.
  The provider and public-publisher jobs stay on v0.3.6, unchanged, by owner
  decision; no job is executed and no provider is polled.

## Rollback

Restore dashboard traffic to the v0.3.6 revisions recorded before promotion.
