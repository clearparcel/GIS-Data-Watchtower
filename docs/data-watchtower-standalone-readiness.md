# GIS Data Watchtower standalone/public-readiness plan

Watchtower has been extracted into a standalone repository and remains in private validation before public release.

## Standalone runtime surface

Required Watchtower files:

- `clearparcel/datawatch/`
- `config/data_sources.json`
- `requirements-watchtower.txt`
- `setup_watchtower_env.ps1` for the current Windows deployment

Standalone command:

```text
python -m clearparcel.datawatch --config config/data_sources.json check
```

The runtime uses environment-driven path overrides:

- `CLEARPARCEL_WATCHTOWER_ROOT`
- `CLEARPARCEL_WATCHTOWER_STATE_FILE`
- `CLEARPARCEL_WATCHTOWER_HISTORY_FILE`
- `CLEARPARCEL_WATCHTOWER_ALERTS_FILE`
- `CLEARPARCEL_WATCHTOWER_ALERTS_TEXT_FILE`
- `CLEARPARCEL_WATCHTOWER_CONFIG`
- `CLEARPARCEL_WATCHTOWER_DASHBOARD_USER`
- `CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD`

## Public repository gate

Do not make the extracted repository public until:

1. provider-use review remains current;
2. Aitkin/Morrison direct-source questions are resolved or excluded from public derivations;
3. CI passes on Windows and Linux;
4. public static output contains only sanitized, plain-language fields;
5. Internet dashboard exposure is either disabled or protected by authentication;
6. a LICENSE, SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md and public README are selected/reviewed;
7. public examples contain no local machine names, private paths, secrets, or operational state;
8. the extracted repository receives its own versioning/release policy.

## Current deployment

the current private Windows host remains the authoritative processor. A Windows scheduled deployment may invoke `run-datawatch.cmd`, which uses the isolated `.venv-watchtower` environment. The LAN dashboard may remain unauthenticated while bound only to the trusted private LAN; any future Internet exposure requires `CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD`.

## Cloud migration

The same standalone CLI/config surface is intended for a containerized runtime. Google Cloud Run remains the leading target, but no cloud-specific dependency has been added.
