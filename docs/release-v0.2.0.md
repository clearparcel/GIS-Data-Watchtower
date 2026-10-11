# GIS Data Watchtower v0.2.0

The user explicitly requested publication of the reviewed updates, then specified
version **0.2.0**. PR #64 passed all 15 CI checks and merged at
`e258c39eedb1a21ad17fabc8b892f3ddc0152b74`. The version change in PR #65 also
passed all 15 CI checks and merged at
`308e3a720886db080b908d7a91719e6732b0d736`. **v0.2.0 is published** on
October 10, 2026; all three dashboard services receive 100% traffic on the
verified new revisions.

## Release behavior

- Overview selection populates the adjacent county pane with monitoring details,
  field-population infographics and dated, source-specific MN GAC schema evidence.
- Map frame and county pane share equal heights, including stacked layouts.
  The six research/source accordions stay on the linked complete county profile.
- County suggestions contain each name once. The default map separates statewide
  standardized availability, checked differing direct schemas, documented fee
  policies, unassessed open schemas and unresolved access. Patterns supplement
  color; percentage legends use N/A for unavailable observations.
- Olmsted and 12 other direct counties also appear in MnGeo Open Parcels.
  Unique monitoring coverage is derived: 59 statewide + 24 direct - 13 overlaps
  = 70 counties. Statewide availability and direct schema evidence remain distinct.
- Clearing county selection cancels stale fragment responses. Missing county and
  source detail pages return HTTP 404. County JSON/CSV/XLSX share schema findings.

## Validation and operational boundaries

Merged PR #64 passed the supported Windows/Linux Python 3.12–3.14 matrix,
security/container checks and CodeQL. The merged source passed all 340 offline
tests with ResourceWarning treated as an error, compilation and status/diff checks.
The v0.2.0 version/release change also passed all 340 tests, compilation,
documentation synchronization and diff checks before its passing CI merge.

Builds verify package version, exact source revision and environment inside each
image. The private derivative retains the audited IAP wrapper with SHA-256
`786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`, Python
entrypoint and non-root user. Existing non-image service configuration is retained.
Saved-data UI acceptance precedes production promotion; no GIS provider run is
needed for this release.

Daily cloud provider polling is already enabled at 05:00 America/Chicago under
separate explicit approval. Its October 10 activation passed 35/35 sources and
public arrival. The UI release does not change provider scheduling, registry,
credentials, policy holds or historical worker records. The five-day observation
study and normal Codex Cloud development acceptance remain incomplete.

## Retained rollback targets

- Public: revision `gis-data-watchtower-public-00013-s7q`, image
  `sha256:3dc78daa7e5cbdeda970c4e05c12277c57c0f9ed7d1c289bd22756cb92e8f8f9`.
- Private: revision `gis-data-watchtower-dashboard-00020-lqc`, image
  `sha256:fada00d83d7c5da6462d453a54cc6822ba292201935a1d42061ed62d3cbc96a2`.
- Isolated preview: revision `gis-data-watchtower-public-v2-preview-00018-rkt`,
  image `sha256:f1d1bde9c80d1f77f3b925833456d37fff6199cc794fb13eebcb60b134e67237`.
- The sanitized publisher and provider worker are unchanged by this UI release.

Rollback restores the retained service revision/image without changing runtime
authentication, ingress, IAM, provider settings or saved observations. Verified
new revisions, immutable images and acceptance results are recorded below.

## Verified publication

Cloud Build `87e5c723-23d8-4b10-a7bf-d095d8fe0138` built only committed public
application inputs and verified all image identities. It extracted the retained
private wrapper from the prior immutable dashboard image and verified the exact
hash before and after building the derivative.

| Service | Revision | Immutable image SHA-256 |
| --- | --- | --- |
| Public | `00014-jsr` | `d613d2bbbd57ed25b08e01dbe4a87be9bed5112343838f95e90682aee0c4833d` |
| Private dashboard | `00021-hr8` | `24002f249e2808a463e699a14803de1270bb898838d82d6dc160911e63a4dae3` |
| Isolated preview | `00019-x5b` | `88fda5f0f55d4d7c22705039a8b93b6b4f1a28a5c2e1e831f9f51386bb21a5f1` |

Seven preview and seven production page checks passed with v0.2.0/build
`308e3a7`, the correct build environment, transparent PNG branding and no checked
mojibake. Four exports passed, including 87 county CSV rows and a valid XLSX
workbook. Missing county/source routes returned 404. Public `/healthz` returned
200; the live summary showed 35 healthy sources and derived 70/87 county coverage.

All source results, counts, worker provenance and report/check/success clocks
matched the pre-deployment baselines. Timestamp comparisons normalized timezone
offsets because PowerShell serialized baseline times in Central time. The
production provider report remains October 10, 22:30 CDT; later automatic
publication times are independent of provider checks. No provider run was
triggered by this UI release.

Browser acceptance verified Sibley's differing direct schema and Olmsted's
statewide standardized availability despite its unassessed direct schema.
County selection updates Pane A without a dialog or the removed accordions.
Map and pane heights matched after asynchronous details loaded, including
390px width with no horizontal overflow. All five schema/open-data legend
categories rendered; the live footer shows v0.2.0/build `308e3a7`/Production.

All three services preserved their non-image runtime specifications and security
annotations. Public/private IAM bindings and both Scheduler definitions were
unchanged. Anonymous private access still returns a 302 redirect to Google
authentication. The private image identity and audited wrapper were verified;
fresh acceptance behind a signed-in private session was not performed.

The isolated preview retains its October 7 saved observations; its age and
historical source issue are fixture limitations, not current production health.
The sanitized publisher and provider worker continue using their existing images;
this release updates dashboard behavior, not provider processing.

Superseded v0.1.2 build `2692d853-66ed-4041-9935-97958f3aefd1` was canceled after
the user requested v0.2.0 and was never deployed. Temporary public build archives,
build contexts and private runtime copies were removed after acceptance.
