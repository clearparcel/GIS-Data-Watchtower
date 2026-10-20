# GIS Data Watchtower v0.3.6 (coordinated release)

**Deployed to every surface October 20, 2026 (about 6:10 PM America/Chicago),
before the first of the five observed daily runs (05:00, October 21), so all
five runs use this version.** The owner approved releasing tonight.

## Scope

- Provider-run spacing guard
  ([#125](https://github.com/clearparcel/GIS-Data-Watchtower/pull/125)):
  `WATCHTOWER_MIN_DISPATCH_HOURS=23` on the provider job, with the default
  10-minute start-delay tolerance (effective floor 22 h 50 min). Every
  `cloud-job` and `check` execution claims the `cloud` slot before any
  provider request; an early run exits 4 unless it records
  `--override-min-interval "reason"`. The hosted private dashboard is
  observation-only (its refresh form is hidden and POST returns 405), so it
  is not a provider-run path.
- County metadata dates (#125): `item_metadata: true` on the MnGeo county
  catalog source. Counties whose catalog entry links an ArcGIS hub or
  opendata dataset get one bounded daily read of that item's metadata from
  `www.arcgis.com`; hold-for-terms counties are never read. Dashboards label
  MnGeo's acquisition date as such and show the county's metadata
  publication and content dates beside it.

## Source and checks

- Deployed source: merged `main` **`77dd1e47659af96f4e2c21f16268a869c61d760b`**
  ([#126](https://github.com/clearparcel/GIS-Data-Watchtower/pull/126)); #125
  and #126 passed all eight CI checks. #125 had an independent Claude review
  and re-review; all findings were fixed before merge.
- Local release validation on GERTKEN-PC at `77dd1e4`: 699 tests, 3 platform
  skips, required Node 24 behavior tests; compile and status sync passed.
- Live version preflight passed: v0.3.5 to v0.3.6.

## Build

Cloud Build **`da835e18-a421-4201-9fe1-0a90c851af58`** passed all 20 steps
from a committed-only archive of `77dd1e4`: identity `0.3.6` / full SHA /
`production` and certifi 2026.10.19 on both images; the private wrapper
copied unchanged and verified by SHA-256; in-image tests including the new
dispatch-guard and item-metadata suites; actual private Handler acceptance;
CLI smoke. The build source upload was removed afterwards.

| Surface | Image | Predecessor |
| --- | --- | --- |
| Public dashboard | `watchtower@sha256:72d1932c…2f2d422d` (revision `gis-data-watchtower-public-00039-vaw`, 100%) | `00037-yoy` (v0.3.5) |
| Private dashboard | `dashboard@sha256:4db54bca…ffdd88471` (revision `gis-data-watchtower-dashboard-00041-cot`, 100%) | `00039-wif` (v0.3.5) |
| Provider job | `watchtower@sha256:72d1932c…2f2d422d` + `WATCHTOWER_MIN_DISPATCH_HOURS=23` | v0.3.5 `e5200d8c…` |
| Publisher job | `watchtower@sha256:72d1932c…2f2d422d` | v0.3.5 `e5200d8c…` |

## Rollout and acceptance

- Dashboards were deployed as zero-traffic candidates with non-image settings
  and traffic verified, then promoted. The public candidate tag URL is not
  reachable through the service's ingress, so public acceptance ran before
  (v0.3.5) and after (v0.3.6) on the normal URL: all routes, security
  headers, CSV/XLSX/JSON exports and the Cass STATE_PIN scan passed, provider
  observations were unchanged during the rollout, and county pages show
  "MnGeo acquired county data" instead of "Last county update".
- Private: signed-in check of the Wabasha county page on the normal URL
  showed the new label; the MN GAC route returned 200.
- Jobs: only the images changed, plus the one guard variable on the provider
  job; schedulers unchanged; no job was executed and no provider was polled.
  The publisher's next scheduled run succeeded on v0.3.6.
- Private registry: one new Secret Manager version adds `item_metadata` to
  the catalog source only; every other source definition hash is unchanged.

## Pending first-run validation

At the 05:00 October 21 run: the guard's first `cloud` claim in
`runs/dispatch-guard-cloud.json`, the run receipt, county `item_metadata`
statuses on the catalog record, and the new dates on the public site after
the next publish.

## Rollback

Dashboards: restore traffic to `00037-yoy` (public) and `00039-wif`
(private). Jobs: restore the v0.3.5 image and remove
`WATCHTOWER_MIN_DISPATCH_HOURS` from the provider job. Registry: disable the
new version so `latest` returns to the previous one. Rollback was prepared,
not exercised.
