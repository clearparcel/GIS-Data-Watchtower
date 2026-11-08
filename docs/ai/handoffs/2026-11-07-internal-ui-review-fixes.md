# Internal UI independent-review fixes

- Objective: address the two P2 findings from the independent review of v0.4.3.
- Base: `72644a63b6f05523a83eb9d1550477c2ab6a37e7`, the documentation head in
  PR #224, containing application source `81807110dca882a57fed7d7f3acf7449badc7946`.
- Branch: `codex/fix-internal-ui-review`, isolated checkout.
- Implementer: Codex. The original findings were reproduced by a separate Codex
  assistant using synthetic state and a browser with requests intercepted locally.
- Shared CCE memory and Claude tools remain unavailable; no published-memory
  revision or freshness is asserted. The owner's existing cloud UI exception
  covers these UI fixes and offline validation.

## Changes and acceptance

Refresh persistence waits until saved preferences are restored. Initial hash
navigation opens the target evidence after restoration, preserving paused refresh,
previously open sections and the target link. A Node regression exercises toggle
events both before initialization and during restoration.

Record-count dates use the current check when the record establishes that a count
was measured, including quality errors. Request failures, backoff, unknown results
and absent measurements show Unavailable rather than borrowing last_success_at.
Synthetic merge/render regressions distinguish a new count with a quality failure
from retained or unmeasured counts. Provider polling and storage formats are
unchanged.

## Validation

- All 1,030 repository tests passed with Node required and no skips.
- Compileall, status synchronization and whitespace checks passed.
- Synthetic Chromium navigation at 1440px and 390px preserved both paused and
  resumed preferences, restored open sections, revealed the linked change and
  displayed the current count measurement time, without JavaScript errors.
- The new regression cases failed against the original implementation before
  the fixes. The exact implementation head and CI results are recorded in the PR.

Merge and release remain subject to the repository's existing approval boundaries.
