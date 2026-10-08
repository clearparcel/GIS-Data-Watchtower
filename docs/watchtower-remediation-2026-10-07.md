# October 7 review remediation

This implementation is prepared on a feature branch. It has not been deployed,
and it does not change authoritative provider scheduling. The production
application remains the separately recorded v0.1.1 rollout.

## Observation semantics

Catalog checks preserve the previous successful `county_records` on failure.
`catalog_observed_at` identifies the retained payload; `checked_at` identifies
the latest attempt. `catalog_retained` does not clear the source's error or
renew observation freshness. Recovery replaces the payload. Older records may
infer their observation time from `last_success_at` (or an explicitly successful
check), marked by `catalog_time_inferred`; a failed attempt is never that fallback.

The county acquisition-age chart distinguishes unavailable catalog data,
missing county entries, and provider-supplied missing dates. Retained catalog
data has an explicit notice and the original observation time. GAC public
projection preserves its own `observed_at` and typed `observation_status`.
Missing legacy GAC times are labeled as inferred from a successful observation.

## Read-only dashboard contracts

`GET /api/summary` returns schema version 1, `content_revision`, publication and
provider observation times, source/worker observation metadata, freshness
thresholds, county paths, research counts, and the three standards' summary
measurements and six largest mandatory-field gaps. It contains no raw worker
configuration or provider connection details. `refresh_failed` identifies a
cached snapshot after a storage-read failure.

Content revision hashes the sanitized observation content, application identity,
static research, and freshness thresholds. It excludes publication-only time and
relative age labels. Publication-only updates therefore change the summary's
HTTP ETag without forcing a full-page transfer. Matching `If-None-Match` returns
304; HTML and JSON support negotiated gzip and retain the public security headers.

`GET /api/county-profile?slug=...&revision=...` returns one escaped county HTML
fragment from the same captured snapshot as its summary. Unknown counties return
404; obsolete/missing revisions return 409. The client refreshes the summary and
retries once, then offers the existing county-page link on failure. A native
dialog preserves keyboard/Escape behavior and returns focus to its opener.

Public views poll summaries every 30 seconds while visible and unpaused.
Observation changes defer reload until open dialogs/evidence close. User pause
is separate from temporary reading suppression and survives reload. Map metric,
county, gap standard, filters, focus and scroll are retained for the browser tab.
Private views keep their existing reload cadence with the same intent-preserving
pause controller. Generated offline static pages retain their reload fallback;
they do not require the dynamic summary API.

Mobile tables retain semantic column headings inside keyboard-focusable scroll
regions. Export sits outside the navigation's overflow context. Graphics share
the API calculations: exclusive parcel paths, coverage and record-weighted/median
county mandatory population for each standard, and ranked mandatory-field gaps.
Each has a table/download alternative. Unscanned fields do not become zeros.
Road representation and opt-in metadata remain distinct; the cause of the
71-versus-55 discrepancy remains unresolved. These measures do not certify value
accuracy, geometry, provider permission, NG911, or standards compliance.

## Hybrid candidate and validation preparation

The inspected authoritative task still runs the older 26-source local package.
Its successful exit does not maintain the 35-source hybrid public aggregate.
The scoped cloud scheduler inventory contains only the sanitized publisher.
No schedule or installed production package was changed by this implementation.

Worker reports now carry private `runtime_identity`: build version/revision,
normalized package hash (Python and bundled JSON standards/county resources),
and configuration hash. Runtime artifact paths are
excluded because local and cloud locations differ. These fields are excluded
from public projection. Public observation times allow offline arrival checks.

Use the current private registry and the candidate package to prepare a manifest:

```powershell
python scripts/validate_hybrid_observations.py --config PRIVATE_REGISTRY --prepare --output PRIVATE_MANIFEST
```

The manifest derives expected cloud/local IDs from explicit execution profiles,
fails closed on unassigned/invalid/duplicate IDs, records five required daily
cycles, and sets `activation_authorized=false`. Never commit a registry or receipt.
Do not run this preparation against the old unprofiled authoritative registry
and treat it as a valid hybrid candidate.

For each separately authorized daily cycle, use the existing cloud worker with
the cloud profile and the local first-class CLI (`check --execution-profile local`)
with the same candidate package/registry. Give the local candidate a separate
private state/history directory; do not replace the authoritative local task.
Use the existing private staging storage prefix and aggregate destination, with
the local CLI publishing only its profile report through CAS. Preserve provider
assignments, request limits, 429 stop behavior, and daily cadence. Coordinate
checks with the authoritative process rather than silently adding polling.

Capture the worker reports, private aggregate, and sanitized public snapshot to
private storage, then validate without making provider or storage requests:

```powershell
python scripts/validate_hybrid_observations.py --config PRIVATE_REGISTRY --cloud CLOUD_REPORT --local LOCAL_REPORT --aggregate AGGREGATE --public PUBLIC_SNAPSHOT --output PRIVATE_RECEIPT
```

A passing receipt requires complete inventories, identical runtime identity,
matching worker/source observation timestamps and provenance, healthy source
results, and matching catalog/GAC observation identity in public output. Shared
sources are compared with the latest accepted worker report while both workers'
inventories, identities, and health are validated. It does
not establish scheduling authority or count five daily cycles automatically.
Retain dated receipts, parity checks against the authoritative process, CAS/
failure/recovery evidence, and JSON/CSV/XLSX/dashboard verification for five
distinct daily cycles under issue #20. Same-day retries do not add cycles.

Before activation, prepare exact installation/configuration identities,
worker ownership and daily timings, destinations, acceptance receipts, prior
package/task definitions, and rollback steps. Schedule activation, production
configuration writes, PR merge, and application deployment each retain their
existing explicit approval boundaries. The earlier application-rollout waiver
did not pass the multi-day validation gate.

## Verification and remaining gates

The reviewed snapshot reproduces 46 MnGeo-only, 11 direct-only, 13 overlapping,
and 17 unobserved parcel paths. Mandatory weighted/median rates reconcile to
78.37/57.14% parcels, 97.21/99.92% addresses, and 95.94/96.95% roads. Research
remains 15/87 complete profiles, with 216 reviewed and 132 blocked category slots.

Local QA reduced the homepage from 1,782,856 decoded bytes to approximately
131 KB decoded / 38 KB gzip, and the summary to approximately 15 KB decoded /
3 KB gzip. This satisfies the 250 KiB homepage and 64 KiB summary budgets.
These are fixture-based transfer measurements, not production/mobile timing
benchmarks. Regression coverage includes retention/recovery, typed projection,
hybrid identity/arrival, weighting and missing values, revision conflicts,
ETags/gzip, manual pause during in-flight requests, publication label updates,
shared-profile winner validation, runtime schema identity, and pending updates
after 304 responses. The final required suite passes 306 tests; compilation,
status-document consistency, and whitespace checks pass.

Provider validation cycles, staging deployment, production rollout, and schedule
activation remain pending. County matrices and durable history/trends are deferred.
