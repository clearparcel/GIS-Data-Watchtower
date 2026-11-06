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

- The trusted-frontend dashboard requires read-only mode. Establish the
  administrator write boundary before wiring Apply and attachments. Connect
  the publisher to Apply and an authorized retry mechanism.
- GitHub reported strict required checks on `main` and auto-merge disabled.
  The checked-in CI workflow has no deploy job. External deployment triggers
  and staging identity, storage, scanner, and rollback remain unverified.
- No PDF renderer is declared in the package or installed by the Dockerfile
  explicitly. Prove pagination, selectable text, clickable links, and the
  container dependency before committing to a renderer.

This slice was authorized as local implementation. Merge, staging,
production rollout, and authoritative provider changes require their own
scope.
