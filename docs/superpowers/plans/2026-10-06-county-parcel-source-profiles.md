# County Parcel-Source Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Minnesota county click expose an evidence-backed parcel-source profile, with separate source categories and current observations, then validate and deploy the v2 preview.

**Architecture:** A pure profile composer joins validated static research with one sanitized aggregate read. A shared panel renders that profile independently of map fill metrics, and the same profiles feed county pages and exports. An isolated sanitized preview snapshot supplies safe metadata absent from the production publication.

**Tech Stack:** Existing Python standard library, unittest, SVG and vanilla browser JavaScript; existing native XLSX writer; authenticated GitHub/gcloud CLI on GERTKEN-PC. Preserve Python 3.12–3.14 compatibility; no new runtime dependencies planned.

**Spec:** [Approved design](../specs/2026-10-06-county-parcel-source-profiles-design.md), approved by the user on 2026-10-06.

Status: **User approved on 2026-10-06; Subagent-driven execution selected. Tasks 1–7 implemented and reviewed. Task 8 isolated preview deployed and live validation passed; private cleanup, task review and independent final review pending.**

## Global Constraints

- "Support desktop and 390px mobile."
- "Current observed membership/counts take precedence over historical research."
- "Discovery never activates monitoring."
- "Never convert a missing count into zero. A real count of zero remains zero."
- "Free statewide access does not override a county-direct fee."
- "Blue Earth, Faribault, Kandiyohi and Lincoln retain their holds until official evidence changes."
- "Keep the generic operational `url`, raw `tracked_values`, provenance, changes, fingerprints and worker telemetry forbidden."
- "No network access occurs during composition or rendering."
- "Build only from committed Git content."
- "Deploy only `gis-data-watchtower-public-v2-preview`."
- "PRs #39/#42 remain unmerged, `main` untouched, production UI/service/data/configuration unchanged, and authoritative provider scheduling disabled."
- "Existing St. Louis optional QA fail-soft behavior remains."
- Continue on `feat/parcel-access-audit` in the authoritative checkout; preserve dirty work. Do not use DESKTOP-FVRB1SB.
- Private registry copies, credentials, raw aggregate exports and temporary build/evidence files stay outside committed content and are deleted after use.
- After each meaningful change refresh CCE context; tests/builds use normal terminal execution. No Astra escalation without separate explicit user approval.

## Review Focus

- Provider errors or stale observations must leave a county's reporting and source health independently visible; retained counts must retain their observation date (Task 3).
- Alias/case differences in county names and a nonparcel source with a county slug must not silently duplicate or create parcel monitoring coverage (Tasks 1 and 3).
- Hostile provider metadata, credential-bearing URLs and spreadsheet formula strings must not cross any public export boundary (Tasks 2 and 6).
- Dialog focus and scroll position must survive metric changes and a publication refresh; Escape returns focus to the selected county (Tasks 5 and 7).
- A preview snapshot becoming overdue must remain visibly overdue and fail publication health; verification must never refresh its timestamp without rereading the aggregate (Tasks 7 and 8).

## File and interface map

| File | Responsibility |
| --- | --- |
| `clearparcel/datawatch/parcel_access.py` | v2 compatibility, strict v3 inventory validation and public access labels |
| `clearparcel/datawatch/minnesota_county_parcel_access.json` | 87-county static evidence, source inventory, terms and comments |
| `clearparcel/datawatch/public_values.py` (new) | Public evidence-link and spreadsheet-cell validation shared by consumers |
| `clearparcel/datawatch/county_profiles.py` (new) | Pure live/research profile composition and de-duplicated coverage |
| `clearparcel/datawatch/county_profile_panel.py` (new) | Shared panel HTML/CSS/JavaScript; no provider or storage access |
| `clearparcel/datawatch/county_profile_exports.py` (new) | County-summary CSV, category/source CSV and additional XLSX sheet rows |
| `clearparcel/datawatch/public_dashboard.py` | Explicit safe metadata allowlist, overview map, profile API/export routes |
| `clearparcel/datawatch/public_publish.py` | Preserve forbidden-key guard; reuse sanitizer for preview publication |
| `clearparcel/datawatch/dashboard.py` | Compose once, reuse profile in county index/detail/MN GAC/export flows |
| `tests/test_county_profiles.py` (new) | Composition/coverage fixtures and regression contracts |
| `tests/test_county_profile_exports.py` (new) | Profile export coverage, semantics and formula safety |
| Existing public/research/watchtower/hybrid tests | Compatibility, policy, metadata and rendered map/panel regressions |
| `docs/county-parcel-data-access-audit.md` and deployment/status docs | Actual evidence coverage, preview operation and validation |

