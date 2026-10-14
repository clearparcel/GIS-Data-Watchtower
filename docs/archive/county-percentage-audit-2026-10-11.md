# County Percentage and Repository QA — 2026-10-11

> This is the original pre-release QA record. The changes subsequently merged as PR #67 and were [verified in production on October 11](release-county-percentage-fix-2026-10-11.md). The candidate and old deployment identities below are historical.

## Scope and authority

Repository: `clearparcel/GIS-Data-Watchtower`. Authoritative workstation: `GERTKEN-PC`. Local implementation is isolated on `fix/county-percentage-clarity-20261011`, based on main `19c075347b44ade3193125c676ed589704427dc8`. The currently documented production release is v0.2.0, build `308e3a7` (public `00014-jsr`, private `00021-hr8`); the branch does not update those deployments.

Read-only source verification: public `/healthz`, `/mngac.json?standard=parcel`, and `/county-profiles.csv` at https://gis-watchtower.clear-parcel.com on October 11. The saved parcel population observation reports `2026-10-11T10:03:06.034485+00:00`. These reads did not initiate GIS-provider polling.

## Confirmed finding: many identical mandatory percentages are mathematically valid

The official MN GAC Parcel standard in the statewide transfer dataset includes **91 total fields**, of which **7 are Mandatory**. The published October 11 observation covers **59 counties** and **2,710,201 parcel records**.

| Mandatory-field population | Represented counties |
| --- | ---: |
| 57.14% | 15 |
| 42.86% | 9 |
| 100.00% | 5 |

These are descriptive record-weighted proportions of populated cells in the seven Mandatory fields. When each of the seven fields is either completely full or empty within a county, the possible rates are discrete multiples of 100/7 (14.2857 percentage points). **A tie does not indicate duplicated data or a calculation defect.**

Independent spot check against the published `counties` and `fields` records:

| County | Parcel records | Mandatory rate | All-91-field rate |
| --- | ---: | ---: | ---: |
| Aitkin | 43,024 | 57.14% | 33.19% |
| Fillmore | 20,917 | 57.14% | 15.24% |

For both example counties, `CO_CODE`, `CO_NAME`, `STATE_CODE`, and `ACRES_POLY` are 100% populated, while `CTU_NAME`, `CTU_ID_TXT`, and `EXP_DATE` are 0% populated. The county record counts and all-field percentages differ. This resolves the screenshot's 57.14% symptom.

## User-facing correction

- The parcel overview completeness map, interactive county-results map, and statewide parcel map default to **all-91-field population**, to expose more county-level variation.
- The seven-field Mandatory rate remains clearly available and correctly calculated; it is shown in county cards and as an explicitly selectable statewide map statistic.
- The overview displays the all-field ring first and labels the Mandatory ring as seven fields.
- Address and Road maps retain their Mandatory statistic, because routine observations scan Mandatory fields and should not invent values for unscanned fields.
- A note explains why percentage ties occur and states that neither statistic grades compliance. Conditional, If Available, and Optional fields can legitimately be unpopulated.

The fix changes **presentation**, not source observations, county joins, GIS sampling, or percentage formulas. A future all-field tie is also legitimate if the stored rate is genuinely equal.

## Related code issues found and addressed in the isolated branch

1. **Legend/code drift:** current implementation had bins below 50, 50–60, 60–70, above 70, but the approved documentation had below 30, 30–50, 50–70, above 70. The patch restores `p<30`, `30<=p<50`, `50<=p<=70`, `p>70` for both server map and browser classifier, sharing one bin table. Exact 30, 50, 70, 0, and 100 are regression-tested.
2. **Out-of-range percentage acceptance:** public sanitization previously accepted positive values above 100, even though such figures cannot represent populated-record percentages. A bounded `_public_percent` validator now rejects out-of-range values and preserves valid 0 and 100, while map rendering classifies invalid, absent, or nonfinite values as unavailable.
3. **Stale current documentation:** candidate status and MN GAC methodology now distinguish current production from an unmerged candidate, and correct obsolete references to older scheduling assignments and outdated percentage breaks. Historical release evidence remains intact.
4. **Intermittent Windows atomic replacement error:** one baseline 340-test run on GERTKEN-PC reported Windows `PermissionError [WinError 5]` when replacing a temporary synthetic replay object. The same replay test passed in isolation; the first complete post-change run passed all 342 then-existing tests. No storage implementation change is justified by this one nonreproducing case; track any recurrence with file handle/antivirus evidence before attempting a fix.

## Verification and acceptance gates

- Required offline unit suite with `ResourceWarning` treated as error.
- `compileall` for `clearparcel`, `tests`, and `scripts`.
- `scripts/sync_current_status.py --check`, `git diff --check`, and review of the committed diff.
- Regression tests for tied mandatory vs distinct all-field county results, output labels, server/browser bins, out-of-range values, and address/road scan scope.
- Review the public change against saved, sanitized observations; do not poll providers or overwrite archived/operational data during validation.
- CI review on a pull request is required before any separately approved merge. Deployment, when approved, requires a fresh preview/browser check and explicit traffic promotion authority.

**Local verification (October 11):** **343/343 automated tests passed** with `ResourceWarning` treated as error; Python compilation, generated-status synchronization and staged diff whitespace checks passed. Hosted GitHub CI and browser/deployment acceptance are separate, pending gates.

## GitHub housekeeping

PR #63 is a superseded historical publication-documentation proposal: the v0.1.2 county-results record is already preserved in main as `docs/mngac-county-publication-2026-10-10.md`, and the subsequent verified v0.2.0 publication is recorded by merged PR #66. It was **closed without merge on October 11**, with a rationale comment, to avoid reverting newer release records.

Keep policy and operations issues open rather than clearing them cosmetically: provider terms (#1/#2), the multi-day cloud observation study (#20), and dedicated PostHog activation (#50). Keep the known CodeQL alert assessments available for separate security triage; do not weaken validation to silence them.

**Protected boundaries:** This branch does not touch the private source registry, production snapshots, provider schedules, secrets, Cloud Run image, IAM, IAP, or any county authoritative GIS data.
