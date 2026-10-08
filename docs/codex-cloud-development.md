# Codex Cloud development

Use Codex Cloud for coding, offline tests, documentation, and synthetic dashboard
previews. The Cloud Run services and GERTKEN-PC provider workers keep their
existing operational roles and execution profiles. This guide prepares the
repository. A private pilot has subsequently been published and preparation
checks passed, but fresh-task restoration remains blocked by provisioning.
See the [October 8 readiness review](codex-cloud-readiness-review-2026-10-08.md)
for exact evidence and remaining gates. Provider assignment to Google Cloud
Run does not supply this development environment with operational authority.

## Environment setup

Provide Python 3.13, Node 24+, CA certificates, curl, and Bash. Python 3.12+ is
supported; select an alternative interpreter with `WATCHTOWER_DEV_PYTHON`.
Node is required because JavaScript regression tests otherwise skip when it is
absent. Use the optional GCS extra to match the CI dependency environment without
granting a Google Cloud identity:

```bash
bash setup_watchtower_env.sh --gcs
source .venv-watchtower/bin/activate
```

The bootstrap installs editable code through `constraints.txt`, runs dependency
checks, and invokes CLI help. It performs no provider checks or state publication.
For core-only development, omit `--gcs`. Restrict setup networking to required
dependency sources; offline development requires no provider access.

Keep production credentials, service-account keys, private source registries,
local environment files, and production state out of this environment. Do not
mount operational storage or inherit an operational environment configuration.
The repository is public.

## Synthetic dashboard preview

From the repository root in the activated virtualenv:

```bash
python scripts/prepare_cloud_development.py
bash scripts/preview_cloud_dashboard.sh
```

Open `http://127.0.0.1:8080` through the environment's supported preview UI. The
server remains bound to loopback. If that UI cannot reach loopback, use a static
build or resolve the preview capability before changing exposure controls.

The generator creates `datawatch/cloud-development/`, which is ignored by Git.
It contains an empty polling configuration, a synthetic local storage object,
and empty history. It creates current timestamps for the cloud worker, a local
worker three days overdue with healthy last-known data, and a warning source.
Every source has an invented development name; none has a provider URL or county
assignment. Existing county research remains the repository's reference data;
these observations make no new county coverage claims.

The launcher explicitly chooses local storage and the synthetic object and
cache paths. It clears inherited state path overrides and GCS bucket/prefix
settings. Public-dashboard refresh reads the local fixture only.

Preparation refuses to overwrite an existing directory. To renew timestamps,
stop the preview, verify that `datawatch/cloud-development/` contains only the
generated fixture/cache, remove that directory, and rerun preparation. For tests
or a separate static build, the generator accepts `--output` pointing to a new
directory. The launcher always uses the default fixture location.

For a static dashboard instead of a server:

```bash
watchtower --config datawatch/cloud-development/config.json dashboard-build --output datawatch/cloud-development/site --json
```

Synthetic status intentionally returns warning exit code 1. Its stale local
worker and source warning are development scenarios, not production findings.

Do not run `check`, `cloud-job`, or `public-publish` as bootstrap or preview
commands. The Docker image's default command is `cloud-job`; container smoke
validation must override it with `--help`. Operational provider polling and
scheduling remain separate authorized work, with daily cadence, 429 backoff,
terms holds, local-only restrictions, and concurrency protections intact.

## Acceptance checks

### Optional offline public snapshot replay

After synthetic setup, an already sanitized public snapshot can be supplied as
a local file for a separate UI replay. Do not use a private aggregate or registry.
The importer makes no network requests, rejects operational fields, applies the
typed public projection, limits input to 8 MiB, and refuses an existing output
directory. It retains observation and publication clocks, so old snapshots can
correctly render as stale. It supplies an empty polling configuration and local
storage; this is not a source of operational observations.

```bash
python scripts/import_public_development_snapshot.py --input public-snapshot.json --output datawatch/public-replay
watchtower --config datawatch/public-replay/config.json dashboard-build --output datawatch/public-replay/site --json
```

Keep replay files under the ignored `datawatch/` tree. Setup and restoration
validation still use synthetic fixtures. Public replay requires no production
credentials or provider access and does not change the default preview launcher.

### Required checks

```bash
node --version
python -m pip check
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m compileall -q clearparcel tests scripts
python scripts/sync_current_status.py --check
watchtower --config config/example_sources.json status --json
git diff --check
```

Require the Node tests to execute. Verify preview metrics, including three
synthetic sources, two workers, and separate stale reporting/source health.
Keep Windows CI for the operational local workers and existing container,
dependency audit, CodeQL, and supply-chain checks.

Before declaring migration complete, select a verified GitHub revision, verify
these checks in a fresh cloud task and a restored/cached task, and establish a
real authority-bound CCE MCP workflow there. SDK installation alone is not CCE
attachment. The Website pilot's temporary CCE exception does not cover Watchtower.
The published Watchtower pilot's temporary, specifically approved exception
covers its synthetic validation only; it does not extend default CCE requirements
for normal coding or operational work. The desktop launcher created a fresh
validation task, but its recorded runtime remained pending/offline. Resolve
provisioning and verify restoration/CCE capabilities before relying on cloud
execution.

Production rollouts and the separately authorized multi-day hybrid validation
gate remain operational work under the existing approval boundaries.
