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
DNS -> Google external Application Load Balancer -> serverless NEG -> Cloud Run public dashboard -> shared GCS aggregate
```

The public service runs `watchtower public-dashboard`, performs no provider polling, and accepts no state-changing POST actions. It downloads the shared aggregate, reduces it to a public allowlist, and renders from that reduced copy. Operational provider URLs, raw change payloads, tracked values, fingerprints, provenance, and worker telemetry are excluded.

Use a dedicated runtime service account with `storage.objects.get` access scoped to the aggregate object rather than granting bucket-wide access. Restrict Cloud Run ingress to `internal-and-cloud-load-balancing`; anonymous access is then provided only through the Google load-balancing path. The private operational dashboard remains behind its own authentication boundary.

The ClearParcel deployment is published at **https://gis-watchtower.clear-parcel.com**. Its Cloudflare record is DNS-only; Cloudflare provides authoritative DNS but does not proxy the application traffic.

## Scheduling

Start with **daily** execution. County parcel and similar GIS datasets generally do not justify high-frequency deep polling. Increase frequency only when provider terms and operational need support it.

## Migration

Run cloud and local processing in parallel before changing production. Compare source status, counts, change events, execution time, and generated snapshots for multiple scheduled runs.


## Validated staging behavior

As of 2026-10-05, a private Cloud Run Job deployment in `us-central1` has been validated with Google Cloud Storage persistence and Secret Manager-provided deployment configuration.

The validated cloud profile processes 22 deployment sources with exact status/count/schema parity against the same local observations. Four provider-specific sources remain local-only because they reject or cannot validate requests from the Google Cloud environment. The project intentionally does not bypass those provider controls.

Hybrid aggregation has also been validated: 22 cloud observations plus 4 local observations merge into one 26-source authoritative state while preserving worker provenance. The hardened post-security-review build completed 22/22 cloud checks and 4/4 local checks with a 26/26 OK aggregate and complete JSON/CSV/Excel exports.

### Cloud Run execution startup latency

Cloud Run may report **Waiting for execution to start** for several minutes after the image is imported and resources are provisioned. This is a control-plane scheduling/provisioning phase; the Watchtower container has not necessarily started yet.

In the validated staging environment, successful executions have required approximately **2m30s to 4m15s** to reach the Started condition. Therefore:

- do not cancel solely because Started is still Unknown during the first five minutes;
- inspect execution conditions and regional/control-plane evidence if startup exceeds roughly 5–7 minutes;
- investigate a sustained 7–10 minute wait, but do not infer application failure without a Failed condition or application logs;
- use the configured 15-minute task timeout as the final execution bound.

This guidance prevents normal provisioning latency from being mistaken for a Watchtower hang.

Cloud Scheduler is intentionally not enabled yet. See `current-status.md`.
