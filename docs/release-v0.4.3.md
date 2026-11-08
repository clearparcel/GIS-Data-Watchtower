# GIS Data Watchtower v0.4.3

Internal dashboard rollout: November 7, 2026 (Central time).
Source: `81807110dca882a57fed7d7f3acf7449badc7946`.

[PR #223](https://github.com/clearparcel/GIS-Data-Watchtower/pull/223) combines
the shared presentation changes from #221 and internal workflow improvements
from #222. It advances the version and refreshes the Debian zlib runtime package
while retaining the enforced security scans.

## Changes

- Linked attention queue, readable source failures and actual change history.
- Separate check results, check timing and publisher data age.
- Source/terms filters, complete mobile navigation and scoped downloads.
- Refresh preserves reading state, filters, open sections and focus.
- Shorter county sections with a linked detailed field-results view.

## Validation and promotion

- Version preflight passed from public v0.4.2 to candidate v0.4.3.
- Local tests passed: 1,027 tests with no skips on Linux. All six supported
  Windows/Ubuntu CI combinations passed, including CodeQL, dependency checks,
  both container scans and supply-chain evidence generation. The
  [merged-source CI run](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/42417111860)
  passed for the exact deployed source.
- Fourteen installed-image acceptance steps passed. Installed UI and permission
  data matched committed source; OS and Python components matched the scanned
  CI artifact. The resolved Linux/amd64 image identity was checked before
  promotion.
- The new revision was prepared with no traffic, compared with the predecessor,
  then promoted to 100%. Its live identity, non-image runtime settings and IAM
  matched expectations. The owner confirmed the updated signed-in UI. Anonymous
  requests continued to require Google sign-in.
- The previous revision is retained for rollback. Rollback was not needed.

The read-only internal dashboard alone was updated. The public website remains
v0.4.2. Provider jobs, polling permissions and schedules were unchanged.
Private artifact and operational evidence is retained in the deployment records.

## Verification scope

Read-only follow-up checks verified saved source results and worker provenance.
The bounded post-rollout request-log sample contained successful responses and
no server errors. No new provider polling was run; source results describe saved
observations. The signed-in visual check was supplied by the owner; the assistant
could not inspect that browser session directly. The final private promotion
receipt is retained with the validation evidence.
