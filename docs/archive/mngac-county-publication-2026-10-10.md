> Historical v0.1.2 publication record. The v0.2.0 rollout in [the current release record](release-v0.2.0.md) supersedes the production revisions below.

# MN GAC county-results publication

Published on October 10, 2026 (America/Chicago), following explicit approval to
merge and publish PR #62. Merged source is
`899908121660e82b6b830c6d86bd3a202a77fd25`.

The public MN GAC page now starts with County results and a searchable county
chooser. County summaries and field tables share a destination with map links;
the county persists across standards. Statewide overview remains available.
No data, Not scanned and measured zero population remain distinct.

## Deployed artifact and rollback

- Cloud Build: `7d82bfdb-86ef-4e5f-8b76-a9707439cb13`.
- Source upload: 50 allowlisted application inputs from the merged Git archive.
- Image digest: `sha256:3dc78daa7e5cbdeda970c4e05c12277c57c0f9ed7d1c289bd22756cb92e8f8f9`.
- Public service revision: `gis-data-watchtower-public-00013-s7q`, 100% traffic.
- Display identity: v0.1.2, build `8999081`, Production.
- Rollback revision: `gis-data-watchtower-public-00012-c5j`.
- Rollback image: `sha256:003c60772fc5a5fa1f91ccabbd840c60a4ca52d14160078f7df65adf3205b8b7`.

The prepared revision received no traffic until Cloud Run reported it ready
and its non-image runtime configuration matched the prior revision. The public
service's ingress and authentication-related annotations were preserved.
The private dashboard, isolated cloud preview, sanitized publisher and provider
jobs were not updated. No provider polling or scheduling change was performed.

## Acceptance

All 328 local tests, compilation and diff checks passed before merge. PR and
merged-main CI passed, including the supported Linux/Windows Python matrix and
security checks. The built container verified its version, full source revision,
production environment, and rendering of all three county standards.

After promotion, all six county/statewide standard combinations returned 200
with the expected build and scope. Douglas County counts and percentages matched
saved observations. Overview, county index, county profile, source profile,
87-row county CSV and publication health passed. The 35 source observations,
including provider-check times, worker provenance, statuses and tested counts,
and all saved MN GAC results matched the pre-deployment public baseline.

Chrome verified the live county chooser and Douglas results. Desktop/mobile
navigation, field filters and keyboard map links were verified in the local
candidate preview before merge. Provider freshness remains independent of this
UI publication. The retained Hennepin imagery warning is not resolved by it.
