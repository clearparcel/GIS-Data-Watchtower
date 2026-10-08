# Hybrid execution profiles

Provider connectivity can differ by execution environment. A failed cloud request is evidence about that request and environment; it does not establish a permanent cloud/datacenter restriction. Watchtower does not attempt to bypass provider controls. The [October 8 reassessment](cloud-provider-access-reassessment-2026-10-08.md) found valid Google Cloud responses from all four sources then assigned locally. Subsequent actual worker validation connected [USDA](usda-cloud-connection-2026-10-08.md), [Rice and Beltrami](county-cloud-migration-2026-10-08.md) to the cloud profile. Private registry version 12 assigns all 35 sources to cloud, while the saved aggregate retains its prior observations until a saving worker run. Cloud-only validation and inactive-worker retirement remain operational follow-up work in the [readiness review](codex-cloud-readiness-review-2026-10-08.md).

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

## Candidate validation

Use the current private registry and identical candidate package for both profiles. [The offline manifest and receipt workflow](watchtower-remediation-2026-10-07.md#hybrid-candidate-and-validation-preparation) checks inventory, runtime identity, provenance, and public arrival without running providers. The older authoritative 26-source local task remains unchanged; five distinct daily cycles and explicit activation approval remain pending.
