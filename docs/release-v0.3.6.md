# GIS Data Watchtower v0.3.6 (coordinated release)

**Prepared October 20, 2026 (America/Chicago); deployment pending.** The owner
approved releasing tonight, before the first of the five observed daily runs
(05:00 America/Chicago, October 21), so all five runs use this version.

## Scope

- Provider-run spacing guard
  ([#125](https://github.com/clearparcel/GIS-Data-Watchtower/pull/125)):
  `WATCHTOWER_MIN_DISPATCH_HOURS=23` on the provider job, with the default
  10-minute start-delay tolerance. Every `cloud-job` and `check` execution
  claims the `cloud` slot before any provider request; an early run exits 4
  unless it records `--override-min-interval "reason"`.
- County metadata dates (#125): `item_metadata: true` on the MnGeo county
  catalog source in the private registry. Counties whose catalog entry links
  an ArcGIS hub or opendata dataset get one bounded daily read of that item's
  metadata from `www.arcgis.com`; hold-for-terms counties are never read.
  Dashboards label MnGeo's acquisition date as such and show the county's
  metadata publication and content dates beside it.
- All four surfaces (public and private dashboards, provider and publisher
  jobs) move from v0.3.5 to v0.3.6. The publisher must carry the new public
  projection for the metadata dates to reach the public site.

## Rollback

Restore each surface to its v0.3.5 image and the provider job's environment
and registry version recorded before the update.