Do not add a dependency from the composer to `dashboard.py`. Read canonical
identities from `minnesota_counties.json` in the composer; the file contains a
`counties` array. Keep boundaries unchanged: 87 MnGeo EPSG:26915 polygons.

### Task 1: Define v3 inventory and migrate existing evidence

**Files:** Modify `parcel_access.py`, the research JSON, `tests/test_parcel_access.py`; create `public_values.py`; update `docs/configuration.md`.

**Interfaces:** Retain `validate_parcel_access(data: dict) -> None` and `load_parcel_access(path: Path | None = None) -> dict[str, dict]`. Add `migrate_parcel_access(data: dict, county_index: list[dict], official_urls: dict[str, str]) -> dict`, `public_access_classification(record: dict | None) -> str`, and `safe_public_url(value: object) -> str | None` in `public_values.py`.

- [x] Write `test_v3_requires_exactly_87_canonical_counties`: deleting a county, duplicating a canonical name or adding an unknown name raises `ValueError`; valid v3 has exactly 87 entries. Keep sparse v2 test fixtures accepted for compatibility.
- [x] Write `test_inventory_categories_are_independent`: one REST entry leaves download/repository availability unknown; a reviewed absence requires review date, finding and official evidence references. Reject volatile count/health/check fields in static inventory.
- [x] Write `test_migration_preserves_evidence_without_inventing_reviews`: retain the original 35 counties' fee/terms/evidence and detailed conclusions; add 52 explicitly incomplete records. Preserve legacy `research_complete` as county-direct access review; composed overall completion additionally requires all four inventory reviews.
- [x] Write classification/link tests: supported free access becomes `OPEN`, dataset fee becomes `FEE BASED`, viewer-only and incomplete review become `AMBIGUOUS`; username/password, local/private IP hosts, localhost/internal names and credential/token query parameters return no public link.
- [x] Run `python -m unittest discover -s tests -p test_parcel_access.py -q`; verify new v3 assertions fail before changing implementation.
- [x] Implement `source_inventory` with the four approved keys, each containing `review_status`, `availability`, `review_date`, `evidence` references and `sources`; add `comments`. A source stores inventory ID, name, authority, type, layer ID, approved links, evidence references, monitoring decision and optional existing aggregate source ID. Preserve existing fields; only supported evidence determines migrated category findings.
- [x] Run the targeted suite, validate the migrated repository file with `load_parcel_access()`, and commit `Define evidence-backed 87-county parcel inventory schema` after staged privacy/diff inspection.

### Task 2: Preserve only safe source metadata through both sanitization passes

**Files:** Modify `public_dashboard.py`, `public_publish.py`, `watch.py`, `tests/test_public_dashboard.py`, `tests/test_public_publish.py`, `tests/test_watchtower.py`; extend `public_values.py`.

**Interfaces:** Preserve `sanitize_public_render_state(state: dict) -> dict` and `validate_public_state(state: dict) -> None`. Add `sanitize_source_metadata(source: dict) -> dict` in `public_dashboard.py`, producing an explicitly typed `public_metadata` structure with scalar leaves: `adapter`, `geometry_type`, `provider_updated_at` and `file` containing `type`, `size_bytes`, `etag`, `last_modified`. Add `spreadsheet_cell(value: object) -> str` to `public_values.py` for Task 6.

