# Browser feedback changes — October 7, 2026

These changes are prepared on a feature branch; they are not a production release.

- The overview uses the latest valid source `checked_at`, rather than aggregate generation time, for its latest provider check. It explains publication, provider checks, and provider dataset updates separately. Source overdue counts use the configured reporting window; missing check times remain unknown. Worker reports and successful checks are labeled separately, without treating a report as a success.
- Source entries and unique county coverage are explained together. One statewide source can cover multiple counties; county-direct and statewide coverage overlap. Healthy counts describe the last stored checks, rather than claiming current provider health.
- Research summaries derive dated county reviews and completed profiles separately. All 87 counties have dated research reviews; 15 composed profiles currently meet all completion conditions. Unresolved evidence and terms still prevent completion and do not authorize monitoring.
- The displayed county-direct label is **Open parcel data**. The existing `free-parcel-data` machine classification remains compatible with stored research and exports. Provider findings and policy holds are preserved.
- County record counts use thousands separators. Official evidence is presented as individual findings inside expandable details; detailed research notes use separate list items. Source metadata and evidence remain available.
- The footer links to ClearParcel and embeds the existing ClearParcel logo, obtained from the company site's public brand asset, in the generated page. No external image request is required. The logo is included in Python package data.
- The overview completeness view uses **mandatory-field population**. The MN GAC exploration page defaults to mandatory fields and retains other metric selections. Both maps share fixed percentage classes: `p < 50`, `50 <= p < 60`, `60 <= p <= 70`, and `p > 70`. Exact 60 and 70 belong to the third class. Missing statistics remain No data; observed zero remains in the first class. These are population statistics, not compliance grades.

## Freshness investigation

Read-only checks on October 7 found public worker reports and source checks still dated October 6, despite a current public publication. The local daily task completed successfully at 5:00 AM CDT and stored 26 OK results locally. Its launcher runs a local check, without an execution-profile publication step. This shows that a successful local run does not establish that its results reached the unified aggregate read by the public publisher. The public aggregate contains a different, 35-entry cloud/local inventory.

No provider check, production aggregate write, scheduling change, or deployment was performed for this UI task. Connecting the authoritative local daily results to the public reporting pipeline requires separate operational work and scoped approval for any production changes; simply copying the 26-entry local state over the hybrid aggregate would discard inventory and provenance.
