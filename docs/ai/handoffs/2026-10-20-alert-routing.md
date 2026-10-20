# Offline alert routing — merged PR #112

Published head `e433a9d9c50e7fa33d680afc8d93aa9fee067366` merged as
`1c3b3ed62389c36c3d2e61db60715509cb430076`. All eight PR checks passed;
[post-merge CI](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39461133624)
also passed. The [bounded review](2026-10-20-alert-routing-review.md) found no
actionable issues in `50afe77`. No deployment or notification activation followed.

Implementer: Codex, October 20, 2026.
Branch: `codex/wt-alert-routing-rehearsal`.
Base: `c7ade29cd90581c46de4e50209177faed2c14b6b` (merged PR #111).

Objective: prepare concrete private routing/message previews and synthetic
checks for the next operations acceptance step. Owner selected a private email
destination and escalation owner for the draft only; those values stay outside
public Git. Sending, channel activation and operational changes remain gated.

The new library and CLI reuse the existing triage validator on original saved
reports. Expected worker/source pairs prevent a missing source or worker from
disappearing from coverage. Newer incomplete/partial evidence cannot fall back
to older success. Fresh supported recovery is distinct from overdue checks.
Candidate event keys retain an incident's start across repeated failures when
complete relevant history is supplied. Delivery deduplication remains unbuilt.

Acceptance covers synthetic failures, warnings, rate limits, backoff, age
boundaries, missing/invalid evidence, stale versus fresh recovery, incident
reopening, input preservation, exclusive output creation and diagnostic
minimization. Validation passed: 593 ResourceWarning-strict tests in 30.929
seconds with 3 platform skips and required Node 24 behavior checks; Python
compilation, generated-status synchronization and whitespace checks passed.
The 10 focused tests passed independently. The first focused CLI test was
blocked by Windows sandbox temporary-folder permissions; it passed when rerun
with normal temporary-directory access. No test deadline was changed.

No provider calls, hosted routing inspection, notification delivery, production
configuration changes or deployment occurred. Review, publication, merge and
CI are complete. The next work is transport/delivery acceptance with separate
approval before notification tests or operational activation.
Do not equate the local preview with delivered alerts or five-cycle acceptance.

Shared memory `gis-data-watchtower` was read at published revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`.
Historical `needs-review` context (updated October 13, review due October 14)
does not establish current deployment or monitoring authority.