- [x] Write `test_safe_metadata_is_typed_and_idempotent`: a HEAD file retains valid Content-Length/ETag/Last-Modified in `public_metadata`, ArcGIS retains a validated `editing_info.lastEditDate`, and `sanitize(sanitize(state)) == sanitize(state)`.
- [x] Write `test_arcgis_provider_date_uses_existing_metadata_response`: provider `editingInfo.lastEditDate` is retained as typed `editing_info.lastEditDate` from the already fetched layer response; no new request is issued. Missing/invalid edit dates stay unavailable. Preserve the existing unsupported null-geometry QA regression.
- [x] Write `test_nested_private_values_never_reach_public_metadata`: arbitrary nested dictionaries, credential-like keys, oversized/control-character headers and invalid timestamps/sizes are omitted. Generic `url`, full provenance and raw tracked values remain forbidden. Existing private-value sentinel tests still pass.
- [x] Write `test_unsafe_evidence_links_and_formula_cells`: sanitize catalog links using Task 1's helper; spreadsheet strings beginning with `=`, `+`, `-`, `@`, or control/whitespace-prefixed formulas are emitted as literal text, not formulas.
- [x] Run the existing public dashboard/publisher suites and observe the new tests fail.
- [x] Retain validated ArcGIS edit timestamps in `_arcgis_layer` and propagate them through `_arcgis_service`'s discovered parcel-layer summary using existing metadata responses. Implement narrow extraction from raw observations and validation of already-normalized metadata; do not allowlist entire `tracked_values` or `editing_info` dictionaries. Keep `change_count` idempotent when a previously sanitized record has no raw `changes`. Existing aggregate observations may lack edit dates until an authorized future check; do not poll to manufacture them.
- [x] Run the two targeted suites, prove the forbidden-key guard still rejects operational fields, and commit `Allow safe parcel metadata without exposing operational state`.

### Task 3: Compose all county profiles from one observation snapshot

**Files:** Create `county_profiles.py`, `tests/test_county_profiles.py`; modify `_county_monitoring_counts`/county page integration in `dashboard.py` and public KPI usage; extend hybrid/public tests.

**Interfaces:** Define `FreshnessPolicy(source_stale_minutes: int = 1560, worker_stale_minutes: int = 1560)` as a frozen dataclass. Define `compose_county_profiles(state: dict, research: dict[str, dict], *, now: datetime, freshness_policy: FreshnessPolicy) -> dict[str, dict]` and `county_profile_counts(profiles: dict[str, dict]) -> dict[str, int]`, returning `total`, `active`, `county_direct`, `mngeo_open`, `both`.

Test fixture `coverage_state() -> dict` lives in `tests/test_county_profiles.py`:
use canonical counties `[0:59]` as statewide members and `[46:70]` as 24 direct
parcel observations, yielding 13 overlaps and 70 covered counties. Each source
has an ID, county slug, category `Parcels`, current checked/success time and
distinct count. The statewide source carries a nonempty fields map and county
records so it is recognized by the existing MN GAC contract. Reuse this fixture
in public integration tests rather than storing deployment observations.

- [x] Write `test_composes_all_87_profiles_from_empty_state`: canonical slugs/FIPS, four categories present, no invented counts/dates and explicitly incomplete research.
- [x] Write `test_current_coverage_overrides_static_membership` and `test_no_observation_means_unknown`: current county membership/counts win; absent statewide observation does not become a historical yes or zero.
- [x] Write `test_70_county_union_and_source_identity`: a synthetic 59 statewide + 24 direct fixture with 13 overlapping counties returns active 70; one source listed as REST and download counts once. Use realistic distinct per-source counts; never copy the statewide total into a county record.
- [x] Write `test_nonparcel_slug_alias_and_failed_observation`: imagery cannot activate parcel coverage; canonical county joins do not use substring matching; unhealthy/stale source reporting remains separate and retained counts preserve successful-observation time. No-date records have unknown health/freshness rather than assumed healthy.
- [x] Write `test_repository_requires_distinct_parcel_evidence`, `test_research_change_propagates_without_observation_change`, and fixed examples for Winona/held/viewer-only counties.
- [x] Run `python -m unittest discover -s tests -p test_county_profiles.py -q` and verify failure before implementation.
- [x] Implement the approved profile fields. Use category `Parcels` and vetted inventory joins to identify parcel observations. Never join health by county name alone when multiple products exist. Statewide per-county counts join their statewide source's check/health with catalog acquisition dates kept separate. Repository/catalog observation does not imply the parcel dataset itself was checked.
- [x] Integrate coverage counts with existing `_county_status` compatibility; retain runtime/research separation. Run composer, public and hybrid suites; commit `Compose current parcel source profiles for all Minnesota counties`.

