# Versioning and release policy

The current production runtime is **v0.1.1**, built from merged code commit
`8099ee18ec48714b33a9e998b414ea9ee0cf7d8e`. The user explicitly authorized
waiving the required multi-day staging gate for this rollout on 2026-10-07;
that gate remains incomplete and is not recorded as passed. For future releases,
the deployed runtime changes after CI and applicable staging validation pass,
or after a separately documented owner-authorized exception, followed by merge
and deployment.

## Versioning

The project follows Semantic Versioning intent:

- **patch**: backward-compatible fixes and documentation/security maintenance;
- **minor**: backward-compatible capabilities or supported adapters;
- **major**: incompatible configuration, storage-schema, CLI, or public-output contract changes.

Before 1.0, minor releases may include carefully documented breaking changes
when necessary. Patch releases contain backward-compatible fixes and
maintenance; major releases signal incompatible configuration, storage-schema,
CLI, or public-output changes.

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

## Visible application identity

Every public page footer displays the package version, the first seven characters of the source commit, and the build environment. Source checkouts prefer their matching `pyproject.toml` version over stale installed metadata; installed wheels use distribution metadata. The full commit is available in the label's tooltip. This identifies application code independently of provider checks and public data publication timestamps.

Container builds must pass `--build-arg WATCHTOWER_BUILD_REVISION=<full commit SHA>` and `--build-arg WATCHTOWER_BUILD_ENVIRONMENT=preview` or `production`, as appropriate. Docker writes this identity into packaged `build_info.json`; it is not inferred from runtime Git state or overwritten by runtime environment variables. Build a clean committed checkout and deploy its immutable image digest. Missing identity is displayed honestly as `build unknown · Development`, including ordinary source runs. The package version remains canonical in `pyproject.toml` and changes according to the policy above; each deployed commit remains distinguishable between semantic releases.

## Security fixes

Until the first stable release, supported security fixes are applied to current `main`. See `SECURITY.md` for private reporting.
