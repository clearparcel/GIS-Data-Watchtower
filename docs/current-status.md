# Current project status

Last validated: **2026-10-06**

The offline county-profile composer derives all 87 county profiles and parcel coverage counts from current observations and evidence inventory. Explicit source identity joins preserve source-specific facts; catalog discovery and imagery cannot activate parcel monitoring. Unavailable statewide observations remain unknown, and pending category reviews remain incomplete.


Overview and MN GAC maps now open one complete county source dialog for every canonical county. Overview offers monitoring-path and completeness coloring; both maps share fixed percentage colors and a separate no-data class. The dialog pauses page refresh, preserves date-only evidence, and displays unknown values explicitly. Local and live preview browser/mobile acceptance passed; scoped final review passed; manual cleanup was verified complete on 2026-10-06.

County JSON snapshots now include the composed parcel source profile. Statewide county/category CSV routes and the added County Access/Parcel Sources workbook sheets retain all 87 counties and unavailable values; the legacy monitored-source CSV remains compatible. Export regression, full unit validation and isolated preview deployment passed; scoped final review passed; manual cleanup was verified complete on 2026-10-06.

## Release status

GIS Data Watchtower is a public MIT-licensed repository. The public repository contains provider-neutral example configuration only; deployment-specific source registries and credentials remain private.

Base functionality includes:

- provider-friendly GIS service monitoring and bounded QA;
- plain-language dashboard and county views;
- CSV, JSON, and native Excel (`.xlsx`) snapshot exports;
- Windows and Linux support;
- local filesystem and optional Google Cloud Storage backends;
- Cloud Run Job-compatible container deployment;
- hybrid source execution profiles;
- hybrid worker result aggregation;
- concurrency-safe aggregate publishing (GCS generation preconditions, atomic local locking) with dashboard/export consumption of the unified aggregate state;
- MN GAC parcel-field completeness statistics, county-level field tables, and an interactive Minnesota county map driven by the stored statewide observation.

## CI

The project is tested on:

- Ubuntu 24.04 / Python 3.12
- Ubuntu 24.04 / Python 3.13
- Ubuntu 24.04 / Python 3.14
- Windows / Python 3.12
- Windows / Python 3.13
- Windows / Python 3.14

The Linux 3.14 matrix leg also smoke-tests the Docker image.

## County parcel-data access audit

The earlier county-direct classification audit for **35** registry-derived `needs-source` counties is retained; all 87 four-category inventory reviews have been attempted, with blocked evidence still incomplete. Historical original 35 county-direct results are **12 Free parcel data**, **12 Fee-based parcel data**, and **11 Parcel viewer only**; Blue Earth, Faribault, Kandiyohi, and Lincoln remain `hold-for-terms`. The nine county-direct sources from the earlier staging approval assessment outside current MnGeo coverage are now included in **private staging registry version 7**, all assigned to the cloud profile. The 2026-10-06 hybrid staging cycle used image `473157b`: **31/31 cloud sources OK**, **4/4 local sources OK**, and a generation-protected merge produced a **35/35 OK** aggregate with cloud/local worker provenance intact. Against that aggregate, the county model is **70/87 actively checked** (59 MnGeo, 24 county-direct, 13 overlapping). Both local dashboard rendering and the deployed public v2 preview revision `00002-bn8` were verified to display **70/87**, including the subtext `59 via MnGeo open parcels · 24 via county-direct sources · overlap counted once`. The existing sanitized publisher has propagated the 35-source aggregate to the public data bucket, but the production UI service was not replaced and authoritative GIS-provider scheduling remains disabled. Full evidence and methodology are documented in `docs/county-parcel-data-access-audit.md`.

## Hosted public dashboard

The shareable read-only dashboard is hosted at **https://gis-watchtower.clear-parcel.com**. Public traffic terminates on a Google Cloud external Application Load Balancer and is routed through a serverless NEG to the dedicated `gis-data-watchtower-public` Cloud Run service. The service reads only the sanitized production object at `gs://clearparcel-watchtower-dark-bit-503017-j7/production/aggregate-state.json`; its service account has no read access to the unified staging aggregate.

The `gis-data-watchtower-public-publisher` Cloud Run Job reads only the unified source aggregate, applies the public allowlist and forbidden-field validation, and writes only that production object. `gis-watchtower-public-publish` invokes the publisher every **10 minutes** using a separate scheduler identity. This is a publication schedule only and performs no provider checks. The final least-privilege publisher execution completed successfully in about **3m6s**.

