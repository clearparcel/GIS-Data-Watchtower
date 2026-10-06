# Project status

Last validated: **2026-10-06**

GIS Data Watchtower is public, MIT-licensed, and supports local, cloud, and hybrid execution.

County profiles now compose all 87 canonical counties from one observation snapshot and the evidence inventory. Coverage counts include only parcel observations, deduplicate statewide/direct overlap, and preserve unknown counts, source health, and reporting freshness separately. Category research remains explicitly incomplete until reviewed.


Overview and MN GAC maps now open one complete county source dialog for every canonical county. Overview offers monitoring-path and completeness coloring; both maps share fixed percentage colors and a separate no-data class. The dialog pauses page refresh, preserves date-only evidence, and displays unknown values explicitly. Local and live preview browser/mobile acceptance passed; scoped final review passed; manual cleanup was verified complete on 2026-10-06.

County JSON snapshots now include the composed parcel source profile. Statewide county/category CSV routes and the added County Access/Parcel Sources workbook sheets retain all 87 counties and unavailable values; the legacy monitored-source CSV remains compatible. Export regression, full unit validation and isolated preview deployment passed; scoped final review passed; manual cleanup was verified complete on 2026-10-06.

## Validated capabilities

- Windows and Ubuntu CI on Python 3.12, 3.13, and 3.14
- ArcGIS/WMS/WFS and catalog/API monitoring adapters
- bounded provider-friendly polling and HTTP 429 handling
- plain-language dashboard with county pages
- CSV, JSON, and native Excel (`.xlsx`) snapshot exports
- local filesystem and optional Google Cloud Storage persistence
- Cloud Run Job container deployment
- source execution profiles (`cloud`, `local`, `any`)
- hybrid worker aggregation with per-source worker provenance
- MN GAC parcel-field completeness analysis with county pages, interactive Minnesota county map, and JSON/CSV/Excel exports

## ClearParcel staging validation

A private ClearParcel staging deployment has validated the hybrid architecture against a 26-source production registry:

- **22 cloud-profile sources:** 22 OK / 0 warning / 0 error
- **4 local-profile sources:** 4 OK / 0 warning / 0 error
- **aggregate:** 26 OK / 0 warning / 0 error
- all 26 aggregate observations have worker provenance
- cloud/local parity was exact for the sources accepted from both environments: status, feature counts, and schema hashes matched

The four local-profile sources are kept local because their providers' network/TLS behavior does not support the Google Cloud egress path used in staging. Watchtower does not bypass those restrictions.

The hardened post-security-review build was revalidated end-to-end on 2026-10-05: the Cloud Run worker completed **22/22 cloud sources OK**, the local worker completed **4/4 local-only sources OK**, and the resulting aggregate remained **26/26 OK** with **0 unassigned observations**. JSON, CSV, and Excel exports each represented all 26 monitored sources.

The same staging architecture also validated the MN GAC completeness feature against MnGeo Plan Parcels Open. The 2026-10-05 observation represented **59 of 87 counties**, **2,710,201 parcel records**, and all **91 standard fields** using **8 bounded grouped-statistics queries**. The other 28 counties are reported as **No data**, not 0%. The observed record-weighted all-field population was **42.92%** and Mandatory-field population was **78.37%**; these are descriptive population statistics, not compliance grades. The full cloud retry after this feature was enabled returned **22/22 OK**, preserving the **26/26** hybrid aggregate.

## County parcel-data access audit

The earlier 35-county county-direct classification audit is retained; all 87 four-category inventory reviews have been attempted, with blocked evidence still incomplete. After reconciling public technical endpoints against official county distribution/fee policies, the original 35 county-direct results are **12 Free parcel data**, **12 Fee-based parcel data**, and **11 Parcel viewer only**. Blue Earth, Faribault, Kandiyohi, and Lincoln remain held for terms clarification despite reachable parcel services. The nine county-direct sources from the earlier staging approval assessment outside current MnGeo coverage (Brown, Dodge, Hubbard, Mahnomen, Meeker, Roseau, Sibley, Todd, and Wadena) are now present in **private staging registry version 7** as cloud-profile sources. On 2026-10-06 the hardened staging image `473157b` completed **31/31 cloud checks OK**; the local profile completed **4/4 OK**; the merged staging aggregate completed **35/35 OK**. The staging county-monitoring model now resolves to **70/87 actively checked counties**: 59 through MnGeo Plan Parcels Open, 24 through county-direct sources, with 13 overlaps counted once. The separate public v2 preview was updated to revision `00002-bn8` and its rendered KPI was verified at **70/87**. No authoritative GIS-provider scheduler was enabled and the production UI service was not replaced. See `docs/county-parcel-data-access-audit.md`.

## Public dashboard hosting

