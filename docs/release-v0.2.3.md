# GIS Data Watchtower v0.2.3

**Deployed and verified October 13, 2026 (America/Chicago).** Owner-authorized
[PR #77](https://github.com/clearparcel/GIS-Data-Watchtower/pull/77) merged
to `main` as `f95d9315510497ae25cfd058f9a175b240b6debd`.
The immediately preceding [v0.2.2 release](release-v0.2.2.md) is the
rollback baseline. This release changes website branding only.

## User-requested branding

- Added the supplied dark-background Minnesota Watchtower logo immediately
  beside the public header title; the logo links to the overview and scales
  from 54px on desktop to 44px and 38px on smaller screens. Offline static
  exports use a relative overview link.
- Replaced packaged 16px and 32px favicons with the supplied blue-background
  Minnesota Watchtower artwork. Public, private, and offline page templates
  embed the new favicon locally.
- Embedded the optimized WebP header logo locally, without fetching a
  third-party asset. Retained the established ClearParcel footer branding.
- Bumped the public application release identity to **v0.2.3** as required by
  the live-version preflight. No GIS dataset, API, monitoring, or authentication
  behavior was intentionally changed.

## Source and image validation

The feature commit `2ceb33fb2cf974b30ab0f848d8d092c4a81ee370` passed
all 371 ResourceWarning-strict local tests, compilation, diff checks, status
synchronization, the read-only release preflight (live v0.2.2 to v0.2.3), and
GitHub Actions' seven jobs, including security. The merged `main` commit
also passed GitHub CI (run `38408701690`; PR CI run `38408061860`).

Cloud Build **`78969f3e-021f-41f6-8704-8c7133f21e3a`** succeeded
using six steps reconstructed from the audited v0.2.2 build. Its input was
a committed-only archive of the exact merged source, with 56 allowed build
files (about 2.2 MiB), not a working directory containing untracked files.
The container checks verified application identity as v0.2.3, exact source
revision, production environment, and the existing private wrapper SHA-256
`786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.
The derivative copied that wrapper from the previously audited immutable
private image; it was not rewritten.

| Service | New production revision | Immutable image digest |
| --- | --- | --- |
| Public read-only dashboard | `gis-data-watchtower-public-00019-4zl` | `sha256:4ae84cf389e60fc569fefdd4a3760add07537284469bb8fc1995090ddd631789` |
| Private authenticated dashboard | `gis-data-watchtower-dashboard-00026-6gg` | `sha256:cc2102f4b2ce42fd619271dd600962a80533a4b40aa1eb4e6d8ad5749787d334` |

Both candidates were first deployed at zero traffic and individually checked
for Ready status, immutable image identity, unchanged container configuration,
ingress/IAP settings, and IAM bindings. Previous revisions continued to
serve 100% while the candidates were staged. Both new revisions were then
promoted to **100% traffic**, and post-promotion checks passed.

## Live acceptance

At [gis-watchtower.clear-parcel.com](https://gis-watchtower.clear-parcel.com),
the Overview, Counties, MN GAC, and `/healthz` endpoints returned HTTP 200.
Each public page showed v0.2.3 and the new header logo. The exact header WebP,
16px favicon, and 32px favicon were decoded from live HTML and matched the
packaged files byte-for-byte. Responsive CSS for the header logo was present;
a separate interactive browser screenshot test was not performed.

The unchanged public exports remained readable: 35 source rows, 87 county
profiles, 350 parcel-source rows, and a valid 12-sheet Excel workbook.
Anonymous access to the private Cloud Run service still returned HTTP 302
to Google sign-in. Signed-in private rendering was not independently tested.

The provider worker and public publisher **jobs were not updated** and retain
their previously deployed v0.2.2 image. Their specifications remained
unchanged. Scheduler definitions and enablement were verified unchanged:
provider checks `0 5 * * *`; publisher
`3,13,23,33,43,53 * * * *`; both America/Chicago.
No extra provider poll, publisher execution, source registry, IAM, DNS, secret,
or scheduled task change was performed. The previous observations and the
existing provider warning were not represented as newly refreshed evidence.

The temporary Cloud Build source object
`source/1791900023.378542-c799294797d74389a8ada9a05c87d656.tgz`
was verified at generation `1791900024955061` and deleted with the matching
generation precondition. The immutable pushed images and prior Cloud Run
revisions are retained for rollback.

## Rollback

The immediate rollback revisions are public
`gis-data-watchtower-public-00018-4vx` and private
`gis-data-watchtower-dashboard-00025-7pf` (v0.2.2).
Their previously verified digests are:

- Public: `sha256:2d2f4a5fe1fe9dcadbfd1d622844096b36d670a5710bb268d0e9a9233cccb4b7`
- Private: `sha256:a3ea1d5b7dded078b2fd2f0b2fa748e42846c30e7119ff0a2f21972dd44e48db`

A rollback should shift only service traffic to those known Ready revisions.
Do not change the existing job images, provider schedules, authentication,
IAM, or source observations. The v0.2.2 release record retains older
rollback references and the provider/publisher image evidence.
