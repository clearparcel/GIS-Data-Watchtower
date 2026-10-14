# GIS Data Watchtower repository review — 2026-10-11

## Disposition and scope

**Current disposition (October 12):** the candidate fixes below were merged in
PR #69 and are included in the verified v0.2.1 production release. The following
review text records the original candidate state, not the current deployment.

The review found two functional defects, a small-control UI issue, and stale or
overstated documentation. Narrow fixes are prepared on
`fix/repository-review-20261011`. Repository cleanup is complete for the
confirmed stale branches and scanner findings described below. These candidate
code changes are not a production release.

No high- or critical-severity exploitable vulnerability was reproduced in the
reviewed paths. This was a manual source, configuration-metadata, synthetic-test,
and public-UI review, not an exhaustive penetration test or a hosted Codex
Security scan. Deployment-permission details are retained in the owner-facing
report rather than copied into this public repository.

The review covered provider transport and retry behavior, private/public HTTP
handlers, public-data projection, exports, storage concurrency protections,
dashboard interactions, build/dependency controls, GitHub issues/branches/alerts,
and reconciliation of the authoritative workstation with the deployed service.
Provider checks were not triggered to conduct this review.

## Baseline and current operation

| Area | Verified state |
| --- | --- |
| Repository and authoritative main | `e14dddbbb5751466e9d7d45ffd81be36e49a923f`, initially clean |
| Production application identity | v0.2.0, build `bbc364d29398a7bc19dfb235c23cbb24d3f08712` |
| Production and preview revisions | Public `00015-cjp`, private `00022-pts`, isolated preview `00020-qds`; all Ready with 100% traffic |
| Provider schedule | Daily 05:00 America/Chicago, enabled |
| Sanitized publication schedule | Every ten minutes, enabled; independent of provider polling |
| Latest saved source inventory | 35 observations: 34 OK, one warning, zero errors |
| Warning | Hennepin 2026 imagery |
| Parcel monitoring coverage | 70/87 counties: 59 statewide + 24 direct − 13 overlaps |
| Historical local worker | Retained October 7 record; local poller removed, aggregate worker retirement not completed |
| Five-day observation study | Incomplete; issue #20 remains open |

The October 11 scheduled execution returned exit 1. That is consistent with the
CLI's documented warning exit contract and the saved one-warning aggregate;
the exit code alone does not establish an application crash. The last saved
cloud report is dated 10:02:35 UTC, while later public-publication timestamps
only show that the publisher is fresh.

The main commit after `bbc364d` records the release. It does not imply that a
different runtime was deployed. The v0.2.0 tag remains the original
`308e3a7` release baseline; the later county-percentage correction is identified
by its baked source revision.

Evidence: [deployed release record](release-county-percentage-fix-2026-10-11.md),
[daily activation record](daily-cloud-provider-polling-2026-10-10.md),
[baseline main CI](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/38176075580),
and read-only runtime metadata/public endpoint checks performed during this review.

## Findings and candidate fixes

Severity reflects observed impact and exposure, not a formal risk score.

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| R1 | Medium | Generated static bundles contained navigation/export links to routes they do not generate | Fixed in candidate |
| R2 | Medium | Permanent provider HTTP refusals could be repeated by whole-source retries or swallowed by optional probes | Fixed in candidate |
| R3 | Low | Overview selectors and refresh button rendered as small native controls | Improved in candidate; fresh mobile rendering still outstanding |
| R4 | Low | README/status/security prose mixed historical state with current operation and overstated private UI acceptance | Reconciled in candidate |
| R5 | Medium | Main protection requires six test jobs but does not require the separate security job | Recommended account-setting change; approval required |
| R6 | Operational | Five-day observation evidence is incomplete; Hennepin imagery is warning | Issue #20 retained and updated |
| R7 | Low / operational | Retained local-worker history appears overdue after the local poller was removed | Explicit worker-retirement decision remains open |

### R1 — Static output links

`build_static_site` writes `index.html`, `state.json`, and one source HTML
file per source. Its shared hosted shell also offered `/counties`,
`/mngac`, and snapshot export routes that are absent from a static bundle.
On subdirectory hosting, root-relative links also escaped the bundle.

