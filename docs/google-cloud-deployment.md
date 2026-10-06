# Google Cloud deployment

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

The validated cloud profile processes 22 deployment sources with exact status/count/schema parity against the same local observations. Four provider-specific sources remain local-only because they reject or cannot validate requests from the Google Cloud environment. The project intentionally does not bypass those provider controls.

Hybrid aggregation was initially validated with 22 cloud observations plus 4 local observations, producing a 26-source authoritative state while preserving worker provenance. The hardened post-security-review build completed 22/22 cloud checks and 4/4 local checks with a 26/26 OK aggregate and complete JSON/CSV/Excel exports.

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

## Isolated county-profile preview release (2026-10-06)

The approved preview release now serves committed product tree `b342b5d` on
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
occurred. PRs #39/#42 remain draft and unmerged. Independent final review and final
documentation push/CI verification remain pending. Required validation: 186 tests
passed with ResourceWarning as error (5.315s), compileall and diff checks passed.

The dedicated preview bucket/object/identity and retained image are intended
preview resources; storage, Cloud Build/image retention and preview requests may
incur usage charges. Remove them only when the preview is retired; do not remove
production resources. Automatic approval review blocked even individual verified
raw temporary-file deletion. Private temporary cleanup remains pending user
assistance; release completion is not claimed until cleanup is verified.


## Final review product fixes (pending preview release)

Public sanitation now projects typed source, worker, count, catalog and MN GAC
leaves and completeness metrics. Raw completeness errors and unknown nested
payloads are omitted; a second sanitation pass preserves the public result.
All 59 inventories for the exact vetted MnGeo Plan Parcels Open official item
carry `mn-state-parcels` identity and a consistent product name. Fifty newly
linked inventories now retain their stable inventory IDs and approved links on
the row receiving that county's current observed count. Historical membership
cannot supply a missing observation or count; other products remain separate.

Offline composition produces 87 profiles and 348 category/product rows both
without observations and with a synthetic 59-member statewide observation.
For the unchanged aggregate used by old preview `00003-xzg`, removing its 50
duplicate rows projects 350 rows (400 minus 50). This is an offline projection,
not fresh live acceptance or a fixed row-count requirement. The deployed
`b342b5d` preview still has the previously measured 400 rows until a new committed
build, isolated redeploy and actual live validation. The product fixes pass 193
ResourceWarning-strict unittest tests, compileall and diff checks. Independent
fix review and required manual private temporary cleanup remain pending.
