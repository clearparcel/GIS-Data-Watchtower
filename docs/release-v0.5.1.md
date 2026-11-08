# GIS Data Watchtower v0.5.1

Deployed November 8, 2026 (Central time). Immutable application source:
`f7e82feaa05afaa01f2766a57a3ad9371ad31c02`, incorporated by merged PR #231
at `93f8a5c2aa0c88ed47393270cd72f0cd57d996f7` (identical source tree).

The public dashboard, internal dashboard, county editor, regular cloud worker
and public publisher use this release. Scanner and weekly digest images were
outside this coordinated application update.

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

## Validation

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

## Promotion and live verification

- [Candidate CI](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/42507821092)
  passed all six Windows/Linux Python combinations, dependency audit, CodeQL,
  both container scans and supply-chain evidence. [Merged-main CI](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/42508589757)
  also passed.
- Live-version preflight passed v0.5.0 → v0.5.1 before the clean committed build.
  The installed image matched every source hash and immutable identity, passed
  148 synthetic tests, and matched the scanned CI artifact's Python/OS inventory.
- Isolated real staging storage verified atomic audit attribution and replay,
  public privacy, bounded attachment metadata and hash-verified downloads.
  Synthetic staging objects were removed. Existing private aggregate/history
  passed the new validator before promotion.
- Candidate service revisions were prepared without production traffic and
  compared with rollback baselines. Production runtime settings, IAM, authentication
  controls and scheduler configuration were preserved. All five images and the
  three service traffic allocations were verified.
- Public footer v0.5.1, readiness including directory availability, county page,
  summary and CSV/JSON exports passed. All 24 source observations and worker
  provenance matched the aggregate, and the snapshot retained all 87 counties.
  The bounded production error-log query returned no error entries.
- The editor's unauthenticated request still redirects to sign-in. The internal
  dashboard's default service URL remains disabled. No authenticated browser
  walkthrough is claimed: the staging route required Google sign-in.
- No additional provider run or scheduler change occurred. Automatic approval
  review rejected a manual publisher execution because it would republish
  authoritative data; it was not performed. The deployed publisher image is verified
  through its configuration; a new execution will be observed on the existing
  schedule.

Previous service revisions and job image references remain available for rollback.
Private artifacts, operational settings and detailed verification records stay
outside the public repository. Deferred features and infrastructure decisions are
listed in the [review disposition](review-remediation-v0.5.1.md).
