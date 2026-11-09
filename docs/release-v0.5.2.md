# GIS Data Watchtower v0.5.2

Deployed November 9, 2026. Built from merged source commit
`6ac707952037e9ef4c8acb7ba82581885344b434`, incorporating PR #233.

This candidate updates the County editor and county-direct source monitoring:

- Terms or policy links and permission dates are optional.
- A bounded public REST check may be enrolled after review finds no applicable
  restriction, without requiring prior affirmative county permission.
- A specific county policy, employee request, cease-and-desist, explicit decline,
  fee, licensing condition or other applicable restriction continues to block
  the check.
- Direct file update checks still require affirmative county permission.
- County-reported direct-data update frequency is recorded as descriptive
  information and does not change the Watchtower schedule.

## Validation and promotion

- Candidate CI passed all six Windows/Linux Python combinations and security
  checks; [merged-main CI](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/42647933798)
  also passed. Local validation passed 1,086 tests (3 skipped), compileall,
  current-status synchronization and diff checks.
- IAP-protected synthetic staging UI review confirmed the optional policy link,
  permission date and county update-frequency fields. The test stayed in an
  unsaved draft; no real county record or monitoring enrollment was changed.
- Production rollout updated the public and internal dashboards, county editor,
  regular cloud worker and public publisher. The public site returned HTTP 200
  and displayed v0.5.2 after promotion. Candidate revisions were verified ready
  before traffic moved; runtime settings, service identities, ingress controls
  and scheduler targets were preserved. Prior service revisions and job images
  remain the rollback targets.
- No provider polling was started and no provider or publisher schedule was
  changed. Scanner and weekly digest images were outside this coordinated
  application update. Detailed deployment identifiers remain in the private
  deployment record.
