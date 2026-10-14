# Final Watchtower UI, repository and operational review

Review date: October 10, 2026, CDT (October 11 UTC). Reviewed on GERTKEN-PC.
Candidate: PR #64, `codex/inline-county-pane`, based on main `8999081`.
Live public application: v0.1.2, build `8999081`, revision `00013-s7q`.

## Result

Two application bugs and one weak test assertion were corrected in the candidate.
The required offline suite passes all **340 tests**. The local interactive preview
passes the tested UI flows and preserves equal map/selected-county pane heights.
Git branch/build housekeeping is complete for the verified obsolete items.

The review found overdue provider observations, a legacy local daily poller
and three open CodeQL alerts. The legacy poller was subsequently removed under
explicit user approval; see the follow-up below. During the original review,
no production deployment, merge, provider retry, scheduling change,
registry change or worker retirement was performed during this review.

## Bugs corrected

| Finding | Reproduction and consequence | Correction and verification |
| --- | --- | --- |
| Stale selected county | Select Sibley, then “Choose a county…”. The picker clears but Sibley remains highlighted and Pane A retains its details. | Clear the highlight, county metrics, links, details and infographics. Abort the pending fragment request and invalidate its response. Browser reproduction passes; the JavaScript regression verifies a late response cannot restore old details. |
| Missing detail pages return success | Unknown `/source?id=…` and `/county?slug=…` pages display “not found” with HTTP 200. Clients and status checks can mistake these for valid pages. | Both public and private handlers now return 404 for missing details and 200 for valid details. A handler regression exercises both servers. Actual unknown-source HTTP check now returns 404. |
| Weak example-host assertion | The test accepted any URL containing `example.com`, including unrelated hosts with that text in a path or query. | Compare the parsed hostname exactly to `example.com`. This was a test-quality defect, not a production URL allowlist. |

## UI acceptance

The review exercised the candidate in the in-app browser and through bounded
HTTP reads. It used saved sanitized observations and did not poll GIS providers.

- Overview county selection updates Pane A without opening a dialog. Keyboard
  Enter on a county map target updates the same pane. Clearing selection removes
  stale content and restores the county-choice prompt.
- The compact pane excludes the six requested source/research accordions; the
  full county profile retains its research evidence. County infographics remain
  beneath the monitoring/schema summary.
- Schema/open-data status, monitoring paths and field-population percentages
  remain separate map views. Schema legend categories distinguish MN GAC data
  availability, differing checked direct feeds, documented lack of confirmed
  open data, unassessed open schemas and unresolved access. Patterns supplement
  color. The percentage legend says **N/A** rather than “No data”.
- Olmsted correctly shows statewide MN GAC data availability despite its direct
  feed being unassessed. Sibley shows checked direct-feed schema differences
  without inventing a statewide population percentage or claiming county-wide
  noncompliance.
- Sibley map/pane heights were equal at 390px width (1233.625px each) and 1062px
  width (1250.125px each). Olmsted was equal at the default desktop width
  (1062.78125px each). No horizontal page overflow was observed. Temporary
  viewport overrides were reset. Equal height on stacked layouts produces tall
  cards; this follows the requested equal-height behavior.
- The MN GAC county chooser accepts the simple county name. Selecting Olmsted
  opens its results; switching Parcels → Address Points → Road Centerlines
  preserves the county. Statewide overview remains separately selectable.
- County field search for `CO_NAME` returns the corresponding county row. The
  county index presents 87 counties and the derived monitoring/coverage counts.
- Data-source search isolates Douglas. The warning filter isolates Hennepin
  imagery. Douglas renders correct punctuation, source metrics and the audited
  direct-schema finding. Export navigation and pause/resume controls work.
- No page JavaScript errors were captured during these flows. HTTP-rendered
  HTML uses UTF-8 and passed the mojibake check. The current version is v0.1.2.
  Local source previews intentionally report Development/build unknown because
  they do not contain the deployment's baked immutable build identity.

## HTTP, export and data consistency checks

