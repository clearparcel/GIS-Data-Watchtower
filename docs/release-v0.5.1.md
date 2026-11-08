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

## Validation and promotion checklist

- Required offline tests, Node tests, compileall, dependency consistency and status checks.
- Independent security and regression review of the pinned candidate.
- Full Windows/Linux CI matrix and dependency/container scans.
- Strict live-version preflight before building a clean committed source.
- Installed-image synthetic checks and applicable staging acceptance.
- Preserve service settings, IAM, provider schedules and rollback revisions.
- Verify each promoted image, public version, readiness, source observations and provenance.
- Publish the tag/release only after verified deployment.

Actual results and deployed source will replace this candidate checklist as the
release completes. Private operational evidence stays outside the public repo.