### Task 4: Complete the systematic official-source inventory

**Files:** Update the research JSON, `docs/county-parcel-data-access-audit.md`, `tests/test_parcel_access.py` and `tests/test_county_profiles.py`.

**Interfaces:** Consume Task 1's schema and Task 3's composer. Produce category-specific official findings for all 87 canonical county records. Use the existing contact catalog only for discovery; no new provider activation or registry writes.

- [x] Add `test_inventory_completion_requires_all_four_evidence_reviews`: incomplete/blocked categories cannot yield composed `research.complete=True`. Add representative fee/viewer/held source assertions before editing records.
- [x] Review existing 35 records alphabetically: statewide membership, distinct MnGeo repository, authorized county REST, official download, then access and comments. Reuse valid evidence, recheck missing categories, and retain the four policy holds.
- [x] Review the remaining 52 alphabetically in these work batches: Aitkin–Clay; Clearwater–Houston; Isanti–Mower; Olmsted–Scott; Sherburne–Stevens; Swift–Yellow Medicine. Batch names are iteration boundaries, not assertions that all intermediate county names are missing. Derive each batch's actual names from the canonical index minus the original 35.
- [x] For each county store final official pages, parcel-specific finding, source authority, checked date, category review status, public link and monitoring decision. A county REST-backed Hub download may populate both categories but retain one observation identity. A county catalog's generic GIS resources or statewide parcel link cannot establish the distinct repository category.
- [x] Check provider policy and fee-product scope for each conclusion; do not treat custom GIS labor, deeds/maps/subscriptions as parcel dataset fees. Use bounded metadata/HEAD queries only where authorized; stop/back off on 429 and record blocked reviews honestly.
- [x] After each batch run the research/profile suites and validate all 87 identities; inspect evidence and stage only public research/doc changes, then commit that batch with its actual coverage. Do not mark completion merely because every category key exists.
- [x] Generate a category completion tally from stored records and update the audit. If external evidence is blocked, retain an explicit unknown and report it; do not manufacture a negative or complete review.
- [x] Recheck Winona, one viewer-only county, one held county, Brown and Dodge; verify policy/count/date joins and all completed findings are backed by official evidence.

### Task 5: Build one complete panel and connect both map views

**Files:** Create `county_profile_panel.py`; modify public overview and `render_mngac`/county index/detail in `dashboard.py`; extend `tests/test_public_dashboard.py`, `tests/test_watchtower.py`.

**Interfaces:** Define `render_county_profile_panel(profiles: dict[str, dict]) -> str` and `render_county_profile_body(profile: dict) -> str` in the new module. Return safely escaped markup and shared scoped CSS/JS; the panel payload uses Task 3's exact profile fields. Dialog ID is `county-profile-dialog`; county buttons retain `.mngac-county` and `data-slug`.

Store the safely serialized 87-profile payload in a non-executable JSON script
with ID `county-profile-data`; rendering tests parse that script independently
of the selected metric. Labels for the four groups are exactly `MN GAC Public
Parcels`, `MnGeo Public County Repository`, `County ArcGIS REST`, and `County
Website Download`.

