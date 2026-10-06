# Minnesota county parcel-source profiles

Date: 2026-10-06. Status: **User approved on 2026-10-06; implementation-plan review pending.**

## Intent and scope

Every Minnesota county click should answer where parcel data is available,
how Watchtower observes it, how recently each source was checked, and what
official access conditions apply. Preserve the public v2 dark visual system,
MN GAC metric switching, provider compliance, and the separation between
research conclusions and operational health. Support desktop and 390px mobile.

The user's continuation brief authorizes development and preview deployment.
This design defines the requested schema and regression contract before UI work.
The requested Superpowers architectural workflow requires review of the written
design and then the implementation plan before product implementation.

## Verified diagnosis

The authoritative GERTKEN-PC checkout is clean on `feat/parcel-access-audit`
at `5b6345112505cdd39ef739f412a6b78ec6da3448`, matching its remote-tracking branch.
PR #42 remains draft and open, stacked on `feat/public-dashboard-ui-v2`.

Read-only inspection of preview revision `00002-bn8` on 2026-10-06 found:

- The rendered headline and `/api/state` agree: 35 sources; 70/87 active
  counties; 59 statewide, 24 county-direct, 13 overlapping.
- All 87 county SVG click targets exist.
- Brown's direct source is healthy with 18,393 features, but its overview
  map click shows only MN GAC "No data" and no direct-source information.
- The overview's `map_data` in `public_dashboard.py` is built exclusively
  from `mngac_completeness.counties`. The fill and click summary cannot
  reflect county-direct sources or research changes.
- `render_mngac` in `dashboard.py` likewise renders a metric-specific
  summary. It does supply placeholder rows and county links for counties
  absent from the statewide layer; there is no reproduced missing-link bug.
- Research contains 35 complete records, leaving 52 counties without records.
  Its single `download_or_service_url` cannot represent REST and downloads
  independently. The existing catalog has 87 rows and 50 nonempty `data_url`
  values; those values alone do not prove distinct MnGeo repository membership.
- The public sanitizer preserves health, counts and check times but removes
  adapter/kind, geometry, provider update timestamps and file headers.
  Dodge's HEAD headers are stored privately inside `tracked_values`.
- Preview currently reads the production **sanitized** snapshot with a
  30-second cache. A UI deployment cannot recover omitted metadata.

These findings establish a mismatch between the map's statewide-only purpose
and the desired complete profile. They do not establish that the aggregate is
stale or that all county research is complete.

## Approaches considered

1. **Recommended: shared profile composer.** Normalize evidence in the research
   model, compose all 87 profiles from a single aggregate read, and reuse the
   result in both maps, county pages and exports. This provides one set of
   semantics and independently testable privacy and precedence rules.
2. Extend each existing map's JavaScript payload separately. Smaller initial
   changes, but duplicates joining, privacy and classification logic across
   pages and exports.
3. Materialize live county profiles into the research JSON. Simple rendering,
   but duplicates volatile counts/health and would recreate stale profiles.

## Static research schema

Extend `parcel_access.py` and migrate the research JSON to schema version 3.
Retain the existing detailed classifications, fee evidence, policy assessments,
evidence and review logs. Require exactly the canonical 87 county identities;
partial research may be stored but must remain explicitly incomplete.

Each county has four separate inventory categories in this order:

1. `mngac_public_parcels`: statewide source reference and historical membership
   evidence. Current membership is derived from the aggregate, not this field.
2. `mngeo_public_repository`: only distinct parcel-specific county catalog or
   repository resources. A statewide-layer link or unrelated GIS catalog item
   cannot satisfy this category.
3. `county_arcgis_rest`: county or county-authorized parcel layers, with service
   name, service type, layer ID, authority and approved public evidence links.
4. `county_download`: parcel download products, file type, official product
   links and authority. Preserve REST-backed downloads as a separately offered
   product, without inventing a separate monitored source.

Each category contains `review_status`, `availability` and `sources`.
`review_status` is `pending`, `reviewed`, `not-found` or `blocked`.
`availability` is `yes`, `no` or `unknown`; `no` requires a completed,
documented parcel-specific search. `sources` is an array so a county can have
multiple products in a category. Record category review dates and evidence.

Each source carries a stable inventory ID, dataset/product name, authority,
type, approved public links, review date, monitoring decision and evidence
references. An optional `monitored_source_id` joins an already monitored
aggregate source. Discovery never activates monitoring. Do not store private
registry content or copy live counts, health, file headers or check times here.