A dedicated static-bundle mode now keeps the existing public theme while
offering only generated relative Overview and sanitized-state links. The
hosted dashboard's routes and export menu retain their existing behavior.

Source IDs containing reserved or non-ASCII characters exposed a related
filename problem. Disk filenames deliberately contain an encoded source ID;
the href must then encode that filename's literal percent characters so a
static server's normal URL decode resolves the intended file. The new
regression uses `county/space ü?#` and checks every generated internal link
and fragment under a subdirectory.

Relevant files:
[`dashboard.py`](../../clearparcel/datawatch/dashboard.py),
[`dashboard_templates.py`](../../clearparcel/datawatch/dashboard_templates.py),
[`test_watchtower.py`](../../tests/test_watchtower.py).

### R2 — Permanent provider responses

HTTP 401, 403, 404, and 410 now propagate as a typed
`PermanentProviderError`, stopping the current source attempt without
automatic whole-source repetition. HTTP 429 retains its existing separate
stop/backoff behavior. Timeouts without an observed permanent status and
transient HTTP failures retain bounded retry behavior.

The fix covers urllib, curl, GET/POST fallback, and an important edge case:
curl can observe a permanent HTTP status and then time out while consuming
the response. The observed status must not become a generic retryable
timeout. Optional GAC/parcel-quality probes also propagate the permanent
error so later optional requests are not issued after the provider refuses
the request.

This changes failure handling within a check. It does not change source
registries, provider authorization, TLS verification, redirect restrictions,
request budgets, or normal daily scheduling. A previously swallowed optional
permanent error now ends the source check and is recorded through the normal
source-failure handling path.

Regressions exercise all four permanent statuses, absent-status timeouts,
fallback propagation, one-attempt behavior, transient retries, and prevention
of subsequent optional probes. These use mocked transports; they do not
contact providers.

Relevant files: [`watch.py`](../../clearparcel/datawatch/watch.py),
[`test_transport_security.py`](../../tests/test_transport_security.py),
[configuration reference](../configuration.md).

### R3 — Control sizing

The deployed overview selectors measured approximately 19px high and the
refresh button approximately 21px high in the inspected desktop browser.
Their native appearance also differed from the surrounding public theme.

The candidate gives these specific controls a 44px minimum height, consistent
colors/padding, and full-width overview selectors on narrow layouts. The
changes are limited to overview selectors, the gap-standard selector, and
the public refresh button. Existing theme, tables, and page structure are
preserved.

Fresh desktop production interactions passed. The current browser session
did not expose viewport resizing, so the candidate's mobile layout has not
received a fresh rendered check. The earlier release record contains a
390px check of the deployed build; that historical evidence does not verify
this candidate CSS.

### R4 — Current and historical documentation

README and STATUS now distinguish the deployed `bbc364d` runtime from the
newer documentation commit and from this candidate branch. Historical
October 6–7 previews, inventories, and scheduling statements remain dated
records, with a current checkpoint taking precedence.

The README now explicitly states that private service readiness and the
anonymous Google sign-in redirect passed, while signed-in private rendering
remains unverified.

SECURITY.md now accurately describes the intentionally public coarse worker
labels, source assignments, health/count summaries, report/success times,
and retirement identifiers/timestamps. Raw diagnostics, detailed execution
provenance, resource telemetry, private provider URLs, tracked values, and
arbitrary nested worker data remain excluded. Worker labels must be
non-sensitive. The generated current-status document remains synchronized
from STATUS.md.

## Security review and alert triage

The inspected controls include:

- Public projection rejects or omits malformed/nested private values and
  escapes hostile labels when rendered. Tests covered script/markup strings,
  private URLs, tracked payloads, fingerprints, invalid numeric values, and
  invalid dates.
- CSV formula-like values are neutralized; XLSX text is escaped and invalid
  XML control characters are removed. The downloaded public workbook passed
  ZIP integrity checks.
- Private mutation routes include authentication/CSRF checks and request
  bounds. Anonymous access to the deployed private service returned HTTP 302
  to Google sign-in. Signed-in rendering and its private wrapper were not
  independently exercised end to end.