A separate read-only Cloud Run service serves the shareable dashboard at **https://gis-watchtower.clear-parcel.com** through a Google Cloud external Application Load Balancer. The dashboard now reads only the sanitized production object at `gs://clearparcel-watchtower-dark-bit-503017-j7/production/aggregate-state.json`; its service account no longer has access to the unified staging aggregate, private provider registry, or provider credentials.

A dedicated Cloud Run publisher job reads only the unified aggregate object, applies the public allowlist and fail-closed forbidden-field validation, then writes only the production aggregate object. A separate least-privilege scheduler identity invokes that job every **10 minutes**. The final least-privilege publisher execution completed successfully in about **3m6s**. This publication schedule performs no GIS-provider polling and does not replace the multi-day validation gate for the authoritative monitoring schedule.

The public renderer removes operational provider URLs, raw change payloads, tracked values, fingerprints, provenance details, and worker telemetry before rendering or exporting state. The existing private operational dashboard remains separate. Cloudflare is used only for authoritative DNS for the hostname; the record is DNS-only and application traffic is served by Google Cloud. Cloud Armor applies a conservative 120 requests/minute/IP throttle, load-balancer request logging is enabled at full sampling, and Cloud Monitoring checks `/healthz` every minute with availability and Cloud Run 5xx alert policies. Public snapshots carry their own publication timestamp; `/healthz` is designed to fail if publication age exceeds 30 minutes.

## Staging architecture

```text
Cloud Run Job (cloud profile, 22)
              \
               -> aggregate state -> dashboard/exports
              /
Local worker (local profile, 4)
```

The cloud worker persists its staging artifacts in Google Cloud Storage. Private production configuration is supplied through Secret Manager and is not included in this public repository or its container image.

## Concurrency-safe aggregate publishing

The shared aggregate store now uses compare-and-swap writes: Google Cloud Storage deployments use object-generation preconditions, and local/shared-filesystem deployments use an atomic lock-and-replace with retry. Ordinary cloud-job state, history, and alert artifacts also use version preconditions so a stale execution fails closed instead of overwriting a newer object. A normal profiled `watchtower check` run can publish directly to the configured shared aggregate store (opt-in via `aggregate_object` / `WATCHTOWER_AGGREGATE_OBJECT`); no separate script is required. The dashboard and the CSV/JSON/Excel exports read the unified aggregate state and show worker provenance, last-success time, and reporting freshness, with unhealthy sources tracked separately from stale/overdue reporting. See `docs/hybrid-aggregation.md` for the safety model and regression-test coverage.

A single hardened hybrid staging cycle has now been completed successfully. The remaining validation gate is multi-day parallel observation, not basic Cloud Run or aggregate correctness.

## Not yet enabled

- No Cloud Scheduler trigger has been enabled for the GIS-provider staging/check job. The only enabled Cloud Scheduler job is the 10-minute sanitized public-publication job, which performs no provider polling.
- The existing local production monitoring schedule has not been retired.
- The hybrid staging deployment is not yet the authoritative production monitoring scheduler.

## Cloud Run startup behavior

Cloud Run Job provisioning can remain in **Waiting for execution to start** for several minutes after the image is imported and resources are provisioned. In the validated staging environment, successful executions have taken approximately **2m30s to 4m15s** to reach the Started condition. This delay is a Cloud Run scheduling/provisioning interval, not evidence that Watchtower itself has failed.

Operationally, do not cancel an execution solely because Started is still Unknown during the first five minutes. Inspect the execution conditions if the delay exceeds roughly 5–7 minutes, investigate further by 7–10 minutes, and treat an explicit Failed condition as the real failure signal. The configured 15-minute task timeout remains the final execution bound.

## Next validation gate

Run the hybrid system in parallel for several days using the concurrency-safe publishing path, verify aggregate freshness and failure/recovery behavior over multiple real runs, then decide whether Cloud Scheduler should become the primary orchestration mechanism while retaining the local worker for provider-restricted sources.

The 2026-10-06 inventory now covers actual reviews of all 87 county records, including the exact final eight Swift–Yellow Medicine counties (27 reviewed / 5 blocked assessments). Derived totals are 216 reviewed, 132 blocked and 0 pending categories; 16 counties have all four categories reviewed. County-direct classifications total 82: 58 free, 13 fee-based and 11 viewer-only; 5 county-direct classifications remain unresolved. Wabasha, Waseca, Washington and Wright have distinct county parcel repository products, including Washington's verified regional county subdataset; regional aggregate facts remain separate. Swift's actual 2026 GIS parcel fees and Wilkin's signed-waiver applicability add research holds while Wilkin's explicitly fee-exempt self-service parcel download remains free. All nine existing holds remain, for 11 research holds total. Technical availability, licensing research, runtime membership/counts/health and schedules remain independent. No provider/configuration/scheduling/deployment/production changes were made; St. Louis optional null-geometry QA remains unchanged.


