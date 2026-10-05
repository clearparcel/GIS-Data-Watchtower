# Versioning and release policy

GIS Data Watchtower is currently **pre-1.0**. The package version is `0.1.0.dev0`.

## Versioning

The project follows Semantic Versioning intent:

- **patch**: backward-compatible fixes and documentation/security maintenance;
- **minor**: backward-compatible capabilities or supported adapters;
- **major**: incompatible configuration, storage-schema, CLI, or public-output contract changes.

Before 1.0, minor releases may still include carefully documented breaking changes when necessary.

## Main branch

`main` is the current development and supported security branch. Changes should arrive through reviewed pull requests with passing CI unless an emergency repository-owner fix requires otherwise.

CI covers supported Windows and Ubuntu runners on Python 3.12, 3.13, and 3.14 plus a Linux container smoke test.

## Release criteria

A tagged release should:

1. pass the full CI matrix;
2. have current README/status/configuration documentation;
3. contain no deployment secrets or private provider registry;
4. document material configuration or public-output changes;
5. retain provider-compliance boundaries;
6. pass any required private staging validation for changes that affect storage, cloud execution, aggregation, or provider I/O.

Tags use `vMAJOR.MINOR.PATCH`. GitHub release notes should summarize user-visible changes and known limitations.

## Security fixes

Until the first stable release, supported security fixes are applied to current `main`. See `SECURITY.md` for private reporting.
