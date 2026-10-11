# GIS Data Watchtower v0.2.0

The user explicitly requested publication of the reviewed updates, then specified
version **0.2.0**. PR #64 passed all 15 CI checks and merged at
`e258c39eedb1a21ad17fabc8b892f3ddc0152b74`. Publication is in progress; no v0.2.0
image has been deployed yet.

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
The version-only release will be checked again before building committed source.

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
new revisions, immutable images and acceptance results will be recorded after
publication.
