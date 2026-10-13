# GIS Data Watchtower v0.2.2

Release candidate prepared October 12, 2026 (America/Chicago). Deployment is
authorized by the owner and pending CI, immutable-image verification, and live
acceptance. The verified production baseline remains [v0.2.1](release-v0.2.1.md).

## Review corrections

- Raw GAC exception text is excluded from public JSON and rejected by the public
  publisher. Public pages retain a generic warning and the last successful GAC
  observation; private diagnostics remain available internally. The review
  reproduced a conditional disclosure using synthetic data, not an actual leak.
- ArcGIS refusals returned inside HTTP 200 JSON now preserve provider stop
  signals. Codes 401/403/404/410/498/499 stop retries; 429 stops with backoff.
  Other errors retain existing retry behavior. No authentication bypass is added.
- GAC row and population statistics require integers within their valid ranges.
  Missing aliases, booleans, fractions, strings, negative values, and populations
  above the denominator fail the observation. SQL SUM may be null only for an
  empty group. Failed checks retain the previous successful observation time.
- Statewide exports load county contacts once per snapshot instead of 348 times.
  Standalone county snapshots continue to load current contact records.
- Existing table scroll regions and their descriptive labels are reused, removing
  duplicate keyboard stops. Bare tables still receive one accessible region.

## Operational corrections already verified

Main now requires the GitHub Actions `security` check in addition to all six
Windows/Linux Python test checks, with strict branch freshness unchanged.

The obsolete local worker was retired at `2026-10-13T01:50:44.059218+00:00`
using the existing generation-checked retirement operation. All 35 source
observations and their cloud ownership were unchanged. The retired worker is
archived in the aggregate tombstone history. No provider polling or scheduling
change was performed.

## Validation and release boundaries

The regression tests reproduced the original failures before implementation.
An owner-approved independent CCE review (two Luna workers and a Sol synthesis)
found no concrete actionable patch regression. Its scope was the bounded diff
and supplied tests, not independent cloud or repository execution.

The release updates the public and private dashboards, provider job image, and
public publisher image. The job images need the fixes as well as the UI. Existing
source assignments, secrets, identities, ingress, authentication, task retry
limits, and scheduler cadence must remain unchanged. No extra GIS-provider run
is needed for deployment; refusal handling is tested offline with synthetic
responses. A publisher-only run may validate sanitized publication.

Deployment evidence, exact image digests, revisions, and rollback references
will be added after verification. Private authenticated rendering and the next
scheduled live provider cycle must not be claimed as verified without evidence.
