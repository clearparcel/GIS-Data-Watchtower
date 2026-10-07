# Project status

Public footer application identity is implemented for the next preview build: canonical package version, baked source commit and Preview/Production/Development label. Data publication and provider observation times remain separate. See [release identity configuration](docs/release-policy.md).

Browser feedback changes are **published to the isolated preview**, with production unchanged: mandatory-field map classes below 50%, 50–60%, 60–70%, above 70%; clarified publication/check freshness and research progress; linked branding and readable evidence. See [the feedback record](docs/browser-feedback-2026-10-07.md). Preview revision `00010-tmt` serves product commit `feb285b`; the production release described below retains its deployed behavior until separately approved.

Operational record updated: **2026-10-07** after the user-approved follow-up release. Provider observations remain dated; this deployment did not re-poll GIS providers.

Follow-up manual review corrections are **merged and deployed**: PR [44](https://github.com/clearparcel/GIS-Data-Watchtower/pull/44), merge `284cf0c`, addresses report/publication ordering, worker inventory retirement, dashboard profile isolation, process-owned local locks, unique atomic scratch and WMS/WFS query composition. Release source is `afa908d`, including the approved merge-status documentation. See [fixes and upgrade requirements](docs/review-fixes-2026-10-06.md).

## Recorded deployment and coverage

The latest recorded hybrid staging cycle passed **31 cloud + 4 local = 35 sources**, all healthy with worker provenance. Parcel monitoring covered **70/87 counties = 59 statewide + 24 county-direct - 13 overlaps**. These recorded observations do not establish present live health. The earlier 22-cloud/26-total cycle is historical.

The reviewed application release is merged commit `afa908d`: isolated preview `00009-nws`, production public `00008-lzd`, and private dashboard `00013-fnn`, each Ready at 100% traffic. Publisher and staging worker job images use the same release; runtime settings, IAM, ingress, IAP and schedules are preserved. One separately approved publisher run passed on the new image; the provider job was not executed. See [release verification](docs/release-2026-10-07.md). The preview retains its older sanitized publication; production publication advances through the existing publisher. Publication age remains separate from actual source observation time and provider health.

The public service reads only the sanitized public aggregate. A separate publisher reads the private unified aggregate, applies typed allowlists and forbidden-field validation, and writes the public object. Its recorded 10-minute schedule performs no provider polling. Authoritative cloud GIS-provider scheduling remains disabled; the existing local production schedule remains authoritative pending the multi-day parallel validation gate and explicit approval.

## Product and research

The public title is **Minnesota Open Data Watchtower**. Both county maps use four percentage classes: <30%, 30–50%, 50–70%, >70% (`p<30`, `30<=p<50`, `50<=p<=70`, `p>70`). Exact 70 belongs to the third class; observed zero belongs to the first, and unknown remains No data. All 87 county profiles and JSON/CSV/XLSX exports retain source identity and unavailable values.

Recorded MN GAC statistics: **91 fields**, **2,710,201 parcels**, **42.92% all-field** and **78.37% mandatory-field** population. These describe population, not compliance grades. Research reviewed all 87 county inventories: 216 reviewed categories, 132 blocked, zero pending; 16 fully reviewed inventories and 15 complete composed profiles. County-direct classifications are 58 free, 13 fee-based, 11 viewer-only and five unresolved. Eleven research holds remain, including Blue Earth, Faribault, Kandiyohi and Lincoln. Research access, statewide coverage and runtime monitoring health remain separate.

## Repository review and remaining gates

The October 6 review fixes public socket deadlines, protected redirect address binding, total provider request deadlines and 429 stop propagation. Reporting freshness follows reports/checks independently of historical success; public zero counts stay zero; publisher scratch is unique and cleaned on success/failure. These changes are **merged and deployed** to the existing application services and job images. No fresh provider execution is claimed. See [the dated repository review](docs/repository-review-2026-10-06.md) for actual commits, validation and limitations.

Issues 1/2 (provider constraints) and 20 (multi-day validation) remain open. Issue 40 was closed after all original 35 classifications were verified complete. PRs 39/42 were merged after fresh required CI passed. User-approved main protection requires PRs, zero required approving reviewers, six strict Actions checks, resolved conversations and admin enforcement; force pushes/deletion are blocked. Main advanced through approved PR merges; no direct main push or provider scheduling change occurred.

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
