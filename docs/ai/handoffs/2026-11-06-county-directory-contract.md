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
the implementation context. No independent model review ran.

Local validation on Windows used Python 3.14.6 and Node 24.19.0 with
`WATCHTOWER_REQUIRE_NODE=1`. The baseline ran 961 tests and the feature run
ran 966, both with three skips and no test failures. Both runs emitted a
`ResourceWarning` during cleanup of an HTTP 403 test fixture. The five
directory tests, compileall, status sync, and staged diff checks passed.

## Open integration work

- Build synthetic private saves and publication on the existing versioned
  storage interface. Test revision conflicts, durable intent, retry after
  ambiguous writes, and stale publisher behavior before adding routes.
- The trusted-frontend dashboard requires read-only mode. Establish the
  administrator write boundary before wiring Apply and attachments.
- GitHub reported strict required checks on `main` and auto-merge disabled.
  The checked-in CI workflow has no deploy job. External deployment triggers
  and staging identity, storage, scanner, and rollback remain unverified.
- No PDF renderer is declared in the package or installed by the Dockerfile
  explicitly. Prove pagination, selectable text, clickable links, and the
  container dependency before committing to a renderer.

This slice was authorized as local implementation. Merge, staging,
production rollout, and authoritative provider changes require their own
scope.