The public rendering path strips operational provider URLs, raw change payloads, tracked values, schema/observation fingerprints, provenance, and worker telemetry. It preserves derived health/freshness summaries, county views, MN GAC completeness, the interactive county map, public catalog/contact references, and JSON/CSV/Excel exports. The private operational dashboard remains separate and is not made anonymously accessible.

Cloudflare remains authoritative for the parent DNS zone, but the Watchtower record is DNS-only; dashboard content and TLS termination are handled by Google Cloud. Cloud Armor is attached with a conservative **120 requests/minute/IP** throttle, load-balancer logging is enabled at full sampling, and Cloud Monitoring runs a one-minute HTTPS `/healthz` check plus availability and Cloud Run 5xx alert policies. Public publications are timestamped independently of source-data observation time, and `/healthz` fails once the production snapshot is more than **30 minutes** old.

## Validated cloud staging

A private Google Cloud staging deployment has been validated in `us-central1`.

The cloud execution profile currently handles **22 sources**. Against the corresponding local observations, validation found:

- 0 status differences;
- 0 feature-count differences;
- 0 schema-hash differences.

Four deployment-specific sources remain local-only because their providers do not accept the same Google Cloud egress path or TLS environment. Watchtower does not bypass those restrictions.

## Validated hybrid aggregation

The aggregate state was validated with:

- **26 total sources**
- **26 OK**
- **0 warnings**
- **0 errors**
- **22 cloud observations**
- **4 local observations**

Worker provenance, check timestamps, counts, and telemetry are retained in the aggregate state.

The hardened post-security-review build was revalidated on 2026-10-05. The Cloud Run worker completed **22/22 cloud sources OK** and the local worker completed **4/4 local-only sources OK**. The resulting aggregate remained **26/26 OK**, with **0 unassigned observations**; JSON, CSV, and Excel exports each represented all 26 sources.

### Validated MN GAC completeness observation

The current MN GAC feature was validated against MnGeo Plan Parcels Open on 2026-10-05:

- **59/87 counties represented** in the statewide open parcel layer;
- **28 counties explicitly reported as No data**, rather than 0%;
- **2,710,201 parcel records** in the denominator;
- **91/91 standard fields present** in the MnGeo source schema;
- **8 bounded grouped-statistics queries** at the default 12-field batch size;
- **42.92%** record-weighted population across all 91 fields;
- **78.37%** record-weighted population across the standard's Mandatory fields.

These percentages describe field population only. They are not pass/fail standards-compliance scores because Conditional, If Available, and Optional fields may legitimately be blank. The interactive county map, county field tables, JSON/CSV output, and Excel MN GAC sheets were validated against the stored observation.

## Concurrency-safe aggregate publishing

The shared aggregate object is now written with compare-and-swap semantics: Google Cloud Storage generation preconditions for cloud deployments, and an atomic lock-and-replace with retry for local/shared-filesystem deployments. A competing writer reloads the latest aggregate, re-merges, and retries instead of overwriting another worker's observations. A normal profiled `watchtower check` run (for example, the `local` execution profile) can publish directly to the configured shared aggregate store when opted in via `aggregate_object` or `WATCHTOWER_AGGREGATE_OBJECT`; this does not require a separate one-off script.

The private dashboard and the CSV/JSON/Excel snapshot exports now read the unified aggregate state. They show worker provenance, each worker's and source's last-success time (America/Chicago primary, UTC secondary), and reporting freshness against configurable thresholds, while keeping unhealthy sources (bad data) distinct from stale reporting (a worker or source overdue for a check). See `docs/hybrid-aggregation.md` for details and regression-test coverage.

Cloud Run startup latency was also characterized during this validation. A Job can remain in **Waiting for execution to start** for several minutes even after its image and resources are ready. Successful staging executions have taken roughly **2m30s to 4m15s** to reach Started. Operators should not treat this state alone as a failure during the first five minutes; explicit Failed conditions and the 15-minute job timeout are the authoritative failure bounds.

## Not yet enabled

The GIS-provider staging Cloud Run Job remains manually invoked. **No Cloud Scheduler automation is enabled for provider polling/check execution.** The only Scheduler automation is the separate 10-minute sanitized public-publication job. A local production monitoring worker remains active while parallel validation continues.

Automated local-worker publication to the shared aggregate and dashboard consumption of the aggregate state are implemented and have completed a successful one-cycle hardened hybrid validation. They have not yet completed a multi-day parallel validation run. The next release phase is that longer observation window, followed by scheduled cloud orchestration only once it passes.

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
See [resource isolation, validation and limitations](google-cloud-deployment.md#final-committed-preview-release-2026-10-06).


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
