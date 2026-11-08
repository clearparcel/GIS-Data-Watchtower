# November 8 review disposition — v0.5.1

Base: `8661beaf65a0017d2c47c97d300fa535567d76d5`. This records the response to the
repository review; it is not a claim that every operational backlog item has
been completed. See the release record for actual promotion state.

| Finding | Candidate correction / disposition |
| --- | --- |
| R01 High: enrolled-source SSRF | Incorporates PR #230, including DNS validation, address pinning, proxy rejection and all shared transports. |
| R02 Medium: corrupt private sync | Validate aggregate structure/totals and history containers before replacement; preserve good files, show cached-data warning and expose authenticated `/healthz` sync failure. |
| R03 Medium: directory outages | Back off failed reads for at least five seconds; all directory CSV exports return controlled 503; public readiness includes directory availability. |
| R04 Medium: storage amplification | 30-second editor summary cache with successful-save invalidation; bounded 2,052-byte attachment metadata reads tied to a storage generation. Cold lists still read 87 county records; no unbounded parallel fan-out was introduced. |
| R05 Medium: LAN authentication | Password-free access is loopback-only; existing read-only hosted IAP trust is preserved. |
| R06 Medium: save attribution | Verified actor, time and revisions are committed atomically with each private save; replay creates no duplicate event. Retention and private retrieval are documented. |
| R07 Low: repeated research validation | Cache a private research snapshot/digest for the immutable application process; freshness buckets remain independent. |
| R08 Low: stale current claims | Remove conflicting current-release summaries; source-version/doc consistency is checked; label backup history by date and retain scanner acceptance evidence. |
| R09 Low: contributor dependencies | Document constrained full-extra installation and Node 24; optional scanner transport test skips when its dependency is absent. |
| R10 Low: stale work | Disposition below preserves unique work and separates obsolete releases from unfinished features. |
| R11 Low: personal checkout | Replace current public machine/account mapping with a role and private inventory; remove the hygiene-test exemption. No public history rewrite. |
| R12 Low: concentrated modules | Consolidate the identical timestamp parser, preserving legacy aliases. Broad adapter/editor decomposition is deliberately incremental; it is a maintenance backlog, not a demonstrated runtime defect. Compatibility shims and historical evidence remain intentional. |

## Branch/PR disposition

No unique remote history is deleted in this patch. Git commit permalinks and
existing PRs retain the original evidence. Branch retirement below means no
further development should target that obsolete release; it does not erase refs.

- **PR #230**: incorporated by ancestry in v0.5.1; close only when the release PR
  merges and its commits are on main.
- **PR #209 / `codex/washington-parcel-release`**: obsolete v0.3.14 packaging;
  close as superseded when this disposition merges. Washington's fees/license
  conflict remains a terms hold. This release does not enroll it or poll it.
- **PR #213 / `codex/watchtower-v040-live-verification`**: historical live
  acceptance retained in `docs/release-v0.4.0.md` from
  `fc12973f9c6d6e62a2610aac08d03b3f87e0be0a`; close the superseded draft after merge.
- **PR #143 / `claude/county-data-fees`**: preserve as explicitly deferred feature
  work at `89c59792bfb6797de47d10220f91ef18f67e10fd`. It needs a current county-editor
  integration design and refreshed citations before rebase. Shipping a new fees
  dataset is outside this security/maintenance patch; do not merge its old UI.
- **`codex/status-handoff-20261020`**: retire the historical continuation lane.
  Unique evidence stays at [its exact commit](https://github.com/clearparcel/GIS-Data-Watchtower/commit/7e0890c2951d1ae585a23202568c77883fced73f).
- **`feat/data-freshness`**: superseded by PR #197 and later history/MnGeo fixes.
  Its [original commit](https://github.com/clearparcel/GIS-Data-Watchtower/commit/a840a7c7244e2ef3e4f26513ded3b58f6557fe41)
  stays available; do not merge the older implementation over main.
- **Research branches**: preserve both documents in `docs/research/`, explicitly
  historical. Original heads: credential research `a767ab564e3b83b9d12c3f7baa73303f406f6021`;
  retention research `6e083b28b654e6bd6519f6fa4e8d117be69861a0`. Their operational
  proposals remain subject to issues #189–#191 and current owner decisions.
- **Dependabot branches**: recent automated work, not classified stale. Keep
  normal dependency review/CI; no blanket deletion or unsolicited dependency bump.

## Remaining operational and maintenance scope

The previously owner-deferred independent backup/project separation (#181/#205),
independent heartbeat (#202), and future drafting-credential governance (#191)
remain tracked decisions. No new credential, backup project, irreversible
retention lock or provider schedule is created by this patch. Historical accepted
public release evidence and intentional professional county contact data are
retained. Large-module extraction should proceed behind stable interfaces with
adapter and editor recovery tests, rather than combining a wholesale rewrite
with this patch release.
