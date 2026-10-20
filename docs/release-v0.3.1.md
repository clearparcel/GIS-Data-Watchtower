# GIS Data Watchtower v0.3.1

**Historical release, deployed October 20, 2026; superseded by [v0.3.2](release-v0.3.2.md).** Both dashboard services received 100% traffic
on verified v0.3.1 images. Public routes and authenticated private county
flows passed bounded acceptance. The separate private GAC county selector
was an acceptance gap at this release, corrected and verified in v0.3.2.

## Changes and authority

The owner requested merge and deployment after isolated-restore PR #105 passed
hosted CI. It merged as `cd2e071672740bebc10955720d8bd00d5fa89899`.
Release preparation PR #106 incremented the required version and merged as
**`9ee6c5a3caa7a1d118e7d9f27e32eb200126848b`**, the deployed application source.
Later documentation receipts do not change that artifact identity.

- WT-01 (#102) corrects county schema/scan labels across pages and exports.
  Explicit false, unknown, unavailable and scanned zero-population values
  remain distinct.
- Offline operations tools (#103–#105) provide saved-run triage,
  monitoring-authority evidence matching and synthetic local restore/CAS
  rehearsal. Their command scripts remain repository tools; the Dockerfile
  does not package `scripts/` as operational commands.
- Only dashboard service images and their traffic were promoted. Provider
  and publisher jobs, schedules, source assignments, registry data, credentials,
  IAM, ingress, IAP and non-image runtime settings were preserved.
  No provider job or rehearsal was executed. There are no data migrations.

## Exact artifact and validation

- Local versioned candidate: **575 tests passed, 3 platform skips**, 29.238
  seconds, Python 3.14.6 and required Node 24 tests enabled. Compilation,
  status synchronization and whitespace checks passed.
- The isolated-restore application diff received the owner-requested bounded
  CCE review with no actionable findings; release preparation changed
  version metadata and documentation.
- PR #105 CI [39425151613](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39425151613)
  and post-merge CI [39426148900](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39426148900) passed.
- PR #106 CI [39434023400](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39434023400)
  passed all eight checks. Deployed-source CI
  [39434614599](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39434614599) passed.
- Release preflight confirmed the strictly newer version, v0.3.0 → v0.3.1,
  before either service was promoted.
- Regional Cloud Build **`e0c744d6-e783-41af-86db-f81bbfa88bfa`** passed all
  nine steps using a committed-only source archive. Both images reported
  v0.3.1, the exact source above and `production`; both ran the WT-01
  `test_county_scan_projection.py` regressions inside the built image.
- The private wrapper was copied from the verified predecessor and checked
  for imports and referenced dashboard attributes. Its unchanged SHA-256 is
  `786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.

Image repository prefix:
`<region>-docker.pkg.dev/<project-id>/<artifact-repository>/`.

| Service | Image and immutable digest | Promoted revision | Traffic |
|---|---|---|---|
| Public | `watchtower@sha256:35d964177e30cb00306007aede625f22893b6c894cd7b6aca989fcabdcc479cb` | `gis-data-watchtower-public-00033-mak` | 100% |
| Private | `dashboard@sha256:11c2bc0dc7f1e76f6428a593c682637f40d374703503c0eba454f9348b12d6e3` | `gis-data-watchtower-dashboard-00035-vom` | 100% |

Both candidates were Ready with zero traffic before promotion. Actual traffic,
image identity and unchanged non-image/security settings were read back after
each promotion. The public tagged `run.app` route returned Google's 404 under
the existing `internal-and-cloud-load-balancing` ingress. That restriction was
preserved: public HTTP acceptance ran immediately after promotion through the
authorized public domain, with rollback ready. A pre-promotion public tagged
HTTP pass is not claimed.

## Bounded live acceptance

The public receipt was observed at **2026-10-20T14:30:00.210564+00:00**:

- Ten routes passed: overview, county index, Cass and Brown profiles, Cass
  GAC detail, public state, Cass JSON/CSV/XLSX and health.
- Public footers showed v0.3.1; applicable responses retained hash-based
  script CSP without `unsafe-inline`, and `nosniff`.
- Cass `STATE_PIN` changed from the reproduced profile mismatch
  `Unknown / Not scanned` to **Present / Scanned / 51,689 / 51,689 / 100%**,
  agreeing with the public GAC view. JSON flags and workbook detail matched;
  CSV parsed successfully.
- Source IDs and their saved `checked_at`, status, worker and `last_success_at`
  values matched the pre-release snapshot. Publication is not a new provider
  observation.

Authenticated private acceptance used the existing operator login:

- Candidate and promoted live Cass county pages displayed the same corrected
  row. Field search and inclusion filters passed; JSON flags/counts matched.
- The downloaded candidate workbook was parsed and its scan flag, counts and
  percentage verified. It came from the exact immutable image subsequently
  promoted; no second post-promotion workbook download is claimed.
- The separate private `/mngac?standard=parcel&county=cass` page showed an
  unselected county input without detail. The initial accessibility inspection
  did not establish the datalist contents. Subsequent investigation found all
  87 suggestions present and reproduced the selection loss: the retained
  wrapper discards query parameters. The subsequent [fix](ai/handoffs/2026-10-20-private-gac-selector.md)
  was deployed and verified within the [v0.3.2 acceptance scope](release-v0.3.2.md).

A bounded query for ERROR-level logs from the two new revisions returned
zero entries. This is not proof of every route or future request. The private
overview already showed a Todd source error before rollout; this deployment
does not resolve it or establish all-provider health.

## Rollback and remaining operations work

The retained v0.3.0 predecessors are:

| Service | Revision | Image digest |
|---|---|---|
| Public | `gis-data-watchtower-public-00031-ciw` | `sha256:3df9fe0ce9373509ba1d80d1008e240274014626848c052cf8104eecd90f8f76` |
| Private | `gis-data-watchtower-dashboard-00033-qor` | `sha256:05599e269642ae0031d3d75682cadd3ffffc097ae5a224351edd06a4031ddb54` |

Each predecessor had 100% traffic before this release. Restore that captured
allocation if rollback is needed, then verify identity and behavior.
**Rollback was not exercised.** See [v0.3.0 evidence](release-v0.3.0.md).

Both provider and publisher jobs were independently read back on the unchanged
v0.3.0 `watchtower` digest above. Private configuration snapshots and raw
acceptance evidence remain outside public Git. Monitoring-authority evidence,
complete-backup/GCS restore, alert delivery, IAM proof and five ordinary daily
cycles remain separate operational work; deploying these images does not
establish those outcomes.