- Valid overview, county index/detail, source, MN GAC county/statewide routes and
  JSON/CSV/XLSX exports passed bounded HTTP reads.
- **87/87** revision-bound county fragments returned HTTP 200 with no failures.
- Invalid MN GAC county input returns 400. Invalid county export input containing
  CRLF returns 404 and emits no injected response header. Regression coverage
  also rejects quote and path-traversal-shaped county slugs before the filename
  sink. Conditional overview requests correctly return 304.
- The county CSV contains 87 rows; snapshot JSON contains 87 counties and 35
  sources; the XLSX ZIP integrity check passes with 12 worksheets.
- Coverage remains derived as **59 statewide + 24 direct − 13 overlaps = 70**
  distinct monitored counties. The partitions are 46 statewide-only, 11
  direct-only, 13 both and 17 neither. Olmsted is in the overlap.
- The direct-schema audit records 21 checked feeds: Wabasha contains all 91
  standard physical field names; 20 checked feeds lack names. Olmsted, Ramsey
  and Dodge remain unassessed. Field-name matches alone are not full compliance.
- The saved local fixture lacks a public publication timestamp, so preview
  `/healthz` correctly returns 503. Its observation clocks were preserved.
  Production `/healthz` returns 200 with a fresh publisher timestamp. These
  distinct outcomes must not be “fixed” by rewriting saved timestamps.

## GitHub and stale-item cleanup

- Remote branches are only `main`, `codex/mngac-publication-record` and
  `codex/inline-county-pane`. Stale remote-tracking refs were pruned. GitHub's
  automatic merged-branch deletion is enabled.
- Removed **24 local branch references** only after verifying ancestry in main
  or an exact head match to a merged PR whose merge commit is in main. Local
  `main` now matches `origin/main` at `8999081`; no direct push to main occurred.
- Removed the clean October 7 temporary validation worktree and obsolete
  preview build context/archive. The active checkout is the only worktree.
- Preserved user attachments and dated research/release/rollback evidence.
  `.codex-remote-attachments/` is now ignored to prevent accidental public
  commits. Private working directories remain ignored.
- Corrected current-status prose that still called the deployed MN GAC county
  page a preview. Deployment documentation now identifies public `00013-s7q`
  and labels `00012-c5j` as the initial historical rollout. Generated status
  documentation was synchronized from `STATUS.md`.
- PR #63 is a legitimate pending detailed publication/rollback record; PR #64
  is the current UI/data candidate. Neither was merged. Because both touch
  status documentation, reconcile those sections in merge order.
- Issues #1/#2 (provider terms), #20 (cloud activation) and #50 (analytics) remain
  legitimate open work. They were not closed as stale simply to empty the list.
- No open Dependabot alerts were returned. A targeted scan of tracked files
  found no private-key blocks, GitHub-token or AWS-key patterns. Tracked-path
  inspection and patch review found no private registry, credentials, scratch
  or temporary exports staged for publication. This is not a full Git-history
  credential audit.

## Security scanner findings

| GitHub alert | Assessment | Current disposition |
| --- | --- | --- |
| #1 `py/incomplete-url-substring-sanitization` | Flags the weak hostname assertion in a test, not a production sanitizer. Exact parsed-host comparison now replaces it. | Corrected in PR #64; alert on existing main remains open pending integration/rescan. |
| #2 public and #3 private `py/http-response-splitting` | Both trace county query input to an XLSX attachment filename. Every shipped county callback first requires an exact match in the packaged canonical county list; malformed input returns no snapshot and reaches 404 before the header. Statewide filenames are constants. The current-path evidence supports a false-positive assessment. | Both retained open for explicit scanner/reviewer disposition. Added a regression for the canonical lookup boundary; no suppression or security-control weakening. |

The previous candidate's CI matrix, dependency audit, CodeQL job, container
HIGH/CRITICAL scan and SBOM checks passed. A successful CodeQL job does not mean
zero alerts. Final commit CI is separately visible on PR #64; inspect its exact
head before merge. No claim of a complete penetration test or absence of all
possible defects is made.