Stable county-source geometry and offered file MIME facts now project from validated
evidence when safe live metadata lacks them. Repository acquisition/refresh dates
require a unique vetted product-reference match; generic county/Hub links and
unrelated products retain null dates. Statewide county contribution dates remain
separate. Already-reviewed metropolitan evidence establishes Ramsey/4 and Scott/5
as distinct county polygon repository resources, matching the other five metro
counties; Scott's four-category inventory is now complete. Native observations,
county-direct classifications and eleven holds are unchanged. No monitoring,
provider polling, scheduling, runtime configuration or deployment changed.


## Local county-profile acceptance (2026-10-06)

Task 7 uses actual Chrome Browser/CUA interactions against an isolated sanitized
local public fixture. All 87 canonical targets opened the four complete source
groups in both overview modes and all three MN GAC summaries, plus representative
Conditional, Mandatory and If Available fields. Desktop and 390px panels,
keyboard focus containment/return, internal scrolling and pause/resume of the
30-second overview refresh passed. Long product names/URLs and twelve source
products stayed within the mobile dialog. Internal HTTP JSON/CSV/XLSX exports
agreed for all 87 profiles, source identities, dates and unknown/zero values.

Publication reporting now explicitly says Current, Overdue or Unknown using the
same configured threshold as `/healthz`. A synthetic overdue publication returned
503 while a source retained health `ok`, reporting `overdue`, its count and its
actual old check time. Research wording now identifies **15 complete composed
profiles**, separately from **16 fully reviewed four-category inventories**.
All 87 counties were attempted; 216 categories are reviewed, 132 blocked and zero
pending. County-direct classifications remain 82 resolved (58 free, 13 fee-based,
11 viewer-only), five unresolved, and 11 research holds. Runtime monitoring
coverage continues to be derived from the supplied current aggregate; these local
fixtures do not establish new live coverage. The live release below establishes
current preview coverage; scoped final review passed, while manual cleanup was verified complete on 2026-10-06.

Required validation: 186 unittest tests passed with ResourceWarning treated as an
error; compileall and `git diff --check` passed. Live acceptance is recorded below.

<a id="isolated-county-profile-preview-release-2026-10-06"></a>

## Initial isolated county-profile preview release (2026-10-06)

