# GIS Data Watchtower v0.5.7

Candidate, not yet deployed. This patch release contains the fixes from the
Codex third review of v0.5.6 (`2310764`), merged through PRs #274 to #276:

- **#274, publication integrity:**
  - A source's measured values are ordered by provider check time, so
    overlapping workers cannot republish an older observation (T01).
  - The publisher refuses an aggregate dated more than five minutes ahead of
    its clock, and stored or published future times no longer block recovery
    (T02).
  - A mistyped source status is refused before publication (T03).
  - A worker's first filtered report records only its heartbeat (T10).
  - The public worker card reads "Last fully successful worker run" (T11).
- **#275, provider options and change detection:**
  - Request-producing options must be JSON booleans (T04).
  - The Minnesota county catalog must name all 87 counties once, checked per
    raw row; aliases are stored under the canonical name (T05).
  - Malformed statistics groups are unavailable rather than zero (T06).
  - Unmeasured parcel schemas report no change; tracked values keep a per-key
    baseline (T07).
  - An explicit `null` `extent_shift_percent` is refused (T08).
- **#276, operations:** the publisher watchdog default also expects workers
  that sources are assigned to (T09); the Windows lock test stops its owner
  gracefully (T12); the CRM terms client closes HTTP error responses (T13).

Deployment notes:

- **Private registry:** must pass the v0.5.7 checks before rollout: JSON-boolean
  `count`, `discover_parcel_layer`, `parcel_quality`, `geometry_sample`,
  `item_metadata` and `prefer_curl` when set, and no `null`
  `extent_shift_percent`.
- **County catalog:** the next MnGeo catalog check fails, keeping the last
  complete catalog, unless it names all 87 counties exactly once.
