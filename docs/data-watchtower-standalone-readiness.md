# GIS Data Watchtower standalone/public-readiness status

Last reviewed: **2026-10-05**

GIS Data Watchtower has been extracted into this standalone **public, MIT-licensed** repository. This document is retained because earlier project documentation links to the original readiness plan; it now records the current standalone boundary and the completed public-release gate.

## Standalone runtime surface

Core runtime files:

- `clearparcel/datawatch/`
- `config/example_sources.json`
- `pyproject.toml`
- `Dockerfile`
- optional Windows helper: `setup_watchtower_env.ps1`

Install:

```bash
python -m venv .venv
# activate the environment
python -m pip install -e .
```

For Google Cloud Storage support:

```bash
python -m pip install -e ".[gcs]"
```

Run:

```text
watchtower --config config/example_sources.json check
```

See [configuration.md](configuration.md) for supported configuration keys and environment variables.

## Public-repository boundary

The repository intentionally contains:

- provider-neutral example source configuration;
- monitoring, aggregation, dashboard, export, and storage code;
- Minnesota county reference/contact provenance used by the dashboard;
- tests and deployment documentation.

It intentionally does **not** contain:

- private production provider registries;
- credentials or API secrets;
- workstation-specific operational state;
- private GCP resource identifiers or runtime secrets;
- raw parcel-owner/assessment datasets.

Deployment-specific provider configuration belongs outside the public repository.

## Completed public-release gate

The repository is already public. The original release prerequisites are complete:

- MIT license present;
- SECURITY, CONTRIBUTING, and Code of Conduct present;
- Windows/Linux CI active;
- public examples sanitized;
- dashboard defaults private and Internet/wildcard binding fails closed without authentication;
- static publication uses a reduced public schema;
- provider-compliance guidance is documented;
- versioning/release policy is documented in [release-policy.md](release-policy.md).

Aitkin and Morrison provider-use questions remain tracked as **deployment/provider constraints**, not blockers to repository visibility, because the public repository does not ship the private production source registry or redistribute those providers' raw data.

## Current deployment posture

A local production schedule remains authoritative while a private hybrid staging deployment is validated over multiple daily cycles. Cloud Run and GCS have passed one-cycle hardened validation; Authoritative GIS-provider scheduling remains disabled pending the multi-day validation gate; the separate sanitized publisher has a recorded 10-minute schedule.

See [current-status.md](current-status.md) and [google-cloud-deployment.md](google-cloud-deployment.md).
