# GIS Data Watchtower v0.3.0 — release candidate

**Status: merged to `main` on 2026-10-14 (`a531161`), not deployed.** Production remains
[v0.2.3](release-v0.2.3.md), and v0.2.3 is the rollback baseline. The owner
chose v0.3.0, a minor release, because the review stack changes CLI exit
codes, aggregate and public-state fields, and the dashboards. Nothing here is
merged, built or deployed without separate owner approval.

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

## Release gate (per AGENTS.md and the release policy)

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

## Deferred to a later release

- Whether schema-missing GAC fields should leave the mandatory-population
  denominator. That would change published percentages and needs an owner
  decision.
- Dropping `'unsafe-inline'` from the CSP, which needs nonces for every
  inline script.
- Removing stored query strings from private state.