- [x] Write `test_both_maps_embed_all_87_complete_profiles` and `test_county_panel_sections_are_metric_independent`: four source sections, summary cards, access/evidence and conditional comments are present even without a statewide count. Preserve all MN GAC metric options and county detail links.
- [x] Write `test_labels_keep_dates_and_counts_source_specific` and `test_panel_escapes_payload_and_links`: provider/acquisition/check/success/review/publication dates remain separately labeled; missing values say Not available; valid links have `_blank`/`noopener`; script terminators and hostile names do not inject markup.
- [x] Run public and Watchtower suites and confirm new assertions fail.
- [x] Implement the shared dialog/body: dark surface, visible close control at upper edge, responsive grids, wrapped long values and vertical scrolling. Use native dialog semantics with focus return and Escape; update content using text or pre-escaped markup, never untrusted HTML.
- [x] Integrate canonical-slug click/Enter/Space events on overview and MN GAC maps; color updates do not close or replace the full panel. Add overview monitoring-path/completeness selector, retain MN GAC field selectors, and generate legends from the same fixed breaks/colors used for fills. Keep no-data distinct from zero.
- [x] Load research/state once per page composition and reuse profiles for panel and KPI/index/detail views. Suspend any full-page refresh while the dialog is open; Task 7 verifies behavior. Do not refactor unrelated private dashboard layout.
- [x] Run targeted suites; commit `Show complete parcel source profiles from every county map click`.

### Task 6: Export the same county and source profiles safely

**Files:** Create `county_profile_exports.py`, `tests/test_county_profile_exports.py`; modify snapshot helpers and HTTP routes in `dashboard.py`/`public_dashboard.py`; extend hybrid export tests and relevant docs.

**Interfaces:** Define `county_profiles_csv(profiles: dict[str, dict]) -> str`, `parcel_sources_csv(profiles: dict[str, dict]) -> str`, and `county_profile_xlsx_sheets(profiles: dict[str, dict]) -> list[tuple[str, list[list]]]`. Consume Task 2's `spreadsheet_cell`. Existing JSON snapshots append `parcel_source_profile` per county.

- [x] Write `test_all_87_counties_in_json_csv_and_xlsx`: profile-summary CSV has 87 unique counties; source CSV has at least one placeholder per county/category (348 category rows minimum) and additional rows for multiple sources; XLSX has existing sheets plus `County Access` and `Parcel Sources`.
- [x] Write `test_export_counts_dates_and_nulls_agree`: source counts and dates match profile JSON; no manufactured zero; approved evidence links only; all timestamps retain machine-readable semantics. Test formula/control-character payloads as literal cells in both CSV and XLSX.
- [x] Write `test_legacy_aggregate_source_csv_still_contains_every_source`: preserve existing `/snapshot.csv` source-row contract and current aggregate source coverage tests.
- [x] Run the export/hybrid tests and observe new cases fail.
- [x] Implement `/county-profiles.csv` (87-county summary) and `/parcel-sources.csv` (category/source rows), expose them in the existing export menu, and retain legacy `/snapshot.csv`. This explicit compatibility choice supplies the requested statewide county CSV without changing the existing monitored-source CSV contract. Append county detail CSV summary columns; preserve existing JSON/XLSX fields/sheets.
- [x] Refactor only snapshot composition so statewide export reads one state/research generation for all 87 county rows; avoid `_county_snapshot` reloading the aggregate on each loop. Add a regression where a changing mocked state loader is called once.
- [x] Run export/public/hybrid suites, decode the native XLSX ZIP/XML and verify actual county/source rows; commit `Export county parcel profiles without losing aggregate source exports`.

### Task 7: Validate browser behavior and publish local evidence

**Files:** Update `README.md`, `STATUS.md`, `docs/current-status.md`, audit/configuration/hybrid docs as applicable; fix only issues identified by validation in Tasks 1–6.

**Interfaces:** Consume shared panel, canonical profiles and export routes. Use the Browser plugin/CUA for actual UI interactions and viewport checks; no new browser automation runtime dependency.

