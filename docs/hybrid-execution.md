# Hybrid execution profiles

Some public GIS providers accept requests from local/residential or organizational networks but reject cloud-datacenter egress. Watchtower does not attempt to bypass those controls.

A source may optionally declare:

```json
"execution_profiles": ["cloud"]
```

or:

```json
"execution_profiles": ["local"]
```

Sources without this field run only in ordinary unprofiled checks. When a worker requests a profile, only sources explicitly tagged for that profile (or `"any"`) run. This prevents one hybrid worker from overwriting another worker's observations.

Use `watchtower check --execution-profile local` for a local worker. Cloud jobs default to the `cloud` profile and can override it with `WATCHTOWER_EXECUTION_PROFILE`.

The built-in private dashboard requires `WATCHTOWER_EXECUTION_PROFILE` or `dashboard_execution_profile` when any configured source has profile assignments. Only `cloud` and `local` are accepted. Manual refresh passes that profile to the same source filter as worker checks, including `any` sources and excluding unassigned sources. Unprofiled legacy configurations remain supported. A separate deployment wrapper may disable refresh entirely; this requirement applies to the built-in handler.

Worker run locks belong to the process, independent of file age, and recover immediately when the process exits. Lock files persist and must not be deleted while a worker could be active. Stop all old-version workers before upgrading the local lock protocol; see [upgrade instructions](review-fixes-2026-10-06.md#upgrade-and-release-validation).

This is intended for respectful hybrid deployments, not for circumventing provider blocks. If a provider rejects cloud traffic, mark that source local-only or remove it.