Keep concise `comments` separate from the longer evidence findings. Public
comments contain supported facts only. Do not mark a migrated category reviewed
unless its existing evidence actually establishes that category's finding.

## Composed profile contract

Add a focused `county_profiles.py` module independent of HTML rendering.
`compose_county_profiles(state, research, now, freshness_policy)` returns exactly
87 profiles keyed by canonical slug. Load the aggregate and research once per
render/export request. No network access occurs during composition or rendering.

Each profile contains:

```text
schema_version
county: name, slug, fips
monitoring: active, paths, health, reporting, active_parcel_source_count,
            last_checked_at, last_success_at, aggregate_generated_at
mngac_public_parcels: availability, review_status, sources[]
mngeo_public_repository: availability, review_status, sources[]
county_arcgis_rest: availability, review_status, sources[]
county_download: availability, review_status, sources[]
access: public_classification, detailed_classification, dataset_fee, fee_product,
        monitoring_decision, evidence_links[]
comments[]
research: complete, review_date, category_review_statuses, evidence_links[]
```

Each composed source retains its source-specific values:

```text
inventory_id, monitored_source_id, name, authority, dataset_type, layer_id
approved_public_links[], geometry_type
feature_count, feature_count_basis
provider_updated_at, county_acquired_at, catalog_refreshed_at
checked_at, last_success_at, health, reporting
execution_profile, monitoring_decision
file: type, size_bytes, etag, last_modified
```

Values unavailable in either evidence or safe live observations remain null.
Render "Not available" for unknown counts/dates and "Not included" only for
verified nonmembership. Never convert a missing count into zero. A real count
of zero remains zero. A source shared across categories retains the same
identity and counts once in the active source total.

Current observed membership/counts take precedence over historical research.
If a statewide observation is unavailable, expose uncertainty rather than
using an old research membership flag as a current fact. Preserve unhealthy
and overdue statuses separately: configured observation coverage is not a
claim of healthy or fresh reporting. Restrict parcel-source totals to parcel
sources; county imagery or other GIS sources cannot imply parcel monitoring.

Public access refers to **county-direct** availability:

- `OPEN`: verified free dataset/download or authorized machine-readable access.
- `FEE BASED`: official evidence prices the parcel dataset itself, with product
  and fee recorded. Associated service/document fees do not qualify.
- `AMBIGUOUS`: viewer-only, unclear/restricted request access, conflicting terms
  or no verified direct dataset after review. Incomplete review explicitly
  says "Research incomplete" alongside the conservative classification.

Free statewide access does not override a county-direct fee. A fee-based
county can also have a `hold-for-terms` REST endpoint. Blue Earth, Faribault,
Kandiyohi and Lincoln retain their holds until official evidence changes.

## Public boundary and preview data

Keep the generic operational `url`, raw `tracked_values`, provenance, changes,
fingerprints and worker telemetry forbidden. Public source links come only
from individually approved research/catalog evidence and pass safe-URL checks.
Reject credential-bearing links, private/internal hosts, secret-bearing query
parameters and unsafe schemes; prefer verified HTTPS. Escape all rendered text
and serialize embedded JSON safely. Links open with `_blank` and `noopener`.

Add explicit scalar allowlists for the necessary safe derived metadata. Extract
only validated file headers and provider dates into a dedicated public metadata
structure; never copy whole operational dictionaries. Test sanitization twice
to cover both publisher and service-cache passes. Public API, HTML and exports
must all use the same sanitized representation.

The existing production snapshot lacks this metadata. Prepare an isolated
sanitized preview snapshot from a bounded read of the current aggregate, under
a preview namespace, with least-privilege preview read access. Never grant the
anonymous service access to the raw registry or aggregate. Do not redeploy the
production publisher or write the production object to make preview work.
Where observations do not expose a provider date, keep it unavailable. Identify
any missing safe metadata before claiming complete live fields.

## Map and panel behavior

Use one complete county panel component in overview and MN GAC maps. The
selected metric controls fill only. A click, Enter or Space always opens the
same complete profile for that slug. Add overview monitoring-path coloring
with an explicit legend; retain statewide completeness as a selectable view.
Keep MN GAC summary and field selectors and their descriptive semantics.

The panel uses a dark bordered surface, county heading and monitoring summary,
then four compact cards: active monitoring, county-direct access, active parcel
sources and latest county Watchtower check. Follow with the four source groups,
access/research evidence and conditional comments, in the requested order.
The selected metric may be shown as secondary context without hiding groups.

