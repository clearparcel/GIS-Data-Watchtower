# Private GAC county selection — local candidate

Date: October 20, 2026. Implementer: Codex.
Base: `ad1b7a2c698d420dac49e5f18cd67a830e38a0fc`.
Branch: `codex/private-gac-county-selector`.
Scope: owner-requested investigation, fix and required checks; no new
deployment, merge, provider polling or production configuration changes.

## Diagnosis

Authenticated live navigation to Cass and form submission both returned the
default parcel landing page. All 87 county suggestions are present in the
datalist; the earlier “empty options” interpretation was incorrect.
The exact deployed private image's retained wrapper was read without executing
its cloud bootstrap. Its `/mngac` handler calls `render_mngac(config)` without
county, standard or view. Its JSON/CSV routes also always use parcel data.
Repository public/private server routes already forward these parameters.

Verified original wrapper SHA-256:
`786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.
The same wrapper was preserved by v0.3.1; WT-01 did not introduce this route.
Private deployment settings and downloaded wrapper source stay outside Git.

## Candidate

- `dashboard_routes.dispatch_gac_routes` validates the standard and selected
  county/view, renders saved observations, and honors the standard for exports.
  Invalid selections return 400; absent export observations return 404.
- `dashboard.dispatch_gac_routes` exposes the adapter to retained wrappers.
- `scripts/migrate_private_gac_wrapper.py` requires an operator-verified
  SHA-256, replaces exactly one known legacy route block, preserves its line
  endings and all surrounding bytes, checks syntax and creates a separate
  candidate exclusively. Unexpected input or existing output fails closed.
- Authentication, response headers, storage synchronization, POST refusal,
  unrelated routes and provider behavior are unchanged. The migration does
  not start a server, contact a provider or deploy anything.

The locally migrated retained wrapper SHA-256 is
`bf6e99865f12cc3ee6dbe3968fe5e7211f1383aefa724319016a60bca2586cb0`.
This is a candidate source hash, not a built/deployed image identity.

## Validation

Eight synthetic regressions cover the reproduced old failure, county form/map
URLs, all three standards, statewide navigation, invalid query values, absent
observations, standard-specific JSON/CSV, read-only behavior, migration drift,
LF/CRLF preservation and refusal to overwrite input/output.

Separately, the actual original and migrated wrapper Handler classes were
loaded with synthetic observations and cloud bootstrap excluded. The original
reproduced selection loss; the migrated class passed county/statewide results,
three-standard exports and invalid-query responses.

A loopback-only HTTP server using the migrated Handler passed browser form
submission for Douglas, switching to Road Centerlines and Statewide overview
while retaining Douglas. These are synthetic checks, not new provider evidence
or production acceptance.

Required checks passed on the candidate:

- `WATCHTOWER_REQUIRE_NODE=1 python -W error::ResourceWarning -m unittest discover -s tests -q`:
  583 tests run, 3 platform skips, 30.130 seconds.
- `python -m compileall -q clearparcel tests scripts`.
- `python scripts/sync_current_status.py --check`.
- `git diff --check`.

Hosted CI has not been run for this candidate. The prior release's checks do
not establish this candidate's hosted result.

## Next authorized release

Package changes alone cannot fix a wrapper that never forwards the query.
After normal review/CI and separate release approval:

1. Read back the current private immutable image and wrapper hash. If it has
   changed, inspect it rather than relaxing migration guards.
2. Extract the retained wrapper into a private temporary build directory.
   Prepare a new file using:

   ```text
   python scripts/migrate_private_gac_wrapper.py --input <retained-wrapper.py> --output <candidate-wrapper.py> --expected-sha256 <verified-original-sha256>
   ```

3. Build the new versioned application and private image with the migrated
   wrapper installed as `/app/dashboard_app.py`. Verify exact source/version,
   wrapper hash and route behavior inside that image. Do not reuse an old
   wrapper-hash assertion or copy the unchanged predecessor over the candidate.
4. Preserve security/runtime configuration and rollback traffic. Verify
   authenticated candidate county selection, map navigation, standard/scope
   switching, invalid-selection handling and JSON/CSV before promotion.
   Read back live image/traffic and repeat the applicable checks after promotion.
5. Remove temporary wrapper copies after retaining only necessary hashes and
   receipts. No provider/publisher job or schedule change is needed.

## Shared context and review

Published CCE record `gis-data-watchtower` was read at revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`.
It is published but historical `needs-review`, updated October 13 and due
October 14. Current source and observed behavior take precedence.
The owner accepted an independent bounded CCE review of exact implementation
head `eb5a4f9f2843ba4e01331ef109ccd44602ef3bdc` against the base above.
One `gpt-6-luna` worker at medium reasoning completed the review with
**no actionable findings established**. It assessed query routing, migration
guards and the supplied regression coverage. No Astra call was made.
The reviewer had only the supplied diff/context and did not independently
rerun tests, inspect live wrapper bytes or validate surrounding caller security.
This subsequent review receipt changes documentation only; the tested and
reviewed application remains at `eb5a4f9`.