- [x] Run the required suite: `python -W error::ResourceWarning -m unittest discover -s tests -q`, `python -m compileall -q clearparcel tests`, `git diff --check`. Require zero failures and no ResourceWarning.
- [x] Serve a local public-mode sanitized fixture with the new renderer. Check all 87 targets and activate each through canonical slug with keyboard input; verify representative pointer clicks; verify full source groups appear for all map summary modes and representative individual MN GAC fields.
- [x] At desktop and 390px widths verify Brown, Winona, viewer-only and held counties; cross-check rendered counts/dates/access and links against the composed JSON. Capture one useful desktop screenshot and one mobile screenshot.
- [x] Verify `document.documentElement.scrollWidth <= innerWidth` and dialog content width is bounded at 390px with long URLs, many sources and expanded evidence. Check keyboard open/close, focus containment/return, metric switching, scrolling and refresh while a panel is open.
- [x] Reproduce stale source and stale publication fixtures: separate health/reporting labels; overdue publication fails health without hiding the profile or pretending a new provider check occurred. Compare legend swatches to actual fills and confirm zero and no-data classes.
- [x] Fetch JSON/CSV/XLSX and county detail JSON via local routes; verify 87 profiles, source identities and safe values across formats. Record actual research completion separately from profile coverage.
- [x] Run focused regression tests for any fixes, then the full required suite if code changed. Inspect status/diffs for private material; commit docs and verified fixes with branch push handled by the controller after task review.

### Task 8: Prepare isolated preview data, deploy committed content and verify live

**Files:** Update deployment/status/audit docs and draft PR #42; no production resource/configuration changes.

**Interfaces:** Reuse `publish_public_snapshot(source, destination, *, source_object, destination_object, workdir) -> dict` with explicit preview destination and Task 2's sanitizer. Build the existing Docker image from the final committed tree. The target service is exactly `gis-data-watchtower-public-v2-preview`.

- [x] Inspect current preview service identity, storage bindings, snapshot source and scheduler state read-only. Preserve the existing production service revision/object generation and scheduler configuration as comparison evidence; do not copy secret values into logs.
- [x] Read the current unified aggregate once into a private temporary directory and sanitize it locally with committed code. Validate the public state, 87 profiles and de-duplicated current coverage, plus source/worker provenance internally. Use available safe metadata; never run provider checks just to fill UI fields.
- [x] Upload the validated sanitized snapshot only under an isolated preview namespace. Prefer existing preview-scoped read permissions. If a broader/security-sensitive grant would be necessary, prepare the exact object-scoped change and seek explicit approval; never grant the anonymous preview service raw aggregate/registry access.
- [x] Keep the preview snapshot current by manually republishing from a fresh aggregate read when needed during QA, not by editing timestamps or introducing a scheduler. If a refresh is not possible, show the real overdue state and document the preview limitation.
- [x] Before build, inspect `git status`, `git diff` and staged diff; require all intended product changes committed. Export `git archive HEAD` to a fresh temporary build directory and run Cloud Build from that directory only. Never submit the working directory containing private/untracked files.
- [ ] Delete the temporary archive/build context after the release; scoped cleanup remains pending.
- [x] Deploy the built immutable image digest to the named preview service with the isolated sanitized object and required preview-only identity settings. Preserve production UI/service/publisher/data/configuration and all provider schedules.
- [x] Query the deployed service/revision and live profile/export data; recompute coverage from its current aggregate rather than hard-coding 70. If still the validated baseline, require 70/87 = 59 + 24 - 13. Verify all panel groups, source-specific counts/dates, links, metric switching, keyboard behavior and 390px overflow on the actual preview.
- [ ] Verify Cloud Run source-level results and aggregate provenance used in the snapshot; a successful container exit alone is insufficient. Confirm no source activation, production write, merge or scheduler change occurred. Delete all temporary raw/config/evidence artifacts.
- [ ] Update docs and PR #42 with architecture, actual 87-county/category review status, tests, deployed revision and visual evidence. Keep both PRs draft/unmerged. Push final documentation and inspect CI for the actual branch head; report unresolved checks accurately.


## Concrete regression assertions

These assertions anchor the test steps above; fixture setup stays in each named
test module. They are test contracts, not product implementation.

