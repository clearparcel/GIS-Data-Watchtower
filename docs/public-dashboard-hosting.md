# Public dashboard hosting

GIS Data Watchtower supports a separate, anonymous, read-only presentation service for sharing derived monitoring results without exposing the private operational dashboard.

## Production URL

The intended public hostname is:

`https://gis-watchtower.clear-parcel.com`

The hostname is served through Google Cloud's external Application Load Balancer and a Google-managed TLS certificate. DNS may remain with the parent `clear-parcel.com` zone; the Watchtower record is DNS-only and points at the Google load balancer.

## Architecture

```text
Internet
  |
  +-- gis-watchtower.clear-parcel.com
  |
Google external Application Load Balancer
  |
Serverless NEG
  |
Cloud Run: public read-only dashboard
  |
Google Cloud Storage: shared aggregate object
             ^
             |
       hybrid publishers
       +-- cloud worker
       +-- provider-restricted local worker
```

The public Cloud Run service uses `internal-and-cloud-load-balancing` ingress. Its direct `run.app` hostname is therefore not the intended public entry point.

## Public/private boundary

The anonymous service downloads only the shared aggregate object, immediately sanitizes it in memory/on ephemeral disk, and renders from the reduced representation.

Public output may include:

- source name, provider, category, health, record counts, and freshness;
- county coverage and public county contact information;
- public MnGeo catalog links and dates;
- MN GAC completeness statistics and the interactive county map;
- sanitized JSON, CSV, and Excel exports.

The public representation intentionally omits:

- provider connection URLs used by the monitoring engine;
- source fingerprints and schema hashes;
- tracked values and raw change payloads;
- provenance internals and request telemetry;
- private source registry/configuration;
- provider credentials and Secret Manager content;
- the private dashboard's manual refresh/check controls.

The service account used by the public dashboard should have read-only access only to the shared aggregate object, not to the broader Watchtower bucket or deployment secrets.

## Runtime

The container uses the standard Watchtower image with the public command:

```text
watchtower --config /app/config/example_sources.json public-dashboard --host 0.0.0.0 --port 8080
```

The example configuration is loaded only to satisfy the CLI's configuration contract. The public service does not use its source registry to contact providers. Its display state comes from the sanitized shared aggregate downloaded from Google Cloud Storage.

The public service refreshes the aggregate cache on a bounded interval (30 seconds in the production deployment). Page refreshes do not trigger external provider requests.

## Security expectations

- Keep the operational dashboard private behind its existing authentication/IAP controls.
- Keep public Cloud Run ingress limited to internal traffic and Google Cloud Load Balancing.
- Do not grant the public service account Secret Manager access.
- Keep the DNS record unproxied when Google is terminating TLS at the load balancer.
- Preserve the sanitized-state regression tests before deployment.
- Treat any addition to the public state schema as a security-sensitive change.