- Redirects remain disabled by default; enabled redirects validate and bind
  destinations, preserve TLS/Host checks, and fail closed where a proxy cannot
  enforce the binding. Response limits, deadlines, and the separate 429 stop
  behavior remain intact.
- State/aggregate writes retain storage-version preconditions and worker
  retirement/concurrency safeguards. This review did not exercise production
  recovery or write production state.
- CI uses pinned action revisions and a pinned container base, dependency
  auditing, CodeQL, fixable high/critical container scanning, and supply-chain
  evidence. A passing configured scan is bounded by its enabled rules and
  vulnerability policy.

The live public response included CSP, HSTS, `nosniff`, frame denial,
no-referrer, and restrictive Permissions-Policy headers. CSP still permits
inline scripts/styles; nonce/hash migration is a future defense-in-depth
improvement, not a reproduced XSS vulnerability. Public analytics remain
dormant behind the separate issue #50 privacy gates.

### CodeQL findings

CodeQL alerts #2 and #3 reported `py/http-response-splitting` at the public
and private Excel Content-Disposition sinks. Both were reviewed against
main `e14dddb` and dismissed as **false positives**, with the reasoning
retained on each alert.

In both reachable routes, the percent-decoded county slug passes through
`_county_snapshot`, which requires an exact match in the packaged set of
87 canonical county slugs. An unknown, CRLF-bearing, quoted, or traversal-like
slug returns 404 before the attachment-header sink. The statewide filename
is a fixed literal. The existing regression
`test_county_export_rejects_header_control_input_before_filename_sink`
uses the real lookup callback and passed. Both callbacks and the county
inventory were inspected independently.

Alert #1 was already fixed. After triage, GitHub reported zero open CodeQL
alerts, zero open Dependabot alerts, and zero open secret-scanning alerts.
These counts describe the enabled GitHub findings at review time; they do
not prove the repository or complete history contains no secrets or defects.
No scanner was disabled, suppressed, or weakened.

Main protection enforces administrators, rejects force pushes/deletions, and
requires the six Linux/Windows Python test checks. The separate `security`
job runs but is not a required status check. Add it through a separately
approved branch-protection change while preserving the existing required
checks.

## UI, data, and export acceptance

| Check | Result / limit |
| --- | --- |
| Public desktop layout | No page-wide horizontal overflow at the inspected 1363px viewport |
| Overview county selection | Olmsted selection and clearing updated metrics/links; 87 interactive map counties |
| County metric semantics | Olmsted displayed 29.06% all-field, 42.86% Mandatory, 75,579 parcel records; unavailable remains distinct from zero |
| MN GAC navigation | Winona selection persisted across parcel/address/road switches and county-result links |
| Field search | `CO_NAME` narrowed Winona road results to left/right county-name fields |
| Refresh and export controls | Pause/resume state changed correctly; export menu opened and Escape dismissed it |
| Browser errors | No application JavaScript errors observed; browser-extension messages excluded |
| Health and public APIs | `/healthz`, `/api/summary`, `/api/state`, and `/snapshot.json` returned 200 |
| County CSV | 87 county rows |
| Parcel-source CSV | 350 rows, including intentional empty-category placeholders |
| MN GAC parcel CSV | 91 standard-field rows |
| Excel snapshot | Valid ZIP/workbook, 12 worksheets |
| Invalid routes | Unknown county/source returned 404; invalid GAC standard returned 400 |
| Private anonymous access | 302 redirect to `accounts.google.com` |
| Fresh mobile / signed-in private | Not independently verified in this review |

Saved public data showed 2,710,201 parcel records across 59 represented counties,
with 91 fields scanned and seven Mandatory fields. Address/road routine
observations scan Mandatory fields; the UI correctly identifies unscanned
all-field metrics. Road representation, open-product metadata, and
out-of-jurisdiction exclusions remain distinct concepts. No hard-coded
county coverage or denominator change was introduced during this review.

Public endpoint timings included the review environment's network overhead;
they were not treated as isolated server benchmarks. Large public JSON and
workbook outputs were checked, but no production load or denial-of-service
testing was performed.

## GitHub and workstation cleanup

