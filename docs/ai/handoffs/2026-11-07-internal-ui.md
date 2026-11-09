**Internal dashboard improvements — November 7, 2026**

- Objective: implement the internal UI review's attention queue, failure and
  change details, reading-safe refresh, complete mobile navigation, relevant
  source metrics, terms filters, scoped downloads and clearer county/field views.
- Base: `416454ff30a316035f772f9962d91dd39f5fefde`, the public UI candidate in
  PR #221. This branch builds on that shared presentation work.
- Branch: `codex/improve-internal-ui`. Implementer: Codex. No independent
  reviewer has reviewed this task's head.
- Context: repository instructions and the recorded private v0.3.13 source
  informed the review. Live authenticated content and CCE memory were unavailable.
  This follow-up continues the owner's approved UI-only cloud exception and
  explicit request to implement the reviewed recommendations.
- Boundaries: synthetic local fixtures and offline validation; no provider
  polling, scheduling, production state/configuration, authentication or
  permission-gate changes. Merge/deployment remain separate approvals.
- Acceptance: failure reasons and actual changes are readable; links work;
  refresh preserves open sections/focus/filters; all mobile destinations are
  reachable; zero/unknown/not-applicable states remain distinct; source exports
  are scoped and allow-listed; provider terms remain read-only and separate
  from monitoring permission; required repository checks pass.

Validation and the exact final head are recorded in the pull request after
implementation. The inherited container scan blocker in PR #221 is outside
this UI task's scope.

## Implementation and validation

- Presentation modules: `dashboard_activity.py` (attention, bounded change feed,
  downloads and source allowlist), `dashboard_source.py` (source measurements),
  plus the existing private routes, templates, terms, county and refresh modules.
- Added ten regression tests, including an executable Node refresh-state test.
  Existing presentation assertions follow the intentional labels and linked
  field-results destination. County scan, permission and exact-ID measurement
  assertions remain covered; the overview still reads history once.
- Required local suite: 1,026 tests passed, no skips, Python 3.13.15 and Node 24,
  with ResourceWarning treated as an error. Compileall, status synchronization
  and diff whitespace checks passed. CI results are recorded in the PR.
- Synthetic browser checks: 16 routes at 1440, 768, 390 and 320 pixels (64 cases),
  no page overflow, duplicate IDs or JavaScript errors. Interaction checks cover
  broad search, status/timing/sort filters, terms actions, date filtering, mobile
  More/Escape, active navigation, source change links, county disclosure links,
  scoped downloads, read-only POST refusal, reading holds, and manual update
  restoration of details/filter/focus. No provider requests were made.
- Preview state, invented CRM cache and captures stay under ignored `datawatch/`.
  They are not deployment evidence. No credentials or private registries entered
  the checkout. The local preview server was stopped after checks.
- Dockerfile, dependency constraints and security scan policy are unchanged.
  PR #221 already has a container-scan blocker for existing base-image zlib
  advisories. This candidate does not claim to repair those advisories.
- No independent model review has been requested or performed. An independent
  review can be requested against the pinned PR head when CCE is available;
  neither review nor this UI implementation authorizes merge or deployment.

## Deployment update

PR #223 merged this implementation as part of source
`81807110dca882a57fed7d7f3acf7449badc7946`. The internal dashboard was deployed
as v0.4.3 on November 7, 2026, after owner merge/deployment approval. Release
preparation resolved the inherited container-scan blocker; main CI and image
acceptance passed. The owner confirmed the updated signed-in UI. See the
[release record](../../release-v0.4.3.md) for scope and verification limits.
