# Google Cloud deployment

Operational deployment evidence below is dated. Latest recorded preview `00007-zfh` serves `5aac504`, before the [repository-review fixes](repository-review-2026-10-06.md); no live provider/deployment validation was performed in that review. See [current status](current-status.md).

GIS Data Watchtower can run as a scheduled **Cloud Run Job** while retaining the same CLI and monitoring engine used locally.

## Architecture

Cloud Scheduler → Cloud Run Job → GIS providers → Google Cloud Storage

The job downloads the last saved state/history into ephemeral `/tmp`, performs one bounded Watchtower run, then uploads the resulting artifacts back to Cloud Storage. Dashboard hosting remains separate from provider polling.

## Required environment

- `WATCHTOWER_STORAGE=gcs`
- `WATCHTOWER_GCS_BUCKET=<bucket>`
- optional `WATCHTOWER_GCS_PREFIX=<prefix>`
- optional `WATCHTOWER_WORKDIR=/tmp/watchtower`

Use the Cloud Run Job's service account and IAM instead of JSON service-account keys. The service account needs object read/write access only to the Watchtower bucket/prefix.

## Container

```bash
docker build -t gis-data-watchtower .
docker run --rm gis-data-watchtower --config config/example_sources.json status --json
```

The default container command runs:

```text
watchtower --config config/example_sources.json cloud-job
```

## Cloud Run Job

Example outline:

```bash
gcloud run jobs create gis-data-watchtower \
  --image=REGION-docker.pkg.dev/PROJECT/REPOSITORY/watchtower:TAG \
  --region=REGION \
  --set-env-vars=WATCHTOWER_STORAGE=gcs,WATCHTOWER_GCS_BUCKET=BUCKET \
  --task-timeout=15m \
  --max-retries=0 \
  --service-account=SERVICE_ACCOUNT
```

Use `--max-retries=0` initially: Watchtower already implements provider-aware retry behavior, and an infrastructure-level job retry can unnecessarily duplicate provider requests.

## Public read-only dashboard

ClearParcel's hosted public view uses a separate Cloud Run service from the private operational dashboard:

```text
DNS -> Google external Application Load Balancer -> serverless NEG -> Cloud Run public dashboard -> sanitized production GCS aggregate
                                                                                                      ^
                                                                                                      |
                                                Cloud Scheduler -> Cloud Run public publisher -> unified private GCS aggregate
```

The public service runs `watchtower public-dashboard`, performs no provider polling, accepts no state-changing POST actions, and reads only the sanitized production object. A separate `watchtower public-publish` Cloud Run Job reads the unified aggregate, reduces it to a public allowlist, validates that forbidden operational fields are absent, and writes the production object. Operational provider URLs, raw change payloads, tracked values, fingerprints, provenance, and worker telemetry are excluded.

Use separate least-privilege service accounts: the public dashboard receives `storage.objects.get` only for the production aggregate; the publisher receives source-object read plus production-object write; the Scheduler identity receives only `run.jobs.run` through the job's invoker binding. Restrict Cloud Run ingress to `internal-and-cloud-load-balancing`; anonymous access is then provided only through the Google load-balancing path. The private operational dashboard remains behind its own authentication boundary.

The ClearParcel deployment is published at **https://gis-watchtower.clear-parcel.com**. Its Cloudflare record is DNS-only; Cloudflare provides authoritative DNS but does not proxy the application traffic.

## Scheduling

Start provider-check execution at **daily** cadence. County parcel and similar GIS datasets generally do not justify high-frequency deep polling. Increase provider-check frequency only when provider terms and operational need support it.

The sanitized public publisher is different: it performs no provider requests and may run more frequently. The ClearParcel deployment currently uses a **10-minute** publication cadence (`3,13,23,33,43,53 * * * *`, read-only verification on 2026-10-06), selected to leave ample room around observed Cloud Run Job startup/runtime while keeping the public snapshot reasonably fresh.

## Migration

Run cloud and local processing in parallel before changing production. Compare source status, counts, change events, execution time, and generated snapshots for multiple scheduled runs.


## Validated staging behavior