Before cleanup, GitHub had main and one stale closed-PR branch, with no open
pull requests. The superseded PR #63 publication record is preserved on main
in full, with a historical banner. Its other documentation was superseded by
later merged release records. The old branch must not be merged back.

The following stale references were removed after exact-head and worktree
checks. A verified private Git bundle preserves their full history.

| Removed ref | Exact preserved head | Evidence |
| --- | --- | --- |
| GitHub `codex/mngac-publication-record` | `c702aba4ce566a0680e577edc926e6f38d7db7f6` | [Closed/superseded PR #63](https://github.com/clearparcel/GIS-Data-Watchtower/pull/63); publication file preserved |
| Local `codex/inline-county-pane` | `a6694a883acdfc315c49c86391c690c073300c41` | [Merged PR #64](https://github.com/clearparcel/GIS-Data-Watchtower/pull/64) |
| Local `codex/release-v0.2.0` | `286ef05079220fe331bd796bae6c500ccdb4603f` | [Merged PR #65](https://github.com/clearparcel/GIS-Data-Watchtower/pull/65) |
| Local `codex/v0.2.0-publication-record` | `83ed5e89304d26140c2e1f5522316ce05af8fbc4` | [Merged PR #66](https://github.com/clearparcel/GIS-Data-Watchtower/pull/66) |
| Local `docs/watchtower-bbc364d-release-20261011` | `7df9a10c29816df16ba390aa4151e0c10b22c702` | [Merged PR #68](https://github.com/clearparcel/GIS-Data-Watchtower/pull/68) |

The remote deletion used an expected-head lease. Local deletions used
expected-old-value ref updates. Stale remote-tracking refs and the deleted
local branches' configuration were pruned. Main, the retained county-fix
worktree, and this review worktree were preserved. No release tag, historical
issue, release record, or production revision was removed.

Issue [#20](https://github.com/clearparcel/GIS-Data-Watchtower/issues/20) was
retitled **Complete five-day cloud worker observation study**, updated with
the October 11 warning/retained-worker checkpoint, and kept open. Its broken
link to a deleted branch now points to the same activation document at an
immutable main commit. Earlier evidence remains below the current checkpoint.

The four legitimate open issues remain:

| Issue | Reason to retain |
| --- | --- |
| [#1](https://github.com/clearparcel/GIS-Data-Watchtower/issues/1) | Aitkin provider terms / redistribution clarification |
| [#2](https://github.com/clearparcel/GIS-Data-Watchtower/issues/2) | Morrison unattended-use / provider policy clarification |
| [#20](https://github.com/clearparcel/GIS-Data-Watchtower/issues/20) | Five-day observation, recovery, parity, and rollback evidence incomplete |
| [#50](https://github.com/clearparcel/GIS-Data-Watchtower/issues/50) | Separate analytics project and IP/privacy gates incomplete |

## Validation and remaining decisions

The baseline suite contained 343 tests. The candidate contains **352 tests**;
the full ResourceWarning-strict Linux and authoritative GERTKEN-PC Windows
runs passed (352 each), as did focused transport tests, compilation,
generated-status synchronization, and Git whitespace
checks. Two independent reviewers checked the relevant functional/security
diffs; the final retry edge cases were corrected before PR preparation.
Exact-commit CI results are recorded on the pull request.

Use the complete Linux/Windows Python 3.12–3.14 matrix and the separate
security job when assessing the PR. Deployment acceptance still needs a fresh
mobile check of the candidate and signed-in private rendering. The prior
release notes document intermittent Windows temporary-file permission errors;
this is a follow-up if reproduced, not a reason to speculate about storage
changes.

Per [AGENTS.md](../../AGENTS.md), merging, pushing main, deploying, and changing
production data/configuration or authoritative schedules require explicit
approval in the current task. This review prepared a feature-branch change
and performed reversible stale-item cleanup. It did not merge or deploy the
candidate, change provider schedules/registries, retire aggregate worker
history, or modify authentication/IAM.

Recommended next decisions are: review the candidate PR; make the security
job required; scope the private dashboard identity to its read needs;
complete the five-day study while investigating the Hennepin warning at the
normal cadence; and approve a documented historical-worker retirement if
desired. Keep provider-policy and analytics gates open until their evidence
is resolved.
