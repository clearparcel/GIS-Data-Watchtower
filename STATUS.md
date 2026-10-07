# Project status

## Address/Road GAC, observability and hardening release — 2026-10-07

The approved implementation is **merged and deployed**. PR
[#48](https://github.com/clearparcel/GIS-Data-Watchtower/pull/48) merged to
protected `main` at
`53748af5e3ee8a1a205595b070142b537c1b0280`. Merge-commit CI run
[#310](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/37657720916)
passed all seven jobs: Windows and Ubuntu on Python 3.12–3.14 plus the security
job. The Linux 3.14 lane passed container smoke testing, the fixable
High/Critical Trivy gate, SBOM/provenance generation and artifact upload;
dependency audit and CodeQL also passed.

Production/runtime deployment now uses the merged source:

- public dashboard: `gis-data-watchtower-public-00010-75k`, 100% traffic,
  universal production image
  `sha256:20bdbbb967012dfee1b7de3b57ddd17ed3dbd5c197762e8d9c9d6beb3bdfb10f`;
- isolated preview: `gis-data-watchtower-public-v2-preview-00013-4lh`, 100%
  traffic, preview image
  `sha256:38538de3ed5696813a45964abbf2609b2ccc7535f16361b0eafef4fc6c5a4f53`;
- private dashboard: `gis-data-watchtower-dashboard-00018-vtw`, 100% traffic,
  derivative image
  `sha256:15459106816fc7ea71467fa97b46d38dcb25c45fbc04f695f3041a380b5fdcc3`;
- staging provider job and sanitized publisher job use the universal production
  image. The private derivative preserves the previously audited
  `/app/dashboard_app.py` wrapper exactly, SHA-256
  `786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.

The private staging registry advanced to Secret Manager version **9** without
changing its 35 source IDs. Existing `mn-state-addresses` and
`mn-state-roads` definitions were upgraded in place with the generic GAC
checks; no duplicate sources were added. The shared engine retains legacy
parcel compatibility and packages the official **53-field Address Point v1.3.2
schema (18 Mandatory)** and **73-field Road Centerline v1.1.1 schema (34
Mandatory)**.

One explicit full cloud staging cycle,
`gis-data-watchtower-staging-8rmpk`, generated a fresh 35-source aggregate at
`2026-10-07T18:52:22.972301+00:00`. Address and Road both passed:

- **Address Points:** 2,116,804 records, 53/53 standard fields present,
  56 Minnesota counties represented, **97.21% Mandatory-field population**,
  two grouped-statistics requests, 87 metadata counties, 85 NG911 participants
  and 56 GAC public opt-ins.
- **Road Centerlines:** 439,374 source features, 437,805 Minnesota
  county-grouped records, 73/73 standard fields present, 71 Minnesota counties
  represented, **95.94% Mandatory-field population**, three grouped-statistics
  requests, 87 metadata counties, 85 NG911 participants and 55 GAC public
  opt-ins. `Howard` and `Out of Jurisdiction` are explicitly excluded from
  the Minnesota county denominator, leaving 1,569 source features outside it.
- The latest submission date reported by the MnGeo metadata layer during this
  validation was **2026-05-20** for both standards. This is provider metadata,
  not Watchtower observation or publication time.

The full staging execution exited nonzero only because
`mn-parcel-county-catalog` hit its existing provider wall-clock deadline after
two attempts (about 61 seconds). Its prior successful observation was retained.
A separate read-only/no-save Cloud Run retest,
`gis-data-watchtower-staging-p9m94`, subsequently completed successfully. The
aggregate intentionally preserves the original transient failure rather than
rewriting full-fleet history from a one-source retest. Issue
[#20](https://github.com/clearparcel/GIS-Data-Watchtower/issues/20) records this
cycle as evidence toward, but not completion of, the multi-day validation gate.

Address/Road routine checks use Mandatory fields at validated batch size 12;
all standard fields remain schema-checked. Text population uses
`COUNT(NULLIF(field,''))`, while numeric/date fields use native
`COUNT(field)`. Full scans using 20-field batches produced provider wait
timeouts during validation, so Watchtower does not raise request budgets to
force them.

Production public acceptance passed through
`https://gis-watchtower.clear-parcel.com`: Address and Road pages and JSON
return the live metrics above with **v0.1.0.dev0 · build 53748af · Production**,
`/healthz` returns 200 while publication is current, Address CSV is live, and
the statewide workbook now contains `GAC Standards`, `GAC Counties`,
`GAC Fields` and `GAC Detail` in addition to the legacy parcel sheets. The
private dashboard still redirects anonymous traffic to Google IAP.

Aggregate correctness work separates worker `last_report_at` from true
all-clear `last_success_at`, records explicit source-retirement tombstones,
and makes public publication reject source disappearance unless a newer
retirement authorizes it. Read-only `check --no-save` no longer acquires the
state-file run lock; saved checks retain normal lock behavior.

Privacy-first PostHog integration is deployed **dormant**. Autocapture, Session
Replay, automatic pageview/pageleave capture, exception capture, persistent
identity and feature-flag requests are disabled. Production HTML contains no
PostHog loader and its CSP contains no PostHog origins. A dedicated
`GIS Data Watchtower` PostHog project could not be created because the current
PostHog plan is at its project limit; the existing `CRM staging pilot` project
was not repurposed or deleted. Activation remains gated by Issue
[#50](https://github.com/clearparcel/GIS-Data-Watchtower/issues/50), including
verified client-IP discard before setting the runtime activation flag.

Release hardening includes exact Python runtime constraints, a digest-pinned
Python base image, dependency audit, CodeQL, fixable High/Critical Trivy
enforcement and CI-generated CycloneDX SBOM/provenance/image-ID evidence.

**Scheduling authority is unchanged.** The Windows task
`\\ClearParcel Data Watchtower Daily` remains the authoritative provider
schedule. No Cloud Scheduler GIS-provider job was enabled. The only Cloud
Scheduler entry remains the 10-minute sanitized publisher
(`3,13,23,33,43,53 * * * *`, America/Chicago). See
[the release record](docs/release-gac-address-road-2026-10-07.md).

Public footer application identity is deployed to production revision `00010-75k`: **v0.1.0.dev0 · build 53748af · Production**. Data publication and provider observation times remain separate. See [release identity configuration](docs/release-policy.md).

The earlier browser-feedback release remains historical evidence. The current production public revision is `00010-75k` from `53748af`; the current isolated preview is `00013-4lh`. See [the Address/Road release record](docs/release-gac-address-road-2026-10-07.md) and the earlier [browser-feedback verification](docs/public-ui-release-2026-10-07.md).

Operational record updated: **2026-10-07** after the Address/Road release. One explicit cloud staging provider cycle was executed for validation; cloud scheduling remains disabled and the local daily task remains authoritative. Provider observation and public publication timestamps remain separate.

Follow-up manual review corrections are **merged and deployed**: PR [44](https://github.com/clearparcel/GIS-Data-Watchtower/pull/44), merge `284cf0c`, addresses report/publication ordering, worker inventory retirement, dashboard profile isolation, process-owned local locks, unique atomic scratch and WMS/WFS query composition. Release source is `afa908d`, including the approved merge-status documentation. See [fixes and upgrade requirements](docs/review-fixes-2026-10-06.md).

## Recorded deployment and coverage

The latest explicit cloud validation retained **35 aggregate sources = 31 cloud + 4 local**. The cloud cycle produced 30 OK cloud sources and one transient error on `mn-parcel-county-catalog`; all four retained local observations remained OK. A later read-only/no-save cloud retest of that catalog source succeeded, but the full aggregate intentionally preserves the original failure. Parcel monitoring coverage remains **70/87 counties = 59 statewide + 24 county-direct - 13 overlaps**; Address/Road GAC coverage is reported separately. Earlier all-green hybrid cycles remain historical validation evidence.

The earlier manual-review application release used merged commit `afa908d`: isolated preview `00009-nws`, production public `00008-lzd`, and private dashboard `00013-fnn`, each Ready at 100% traffic. Publisher and staging worker job images use the same release; runtime settings, IAM, ingress, IAP and schedules are preserved. One separately approved publisher run passed on the new image; the provider job was not executed. See [release verification](docs/release-2026-10-07.md). The preview retains its older sanitized publication; production publication advances through the existing publisher. Publication age remains separate from actual source observation time and provider health.

The public service reads only the sanitized public aggregate. A separate publisher reads the private unified aggregate, applies typed allowlists and forbidden-field validation, and writes the public object. Its recorded 10-minute schedule performs no provider polling. Authoritative cloud GIS-provider scheduling remains disabled; the existing local production schedule remains authoritative pending the multi-day parallel validation gate and explicit approval.

## Product and research

The public title is **Minnesota Open Data Watchtower**. The overview completeness map uses mandatory-field population, and the MN GAC page defaults to it with four percentage classes: <50%, 50–60%, 60–70%, >70% (`p<50`, `50<=p<60`, `60<=p<=70`, `p>70`). Exact 60 and 70 belong to the third class; observed zero belongs to the first, and unknown remains No data. All 87 county profiles and JSON/CSV/XLSX exports retain source identity and unavailable values.

Recorded MN GAC statistics: **91 fields**, **2,710,201 parcels**, **42.92% all-field** and **78.37% mandatory-field** population. These describe population, not compliance grades. Research reviewed all 87 county inventories: 216 reviewed categories, 132 blocked, zero pending; 16 fully reviewed inventories and 15 complete composed profiles. County-direct classifications are 58 free, 13 fee-based, 11 viewer-only and five unresolved. Eleven research holds remain, including Blue Earth, Faribault, Kandiyohi and Lincoln. Research access, statewide coverage and runtime monitoring health remain separate.

## Repository review and remaining gates

The October 6 review fixes public socket deadlines, protected redirect address binding, total provider request deadlines and 429 stop propagation. Reporting freshness follows reports/checks independently of historical success; public zero counts stay zero; publisher scratch is unique and cleaned on success/failure. These changes are **merged and deployed** to the existing application services and job images. The October 6 release itself did not perform a fresh provider cycle; the later Address/Road release above did. See [the dated repository review](docs/repository-review-2026-10-06.md) for actual commits, validation and limitations.

Issues 1/2 (provider constraints), 20 (multi-day validation) and 50 (PostHog activation) remain open. Issue 40 was closed after all original 35 classifications were verified complete. PRs 39/42 were merged after fresh required CI passed. User-approved main protection requires PRs, zero required approving reviewers, six strict Actions checks, resolved conversations and admin enforcement; force pushes/deletion are blocked. Main advanced through approved PR merges; no direct main push or provider scheduling change occurred.

Prior deployment, browser, provider-policy, rollback and cleanup evidence is preserved in [historical status](docs/status-history-2026-10-06.md) and [deployment history](docs/google-cloud-deployment.md#four-class-code-only-preview-release-2026-10-06).

## Historical section links

<a id="validated-capabilities"></a>

[Validated capabilities](docs/status-history-2026-10-06.md#validated-capabilities) (historical evidence).

<a id="clearparcel-staging-validation"></a>

[ClearParcel staging validation](docs/status-history-2026-10-06.md#clearparcel-staging-validation) (historical evidence).

<a id="county-parcel-data-access-audit"></a>

[County parcel-data access audit](docs/status-history-2026-10-06.md#county-parcel-data-access-audit) (historical evidence).

<a id="public-dashboard-hosting"></a>

[Public dashboard hosting](docs/status-history-2026-10-06.md#public-dashboard-hosting) (historical evidence).

<a id="staging-architecture"></a>

[Staging architecture](docs/status-history-2026-10-06.md#staging-architecture) (historical evidence).

<a id="concurrency-safe-aggregate-publishing"></a>

[Concurrency-safe aggregate publishing](docs/status-history-2026-10-06.md#concurrency-safe-aggregate-publishing) (historical evidence).

<a id="not-yet-enabled"></a>

[Not yet enabled](docs/status-history-2026-10-06.md#not-yet-enabled) (historical evidence).

<a id="cloud-run-startup-behavior"></a>

[Cloud Run startup behavior](docs/status-history-2026-10-06.md#cloud-run-startup-behavior) (historical evidence).

<a id="next-validation-gate"></a>

[Next validation gate](docs/status-history-2026-10-06.md#next-validation-gate) (historical evidence).

<a id="local-county-profile-acceptance-2026-10-06"></a>

[Local county-profile acceptance (2026-10-06)](docs/status-history-2026-10-06.md#local-county-profile-acceptance-2026-10-06) (historical evidence).

<a id="initial-isolated-county-profile-preview-release-2026-10-06"></a>

[Initial isolated county-profile preview release (2026-10-06)](docs/status-history-2026-10-06.md#initial-isolated-county-profile-preview-release-2026-10-06) (historical evidence).

<a id="final-review-product-fixes-and-deployed-preview"></a>

[Final review product fixes and deployed preview](docs/status-history-2026-10-06.md#final-review-product-fixes-and-deployed-preview) (historical evidence).

<a id="task-9-browser-feedback-2026-10-06-reviewed-and-released"></a>

[Task 9 browser feedback (2026-10-06; reviewed and released)](docs/status-history-2026-10-06.md#task-9-browser-feedback-2026-10-06-reviewed-and-released) (historical evidence).

<a id="feedback-preview-release-2026-10-06"></a>

[Feedback preview release (2026-10-06)](docs/status-history-2026-10-06.md#feedback-preview-release-2026-10-06) (historical evidence).

<a id="four-class-code-only-preview-release-2026-10-06"></a>

[Four-class code-only preview release (2026-10-06)](docs/status-history-2026-10-06.md#four-class-code-only-preview-release-2026-10-06) (historical evidence).

<a id="isolated-county-profile-preview-release-2026-10-06"></a>

[Historical release](docs/status-history-2026-10-06.md#isolated-county-profile-preview-release-2026-10-06).