As of 2026-10-05, a private Cloud Run Job deployment in `us-central1` has been validated with Google Cloud Storage persistence and Secret Manager-provided deployment configuration.

The historical October 5 cloud profile processed 22 deployment sources with exact status/count/schema parity against the same local observations. Four provider-specific sources remain local-only because they reject or cannot validate requests from the Google Cloud environment. The project intentionally does not bypass those provider controls.

Hybrid aggregation was initially validated with 22 cloud observations plus 4 local observations, producing a 26-source staging aggregate while preserving worker provenance. The hardened post-security-review build completed 22/22 cloud checks and 4/4 local checks with a 26/26 OK aggregate and complete JSON/CSV/Excel exports.

On **2026-10-06**, private staging registry version 7 added nine approved county-direct parcel sources outside the current MnGeo Plan Parcels Open footprint. Staging image `473157b` completed **31/31 cloud checks OK**. The local profile completed **4/4 OK**, and a generation-protected merge produced a **35/35 OK** aggregate with worker provenance `cloud=31` and `local=4`. The resulting county-monitoring model is **70/87 actively checked counties**: 59 via MnGeo, 24 via county-direct sources, and 13 overlapping. The separate public v2 preview was updated to `473157b` and confirmed to render **70/87**. Authoritative provider scheduling remains disabled.

### Cloud Run execution startup latency

Cloud Run may report **Waiting for execution to start** for several minutes after the image is imported and resources are provisioned. This is a control-plane scheduling/provisioning phase; the Watchtower container has not necessarily started yet.

In the validated staging environment, successful executions have required approximately **2m30s to 4m15s** to reach the Started condition. Therefore:

- do not cancel solely because Started is still Unknown during the first five minutes;
- inspect execution conditions and regional/control-plane evidence if startup exceeds roughly 5–7 minutes;
- investigate a sustained 7–10 minute wait, but do not infer application failure without a Failed condition or application logs;
- use the configured 15-minute task timeout as the final execution bound.

This guidance prevents normal provisioning latency from being mistaken for a Watchtower hang.

Authoritative GIS-provider scheduling remains disabled. Only the sanitized public publisher scheduler is enabled, as verified below. See `current-status.md`.

<a id="isolated-county-profile-preview-release-2026-10-06"></a>

## Initial isolated county-profile preview release (2026-10-06)

The initial approved preview release served committed product tree `b342b5d` on
`gis-data-watchtower-public-v2-preview-00003-xzg` (100% traffic), built by Cloud
Build `6a855dbe-f3f0-44d3-bfc3-f7d05b4b1bc3` from `git archive HEAD`.
Its immutable image digest is
`sha256:f713471388b024c62653e2ae15202b7e50cdfbacda074c177699c88e3953fc3a`.
The explicit command is `public-dashboard --host 0.0.0.0 --port 8080`.

The preview uses a dedicated private bucket
`clearparcel-watchtower-preview-dark-bit-503017-j7`, object
`preview/aggregate-state.json`, and dedicated identity
`gis-watchtower-preview@dark-bit-503017-j7.iam.gserviceaccount.com`.
Uniform bucket access and public-access prevention are enabled. The identity has
object-reader access conditioned on exactly that sanitized object; no production
bucket/identity bindings or raw aggregate permissions were added. No new scheduler
exists. A bounded private read of the unified aggregate was sanitized using the
committed publisher; publication time is `2026-10-06T17:15:59.241555+00:00`, while
actual aggregate/source dates remain unchanged. Manual republication must reread
the aggregate. After 30 minutes without republication, the preview correctly
reports overdue publication separately from source health.

Actual source-level validation found 35/35 OK, cloud=31/local=4, two healthy worker
summaries agreeing with their source counts and intact private source provenance.
Current coverage derives to 70/87 = 59 statewide + 24 direct - 13 overlapping.
Live JSON/CSV/decoded XLSX agree for 87 profiles, 400 category/product rows and
35 legacy source rows; all 87 individual county JSON profiles match statewide
JSON. Brown retains 18,393 polygon features; Winona retains 25,538 statewide
county records with its separate county-direct fee classification. Dodge retains
its actual file headers (4,221,438 bytes; modified 2026-09-08). Unknown dates and
counts remain null in JSON and blank in spreadsheet cells.

