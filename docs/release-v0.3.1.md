# GIS Data Watchtower v0.3.1

**PREPARED — not deployed.** The owner requested merge and deployment after
PR #105 passed hosted CI. This release preparation follows its merge,
`cd2e071672740bebc10955720d8bd00d5fa89899`.
The production public footer was read on October 20, 2026 and showed v0.3.0.
The required version increment is v0.3.1.

## Changes and scope

- WT-01 (#102): shared county field projection corrects scan/schema labels
  across public/private pages and county exports. Explicit false, unknown,
  unavailable and scanned zero-population values remain distinct.
- Offline operations tools (#103–#105): saved-run triage, monitoring-authority
  evidence matching and an isolated synthetic local restore/CAS rehearsal.
  These tools do not activate monitoring or establish operational acceptance.
- This release changes dashboard service images only. Provider and publisher
  jobs, schedules, source assignments, registry data, credentials, IAM, ingress,
  IAP and other service settings retain their existing configuration.

The offline command scripts remain repository tools; the service Dockerfile
does not package `scripts/` as operational commands. Updating the dashboards
does not execute those tools. There are no data migrations.

## Evidence before promotion

The implementation candidate ran 575 tests with 3 platform skips; all required
checks passed. PR #105 hosted CI passed at
`fb9ba642948b23401360d92d153ae3de8b9dc892`, and its application diff received
an owner-requested bounded CCE review with no actionable findings.
The versioned candidate also passed 575 tests with 3 platform skips in
29.238 seconds, with required Node tests enabled, compilation, status-sync and
whitespace checks. The live release preflight passed: v0.3.0 to v0.3.1.
This versioned release requires its own hosted CI on the exact committed head.

The initial Cloud Run metadata read required operator reauthentication.
The owner restored the session; subsequent reads verified both v0.3.0 services:
public revision `gis-data-watchtower-public-00031-ciw` and private revision
`gis-data-watchtower-dashboard-00033-qor`, each receiving 100% traffic.
Their immutable digests match [the previous release record](release-v0.3.0.md).
Full runtime/security/traffic snapshots are retained in private evidence.
No rollout has occurred.

Before building or promoting:

1. Verify the expected account/project and both live dashboard services.
   Capture full existing traffic allocations, immutable image digests,
   non-image runtime configuration and security settings in private evidence.
2. Run `python scripts/check_release_version.py` once for the coordinated
   release. It must confirm a strictly newer version before any promotion.
3. Build from a clean committed archive with the exact source SHA and
   `WATCHTOWER_BUILD_ENVIRONMENT=production`; record both image digests.
   Preserve the private wrapper from the verified predecessor and validate
   its hash, imports and referenced dashboard attributes in the new image.
4. Verify each image reports v0.3.1, the exact source SHA and production
   environment. Recheck compatibility with existing snapshots and exercise
   the WT-01 synthetic cases. Record actual results, not assumed compatibility.
5. Create image-only candidate revisions with zero traffic. Confirm Ready,
   exact image identity, unchanged settings and retained predecessor traffic.
   Check the candidate services before moving traffic.

## Acceptance and rollback

Promote each verified dashboard revision and read back its traffic/image
identity. Verify public routes, security headers, county scan labels and
JSON/CSV/XLSX export semantics against retained observations. Authenticate to
the private dashboard and verify county pages, filters and exports, including
the Cass-shaped scan-label case. An anonymous login redirect does not establish
private application acceptance.

Keep publication freshness separate from provider-check freshness and record
any provider outage independently of application behavior. Do not run provider
or publisher jobs merely to refresh acceptance evidence.

Retain the exact predecessor revisions and traffic mapping. If a candidate
fails before promotion, retain predecessor traffic. If a promoted service has
a release-caused regression, stop the second promotion and restore that service's
captured predecessor traffic, then independently verify the restored identity
and behavior. Report partial rollout explicitly.

The promotion receipt must include the exact source SHA, CI and build IDs,
digests, before/after revisions and traffic, UTC observation times, public and
authenticated private checks, unchanged settings and rollback result if used.
Until that evidence exists, this record remains PREPARED.
