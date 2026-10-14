# GIS Data Watchtower v0.3.0

**Deployed and verified October 14, 2026 (America/Chicago).** The owner
approved the production release on 2026-10-14. Source is merged `main`
`4e4dbec082dbd966e7af1e18a12f03d0557295c2`, which also carries the CSP
hardening (#99) and the Cass County research update (#100).
[v0.2.3](release-v0.2.3.md) is the rollback baseline. The owner chose v0.3.0,
a minor release, because the review stack changes CLI exit codes, aggregate
and public-state fields, and the dashboards.

## Deployment evidence (2026-10-14)

- **Preflight:** `scripts/check_release_version.py` passed against the live
  site: deployed v0.2.3 → candidate v0.3.0. Afterwards it reports v0.3.0 as
  deployed. CI was green on `main`.
- **Build:** Cloud Build `a8848745-3460-496a-bb42-123b9e088022`, from a
  committed-only `git archive` of the merged SHA. It followed the v0.2.3
  pattern plus the gate's extra checks:
  - both images verified identity `0.3.0` / full SHA / `production`;
  - the private wrapper was copied unchanged from the audited v0.2.3 image,
    with SHA-256 `786cccc2…5fb5e72a`.
  - A new step runs every import in the wrapper and resolves every
    `dashboard.*` attribute it uses. The wrapper starts its server on import,
    so the module is not imported as a whole.
- **Images:**
  - `watchtower` `sha256:3df9fe0ce9373509ba1d80d1008e240274014626848c052cf8104eecd90f8f76`
    serves the public dashboard, the provider job and the publisher job.
  - `dashboard` `sha256:05599e269642ae0031d3d75682cadd3ffffc097ae5a224351edd06a4031ddb54`
    serves the private dashboard.
- **Services:** both were first deployed at zero traffic (tag `v030`),
  checked Ready, and then promoted to 100% traffic. Ingress, IAP, IAM,
  environment and secrets are unchanged.

| Service or job | v0.3.0 | Rollback (v0.2.3 / v0.2.2) |
| --- | --- | --- |
| Public dashboard | `gis-data-watchtower-public-00031-ciw` | `gis-data-watchtower-public-00019-4zl` |
| Private dashboard | `gis-data-watchtower-dashboard-00033-qor` | `gis-data-watchtower-dashboard-00026-6gg` |
| Provider job | `watchtower@sha256:3df9fe0c…` | `watchtower@sha256:2d2f4a5f…` (v0.2.2) |
| Public publisher job | `watchtower@sha256:3df9fe0c…` | `watchtower@sha256:2d2f4a5f…` (v0.2.2) |

- **Execution-profile validation:** one owner-approved provider run on
  v0.3.0, execution `gis-data-watchtower-staging-zwzt2`. It was a single
  bounded check; the daily schedule is unchanged.
  - The `cloud` profile checked 33 sources: 27 ok, 1 warn, 5 error.
  - The run exited with code 2, which in v0.3.0 means a source error.
  - Worker provenance is `cloud` for all 33 sources.
  - All five errors were provider-side and happened during the MnGeo outage:
    MnGeo addresses, roads and parcel catalog (HTTP 502/504), NWI (HTTP 502),
    and FEMA NFHL (connection reset). Their last successful checks were kept.
- **Hold-for-terms:** the run skipped the enabled Brown and Swift
  county-direct parcel sources and retired them from the aggregate with
  tombstones. The inventory guard accepted the report because deliberate
  skips count as covered. As a result, counties with parcel observations
  went from 70/87 to **68/87** (59 via MnGeo, 22 county-direct).
  - The private registry still lists both sources as enabled. Disabling them
    there is an owner configuration change.
- **Publication and live acceptance:**
  - The publisher ran on v0.3.0 (execution `gis-data-watchtower-public-publisher-746r9`).
  - At [gis-watchtower.clear-parcel.com](https://gis-watchtower.clear-parcel.com),
    every page returned HTTP 200 and the footer shows **v0.3.0**: Overview,
    Counties, county profiles (Cass, Brown), MN GAC parcel statewide, MN GAC
    address county, the county CSV and `/api/state`.
  - Each HTML page's `Content-Security-Policy` lists SHA-256 script hashes,
    has no script `'unsafe-inline'`, and no marker attributes are left in the HTML.
  - `/healthz` returned `ok` with a fresh publication.
  - There were no ERROR log entries on either new revision.
  - The private dashboard is behind IAP. It was verified Ready and
    wrapper-checked, but it was not rendered without a signed-in browser.
- **Preview:** the isolated preview now runs the same SHA as a `preview`
  build (`gis-data-watchtower-public-v2-preview-00023-ptp`). It uses a copy
  of the sanitized public snapshot.

## Contents

v0.3.0 is the stack of review pull requests from the 2026-10-13 repository
review. Each one targets the PR below it:

| PR | Package | Summary |
| --- | --- | --- |
| [#79](https://github.com/clearparcel/GIS-Data-Watchtower/pull/79) | 1 Provider compliance | Run-loop enforcement of `enabled: false`, execution profiles and `hold-for-terms`; per-host 429 backoff |
| [#80](https://github.com/clearparcel/GIS-Data-Watchtower/pull/80) | 2 Shared-state guards | Refuse empty, shrunken and future-dated reports to the shared aggregate |
| [#81](https://github.com/clearparcel/GIS-Data-Watchtower/pull/81) | 3 Public accuracy | Dates, freshness ("actively checked" = monitoring path + recent check), tables, contacts, exports |
| [#82](https://github.com/clearparcel/GIS-Data-Watchtower/pull/82) | 4 Public hygiene | Redacted deployment identifiers, archived dated docs, stale docs fixed |
| [#83](https://github.com/clearparcel/GIS-Data-Watchtower/pull/83) | 5 Mobile and accessibility | Phone header and tabs, skip links, map focus, palette, table semantics |
| [#84](https://github.com/clearparcel/GIS-Data-Watchtower/pull/84) | 6 CI and build | CI triggers, base-image single source, required build revision |
| [#85](https://github.com/clearparcel/GIS-Data-Watchtower/pull/85) | 7 Engine hardening | Exit codes, strict JSON numbers, redirects, field names, `last_available_at`, HEAD, storage |
| [#86](https://github.com/clearparcel/GIS-Data-Watchtower/pull/86) | 8 Tests and dead code | Dead code removed, topic test modules, less brittle UI tests |
| [#87](https://github.com/clearparcel/GIS-Data-Watchtower/pull/87) | Release prep | `pyproject.toml` version 0.3.0 and this record |
| Follow-up | Codex review fixes | Retry-After honoured in full, redirect backoff, runtime hold-for-terms, empty and shrunken reports, check-time freshness, overdue counts |

See [STATUS.md](../STATUS.md) for the per-package detail.

## Compatibility notes for operators

- **Exit codes.** Exit code 3 now means Watchtower itself failed. These
  failures used to exit 2. Code 2 still means a source error or an empty run,
  and argument-parser usage errors also exit 2. Update any wrapper that
  treated 2 as a crash. Keep Cloud Run Jobs at `--max-retries=0`.
- **Build revision.** Preview and production container builds fail without
  `WATCHTOWER_BUILD_REVISION`. Confirm the private Cloud Build configuration
  passes the full commit SHA before building.
- **Aggregate publication.** Only the `cloud` and `local` execution profiles
  may publish to the shared aggregate; any other profile is refused before
  polling. `aggregate --worker` accepts only those two. `worker-retire` still
  accepts legacy names.
- **State fields.** These are new or changed:
  - Aggregate source records add `last_available_at`.
  - Each source's `checked_at` is now its own check start.
  - GAC observations may report `observation_status: "none"`.
  - `NaN`/`Infinity` values in older state files are read as `null` and
    written as standard JSON.
- **Provider values.** SDA strings with leading zeros (such as `007`) stay
  text, so they may report one change after deployment.
- **Public state.** Worker names other than `cloud` and `local` are no longer
  published.
- **Legacy imports.** Every module attribute that v0.2.3 exposed and this
  stack removed or moved still resolves through
  `clearparcel.datawatch._compat` (pinned by `tests/test_compat.py`), so code
  built against v0.2.3 keeps importing. New code should not use those names.
- **Rate-limit holds.** A `Retry-After` longer than a week is now honoured
  in full, up to a year, and flagged `operator_review` in private state. It
  is no longer cut to 7 days.
- **Hold-for-terms at run time.** Enabled county-direct parcel sources for
  hold-for-terms counties are skipped (`skipped_sources: hold-for-terms`).
  If the private registry still enables any of them, they stop being polled.
- **Freshness.** Source freshness follows provider-check time, so sources
  deferred by a backoff now show as overdue once their last real check ages
  out.
- **No provider-cadence change.** Scheduling, execution-profile assignments
  and request volume are unchanged. Hold-for-terms counties stay unpolled
  county-direct.

## Release gate (per AGENTS.md and the release policy) — completed 2026-10-14

1. The owner reviews and merges the stack, in order or squashed. CI must be
   green on `main`.
2. Run `python scripts/check_release_version.py` against the live site
   (expect v0.2.3 → v0.3.0). Keep the output.
3. Run Cloud Build from a clean committed checkout. The October 13 v0.2.3
   build pattern already passes the full commit SHA and the environment, so
   it satisfies the new revision check. Reusing that pattern needs these
   changes:
   - The identity checks after each image build must expect
     `{'version': '0.3.0', 'revision': '<full merge SHA>', 'environment': 'production'}`.
   - After the private dashboard image is built, add a step that imports the
     private wrapper module inside that image (without starting the server)
     and fails the build on `ImportError`/`AttributeError`. The wrapper's
     hash check alone cannot detect an incompatible package.
   - The provider and publisher jobs still run v0.2.2 images. Moving them to
     v0.3.0 needs their own image built with the same revision and
     environment arguments.
4. Validate on preview/staging:
   - the applicable execution profile(s);
   - source-level results;
   - aggregate worker provenance;
   - rendered Overview, Counties, MN GAC and `/healthz` metrics.

   A successful container exit alone is not enough.
5. Deploy only after explicit owner approval. Keep the v0.2.3 revisions for
   rollback.
6. Replace this record's status with the deployment evidence, and update
   README, STATUS and docs/README.

## Owner decisions after review (2026-10-14)

- **GAC denominator:** unchanged. Fields missing from a county's schema
  stay in the mandatory-population denominator.
- **CSP:** approved. Inline scripts are now allowed only by SHA-256 hash; see
  the CSP hardening change.
- **Stored query strings:** not stripped from private state.
- **County contact data:** left as is.