Actual Chrome Browser/CUA verified all 87 targets in eight map modes (696 panel
activations), four inventory groups, metric switching, Escape focus return,
Space activation, focus trapping and internal scrolling. Desktop 1920px page
width is 1905px and dialog width/scroll width 923/923; mobile 390px page width is
375px and dialog 349/349. Brown, Winona, viewer-only Cottonwood and all four held
counties passed on desktop/mobile. No external product/archive links were opened.
Publication reporting rendered Current; the open Winona dialog survived the
normal overview refresh interval. Research remains 216 reviewed/132 blocked/0
pending categories, 16 fully reviewed inventories and 15 complete profiles;
82 classifications (58 free/13 fee/11 viewer), five unresolved, 11 research holds.

External `/healthz` returns a Google-branded frontend 404 on both run.app
hostnames. The service is Ready with routes/configuration ready; the application
has no alternate health route. This is consistent with Cloud Run's documented
[reserved paths ending in z](https://docs.cloud.google.com/run/docs/known-issues#reserved-url-paths).
Local publication health tests pass, but external HTTP 200 health verification is
not claimed. No routing/security setting was changed to work around this.

Production public/private revisions remain `00006-82c`/`00011-t4l`; the existing
publisher scheduler remains enabled at `3,13,23,33,43,53 * * * *`, and provider
scheduling remains disabled. Production publication can independently advance its
object. No production write, provider check, activation, main push or merge
occurred. PRs #39/#42 remain draft and unmerged. Scoped final review and validated product/docs CI heads are recorded below;
manual temporary cleanup was verified complete on 2026-10-06. Required validation: 186 tests
passed with ResourceWarning as error (5.315s), compileall and diff checks passed.

The dedicated preview bucket/object/identity and retained image are intended
preview resources; storage, Cloud Build/image retention and preview requests may
incur usage charges. Remove them only when the preview is retired; do not remove
production resources. Automatic approval review blocked even individual verified
raw temporary-file deletion at that historical stage. Cleanup then awaited user
assistance; the user subsequently deleted the original folder and root verified
its absence on 2026-10-06. The denial remains historical evidence.


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


## Final committed preview release (2026-10-06)

Cloud Build `4a4003e0-8dc4-436b-99fc-f59cf8653225` built only a fresh
`git archive` of `5686013`. Preview `00004-sv8` serves 100% of traffic using
`sha256:bbb526e8d82f6669e2194bbfc1268e6eb6e189ab18174dc0d6dc2276436ba8b1`.
The existing dedicated preview bucket/object/identity and explicit public-dashboard
command are retained; no IAM, production service, provider or scheduling changes.
A fresh aggregate read stayed in process memory; only the committed sanitizer's
validated public projection was written. Actual publication time is
`2026-10-06T17:47:57.515129+00:00`; aggregate generation remains
`2026-10-06T11:11:40.540673+00:00`. No raw disk copy, date filling or provider polling.
Actual source/worker validation remains 35/35 OK, cloud=31/local=4 with two matching
worker summaries and private provenance. Live observed export total is 350 rows,
not a fixed constant. Aitkin's single official statewide product retains 43,024
records separately from its 42,996 direct-source records; approved links stay on
the stable inventory product. Final desktop/mobile screenshots were inspected.

The exact owned Cloud Build source upload was removed with its verified generation
precondition; follow-up returned not found. The original local Task8 temporary
folder was deleted by the user; root verified Test-Path returned False on
2026-10-06. Earlier automatic approval review denials remain historical. No new raw file was created for this release. The preview still
requires manual fresh republication after 30 minutes; external healthz remains a
Cloud Run frontend reserved-path limitation. Final browser follow-up availability
is limited as described above. Production revisions remain 00006-82c/00011-t4l,
production bucket IAM etag CAQ= and only existing publisher scheduler unchanged.
Scoped operational review found no new Critical/Important issues. Product head
5686013 CI runs 37506186256/37506177179 and docs head c2c97e2 runs 37507753259/
37507744905 succeeded. Evidence is pinned to these validated heads; the controller
checks the final PR head after publishing documentation. Manual cleanup was verified complete on 2026-10-06.


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
archive/build/sanitized/log cleanup was initially rejected by automatic approval
review with reason "blocked by policy"; no bypass or retry occurred. Later root
and implementer read-only `Test-Path` checks returned False for exact folder
`.cce-agent/task10-feedback-preview-dfacd72`. The user confirmed manual deletion, and
absence is verified on 2026-10-06. Task 10 release and cleanup are complete.
The original Task 8 folder was previously verified absent. Production stays public `00006-82c`/private
`00011-t4l`, bucket IAM etag `CAQ=`, sole existing publisher scheduler unchanged.
No production, provider scheduling, IAM expansion, main, merge or Astra action.
No CI claim is made for the forthcoming documentation head.

## Four-class code-only preview release (2026-10-06)

Reviewed committed `5aac504` was built from a public-only Git archive by Cloud
Build `ad255f2b-30e3-4950-9b64-dea7f29786ac` (SUCCESS, 52.4 seconds).
Existing preview `00007-zfh` serves 100% traffic, with Ready,
ConfigurationsReady and RoutesReady true, pinned to
`sha256:cfe2b3daf8147e51378b7818e8bdb459bd7f6472ec776bc11db5d56cb7017513`.
The explicit `watchtower public-dashboard --host 0.0.0.0 --port 8080` command,
existing identity, environment and sanitized storage object are preserved.
First candidate `00006-kmn` failed because PowerShell combined unquoted comma
arguments into one string; the CLI rejected it before command execution.
Corrected argument quoting produced `00007-zfh`; no default cloud-job ran.

This release did not read the raw aggregate or republish data. The existing
sanitized object generation `1791311397132173` remains unchanged, with actual
publication `2026-10-06T18:29:46.124951+00:00` and source generation
`2026-10-06T11:11:40.540673+00:00`. Public source state matched before/after:
35/35 OK, cloud=31/local=4, matching worker summaries and source check/success
facts. Coverage remains 70 = 59 statewide + 24 direct - 13 overlaps. MNGAC
contains 2,710,201 records, 91 fields and 59 covered counties. Internal exports
passed 87 county CSV rows, 350 source-category rows, 35 legacy rows, all 87
individual JSON profiles matching statewide profiles, and the expected eight
workbook sheets. No provider links were requested. Publication is correctly
overdue once the unchanged timestamp exceeds 30 minutes; source health is
reported separately.

Root browser acceptance passed the exact four-class legend plus No data.
Overview completeness checked all 87 fills with zero mismatches (42/8/9/0
across the four classes, 28 No data). MNGAC overall, mandatory, fields with
values and ANUMBERPRE each checked all 87 fills with zero mismatches; mandatory
had 24 above 70%, and fields with values had seven. ANUMBERPRE retained 45
true zeros and 28 distinct No data counties. At 390px, page width was 375/375,
legend 299/299 and Aitkin dialog 349/349; Enter opened the dialog and Escape
restored focus to Aitkin. Normal viewport reset was verified at 1047/1047.

Owned Cloud Build source upload was removed with exact generation-match
`1791312835856766`; follow-up returned 404. The intended image and preview
resources remain. Automatic approval review rejected root's native scoped
local workspace deletion with "blocked by policy"; the command did not run and
no bypass occurred. The user manually deleted the one public-only build/review
workspace; root verified its absence on 2026-10-06. Review records and screenshots
were preserved outside that temporary workspace.
Production remains public `00006-82c`/private `00011-t4l`, production bucket IAM
etag `CAQ=`, and the existing publisher scheduler configuration unchanged.
No production, main, merge, provider, scheduling, IAM expansion or Astra action.
Task 1's 196 strict tests and compileall passed; this documentation-only release
record did not repeat them. The capability-authorized bounded final review
passed with no substantiated findings. Reviewed head `7490135` passed CI runs
`37517186843` and `37517178118`; the controller checks the final PR head after
this cleanup-record update. No legacy CCE workflow is claimed by selector alone.