Desktop uses a scrollable dialog with compact grids; mobile uses the viewport
width with stacked cards. Use a visible close button near the upper edge,
dialog labeling, Escape close, focus containment and return focus to the county
target. Keep headings/status in text as well as color. Wrap long names/URLs,
set grid children to `min-width: 0`, and bound height with internal scrolling.
Do not rely on page refreshes that close a panel while it is being read.

Keep "No data" visually distinct from zero. Use fixed, nonoverlapping percentage
classes and a legend matching actual dark fills. The existing MN GAC markup
uses light legend swatches even in public mode; reconcile swatches with the
renderer. Boundary input is MnGeo EPSG:26915, simplified at 500m, rendered as
SVG. No geometry, projection or area analysis changes are required.

Display provider update, county acquisition, catalog refresh, Watchtower check,
successful observation, research review and public publication separately.
Use Central Time for instants, preserve date-only values without timezone shifts,
and keep machine-readable ISO times in exports. Do not borrow one date to fill
another label. Freshness describes Watchtower reporting, not an inferred provider
update cadence.

## Research procedure

For each county, review the four categories in the requested order, then
classify county-direct access and write concise comments. Start with existing
official evidence, contacts and catalog rows. Recheck gaps in the existing 35
records and research the remaining 52; do not assume the old audit reviewed a
distinct MnGeo repository. Treat search snippets as discovery only.

Store official evidence, its supported finding, category and review date.
Differentiate a confirmed absence from blocked access or an unfinished search.
Do not scrape Beacon/QPublic/property-search pages, bypass provider controls,
repeat bulk downloads or activate newly discovered sources. Prefer metadata,
small bounded samples and HEAD for archives; stop/back off on 429.

Final reporting must state category-level completion and unresolved provider
evidence honestly; 87 profile objects alone do not prove 87 completed reviews.

## Exports and validation contract

Keep existing JSON fields and append `parcel_source_profile` to county and
statewide snapshots. Extend existing CSV summary columns compatibly and provide
source rows keyed by county, category and source identity so counts/dates stay
separate. Excel retains existing sheets and adds county access and parcel-source
inventory sheets. Every statewide format represents all 87 counties, including
verified absent and unknown category states.

Write failing regression cases before product changes for:

1. Exactly 87 canonical profiles and map targets; reject duplicates/unknown names.
2. Four independent categories; unrelated catalog items do not imply parcels.
3. Statewide membership follows current aggregate rather than static research.
4. Distinct MnGeo repository membership requires parcel-specific evidence.
5. REST and download entries join their correct observations and source counts.
6. Dataset fees, viewer-only access, OPEN/FEE BASED/AMBIGUOUS and policy holds.
7. Winona's county-direct fee with independent free statewide coverage.
8. Conditional comments and safe evidence/source links.
9. Multiple dataset counts, unknown versus zero, and separately labeled dates.
10. Source health versus reporting freshness; stale and failed observation cases.
11. De-duplicated 70/87 fixture: 59 statewide, 24 direct, 13 overlapping.
12. Nonparcel county sources do not create parcel monitoring coverage.
13. Research-only edits propagate without changing the aggregate.
14. Sanitizer idempotence; forbidden fields and hostile nested values/links cannot
    reach API, HTML, JSON, CSV or Excel.
15. All county clicks open the full panel across summary and field metrics.
16. Keyboard open/close and focus return; desktop and 390px panel screenshots.
17. No horizontal overflow at 390px, including long URLs and multiple sources.
18. JSON/CSV/Excel and county-detail data agree on categories, counts and dates.

Run the required full unittest suite, compileall and `git diff --check`, then
browser checks. Cross-check Brown, Winona and a held county against composed
data. Check the legend and zero/no-data distinction and verify desktop/mobile.

## Release boundary and acceptance

Continue on the existing feature branch and preserve unrelated work. Inspect
unstaged/staged diffs for private material before commits. Build only from
committed Git content. Deploy only `gis-data-watchtower-public-v2-preview`.
Verify the actual revision, all panel groups, correct source counts/date labels,
safe links, map selectors and 390px layout against the current aggregate.

Update relevant documentation and draft PR #42 with actual research completion,
validation and preview evidence. PRs #39/#42 remain unmerged, `main` untouched,
production UI/service/data/configuration unchanged, and authoritative provider
scheduling disabled. Existing St. Louis optional QA fail-soft behavior remains.

Implementation, expanded research, tests and preview deployment remain pending
implementation-plan review; this document records no completed
implementation or new provider authorization.
