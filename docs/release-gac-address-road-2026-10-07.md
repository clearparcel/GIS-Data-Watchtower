# Address/Road GAC and Watchtower hardening release — 2026-10-07

Release source: `53748af5e3ee8a1a205595b070142b537c1b0280`  
Pull request: [#48](https://github.com/clearparcel/GIS-Data-Watchtower/pull/48)  
Merge CI: [run #310](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/37657720916)

## Scope

This release adds the shared Minnesota GAC standards engine, Address Point and
Road Centerline completeness monitoring, normalized GAC exports, worker/source
state correctness fixes, privacy-first dormant PostHog hooks and reproducible
release/security controls.

Address Point v1.3.2 is packaged as 53 fields / 18 Mandatory. Road Centerline
v1.1.1 is packaged as 73 fields / 34 Mandatory. Legacy parcel
`mngac_completeness` configuration remains supported.

## CI and supply chain

Merge-commit CI passed all seven jobs: Windows and Ubuntu on Python 3.12, 3.13
and 3.14 plus the security job. The Linux 3.14 lane passed:

- full ResourceWarning-strict tests and CLI/container smoke tests;
- fixable High/Critical Trivy scanning;
- CycloneDX SBOM, provenance and image-ID generation/upload.

The security job passed the exact-dependency audit and CodeQL. The first Trivy
attempt on the feature branch correctly detected vulnerable runtime build
tooling; the runtime image was corrected rather than weakening the severity
gate.

Local release validation passed **276/276** ResourceWarning-strict tests,
`compileall`, status-document synchronization and `git diff --check`.

## Builds

| Build | Purpose | Immutable image |
| --- | --- | --- |
| `1f2fa55e-ecf5-45bd-abe5-b62658d637a0` | production universal image | `sha256:20bdbbb967012dfee1b7de3b57ddd17ed3dbd5c197762e8d9c9d6beb3bdfb10f` |
| `f575c851-5c13-438d-8018-df976327013d` | isolated preview image | `sha256:38538de3ed5696813a45964abbf2609b2ccc7535f16361b0eafef4fc6c5a4f53` |
| `c27a907f-19b1-45f4-84c0-3007d5ad1431` | private dashboard derivative | `sha256:15459106816fc7ea71467fa97b46d38dcb25c45fbc04f695f3041a380b5fdcc3` |

The private derivative uses the production universal image for package code and
copies only the existing audited observation-only `/app/dashboard_app.py`
wrapper from the prior private image. Build-time verification requires wrapper
SHA-256
`786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.
The final image retains the unprivileged `65532:65532` runtime.

## Registry and provider validation

Secret Manager `watchtower-staging-config` advanced to version **9**. The
registry remained 35 sources with unique IDs. Existing `mn-state-addresses`
and `mn-state-roads` entries received GAC configuration in place.

Explicit cloud execution `gis-data-watchtower-staging-8rmpk` produced the
fresh aggregate at `2026-10-07T18:52:22.972301+00:00`.

| Metric | Address Points | Road Centerlines |
| --- | ---: | ---: |
| Source features | 2,116,804 | 439,374 |
| Minnesota county-grouped records | 2,116,804 | 437,805 |
| Standard fields present | 53/53 | 73/73 |
| Routine scanned fields | 18 Mandatory | 34 Mandatory |
| Minnesota counties represented | 56 | 71 |
| Mandatory-field population | 97.21% | 95.94% |
| Grouped statistics requests | 2 | 3 |
| Metadata counties | 87 | 87 |
| NG911 participants | 85 | 85 |
| GAC public opt-ins | 56 | 55 |

Road records grouped as `Howard` or `Out of Jurisdiction` are excluded from
the Minnesota denominator. The 1,569-record difference between source features
and Minnesota-grouped records stays explicit.

The full run's only non-OK source was `mn-parcel-county-catalog`, which timed
out after two attempts under its existing wall-clock budget. Its previous
`last_success_at` was preserved. Targeted read-only/no-save execution
`gis-data-watchtower-staging-p9m94` later completed successfully. The full
aggregate was not rewritten from that filtered retest; Issue #20 retains the
evidence for the multi-day gate.

## Rollout

| Target | Release state |
| --- | --- |
| Isolated public preview | `gis-data-watchtower-public-v2-preview-00013-4lh`, 100% traffic |
| Production public dashboard | `gis-data-watchtower-public-00010-75k`, 100% traffic |
| Private dashboard | `gis-data-watchtower-dashboard-00018-vtw`, 100% traffic |
| Staging provider job | universal production image |
| Sanitized public publisher job | universal production image |

The scheduled publisher ran successfully on the new image and published the
new sanitized GAC schema to the production object. No provider scheduler was
enabled.

During private-dashboard promotion, three candidate revisions failed before
receiving traffic while the service remained on its working revision:
`00014-d9q` used the universal image's default provider command,
`00015-r29` received a combined CLI argument, and `00016-dbr` lacked the
private wrapper's aggregate bootstrapping. The final derivative preserved the
known-good wrapper contract and `00018-vtw` became Ready at 100% traffic.

## Public acceptance

Production acceptance through `https://gis-watchtower.clear-parcel.com`
verified:

- Address and Road HTML/JSON return HTTP 200 with build
  `53748af · Production`;
- Address shows 56 counties, 2,116,804 records and 97.21% Mandatory population;
- Road shows 71 counties, 437,805 Minnesota-grouped records and 95.94% Mandatory
  population;
- each public GAC payload contains 87 county metadata records;
- `/healthz` returns HTTP 200 while publication is current;
- Address CSV exports the GAC field summary;
- statewide Excel contains `GAC Standards`, `GAC Counties`, `GAC Fields`
  and `GAC Detail`, while retaining legacy MNGAC sheets;
- the public CSP contains no PostHog origins and rendered pages contain no
  PostHog loader;
- anonymous private-dashboard access still returns the Google IAP sign-in
  redirect.

The production sanitized aggregate intentionally preserves the transient
catalog error from the full fleet run even though the isolated retest
succeeded. This keeps the audit trail truthful rather than manufacturing a
full-fleet all-green state from a filtered check.

## PostHog

PostHog project creation for `GIS Data Watchtower` was attempted but rejected
because the current plan has reached its project limit. The existing
`CRM staging pilot` project was not repurposed. Analytics remain dormant.
Issue [#50](https://github.com/clearparcel/GIS-Data-Watchtower/issues/50)
contains the activation checklist, including a separate Watchtower project and
verified **Discard client IP data** setting.

## Scheduling and authority

The authoritative local Windows provider schedule is unchanged. Cloud Scheduler
still contains only `gis-watchtower-public-publish` at
`3,13,23,33,43,53 * * * *` America/Chicago. No cloud GIS-provider scheduler
was created or enabled. Issue [#20](https://github.com/clearparcel/GIS-Data-Watchtower/issues/20)
remains the multi-day validation gate before any authority change.

## Rollback

The prior production public revision `00009-tbt`, prior preview
`00011-hkl`, and the prior proven private dashboard image/revision lineage are
retained. Provider/publisher jobs can be returned to the preceding universal
digest
`sha256:22ebd6a5d28e35c75234a728bb5340467501c20d3e98f580d9d14c40ab03c7c6`.
The staging registry can be rolled back to Secret Manager version 8 if the GAC
configuration itself must be reverted. Do not change scheduler authority,
remove audit evidence, or weaken CAS/IAM as part of rollback.