## Operational findings requiring follow-up

### Approved retirement follow-up — October 10, 22:20 CDT

The user explicitly requested disabling and removing ClearParcel Tools polling.
The daily task identified in finding 2 was disabled, stopped and unregistered;
its launcher was removed from active use. Verification found no remaining legacy
provider polling task or process. Private rollback records and historical state
were preserved. The validation-capture task remains enabled because it only reads
saved state/cloud metadata. No cloud provider schedule was created, no aggregate
worker was retired, and the publisher/registry were unchanged. The findings below
describe the inspection before retirement; activation evidence remains pending.

### Findings recorded during the original review

The user subsequently explicitly requested daily Google Cloud polling. The
05:00 America/Chicago provider schedule is now enabled; see the
[daily activation record](daily-cloud-provider-polling-2026-10-10.md) for actual
source/persistence/public-arrival results. Statements below about pending
scheduling describe the earlier review, not the newly approved schedule. The
five-day study and separate historical-worker retirement remain incomplete.

1. **Provider data is overdue.** Production's provider report remains October 9
   at 09:32 CDT, although the sanitized publisher is healthy and publishing every
   ten minutes. Public source health is 34 OK / one warning (Hennepin imagery).
   Last-check health and reporting freshness are intentionally separate.
2. **Legacy local polling is still active.** The daily GERTKEN-PC task invokes
   the older installation under `C:\ClearParcel_Tools`, with 26 configured
   sources and no explicit execution profiles. It ran October 10 at 05:00 CDT,
   writing separate local state: 25 OK, one warning, zero errors. Its exit code
   1 follows the CLI's intentional warning return code; it is not evidence of a
   crash. The validation-capture task ran at 05:30 and returned 0. The local
   installation is stale operational state outside the candidate checkout.
3. **Cloud execution warnings need separate operational treatment.** Latest
   saved cloud execution `gis-data-watchtower-staging-pbq75` completed October 9
   at 09:34 CDT with exit 1, so Cloud Run marks it unsuccessful. Current CLI also
   returns 1 for warning reports. Bounded log reads and saved public health do
   not establish an uncaught exception; this review did not rerun the worker.
   Decide how warning exits should affect operational alerting before changing
   that contract.
4. **Cloud assignment is not authoritative scheduling retirement.** The current
   private registry's 35-cloud assignment does not disable the old local task.
   Cloud Scheduler still contains the sanitized publisher rather than an
   authoritative daily provider schedule. Multi-day activation evidence,
   scheduling approval and safe worker retirement remain open gates.
5. **Codex Cloud readiness remains separate.** Historical synthetic setup
   validation does not establish normal authority-bound CCE availability in a
   fresh cloud development task. This review used CCE on GERTKEN-PC.

Following the separately approved activation, the schedule and one complete
35/35 healthy source/persistence/public-arrival cycle are verified. The remaining
operational work is the multi-day observation study and any separately approved
aggregate-history retirement. The legacy local task is removed; retained
historical local-worker records must not be treated as current polling
assignments or deleted without that separate approval.

## Verification and limits

Completed: `python -W error::ResourceWarning -m unittest discover -s tests -q`
(340 passed), `python -m compileall -q clearparcel tests`, status synchronization,
`git diff --check`, browser interaction/layout checks, bounded dashboard HTTP
checks, read-only GitHub/Cloud Run/Scheduler/task-state inspection and a targeted
tracked-file credential-pattern scan.

This review did not bulk-download GIS data, refresh provider observations,
perform fresh compliance determinations, exercise private production login,
change cloud IAM/networking, deploy a replacement service or approve a merge.
The reviewed fixes subsequently merged through PR #64 and shipped under the
user-approved [v0.2.0 rollout](release-v0.2.0.md). The limits above describe the
original review; subsequent deployment and operational evidence are recorded
separately in the linked release and daily-cloud activation records.
