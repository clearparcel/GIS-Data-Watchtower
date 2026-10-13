# GIS Data Watchtower v0.2.2

**Deployed and verified October 12, 2026 (America/Chicago).** Owner-authorized
PRs [#73](https://github.com/clearparcel/GIS-Data-Watchtower/pull/73) and
[#74](https://github.com/clearparcel/GIS-Data-Watchtower/pull/74) provide the
corrections and supplied favicon. Exact deployed source:
`aba3d23b28ccf93b0de56b4b1b50d2518e3ffd43`.
The prior [v0.2.1 release](release-v0.2.1.md) remains the service rollback baseline.

## Review corrections

- Added the owner-supplied Minnesota Watchtower map icon as 16px and 32px PNG
  favicons. Shared page layouts embed the packaged assets for public, private,
  and offline pages without adding a remote asset dependency.

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

All **368 tests** passed with ResourceWarning treated as an error. Compilation,
generated-status synchronization, diff checks, and the complete GitHub CI/security
matrix passed. The main-commit CI run was `38335142978`. The read-only release
preflight verified deployed v0.2.1 → candidate v0.2.2 before rollout.

Local public-data-only acceptance verified one labelled focusable scroll region
per table, retained labels, mobile keyboard horizontal scrolling at 390px, and
no page-wide overflow. Both public and private page layouts decoded to the exact
16×16 and 32×32 favicon assets (896 and 2,142 bytes).

## Build and deployment

Cloud Build **`d4beed3e-d2a0-43f3-9e41-fff79f38e50c`** succeeded in all six
steps. It uploaded 55 packaged files (about 2.2 MiB), drawn from a 56-file
committed allowlist. No deployment registry, credentials, or local configuration
was in the build context. The private derivative copied the prior audited
wrapper and verified SHA-256
`786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.

| Target | Deployed revision or job | Immutable image digest |
| --- | --- | --- |
| Public dashboard | `gis-data-watchtower-public-00018-4vx`, 100% Ready | `sha256:2d2f4a5fe1fe9dcadbfd1d622844096b36d670a5710bb268d0e9a9233cccb4b7` |
| Private dashboard | `gis-data-watchtower-dashboard-00025-7pf`, 100% Ready | `sha256:a3ea1d5b7dded078b2fd2f0b2fa748e42846c30e7119ff0a2f21972dd44e48db` |
| Provider worker | `gis-data-watchtower-staging` job (existing operational name) | same application digest as public dashboard |
| Public publisher | `gis-data-watchtower-public-publisher` job | same application digest as public dashboard |

Both service candidates were first created at 0% traffic, checked for readiness,
exact digest, and unchanged non-image runtime/security configuration, then
promoted to 100%. Job container arguments, task counts/retries, identities,
environment, volumes, and timeouts were compared before/after and preserved.
Both schedules were read back unchanged and enabled: provider daily `0 5 * * *`
and publisher `3,13,23,33,43,53 * * * *`, in `America/Chicago`.
No extra GIS-provider run, registry change, or scheduling change was performed.
The isolated preview remains v0.2.1 and is not a v0.2.2 acceptance claim.

An earlier correction-only build (`634f0254-e1f4-433a-a11a-f4f10270984b`)
created 0%-traffic candidates before the owner supplied the favicon. Those
candidates were never promoted; the final build above supersedes them.
The two unused candidates were deleted after successful rollout. Both owned
Cloud Build source uploads were removed by their exact object generations.

## Live acceptance and limitations

Publisher-only execution `gis-data-watchtower-public-publisher-jhcql` succeeded
on the final application digest. Its sanitized snapshot was published at
`2026-10-13T02:09:11.187251+00:00` and passed the live checks below. This job
copies retained observations and does not poll GIS providers.

- Production Overview, MN GAC, Counties, and `/healthz` returned HTTP 200.
  Pages rendered **v0.2.2**, and both favicon payloads matched the resized
  supplied artwork byte-for-byte. Browser checks found zero nested table regions.
- Public JSON passed the forbidden-field validator. It shows only the cloud
  worker; local remains in retired history. All 35 source observations, feature
  counts, provenance, check times, and GAC measurements are unchanged.
- Exports contain 35 source rows, 87 county profiles, 350 parcel-source rows,
  and a valid 12-sheet workbook. Status remains 34 healthy, one existing Hennepin
  imagery warning, and zero errors. This release did not claim to fix the provider warning.
- Private anonymous access still returns HTTP 302 to Google sign-in.
  **Authenticated private page rendering was not independently exercised.**
- The next scheduled live provider cycle has not been exercised as part of
  release acceptance; refusal and malformed-statistic behavior was tested offline.

## Rollback baseline

Retain prior service revisions and exact job images. The prior service revisions
are public `gis-data-watchtower-public-00016-dck` and private
`gis-data-watchtower-dashboard-00023-2h9`. Their digests are in the v0.2.1 record.
The prior provider job digest was
`sha256:354da814dc0dc24137e4818e57761769ab13320cda9311d6088cb7662803eec1`;
the prior publisher job digest was
`sha256:003c60772fc5a5fa1f91ccabbd840c60a4ca52d14160078f7df65adf3205b8b7`.
Both are under `us-central1-docker.pkg.dev/dark-bit-503017-j7/gis-data-watchtower/watchtower`.
Any rollback must preserve the required security check, the worker retirement,
provider controls, and unchanged schedules, and needs appropriate authorization.