Initial preview revision `00003-xzg` served committed `b342b5d` using an immutable image,
dedicated private preview bucket and exact-object reader identity. Live validation
passed 87 JSON/CSV/XLSX profiles, 400 category/product rows, 35 legacy sources,
696 county panel activations, desktop/390px layouts and keyboard behavior.
Source results are 35/35 OK, cloud=31/local=4; current coverage derives to
70/87 = 59 statewide + 24 direct - 13 overlap. All research totals/holds remain.
Publication `2026-10-06T17:15:59.241555+00:00` is manually generated from the
actual aggregate; no preview scheduler or provider polling was introduced.
External `/healthz` returns a Google frontend 404, consistent with reserved paths;
external HTTP 200 health is not claimed. Production services/configuration are unchanged.
Required validation: 186 tests, compileall and diff checks passed. Private temporary cleanup is verified complete.
Scoped final review and validated CI heads are recorded below; manual cleanup was verified complete on 2026-10-06.
See [resource isolation, validation and limitations](docs/google-cloud-deployment.md#final-committed-preview-release-2026-10-06).


## Final review product fixes and deployed preview

Public sanitation now projects typed source, worker, count, catalog and MN GAC
leaves and completeness metrics. Raw completeness errors and unknown nested
payloads are omitted; a second sanitation pass preserves the public result.
All 59 inventories for the exact vetted MnGeo Plan Parcels Open official item
carry `mn-state-parcels` identity and a consistent product name. Fifty newly
linked inventories now retain their stable inventory IDs and approved links on
the row receiving that county's current observed count. Historical membership
cannot supply a missing observation or count; other products remain separate.

Both product findings passed scoped independent rereview without new breakage.
The final committed product `5686013` is now deployed as preview `00004-sv8`.
Actual live validation derives 87 profiles, 350 category/product rows and 35 legacy
sources; JSON/CSV/decoded XLSX agree, including all 87 individual county JSON
profiles. All 59 represented statewide county products retain one stable identity,
approved links and their own observed counts. Typed metrics retain 91 fields,
2,710,201 statewide records, 42.92% all-field and 78.37% mandatory population.
Coverage remains derived 70 = 59 statewide + 24 direct - 13 overlap.

The 193-test ResourceWarning-strict suite passed (5.417s); compileall and diff
checks passed. Final targeted browser checks passed 16 desktop overview cases
and 48 mobile MN GAC cases across eight representative counties, with mobile
keyboard focus, Escape/Space and internal scrolling. Final screenshot artifacts
were separately captured, locally viewed and dimension-verified. A fresh controller
IAB check verified all 87 targets, Aitkin's 43,024 statewide versus 42,996 direct
records, four groups, keyboard/Escape focus return and mobile 390px page 375px/dialog client and scroll width 349px.
Nondefault completeness mode and the open dialog survived over 40 seconds; after
closing, over 40 seconds later refresh restored monitoring mode and “Choose a county”.
IAB viewport reset to 1280px/page 1265px. Prior Chrome follow-up timeouts remain a tool
limitation; Chrome cleanup is not claimed. Product head 5686013 and operational
docs head c2c97e2 were pushed with both CI runs successful for each. Required manual
local temporary cleanup was verified complete on 2026-10-06; the controller checks eventual final PR-head CI.

## Task 9 browser feedback (2026-10-06; reviewed and released)

Source now uses the shared public header `Minnesota Open Data Watchtower`. Both maps, summary modes and individual fields share <20%, 20-40%, 40-60%, 60-80%, >80% fill/legend definitions: lower bounds inclusive, upper bounds exclusive except exactly 80 belongs to 60-80. True zero uses the first class; unavailable observations retain No data. Monitoring-path colors remain categorical.

Overview helpers distinguish all-type monitored dataset/service entries from unique counties with parcel observations. One statewide entry can cover many counties; overlapping paths count each county once. Derived counts, all 87 profiles, source identities, privacy, export contracts and provider holds are preserved.

Root verified the user's deletion of `C:/Users/sgert/AppData/Local/Temp/watchtower-task8-b342b5d` with Test-Path returning False. The cloud temporary build object was already verified deleted. Historical automatic-review denials and the Benton archive incident remain recorded; old Chrome cleanup remains unverified, while root IAB viewport reset was verified. The active parent workflow continues this feedback task. Task 9 review passed after its documentation fix. Task 10 separately released committed `dfacd72` to existing preview `00005-c24`; no provider action occurred. See the feedback preview release record.

Task 9 required validation: 196 tests passed with ResourceWarning treated as an error; compileall and git diff --check passed. Independent review and separate Task 10 preview release passed.


## Feedback preview release (2026-10-06)

Task 9 review passed after its documentation fix. Cloud Build
`e4debabe-4cf4-4c3f-ba16-4a8bdee56dd8` successfully built a fresh committed-only
`git archive` of `dfacd72`. Existing preview `00005-c24` serves 100% traffic,
Ready/ConfigurationsReady/RoutesReady true, pinned to
`sha256:c94c030aad2eec2063aabc4a73416a96f2b6163287e46f168f3e01de43f77e15`.
Dedicated preview bucket/object/identity, IAM and explicit
`public-dashboard --host 0.0.0.0 --port 8080` remain unchanged.

Fresh unified aggregate reads stayed in memory; only committed sanitizer output
passed public validation and was written/uploaded. Actual publication is
`2026-10-06T18:29:46.124951+00:00`; aggregate generation remains
`2026-10-06T11:11:40.540673+00:00`. All 35 sources remain OK, cloud=31/local=4,
with matching worker summaries and source check/success/provenance/observed-at
facts. Source dates and nested producer MNGAC completeness were preserved.
Internal exports passed 87 county JSON/CSV/XLSX rows, 87 individual JSON profiles,
350 actual source-category rows and 35 legacy rows. Coverage derives to
70 = 59 statewide + 24 direct - 13 overlaps; each county has at most one official
statewide product. No provider links were requested.

Root's browser acceptance verified exact title/metric explanation, all 87
overview fills, and 87 fills each for MNGAC mandatory, fields with values,
COUNTY_PIN and ANUMBERPRE with zero bin mismatches. ANUMBERPRE distinguished
45 true zeros and 28 No data counties. At 390px, page width was 375/375 and
Aitkin dialog 349/349; title wrapped within 316.98px. Enter opened the dialog,
Escape returned focus to Aitkin. Desktop screenshots were saved and inspected;
viewport reset was verified and the deliverable tab retained.

196 strict ResourceWarning-error unittests passed in 5.629s; compileall and diff
checks passed. Owned Cloud Build source upload was removed with exact generation
precondition `1791311349964872`; follow-up returned 404. Scoped local public-only
archive/build/sanitized/log cleanup was rejected by automatic approval review
with reason "blocked by policy". No bypass or retry occurred; folder
`.cce-agent/task10-feedback-preview-dfacd72` remains pending user cleanup.
The original Task 8 folder was previously verified absent. Production stays public `00006-82c`/private
`00011-t4l`, bucket IAM etag `CAQ=`, sole existing publisher scheduler unchanged.
No production, provider scheduling, IAM expansion, main, merge or Astra action.
No CI claim is made for the forthcoming documentation head.
