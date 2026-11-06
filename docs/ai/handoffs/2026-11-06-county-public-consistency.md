# County public access consistency

The county editor published an access change, but the county page retained an
unqualified research card above the updated settings. The county list and
map/overview detail also summarized research rather than confirmed settings.

## Scope and acceptance

- Base: `4e3104cb7a2fb9e6358edf96c1ad13599dee5be9`.
- Branch: `codex/county-public-consistency`; isolated worktree. Root dirty work is preserved.
- Implementer: Codex. No independent model review was authorized or performed.
- Published settings lead the county page and supply list, popup and export summaries.
- Retained research is explicitly identified; monitoring counts, permission decisions,
  restrictions and authored notes are not rewritten.
- Existing research JSON fields remain compatible; basis metadata and published
  summary columns distinguish them from editable access.
- Regression tests exercise open/fee/unknown publication, all access methods,
  stale revision rejection, map detail refresh, unchanged monitoring, and privacy.
- PDF tests retain standards and historical evidence while excluding private content.

## Validation and release boundary

Focused public-page, directory and PDF tests passed (34 tests). Compile, status
synchronization and whitespace checks passed. The full suite passed: 1,011 tests,
3 platform skips, with Node 24 required. Python 3.14 printed an unraisable
HTTPError cleanup ResourceWarning; the unittest result and process exit were
successful. The PR records required CI results. Local HTTP tests require an execution context that
permits loopback; the sandbox run timed out and is not passing evidence.

The owner's standing feature-scoped merge instruction applies after checks.
Production deployment remains a separate approval; this change makes no county
record, provider registry, permission, scheduling or production configuration write.

## Shared context

The same-chat published catalog receipt for `gis-data-watchtower` used revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, content SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`.
The record was published but marked needs-review (review-after 2026-10-14).
Current source and the verified publication behavior take precedence.