```python
# Task 1: bad_v3 is a copied valid v3 with one canonical county removed.
with self.assertRaises(ValueError):
    validate_parcel_access(bad_v3)
self.assertEqual(public_access_classification(winona_record), "FEE BASED")
self.assertIsNone(safe_public_url("https://user:secret@example.org/parcels"))

# Task 2: state adds typed HEAD headers to the existing public-state fixture.
public = sanitize_public_render_state(state)
self.assertEqual(sanitize_public_render_state(public), public)
self.assertNotIn("tracked_values", public["sources"]["download"])
self.assertEqual(public["sources"]["download"]["public_metadata"]["file"]["size_bytes"], 1024)

# Task 3: compose coverage_state() using a fixed aware now and FreshnessPolicy().
self.assertEqual(len(profiles), 87)
self.assertEqual(county_profile_counts(profiles),
                 {"total": 87, "active": 70, "county_direct": 24, "mngeo_open": 59, "both": 13})
self.assertIsNone(empty_profiles["brown"]["monitoring"]["last_checked_at"])

# Task 4: a held county can have a discovered REST source without monitoring it.
self.assertEqual(research["Blue Earth"]["monitoring"]["decision"], "hold-for-terms")
self.assertFalse(incomplete_profile["research"]["complete"])

# Task 5: payload is parsed from #county-profile-data in both rendered map pages.
self.assertEqual(len(payload), 87)
self.assertIn("County Website Download", render_county_profile_body(profiles["brown"]))
self.assertIn('rel="noopener"', body_with_approved_link)

# Task 6: parse exports with csv.DictReader and existing XLSX ZIP/XML inspection.
self.assertEqual(len(list(csv.DictReader(io.StringIO(county_profiles_csv(profiles))))), 87)
self.assertGreaterEqual(len(list(csv.DictReader(io.StringIO(parcel_sources_csv(profiles))))), 348)
self.assertIn("Parcel Sources", workbook_sheet_names)
```

## Self-review and execution handoff

The eight tasks cover the approved schema, all-county evidence review, composition,
privacy, both maps/panel, exports, desktop/mobile QA and preview release. The five
Review Focus cases each have explicit owning tests/checks. Shared function names,
category keys, date fields and source identity rules match the approved design.
Existing source exports are preserved with an explicitly named new county CSV.

Selected execution: **Subagent-driven**, explicitly selected by the user on
2026-10-06. Tasks run in this chat with isolated implementers and fresh task
reviewers, preserving the approved privacy, provider and deployment constraints.
Task 8 release/live checks passed; private cleanup, final documentation push/CI and independent final review remain pending. Astra has no approval.

Task 8 actual state: revision `00003-xzg`, committed `b342b5d` immutable `f7134713…` image; dedicated preview storage and identity. Live 87-profile/400-product-row JSON/CSV/XLSX parity, 696 browser county activations, desktop/390px, actual 35/35 OK with cloud=31/local=4 and coverage 70=59+24-13 passed. External healthz is blocked by the Cloud Run frontend reserved path; no external HTTP 200 claim. Automatic approval review blocked verified raw-file cleanup; user assistance and final review are pending. See deployment/status release evidence.


## Final review product fixes (pending preview release)

Public sanitation now projects typed source, worker, count, catalog and MN GAC
leaves and completeness metrics. Raw completeness errors and unknown nested
payloads are omitted; a second sanitation pass preserves the public result.
All 59 inventories for the exact vetted MnGeo Plan Parcels Open official item
carry `mn-state-parcels` identity and a consistent product name. Fifty newly
linked inventories now retain their stable inventory IDs and approved links on
the row receiving that county's current observed count. Historical membership
cannot supply a missing observation or count; other products remain separate.

Offline composition produces 87 profiles and 348 category/product rows both
without observations and with a synthetic 59-member statewide observation.
For the unchanged aggregate used by old preview `00003-xzg`, removing its 50
duplicate rows projects 350 rows (400 minus 50). This is an offline projection,
not fresh live acceptance or a fixed row-count requirement. The deployed
`b342b5d` preview still has the previously measured 400 rows until a new committed
build, isolated redeploy and actual live validation. The product fixes pass 193
ResourceWarning-strict unittest tests, compileall and diff checks. Independent
fix review and required manual private temporary cleanup remain pending.
