# GIS Data Watchtower v0.3.2

**PREPARED — not deployed.** The owner authorized deployment of the private
GAC selector fix on October 20, 2026. The current dashboards are v0.3.1.

## Scope and tested source

The application fix is `eb5a4f9f2843ba4e01331ef109ccd44602ef3bdc`; review receipt
`443d7d6c7d20c5aebb0a63df289869986f26a745` changes documentation only.
The full local suite ran 583 tests with 3 platform skips, with required Node
behavior tests enabled. Compilation, status sync, whitespace and staged
repository hygiene checks passed. The accepted bounded CCE review found no
actionable issues. See [the implementation handoff](ai/handoffs/2026-10-20-private-gac-selector.md).

The retained private wrapper ignores county, standard and view query
parameters. This release must install the migrated wrapper along with the
package dispatcher. It fixes private county selection, standard/scope
navigation and standard-specific JSON/CSV exports.

Both dashboard images will use v0.3.2 and the exact merged release source.
Provider/publisher job images, schedules, source assignments, registry,
credentials, IAM/IAP, ingress and other non-image service settings are outside
this change and remain unchanged. No provider checks or data migrations are
required.

## Artifact and acceptance gates

1. Pass the mandatory live version preflight and hosted CI on the release PR.
   Merge only its verified head and build a committed-only source archive.
2. Extract the wrapper from the verified predecessor image. Original SHA-256:
   `786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.
   Apply the guarded migration; expected candidate SHA-256:
   `bf6e99865f12cc3ee6dbe3968fe5e7211f1383aefa724319016a60bca2586cb0`.
3. Verify source/version/environment and wrapper imports/hash inside the
   immutable images. Run projection and route regressions against installed
   image code, plus the migrated actual Handler with synthetic state and
   cloud bootstrap excluded.
4. Prepare Ready zero-traffic candidates; verify exact images, unchanged
   settings and retained predecessor traffic.
5. Authenticate to the private candidate and verify county form/map selection,
   parcel/address/road switching, statewide view, invalid-query responses,
   JSON/CSV standard identity and the corrected Cass scan labels.
6. Promote and independently read back traffic/image identity and live behavior.
   The public tagged route is unavailable under existing load-balancer-only
   ingress; preserve that setting and verify the public domain immediately
   after promotion with rollback ready.

## Rollback baseline

- Public: `gis-data-watchtower-public-00033-mak`, 100% before preparation.
- Private: `gis-data-watchtower-dashboard-00035-vom`, 100% before preparation.
- Source and immutable digests: [v0.3.1 receipt](release-v0.3.1.md).

Retain these revisions and their captured traffic allocations. A failed
candidate must not receive production traffic. On a release-caused failure
after promotion, restore the affected predecessor allocation and independently
verify it; do not claim a rollback test unless actually performed.

The final receipt must record source SHA, CI/build IDs, digests, revisions,
UTC observation times, authenticated checks and limitations. Preparation
does not establish production acceptance or close unrelated operations work.
