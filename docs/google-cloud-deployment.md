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

## Scheduling

Start with **daily** execution. County parcel and similar GIS datasets generally do not justify high-frequency deep polling. Increase frequency only when provider terms and operational need support it.

## Migration

Run cloud and local processing in parallel before changing production. Compare source status, counts, change events, execution time, and generated snapshots for multiple scheduled runs.


## Validated staging behavior

As of 2026-10-04, a private Cloud Run Job deployment in `us-central1` has been validated with Google Cloud Storage persistence and Secret Manager-provided deployment configuration.

The validated cloud profile processes 22 deployment sources with exact status/count/schema parity against the same local observations. Four provider-specific sources remain local-only because they reject or cannot validate requests from the Google Cloud environment. The project intentionally does not bypass those provider controls.

Hybrid aggregation has also been validated: 22 cloud observations plus 4 local observations merge into one 26-source authoritative state while preserving worker provenance.

Cloud Scheduler is intentionally not enabled yet. See `current-status.md`.
