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
Google Cloud Storage: production/aggregate-state.json (sanitized)
             ^
             |
Cloud Run Job: public aggregate publisher
             ^
             |
Google Cloud Storage: unified private aggregate
             ^
             |
       hybrid publishers
       +-- cloud worker
       +-- provider-restricted local worker
```

The public Cloud Run service uses `internal-and-cloud-load-balancing` ingress. Its direct `run.app` hostname is therefore not the intended public entry point.

## Public/private boundary

The anonymous service reads only the sanitized production aggregate. A separate non-public publisher job reads the unified aggregate, applies the public allowlist, validates that forbidden operational fields are absent, and writes the reduced snapshot to the production bucket. The dashboard never needs access to the private aggregate or provider registry.

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

Use three separate identities: the public dashboard service account reads only the sanitized production aggregate object; the publisher service account reads only the unified source aggregate and writes only the sanitized production aggregate; the scheduler identity can only invoke the publisher job. None of these identities needs provider credentials or broad project-level roles.

## Runtime

The container uses the standard Watchtower image with two public-serving commands:

```text
watchtower public-dashboard --host 0.0.0.0 --port 8080
watchtower public-publish --json
```

Neither command loads the private source registry or contacts a GIS provider. The public dashboard reads the sanitized production aggregate from Google Cloud Storage. The publisher reads the unified aggregate, sanitizes it, validates the reduced schema, and writes the production object.

The public dashboard refreshes its local aggregate cache on a bounded interval (30 seconds in the production deployment). A separate Cloud Scheduler job may invoke only the publisher job every five minutes. That schedule is a publication cadence, not a GIS-provider polling cadence, and does not replace the validation gate for authoritative Watchtower monitoring schedules.

## Security expectations

- Keep the operational dashboard private behind its existing authentication/IAP controls.
- Keep public Cloud Run ingress limited to internal traffic and Google Cloud Load Balancing.
- Do not grant the public service account Secret Manager access.
- Keep the DNS record unproxied when Google is terminating TLS at the load balancer.
- Preserve the sanitized-state regression tests before deployment.
- Treat any addition to the public state schema as a security-sensitive change.
