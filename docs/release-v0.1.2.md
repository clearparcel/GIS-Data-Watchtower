# GIS Data Watchtower v0.1.2 review and release

## Publication status

The October 10 project review prepares v0.1.2 for publication. Google Cloud
deployment is pending renewed operator authentication and live acceptance.
The last verified production release remains v0.1.1; this document does not
claim that v0.1.2 is deployed.

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
