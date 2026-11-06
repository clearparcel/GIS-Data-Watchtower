# County directory contract handoff

Codex implemented the first offline slice on `codex/county-admin-contract`
from `9a0e643aeddc85d373c0f15a826eb50885fb7584`. The commit introducing this
handoff contains the implementation. The acceptance boundary is a versioned
public projection with synthetic tests and no route activation. See the
[contract](../../county-directory-contract.md).

The published CCE catalog pin was `34bb01ef001eb4950fd72b8806c20098950d2461`.
The `gis-data-watchtower` record reported SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a` and
`needs-review`, with review due October 14, 2026. Repository evidence supplied
the implementation context.

Local validation on Windows used Python 3.14.6 and Node 24.19.0 with
`WATCHTOWER_REQUIRE_NODE=1`. The baseline ran 961 tests and the feature run
ran 966, both with three skips and no test failures. Both runs emitted a
`ResourceWarning` during cleanup of an HTTP 403 test fixture. The five
directory tests, compileall, status sync, and staged diff checks passed.

## Independent review and storage follow-on

The user authorized a bounded CCE review of the public field projection.
CCE's `gpt-6.1-sol` lead with two `gpt-6-luna` workers reviewed base
`9a0e643aeddc85d373c0f15a826eb50885fb7584` and head
`7af080328e635c63d052212d749a7b2b991abf71` using the projection source,
URL sanitizer, and test summary. The lead reported no concrete findings.
The review assumes server-resolved county identity and did not cover the
subsequent storage implementation, full test assertions, or future consumers.

The storage follow-on uses the existing versioned backend. It persists each
private draft, save receipt, and publication intent together, then writes a
separate allowlisted directory with a readback check. The new tests exercise
two-editor conflicts, request replay, restart and ambiguous-write recovery,
interleaved publication, and the public JSON boundary using local storage.
The updated contract documents the 128-receipt retry window and the separate
publisher invocation.

The follow-on ran 981 tests with Node 24 required, three skips, and no
failures. The existing Provider Terms HTTP 403 fixture cleanup warning
recurred. The 20 targeted tests, compileall, status sync, and diff checks
passed.

## Open integration work

- Establish the hosted administrator write boundary while preserving the
  trusted-frontend dashboard's read-only requirement. The separate local
  editor already exercises authenticated Apply, retry, and attachments.
- Select and validate the hosted scanner, attachment retention, and private
  and public service permissions. Preview uploads remain quarantined.
- Reconcile the packaged starting values with a verified deployed public
  snapshot and prepare migration exceptions before enabling hosted editing.
- GitHub reported strict required checks on `main` and auto-merge disabled.
  The checked-in CI workflow has no deploy job. External deployment triggers
  and staging identity, storage, scanner, and rollback remain unverified.
- Run the exact candidate through hosted CI and container smoke checks.

## Local end-to-end integration

The implementation continues from
`c0ed67df9d0c9bd54f98bcb4f569d0664dc6d98a`. The user directed continued
implementation and declined another model review. This slice adds the
loopback editor, packaged starting values, upload quarantine, an opt-in
sanitized public reader, revision-aware exports, and the county profile PDF.
It uses the same published CCE pin and historical `needs-review` record
documented above. The prior bounded review applies only to the earlier
public projection.

Local tests ran 994 cases with Node 24 required, three skips, and no
failures. The existing Provider Terms fixture emitted the same HTTP 403
cleanup warning. Compilation, status synchronization, and diff checks
passed. Chromium verified the synthetic editing and publication path at
desktop and mobile widths. An already-open county profile showed the second
publication after 12.7 seconds in that run. All 87 county reports opened
and yielded selectable text with synthetic monitoring data. A long policy
and standards fixture confirmed pagination and a clickable official link.
The constrained Python dependency audit reported no known vulnerabilities.
The local Docker daemon was unavailable for a container smoke test.

This slice was authorized as local implementation. Merge, staging,
production rollout, and authoritative provider changes require their own
scope.
