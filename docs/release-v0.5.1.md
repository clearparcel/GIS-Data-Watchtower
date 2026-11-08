# GIS Data Watchtower v0.5.1

Release candidate, November 8, 2026. Production promotion is pending; the last
verified deployed application version is v0.5.0.

This patch incorporates PR #230's public-destination boundary for editor-enrolled
sources. It also preserves validated private snapshots on corrupt downloads,
exposes sync failure, bounds failed directory retries, handles every directory
CSV export consistently, and includes directory availability in public readiness.

Non-loopback operational dashboards now require authentication. Hosted IAP stays
read-only. County saves record a verified actor and timestamp atomically with the
edit, without publishing private audit data. The editor caches county lists and
reads bounded attachment headers; full downloads and scans retain hash checks.
Warm public views reuse validated bundled research.

Contributor setup, current release documentation, historical scanner acceptance,
branch disposition and personal checkout handling have been reconciled. Duplicate
timestamp parsing is consolidated without removing compatibility aliases.

## Candidate validation

- 1,081 offline tests passed with ResourceWarning errors and Node 24 required.
  Compileall, dependency consistency, status/source-version checks and diff
  checks passed on Python 3.12.
- A fresh independent investigator traced the transport and authentication
  boundaries. A separate fresh candidate reviewer examined base `8661bea` to
  `9ca18d9` and found one remaining private nested-state validation gap.
  The correction validates telemetry, counts and source fields before replacement;
  regressions cover aggregate, active history and rotated history while preserving
  legacy absent fields and successful rendering. The implementer verified this
  final correction; the earlier review is not claimed as an exact-final-head review.
- Security triggers are synthetic: blocked private DNS/proxy/fallback cases,
  rejected password-free LAN binds, and rejected malformed nested snapshots.
  Legitimate operator transport, read-only IAP and valid retained state remain
  covered by the existing and new tests.

## Remaining promotion checklist

- Full Windows/Linux CI matrix and dependency/container scans.
- Strict live-version preflight before building a clean committed source.
- Installed-image synthetic checks and applicable staging acceptance.
- Preserve service settings, IAM, provider schedules and rollback revisions.
- Verify each promoted image, public version, readiness, source observations and provenance.
- Publish the tag/release only after verified deployment.

Actual results and deployed source will replace this candidate checklist as the
release completes. Private operational evidence stays outside the public repo.
