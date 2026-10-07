# Browser feedback changes — October 7, 2026

These changes were published to the existing isolated hosted preview on October 7 with explicit user approval. They are not a production release.

- The overview uses the latest valid source `checked_at`, rather than aggregate generation time, for its latest provider check. It explains publication, provider checks, and provider dataset updates separately. Source overdue counts use the configured reporting window; missing check times remain unknown. Worker reports and successful checks are labeled separately, without treating a report as a success.
- Source entries and unique county coverage are explained together. One statewide source can cover multiple counties; county-direct and statewide coverage overlap. Healthy counts describe the last stored checks, rather than claiming current provider health.
- Research summaries derive dated county reviews and completed profiles separately. All 87 counties have dated research reviews; 15 composed profiles currently meet all completion conditions. Unresolved evidence and terms still prevent completion and do not authorize monitoring.
- The displayed county-direct label is **Open parcel data**. The existing `free-parcel-data` machine classification remains compatible with stored research and exports. Provider findings and policy holds are preserved.
- County record counts use thousands separators. Official evidence is presented as individual findings inside expandable details; detailed research notes use separate list items. Source metadata and evidence remain available.
- The footer links to ClearParcel and embeds the existing ClearParcel logo, obtained from the company site's public brand asset, in the generated page. No external image request is required. The logo is included in Python package data.
- The overview completeness view uses **mandatory-field population**. The MN GAC exploration page defaults to mandatory fields and retains other metric selections. Both maps share fixed percentage classes: `p < 50`, `50 <= p < 60`, `60 <= p <= 70`, and `p > 70`. Exact 60 and 70 belong to the third class. Missing statistics remain No data; observed zero remains in the first class. These are population statistics, not compliance grades.

## Freshness investigation

Read-only checks on October 7 found public worker reports and source checks still dated October 6, despite a current public publication. The local daily task completed successfully at 5:00 AM CDT and stored 26 OK results locally. Its launcher runs a local check, without an execution-profile publication step. This shows that a successful local run does not establish that its results reached the unified aggregate read by the public publisher. The public aggregate contains a different, 35-entry cloud/local inventory.

No provider check, production aggregate write, or scheduling change was performed for this UI task. The separately approved preview deployment is described below. Connecting the authoritative local daily results to the public reporting pipeline requires separate operational work and scoped approval for any production changes; simply copying the 26-entry local state over the hybrid aggregate would discard inventory and provenance.

## Hosted preview release

### Visible application version follow-up

With explicit user design and preview-publication approval, product commit `cf06a07cc60265bea402aaf5a8fbf42c0009614c` adds a shared public footer label: **v0.1.0.dev0 · build cf06a07 · Preview**. The full source commit appears in its tooltip. Container builds bake commit and environment into packaged JSON; package metadata supplies the canonical version. Source runs without build metadata show an unknown development build. See [versioning and build arguments](release-policy.md).

Cloud Build `7f2e3819-1fce-4a4c-9590-e86fa1de8ba7` passed, including a packaged identity and rendered-footer assertion. Preview `00011-hkl` is Ready at 100% traffic, pinned to `sha256:a21cc05d8acca181d8d0991506b5d254dcb672f72ade289e404993ee8acd7729`. Prior `00010-tmt` remains available for rollback. All four public page types displayed the correct short and full identity; browser verification confirmed the visible footer and no horizontal overflow. All 254 strict tests, compilation, whitespace checks and six CI jobs passed.

Preview pod settings, IAM, ingress, sanitized state and object generation `1791311397132173` are unchanged. Production public and private service specifications, revisions, traffic and IAM are unchanged. No provider polling, scheduling, merge or production deployment occurred.

### Initial browser feedback publication

Source `feb285bb825d86c08774f434ebc0972442648b86` from PR #47 was built by Cloud Build `21a72f31-ef41-46c4-a209-8eb713a0c5cb` (SUCCESS). The existing preview revision `gis-data-watchtower-public-v2-preview-00010-tmt` is Ready at 100% traffic, pinned to `sha256:06ea68e9d80c69fcbccab33720b9c63ff894d7ca1dc9f36bfe3c58a3759d38f5`. The prior revision `00009-nws` is retained for rollback.

[Open the hosted preview](https://gis-data-watchtower-public-v2-preview-237020802969.us-central1.run.app/).

The runtime pod specification is unchanged except image; entrypoint, identity, environment, ingress and IAM are preserved. The dedicated sanitized object generation `1791311397132173` and public source state are unchanged: 35 stored OK observations with cloud=31/local=4 provenance, publication dated October 6. This is a code-only release, not fresh provider validation. Production public `00008-lzd` and private `00013-fnn` specifications, revisions and traffic were verified unchanged.

Validation: 252 ResourceWarning-strict local tests, compilation and whitespace checks passed. Overview, county index, Aitkin and MN GAC pages returned 200 with the revised UI. Browser checks confirmed the four classes, Aitkin mandatory-field population of 57.14%, loaded embedded logo, 87/87 researched count and no document overflow. Stored-state equality and forbidden-field validation passed. No merge, production write, provider job execution or scheduling change occurred.

The task-owned Cloud Build source upload was removed with an exact generation-match condition after release verification. Automatic approval review rejected scoped recursive deletion of the task-owned `.cce-agent/publish-preview` folder with "blocked by policy". Its untracked local build context and service/configuration snapshots remain pending manual cleanup. No alternative deletion path was attempted. The deployed image and rollback revision are retained.
