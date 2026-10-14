# Versioning and release policy

The current validated production application release is **v0.2.3**, deployed
October 13 (see the [current release and rollback record](release-v0.2.3.md)).
The [v0.2.2 release](release-v0.2.2.md) is the immediate rollback baseline;
older release records are in the [archive](README.md#historical-engineering-and-release-records).
Daily cloud provider polling was
separately approved and activated on October 10; application publication does
not reschedule it. The multi-day observation study remains incomplete. Future
runtime changes require CI and applicable staging validation, or a separately
documented owner-authorized exception, followed by merge and deployment.

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

Public page footers display **only the semantic application version** (for example, `v0.2.1`), with no build SHA or environment tag. The About Watchtower section explains the mission, links to GitHub, and includes a brief disclaimer. The canonical version is the `[project].version` field in `pyproject.toml`; source checkouts prefer it over stale installed metadata, while installed wheels use distribution metadata.

**Every coordinated production deployment containing updated application code must use a new, strictly higher semantic version than the version currently visible on the deployed public site.** The operator must bump `pyproject.toml` in the release candidate before building, run `python scripts/check_release_version.py` against the live public version, retain the preflight evidence, deploy the vetted immutable image, and then verify the publicly displayed version and release record. The script fails closed if the live version cannot be verified, the candidate is not a valid semantic version, or the candidate is not strictly newer. Run this preflight once per coordinated release (before any public/private service rollout), not independently for each service in that release. Preview builds are not production releases.

The source commit and build environment **remain inside immutable `build_info.json` and release/provenance records**, and may continue to inform optional analytics. They are intentionally not shown in the public footer. Container builds still require `WATCHTOWER_BUILD_REVISION` (full commit SHA) and `WATCHTOWER_BUILD_ENVIRONMENT` (`preview` or `production`). The production source package and visible version must agree. Build only from a clean, committed checkout; do not infer revision identity from the runtime Git state.

**v0.2.3 was deployed and verified on October 13, 2026.** The release preflight blocks redeployment of an unchanged v0.2.3 candidate; the next coordinated application-code release must use a strictly newer semantic version. The owner set **v0.3.0** as the next release; its [candidate record](release-v0.3.0.md) lists the contents and the release gate.

## Security fixes

Until the first stable release, supported security fixes are applied to current `main`. See `SECURITY.md` for private reporting.
