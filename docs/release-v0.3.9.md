# ClearParcel GIS Data Watchtower v0.3.9 (coordinated release)

**Deployed to all four surfaces October 29, 2026, from GERTKEN-PC:** the
public and private dashboards and the provider and public-publisher jobs.

## Scope

Changes on the deployed `main` after v0.3.8:

| PR | Change | Commit |
| --- | --- | --- |
| [#154](https://github.com/clearparcel/GIS-Data-Watchtower/pull/154) | Use the official name ClearParcel GIS Data Watchtower | `aa11702` |
| [#153](https://github.com/clearparcel/GIS-Data-Watchtower/pull/153) | Pause county checks that lack permission | `924bf8a` |
| [#155](https://github.com/clearparcel/GIS-Data-Watchtower/pull/155) | Version bump to 0.3.9 | `0526041` |

## Why the jobs are included

#153 changes what the provider job polls. A county-direct parcel source on a
server the county operates is not checked without affirmative permission, and
`stop_requested` also skips a direct query of that county's ArcGIS Online
hosted feature or map service. Public pages do not present that pause as a
failure. #154 is the product name those surfaces show.

## Deployment boundaries

- Job images only. Schedules, the 23-hour dispatch spacing guard, execution
  profiles and provider cadence are unchanged. No job was executed.
- The provider job's private registry was checked with
  `validate_source_registry` for blank, padded or case-insensitively duplicate
  IDs. It was not printed or written.

## Source and checks

- Deployed source: merged `main` **`0526041fb312937a99e6ead27a1f3be75cae5286`**
  (#155).
- Registry check passed: Secret Manager `watchtower-staging-config` version
  13, 35 entries, sha256 `b0b01cd9…`. The registry was not printed or written.

## Build

Cloud Build **`08d5ecf8-ac21-4e59-9901-017340e1fc86`** in `us-central1`
passed all 29 steps. The recipe is the v0.3.8 build plus
`test_county_permission.py` on the watchtower image and a permission-data
identity step.

`test_county_permission.py` reads three committed data files from
`/acceptance`: `minnesota_county_parcel_access.json`,
`county_direct_gac_schema.json`, and `minnesota_counties.json`. Two earlier
submissions, `0e5b454f-…` and `39121a70-…`, failed at step 20 only because
those files were not mounted. The successful build mounts the three committed
files read-only and adds a step that asserts they are byte-identical
(SHA-256) to the copies inside the image. No test was changed or weakened.

Images: `watchtower:v0.3.9-0526041-production` and
`dashboard:v0.3.9-0526041-production`. The private dashboard keeps the
existing wrapper, `dashboard@sha256:a30b43e5…` (`dashboard_app.py` sha256
`bf6e9986…`). The Cloud Build source uploads for all three builds were
deleted afterwards.

| Surface | Image | Revision | Predecessor (rollback) |
| --- | --- | --- | --- |
| Public dashboard | `watchtower@sha256:0eca5b14e267023c320a3633538fdf48e6cdfc62b40c7138d2a5b940c235ae3f` | `gis-data-watchtower-public-00045-fik`, 100% | `00043-cax` (v0.3.8) |
| Private dashboard | `dashboard@sha256:71a37333eb96b86e5e8a5b9c35282a3e8bab4ce9b58a54f40294b5018f42e70f` | `gis-data-watchtower-dashboard-00047-noj`, 100% | `00045-vin` (v0.3.8) |
| Provider job | `watchtower@sha256:0eca5b14e267023c320a3633538fdf48e6cdfc62b40c7138d2a5b940c235ae3f` | — | v0.3.8 `978fea1f4e20…` |
| Publisher job | `watchtower@sha256:0eca5b14e267023c320a3633538fdf48e6cdfc62b40c7138d2a5b940c235ae3f` | — | v0.3.8 `978fea1f4e20…` |

## Rollout and acceptance

- Both dashboards were deployed with `--no-traffic` and tag `v039`, reached
  Ready, and were promoted to 100% after runtime settings and service controls
  were verified unchanged.
- Tagged `run.app` URLs return 404 because ingress is
  `internal-and-cloud-load-balancing`, so acceptance ran on
  `https://gis-watchtower.clear-parcel.com` after promotion, as in v0.3.8.
- Public acceptance passed before (v0.3.8) and after (v0.3.9). Provider
  observations were unchanged during the rollout. The footer shows v0.3.9.
- Jobs `gis-data-watchtower-staging` and
  `gis-data-watchtower-public-publisher`: only the image changed, from
  `978fea1f4e20` to `0eca5b14e267`. Non-image specification hashes are
  unchanged (`d7128b24…`, `dd250179…`). The guard environment is unchanged
  (minimum 23 hours, tolerance 0, execution profile `cloud`). Both schedulers
  are unchanged and ENABLED: `0 5 * * *` and `3,13,…,53 * * * *`,
  America/Chicago. No job was executed.
- A permission-gate dry-run against the live registry skips
  `awaiting-permission` for aitkin, beltrami, dakota, olmsted, pipestone,
  ramsey, rice, st-louis, and waseca, and `hold-for-terms` for brown and
  swift. Koochiching is still checked by design: its source is on ArcGIS
  Online (`services3.arcgis.com`), not a county-operated server, and the gate
  applies only to county servers (ArcGIS Online only for a stop request).

## Rollback

Dashboards: restore traffic to `gis-data-watchtower-public-00043-cax` and
`gis-data-watchtower-dashboard-00045-vin` (v0.3.8). Jobs: restore
`watchtower@sha256:978fea1f4e20…` on the provider and publisher jobs.
