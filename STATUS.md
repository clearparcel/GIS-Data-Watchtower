# Project status

## v0.3.0 release candidate — in review on `release/v0.3.0`, not deployed

The owner set **v0.3.0** as the next release. `pyproject.toml` is bumped on
this branch, which sits at the top of the review stack (#79–#86). Production
remains v0.2.3. Read the
[candidate record](docs/release-v0.3.0.md) for its contents, the operator
compatibility notes (exit code 3, required build revision, publishable
profiles, new state fields) and the release gate. Merging, building and
deploying each need explicit owner approval.

## Tests and dead code — in review on `chore/tests-deadcode`, not deployed

Housekeeping from the 2026-10-13 review (Package 8), stacked on
`fix/engine-hardening`. No behavior changes.

- Removed dead code: the uncalled `_destination_publicity`, `MNGAC_FIELDS_FILE`
  copies, the watch-module `_load_mngac_schema`, both `_county_mngac_summary`
  helpers, an overwritten monitoring-paths build in `_county_status`, the
  unused `_json` panel helper, two unused locals, and unused imports. Names
  other modules or tests reach through `dashboard.*` stay re-exported.
- New topic test modules: `test_aggregate.py`, `test_storage.py`,
  `test_cli.py` and `test_analytics.py` (the PostHog tests moved out of
  `test_gac_standards.py`, with added script-URL and token checks).
- UI tests check visible text (`tests/html_text.py`) instead of exact markup
  and full sentences, so copy and layout edits don't break CI. Policy caveats
  are still pinned.
- The test run prints nothing beyond unittest's own summary. `TOOLS_ROOT` is
  now `REPO_ROOT`.

## Engine and server hardening — in review on `fix/engine-hardening`, not deployed

Lower-severity engine items from the 2026-10-13 review (Package 7), stacked
on `ci/maintenance`. Production remains v0.2.3. Provider cadence, execution
profiles and request volume are unchanged.

- Exit codes: 0 ok, 1 warnings, 2 source error or empty run, 3 Watchtower
  failure (configuration, storage, refused merge, unexpected exception;
  previously 2).
- Provider values: only plain decimal strings become numbers, so leading-zero
  codes stay text (an SDA tracked value such as `007` may report one change
  after deployment). `NaN`/`Infinity` in provider JSON or older state files is
  read as missing, and state is always written as standard JSON.
- Requests: HTTPS→HTTP redirects are refused. Provider field names are placed
  in ArcGIS query clauses only when they are plain identifiers.
- Observations: each source's `checked_at` is its own check start. Aggregate
  records add `last_available_at` (the provider answered) next to
  `last_success_at`, and the private source page shows both. GAC
  observations report `observation_status` `none` when no population was
  scanned.
- Public: only `cloud` and `local` worker names are published, and
  `aggregate --worker` accepts only those; a run that publishes to the shared
  aggregate under any other profile (including `any`) is refused before
  polling. The public server answers `HEAD`.
  County exports are cached per published state, without blocking page views.
- Private dashboard: Basic-auth and refresh-token comparisons handle non-ASCII
  input. Links use the public URL sanitizer. Static-site counts are projected
  to integers.
- Storage: the unused unconditional `upload()` is removed, so every shared
  write is version-conditional. GCS read races back off with jitter.
  `cloud-job` uses a per-run temporary directory unless `WATCHTOWER_WORKDIR`
  is set.
- Deferred, needing owner direction: whether schema-missing GAC fields leave
  the mandatory-population denominator, which would change published
  percentages; dropping `'unsafe-inline'` from the CSP, which needs nonces for
  every inline script; and removing stored query strings from private state.
  Not changed, by decision: `tracemalloc` stays on, because it feeds the
  private memory chart, and no extra retry layer was added, because it would
  increase provider load.

## CI, build and supply-chain maintenance — in review on `ci/maintenance`, not deployed

Repository-tooling changes from the 2026-10-13 review (Package 6). No
application behavior changes. The owner has set **v0.3.0** as the next
release version (prepared separately at the top of the review stack).

- Dependabot now also updates the Docker base image; CI reads the base-image
  digest from the Dockerfile instead of keeping a second copy, and the
  supply-chain tests check that actions are SHA-pinned rather than which SHA,
  so Dependabot updates no longer fail the suite.
- CI: pushes to `main`, every pull request, and manual dispatch; superseded
  PR runs are cancelled; 30-minute job timeouts; CodeQL skipped for fork PRs.
- Preview/production container builds require the source revision;
  `setuptools>=77` matches the PEP 639 license field; the PowerShell setup
  helper checks Python 3.12+ and warns about Node 24; release, receipt and
  SBOM scripts handle truncated responses, byte-order marks and malformed
  inventory lines; ignore and line-ending rules cover agent scratch, the
  generated `build_info.json`, the Dockerfile and Windows scripts.

## Mobile and accessibility — in review on `ui/mobile-a11y`, not deployed

UI changes from the 2026-10-13 review (Package 5), stacked on the
public-hygiene branch. Production remains v0.2.3.

- Phones: the header keeps a "READ ONLY" label and a one-line **Pause refresh**
  button; tabs use short labels (Counties, Sources) so all four are visible at
  375 px (the last runs under a 16 px edge fade), with scroll snapping on
  narrower screens; nothing scrolls sideways at 320–1280 px (the counties page
  previously did at 320 px).
- Keyboard: **Skip to content** is the first Tab stop on public and private
  pages and moves focus into the content; maps start with **Skip county map**,
  shown beside the map when focused; map focus and selection use two-tone
  outlines that stay visible on every fill; both layouts respect reduced motion
  and leave room for the sticky header when jumping to content. (The reusable
  county-profile dialog's focus trap now covers every control, though no
  current production page uses that dialog.)
- Percentage maps use a brighter sequential palette (1.6–2:1 between
  neighbouring bins, up from 1.2–1.8) and a hatched **No data** fill instead of
  a near-black colour.
- Tables get captions and region labels from their section heading, with row
  headers scoped as rows; small text, placeholders, inline links and private
  muted text meet contrast and size guidance.
- axe-core reports no violations on the public overview, counties, county,
  and MN GAC pages or the private overview, counties, and MN GAC pages, at
  320–1280 px (synthetic data), and none of them scrolls sideways.

## Public-repository hygiene — in review on `docs/public-hygiene`, not deployed

Documentation and test changes from the 2026-10-13 review (Package 4),
stacked on the public-accuracy branch. No application behavior changes.

- Deployment identifiers (GCP project ID/number, service-account email,
  buckets, Cloud Run URLs, user-profile paths) were replaced with placeholders
  such as `<project-id>`; a test now fails if those shapes reappear.
- Dated notes, reviews, release records and superseded plans moved to
  `docs/archive/`, with every link rewritten; the documentation index lists
  them all. Status sections from v0.2.2 back moved to the archived October
  2026 status log, so this file holds current and in-review state only.
- README, release policy and the parcel-access audit no longer state stale
  versions or counts; configuration documents the publisher and public-server
  variables; validation instructions include `scripts`, the status-sync
  check and Node.js, and CI now fails (not skips) the JavaScript tests if
  Node is missing.
- Repository screenshots will be refreshed after the next release so they
  show the released UI.

## Public-accuracy fixes — in review on `fix/public-accuracy`, not deployed

Source-only changes from the 2026-10-13 review (Package 3), stacked on the
shared-state guards branch. Production remains v0.2.3.

- County acquisition and catalog-refresh dates show the correct calendar day
  (they previously displayed one day early in Central time).
- A county whose last result was healthy (or unknown) but whose check or worker
  report is older than the freshness window shows **Check overdue** instead of
  "Actively checked"; the counties card is now "Counties with a monitoring
  path" and states how many are overdue. AGENTS.md now defines "actively
  checked" as a monitoring path plus a recent check (owner decision).
- Cached county profiles and exports recompute freshness at least every ten
  minutes, so "current" becomes "overdue" even if publication stalls.
- The private statewide parcel field table has one cell per column again
  (it rendered 7 cells under 9 headers); a test checks table shapes on the MN
  GAC pages (all standards, both views) and the counties page.
- Wabasha (`mn-wabasha-parcels`) appears in the county parcel-quality charts.
- The mandatory-field gap list shows only fields with gaps; record counts use
  thousands separators; the overview card states the county overlap.
- County contacts fall back to the MnGeo directory when the county site lists
  no phone or email; the Fillmore "TBD" placeholder is gone.
- Exports: the GAC Detail "Population scanned" column reports the scan; Excel
  text cells no longer get a formula-guard apostrophe (CSV still does).
- Missing statistics show "—" instead of zero; publication status uses
  Central time.

## Shared-state guards — in review on `fix/aggregate-guards`, not deployed

Source-only changes from the 2026-10-13 review (Package 2), stacked on the
provider-compliance branch. Production remains v0.2.3.

- A run that checks no sources is an error (exit 2): no state save, upload or
  aggregate merge. A full report covering under half of a worker's own
  sources (counting deliberately disabled or reassigned ones as covered)
  retires nothing unless `WATCHTOWER_ALLOW_INVENTORY_SHRINK=1` marks a
  one-time deliberate drain.
- Single-source reports no longer overwrite the worker's fleet-level health.
- Reports dated more than five minutes in the future are rejected by
  independent mergers (the offline `aggregate` command); readers flag
  `clock_skew`. A worker's own publish cannot detect its own clock skew.
- State and aggregate files are written atomically with fsync and keep the
  replaced file's permissions; an undecodable state file falls back to its
  backup, and an unreadable primary never overwrites a good backup.
- `cloud-job` refuses the placeholder example configuration, so the container
  default exits with an error (code 3 since the engine-hardening change)
  instead of silently checking nothing.
- GAC metric times and optional-metric diagnostics no longer register as
  dataset changes (expect one info-level "fingerprint changed" event per GAC
  source on the first run after upgrade); a failing optional
  parcel-ID null-count query no longer fails the whole source; the validation
  receipt reports a failed GAC check instead of crashing.

## Provider-compliance fixes — in review on `fix/provider-compliance`, not deployed

Source-only changes from the 2026-10-13 review (Package 1). Production remains
v0.2.3 until a separately approved release.

- `"enabled": false` sources are never polled (previously only the candidate
  manifest honored it).
- HTTP 429 now stops every request to the host that returned it (including a
  `metadata_url` host) for the rest of the run and persists a private per-host
  backoff honoring `Retry-After` (60 s–7 days, default 1 h). Deferred sources
  keep their previous observation and `checked_at`; backoff timing and hosts
  stay out of worker reports, the aggregate, and public output.
- A check without `--execution-profile` or `WATCHTOWER_EXECUTION_PROFILE` no
  longer polls profile-assigned sources; only unassigned and `any` sources run.
- County hold-for-terms decisions come only from
  `minnesota_county_parcel_access.json` (11 counties); the hard-coded
  four-county override and the stale AGENTS.md list were removed.

Release note: any source already in the aggregate that is now `"enabled": false`
will be retired from the aggregate (and the public dashboard) by the next full
report from its worker, consistent with the candidate manifest. Re-enabling it
restores it on the following report.

## GIS Data Watchtower v0.2.3 — deployed and verified, 2026-10-13

The user-approved branding PR #77 merged at `f95d9315510497ae25cfd058f9a175b240b6debd`.
Both public and private Cloud Run dashboard services now serve v0.2.3 at 100%
traffic: public `00019-4zl` and private `00026-6gg`. The public header now
shows the supplied dark-background Watchtower logo beside the title, and both
packaged favicons use the supplied blue-background artwork. Responsive styling
and static-export links are covered by regression tests.

All seven GitHub checks passed, Cloud Build `78969f3e-021f-41f6-8704-8c7133f21e3a`
passed all six steps, and live Overview, Counties, MN GAC, and health checks
returned HTTP 200. The deployed logo and both favicon assets matched packaged
bytes. Exports retained 35 sources, 87 counties, 350 parcel-source rows, and
12 workbook sheets. Private anonymous access still redirects to Google sign-in.
The verified private wrapper, IAM, ingress, non-image runtime configuration,
provider and publisher job images, and both schedules remain unchanged.
Earlier v0.2.2 service revisions are retained for rollback. See the
[full v0.2.3 release record](docs/release-v0.2.3.md).

## Earlier status

Dated sections from v0.2.2 back to the first deployments are in the
[October 2026 status log](docs/archive/status-log-2026-10.md); older engineering,
release and review records are indexed in the [documentation index](docs/README.md).
