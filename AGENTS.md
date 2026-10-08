# AGENTS.md

## Scope and authority

This file applies to the entire GIS Data Watchtower repository.

- Authoritative machine: **GERTKEN-PC**.
- Authoritative repository: `C:\Users\sgert\source\repos\GIS-Data-Watchtower`.
- Do **not** use `DESKTOP-FVRB1SB` for Watchtower work.
- Treat the checked-out branch, `STATUS.md`, `docs/current-status.md`, and current GitHub state as the operational source of truth.
- Preserve existing dirty work. Before editing, inspect `git status`, the current branch, and recent commits.

Codex Cloud may perform repository coding, offline tests, documentation, and
synthetic dashboard previews. GERTKEN-PC remains the authoritative operational
machine. Follow [the cloud development guide](docs/codex-cloud-development.md).
Cloud setup must use synthetic data and local storage, without production
credentials, private registries, provider polling, or authoritative scheduling.
Keep CCE workflows callable and authority-bound; the temporary Website-only CCE
exception does not apply to Watchtower.

## Approval boundaries

Do not perform any of the following without explicit user approval in the current task:

- merge a pull request;
- push directly to `main`;
- replace or deploy the production UI/service;
- enable, modify, or create authoritative GIS-provider scheduling;
- make production data/configuration writes;
- weaken provider-compliance, security, authentication, or rate-limit controls.

Staging changes are allowed only when the user has asked for staging work. Keep preview/staging and production clearly separated.

## Public repository vs private deployment configuration

The GitHub repository is public. Deployment-specific source registries, credentials, tokens, secrets, private configuration, and temporary exports must remain private.

- Never commit Secret Manager values, private source registries, credentials, tokens, service-account keys, or local environment files.
- Prefer Secret Manager and runtime environment configuration for deployment-specific settings.
- Temporary copies of private configuration must stay untracked and be deleted when the task is finished.
- Before committing, inspect `git status`, `git diff`, and the staged diff for accidental private material.

## Provider compliance

Watchtower is a low-frequency monitoring system, not a bulk downloader or scraper.

- Prefer official county/state GIS endpoints, open-data downloads, ArcGIS REST/FeatureServer/MapServer services, WMS/WFS, and documented APIs.
- Do not scrape human-facing property-search or parcel-viewer pages.
- Do not bypass authentication, referrer restrictions, TLS validation, rate limits, robots/provider controls, or network restrictions.
- Treat HTTP 429 as a provider stop/backoff signal.
- Do not infer that a publicly reachable viewer/backend endpoint is authorized for unattended monitoring.
- When official fee, license, release, or request policies conflict with technical reachability, fail closed and document the source as held pending clarification.
- Keep provider requests bounded. Default GIS-provider cadence is daily unless documented provider terms and operational need justify otherwise.
- Prefer metadata, schema, feature-count, freshness, and small bounded samples over bulk retrieval.

## Parcel-access and monitoring model

Keep these concepts separate:

1. **County-direct parcel access** — how the county itself makes parcel GIS data available.
2. **Statewide open coverage** — whether the county is represented in MnGeo Plan Parcels Open.
3. **Watchtower monitoring coverage** — whether Watchtower actively observes the county through a county-direct source, MnGeo Plan Parcels Open, or both.

Do not overload runtime monitoring health with research conclusions.

- Persistent parcel-access research lives in `clearparcel/datawatch/minnesota_county_parcel_access.json`.
- Research schema/validation lives in `clearparcel/datawatch/parcel_access.py`.
- Runtime source health and worker state remain separate from the research dataset.
- A county is actively checked when it is observed through a county-specific source, MnGeo Plan Parcels Open, or both; overlap is counted once.
- Do not hard-code statewide coverage counts when they can be derived from the current aggregate.
- Until official evidence changes, **Blue Earth, Faribault, Kandiyohi, and Lincoln** remain `hold-for-terms` for unattended county-direct parcel monitoring.

## Hybrid execution

Watchtower supports cloud and local execution profiles.

- Respect each source's `execution_profiles` assignment.
- If a provider rejects cloud/datacenter access, keep that source local-only or remove it; do not work around the restriction.
- Shared hybrid aggregate writes must preserve compare-and-swap/concurrency protections.
- Preserve worker provenance, freshness, and source-health separation.
- The sanitized public publisher is not a GIS-provider poller; its publication cadence is independent of provider-check cadence.

## Development practices

- Work on a feature branch and use pull requests; do not rewrite unrelated history.
- Make the smallest change that solves the task.
- Keep code, tests, README/STATUS/current-status, and relevant docs synchronized.
- Prefer derived metrics to duplicated constants.
- Add regression tests for bugs and policy-sensitive behavior.
- Avoid large dependency additions unless clearly justified.
- Do not leave temporary probe jobs, temporary secrets, private config copies, build contexts, diagnostic outputs, or throwaway virtual environments behind.

## Required validation

For repository changes, run:

```text
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m compileall -q clearparcel tests
git diff --check
```

For deployment/staging changes, also validate the applicable execution profile(s), source-level results, aggregate worker provenance, and rendered dashboard metrics. Do not treat a successful container exit alone as proof that every source passed.

## Documentation

Update documentation when behavior, architecture, deployment state, source coverage, or provider policy changes.

Key references:

- `README.md`
- `STATUS.md`
- `docs/current-status.md`
- `docs/county-parcel-data-access-audit.md`
- `docs/hybrid-execution.md`
- `docs/hybrid-aggregation.md`
- `docs/google-cloud-deployment.md`
- `docs/configuration.md`

When a current factual statement conflicts with older prose, reconcile the documentation instead of preserving stale text.
