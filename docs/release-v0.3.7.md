# GIS Data Watchtower v0.3.7 (dashboard release)

**Deployed to the public and private dashboards October 23, 2026 (about
10:04 AM America/Chicago).** The owner approved merging the October 23
review fixes and deploying the result. The provider and public-publisher jobs
stay on v0.3.6, unchanged, by owner decision.

## Scope

Review fixes merged October 23 (squash commits on `main`):

| PR | Change | Commit |
| --- | --- | --- |
| [#131](https://github.com/clearparcel/GIS-Data-Watchtower/pull/131) | Order alert incidents by check time, not arrival (P1-01) | `7612f32` |
| [#132](https://github.com/clearparcel/GIS-Data-Watchtower/pull/132) | Typed public projection for static exports; retire stale pages (P1-02, P2-06) | `3063d0d` |
| [#133](https://github.com/clearparcel/GIS-Data-Watchtower/pull/133) | County details on one revision; bounded dialog loader (P1-03, P2-05) | `ee7206e` |
| [#134](https://github.com/clearparcel/GIS-Data-Watchtower/pull/134) | Exact source history; one history read per overview (P1-04, P1-05) | `0b1f39e` |
| [#135](https://github.com/clearparcel/GIS-Data-Watchtower/pull/135) | Reject structurally invalid public snapshots (P1-06) | `9f180b9` |
| [#136](https://github.com/clearparcel/GIS-Data-Watchtower/pull/136) | Review quick wins: flags, metadata status, analytics URLs, field labels | `4a9ff0e` |
| [#137](https://github.com/clearparcel/GIS-Data-Watchtower/pull/137) | Type-aware parcel-quality predicates; one parcel-ID count (P2-02, P2-03) | `cf1ef96` |
| [#138](https://github.com/clearparcel/GIS-Data-Watchtower/pull/138) | Project each GAC standard once per statewide snapshot (P2-04) | `2cbbfa9` |
| [#139](https://github.com/clearparcel/GIS-Data-Watchtower/pull/139) | One GAC route dispatcher; no cross-standard CSV fallback (P2-07, P2-11) | `af1d747` |
| [#140](https://github.com/clearparcel/GIS-Data-Watchtower/pull/140) | Confine LocalStorage object names to the storage root (P2-10) | `7f4f242` |
| [#141](https://github.com/clearparcel/GIS-Data-Watchtower/pull/141) | Serve brand images from cacheable hosted routes | `24d88ce` |
| [#142](https://github.com/clearparcel/GIS-Data-Watchtower/pull/142) | Version bump to 0.3.7 | `39cff31` |

Each PR was brought up to date with `main` and passed all seven required
checks (six test jobs and security) before merging. #136 conflicted with #135
in `render_public_dashboard`; the resolution kept #135's known-count block
(missing counts show "—") and added #136's `parcel_counts` line, and passed
local validation before it was pushed. On #133 the first Windows 3.12 run hit
the wall-clock deadline in
`test_pinned_curl_preferred_and_fallback_use_resolve` on a slow runner;
the rerun passed.

## Source and checks

- Deployed source: merged `main` **`39cff3199b5dc82d9db9f86e032d8adbe846ac2c`**
  (#142); post-merge CI on `main` passed at `24d88ce` and `39cff31`.
- Local release validation at the release tree: 760 tests, 3 platform skips,
  required Node 24 behavior tests; compile, status sync and `git diff --check`
  passed.
- Live version preflight passed: v0.3.6 to v0.3.7.

## Build

Cloud Build **`7e16d1bf-2d5f-45fe-9430-c2ed54285ac6`** passed all 24 steps
from a committed-only archive of `39cff31`: identity `0.3.7` / full SHA /
`production` and certifi 2026.10.19 on both images; the private wrapper
copied unchanged and verified by SHA-256 with its dashboard attributes
resolving; in-image tests (alert delivery and routing, run evidence,
operations triage, county scan projection, private GAC routes, dispatch
guard, item metadata, public snapshot validation, history identity, hosted
brand assets); a check that the asset test imports the image's installed
package; actual private Handler acceptance; CLI smoke.

Two earlier submissions did not produce images: `e6895897…` expired in the
Cloud Build queue without starting a step, and `8a4f4b7c…` failed only the
hosted-brand-asset step because the acceptance mount omitted the committed
comparison images. The build harness was corrected to mount those four files
alone; no source changed between submissions.

| Surface | Image | Revision | Predecessor (rollback) |
| --- | --- | --- | --- |
| Public dashboard | `watchtower@sha256:5f5a6d49…e3aa260f` | `gis-data-watchtower-public-00041-ham`, 100% | `00039-vaw` (v0.3.6) |
| Private dashboard | `dashboard@sha256:58dc90a2…f123ef5e` | `gis-data-watchtower-dashboard-00043-nem`, 100% | `00041-cot` (v0.3.6) |
| Provider job | unchanged, v0.3.6 `72d1932c…2f2d422d` | — | — |
| Publisher job | unchanged, v0.3.6 `72d1932c…2f2d422d` | — | — |

## Rollout and acceptance

- Both dashboards were deployed as zero-traffic candidates (tag `v037`);
  non-image runtime settings, ingress, IAP and traffic were verified
  unchanged against the captured predecessor state, then each was promoted
  to 100%.
- The public candidate tag URL is not reachable through the service's
  load-balancer-only ingress (404), as in v0.3.6, so public acceptance ran
  before (v0.3.6) and after (v0.3.7) on the normal URL: overview, counties,
  Cass and Brown county pages, MN GAC, `/api/state`, JSON/CSV/XLSX exports
  and `/healthz` returned 200; the CSP script policy uses hashes without
  `'unsafe-inline'`, and `nosniff`, HSTS, `X-Frame-Options: DENY`,
  `Referrer-Policy` and `Permissions-Policy` are present; the footer shows
  v0.3.7; the Cass STATE_PIN scan row and workbook agree; provider
  observations were unchanged during the rollout.
- Hosted brand images: the four `/assets/` URLs referenced by the overview
  returned 200 with `Cache-Control: public, max-age=31536000, immutable`, an
  `ETag` and an image content type; an unknown `/assets/` path returned 404.
- The v0.3.6 publisher's next scheduled run after promotion succeeded and the
  v0.3.7 public site served that snapshot, so the unchanged publisher's
  output passes the new snapshot validation.
- Private: the revision is Ready, the in-build wrapper and Handler acceptance
  passed, and unauthenticated requests are still redirected to Google
  sign-in by IAP. A signed-in owner check of the private dashboard on the
  normal URL is pending.
- No new error logs on either revision. Jobs: specification hashes and both
  schedulers are unchanged; no job was executed and no provider was polled.

## Rollback

Dashboards: restore traffic to `gis-data-watchtower-public-00039-vaw` and
`gis-data-watchtower-dashboard-00041-cot` (v0.3.6). Jobs need no rollback.
Rollback was prepared, not exercised.
