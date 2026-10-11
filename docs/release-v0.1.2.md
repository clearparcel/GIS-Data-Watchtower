# GIS Data Watchtower v0.1.2 review and release

## Publication status

Published on GitHub and deployed on 2026-10-10 from merged commit
`a3899f6a511906ecb4c0ecfd8c94ab537e6badb8` (PR #60). Public revision `00012-c5j`,
private revision `00020-lqc` and isolated preview `00018-rkt` received 100% traffic
at that rollout. The existing sanitized publisher job uses this production image.
The public service subsequently advanced to build `8999081`, revision
`00013-s7q`; see the [MN GAC publication record](mngac-county-publication-2026-10-10.md).

## Confirmed fixes

- Repair UTF-8 punctuation decoded as Windows-1252/Latin-1 in public display
  labels, including labels containing otherwise valid Unicode. Preserve source
  IDs, worker IDs, slugs and other opaque metadata exactly.
- Use the transparent ClearParcel PNG in the shared public footer and include
  it in installed packages.
- Prefer the matching source checkout's declared package version over stale
  editable-install metadata. Installed wheels retain their package metadata
  fallback; malformed or unrelated project files do not break the footer.
- Report unknown, missing and unsupported source statuses as unknown health,
  independently of reporting freshness, instead of labeling them healthy.
- Restrict Cloud Build source uploads to application inputs and exclude agent
  scratch, attachments and operational data from build contexts.

## Review and validation

The review covered repository state, CI/release configuration, packaging,
provider transport boundaries, public projection/rendering, storage concurrency,
aggregation and status reporting. Independent bounded CCE review established
no additional actionable transport, projection or concurrency defect. This is
a scoped code review, not a claim that the project is free of all defects.

Baseline: 319 offline tests passed. Final local validation: **322 tests passed**,
along with compilation, documentation synchronization and `git diff --check`.
The built wheel contains the transparent asset and renders the v0.1.2 footer
when imported independently of the checkout. The Cloud Build upload allowlist
contains 49 application inputs and excludes private working directories.
Overview, county index/detail, MN GAC and Douglas source pages all returned HTTP
200 with the updated version and PNG, and no corrupted punctuation. Browser
automation was unavailable, so these are HTTP/rendered-markup checks rather
than a fresh visual acceptance. GitHub CI additionally checks the supported
OS/Python matrix, dependencies, CodeQL and the container image.

The local preview uses a sanitized saved cloud report. Replaying it does not
contact providers or renew its observation/publication timestamps. Known
operational gates remain open: multi-day cloud activation evidence, explicit
authoritative scheduling approval and normal Codex Cloud CCE readiness.
No provider schedule, source registry, credentials or worker retirement is
changed by this patch.

## Deployment scope

Build only committed public source with the full commit and environment baked
into the image. Validate the existing isolated preview using its saved public
data before promoting the public UI. Preserve the private service's audited
IAP wrapper if updating that service. Retain prior image digests for rollback.
Do not infer provider health from successful UI deployment or publication.

## Verified rollout

Cloud Build `8f4f0482-b10f-49e9-85a9-f95e92597b62` built both application images
from a clean archive of the merged source, with version, source revision and
environment verified inside each image:

- Preview: `sha256:f1d1bde9c80d1f77f3b925833456d37fff6199cc794fb13eebcb60b134e67237`.
- Production: `sha256:003c60772fc5a5fa1f91ccabbd840c60a4ca52d14160078f7df65adf3205b8b7`.
- Private derivative: `sha256:fada00d83d7c5da6462d453a54cc6822ba292201935a1d42061ed62d3cbc96a2`,
  built by `cbb8b212-7a58-4add-890b-4c74508c2875`. Its existing wrapper hash remains
  `786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`, with the same
  Python entrypoint and non-root user.

Preview and production acceptance passed for overview, county index, Douglas
county, MN GAC and Douglas source pages, all showing v0.1.2/build `a3899f6`, PNG
branding and corrected punctuation. County CSV contains 87 rows. All 35 source
statuses, worker provenance, check/success timestamps and tested counts match
pre-deployment observations. No forbidden private fields appeared in public
state. The snapshot retains 34 OK and one Hennepin imagery warning; latest
provider check is `2026-10-09T14:32:27.969062+00:00`.

All four workloads retain their non-image runtime configuration. Public ingress
and private IAP settings are unchanged; anonymous private access redirects to
Google authentication. Public `/healthz` returned 200. The existing publisher
schedule remains `3,13,23,33,43,53 * * * *`; no provider job was executed or
rescheduled during rollout. This application release does not complete the
multi-day provider activation gate or resolve the existing imagery warning.

The first scheduled execution on the new image,
`gis-data-watchtower-public-publisher-ndhgm`, completed successfully at
`2026-10-10T23:55:12.802272Z`. Its public snapshot timestamp is
`2026-10-10T23:55:06.166329+00:00`. Post-publication page/export and observation
parity checks passed again. Temporary build source archives, local build
contexts and private runtime configuration copies were removed after validation.

Rollback: public `00011-b9c` and publisher production image
`sha256:3f3244054a202c55a464e06e85afea9f72dc750bc34d75cbbe872fde5495dfb6`;
private `00019-c9l` on
`sha256:4fbc66103d968c289e03d48a07646a9c6ac69435cd7d46700c9b137c85dd9ed6`;
preview `00017-s8b` on
`sha256:354da814dc0dc24137e4818e57761769ab13320cda9311d6088cb7662803eec1`.
