# WT-02 monitoring-authority evidence reconciliation

Observed October 20, 2026, through 16:07:58 UTC. **Reconciliation remains
incomplete.** This read-only assessment applies the existing offline matcher
to an actual deployment registry and prepares the outstanding decisions.
It neither grants monitoring authority nor changes production.

## Inventory and evidence result

The provider job's registry reference was inspected and its exact existing
Secret Manager version read into temporary private storage. The private
receipt binds source and research hashes; a separate file hash identifies the
complete registry, including global retry settings. Public Git receives only
this summary, not registry contents, deployment identifiers or approval drafts.

| Supplied inventory | Count | Result |
| --- | ---: | --- |
| County-scoped parcel sources needing complete approval evidence | 22 | 14 have `not-assessed` research; 8 have `candidate-low-frequency`. Neither classification is an approval record. |
| Parcel sources without county-direct scope | 2 | Statewide/catalog classification needs a separate authority scope. |
| Registry sources held by research | 2 | Brown and Swift remain excluded by existing runtime policy. |
| Non-parcel sources | 9 | Outside this matcher's scope, not certified by this assessment. |
| Total | 35 | No source added, removed, enabled or reassigned. |

The CLI returned **1**, with 24 `needs_review`, 2 `held_by_research` and
9 `outside_parcel_scope` rows. No complete, dated approval/cadence ledger was
located in the inspected project evidence or supplied to this run. The owner
confirmed that no separate approval records are known. The tool stops approval
matching at `missing_approval`; this does not mean cadence was verified.

The receipt retains `reconciliation_complete: false`,
`activation_authorized: false` and `live_configuration_verified: false`.
Live configuration was read separately for this investigation; that read does
not upgrade the offline tool's flags or prove every dispatch path.

All 11 existing research holds remain unchanged. Only Brown and Swift occur
in this registry; the other held counties were not added or activated.
The current research file matches the provider job's deployed application
source, so the two held rows are not newly proposed exclusions.

## Aitkin and Morrison

Both configured service identities match their official public parcel catalog
items. This establishes which published product is being referenced, not
permission for every possible automated use.

| County | Existing evidence | Unresolved decision |
| --- | --- | --- |
| Aitkin | The [county GIS page](https://www.aitkincountymn.gov/departments/gis/) links public data downloads. Its [official item metadata](https://www.arcgis.com/sharing/rest/content/items/3cd285cbb13a43478d42e2ade3915403/info/metadata/metadata.xml) retains ordering instructions to ask about current distribution procedures and prices. | Reconcile the published direct service with requested-product terms and the exact bounded monitoring/derived-output scope. No parcel fee amount or categorical automation prohibition is inferred. |
| Morrison | The [county fees page](https://morrisoncountymn.gov/292/GIS-Fees) lists the parcel map layer as open and distinguishes Tax/CAMA and other products. Its [official catalog item](https://www.arcgis.com/sharing/rest/content/items/277775d6801f42c9b8f24afe1955b495?f=pjson) matches the configured service. | Confirm and record the direct API automation/use boundary. The separate LandShark restriction must not be treated as a finding that the configured ArcGIS API is LandShark. |

Existing owner-authored GitHub issues also contain operating constraints:

- [Issue #1](https://github.com/clearparcel/GIS-Data-Watchtower/issues/1)
  permits previously documented private, low-frequency monitoring while
  withholding raw parcel redistribution and requiring clarification for
  broader use.
- [Issue #2](https://github.com/clearparcel/GIS-Data-Watchtower/issues/2)
  describes bounded, low-frequency, read-only direct API checks, no LandShark
  automation, no material cadence increase and no raw-record redistribution
  pending provider-specific confirmation.

Both issues remained open with no comments when read. They are relevant
historical operating evidence, not newly issued authorization. Neither is a
complete approval ledger entry with current source/research hashes, a review
due date and verified combined dispatch spacing. Missing machine-matchable
records therefore must not be described as proof of absent historical
permission or unlawful monitoring.

## Actual check scope and cadence

The priority sources are configured for service/layer discovery and bounded
parcel-quality and geometry sampling. They are **not metadata-only checks**.
The private disposition drafts preserve the exact sample bound, endpoint,
source options and global retry context for review. Any scoped approval must
cover the actual reads and permitted derived output, not just a generic
description of source availability.

The inspected provider scheduler remains calendar-daily at 05:00
`America/Chicago`; the sanitized publisher is a separate schedule. The local
task-name inspection found the existing validation-capture task and no named
daily Watchtower poller. These bounded inspections do not prove there are no
manual, ad-hoc or differently named dispatch paths.

Calendar-daily does not establish a fixed 24-hour minimum: a timezone-aware
calculation gives 23 elapsed hours between 05:00 Central on March 13 and
March 14, 2027. Startup delay can also change spacing between actual checks.
This is a cadence-evidence limitation, not a finding that the provider's terms
were violated. Minimum-spacing assertions must cover DST, retries and all
dispatch paths; average daily frequency is insufficient.

## Prepared decisions and remaining gates

Private artifacts include the full inventory receipt, a source review queue
and Aitkin/Morrison disposition drafts bound to exact hashes. The drafts are
explicitly pending: they contain no fabricated approval, review expiry or
claim that all dispatch paths are covered. No draft was supplied as an
approved record to force a successful receipt.

Next steps:

1. Select a concrete scoped disposition for each source, incorporating any
   additional approval/correspondence evidence found later: document
   continuing use supported by reviewed evidence, or approve a narrowly
   specified hold. Existing issue constraints remain relevant in that decision.
2. Record the actual reviewer, decision reference, official terms reference,
   source/research/configuration identities, review date and due date.
3. Resolve calendar-daily versus fixed minimum spacing and verify combined
   dispatch controls. Do not assert `covers_all_dispatch_paths: true` from one
   scheduler inspection.
4. Rerun matching with the reviewed records. Treat statewide/catalog and
   non-parcel sources under their applicable scopes instead of counting them
   as approved county-direct sources.
5. Apply any resulting source/cadence change only through its own reviewed,
   owner-approved configuration change and readback.

**Watch result: UNVERIFIED for complete monitoring authority.** Public product
identity and the existing constraints were verified within this scope; no
change in provider permission is claimed. No GIS data query, provider job,
outreach, registry edit, research-decision edit or schedule change occurred.

See the [matcher contract](monitoring-authority-reconciliation.md) and the
[historical source diagnosis](operations-diagnosis-2026-10-20.md). This work
does not close alert delivery, GCS restoration, effective IAM or five-cycle
operational acceptance.

## Candidate and verification record

Implementer: Codex. Branch `codex/wt02-authority-evidence`, base
`f2ca5c0c2512c1a9fa4ae90de68d14715f5d1baf`. Changes are documentation only.
The original matcher and public research decisions are unchanged.

- Registry receipt: expected exit 1 with the evidence gaps described above.
- Final readback: provider job specification, registry version and scheduler
  definitions unchanged; provider image remains the previously verified v0.3.0
  artifact. No provider dispatch was performed.
- Strict local suite: 583 tests in 29.770 seconds, 3 platform skips, exit 0,
  with required Node 24 behavior tests enabled.
- Compilation, current-status synchronization and whitespace checks passed.

The private temporary registry copy is removed after retaining its hash and
exact version reference. Receipts, policy evidence and pending decision drafts
remain private. No independent model review has run on this assessment.

Published CCE context `gis-data-watchtower` was read at revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`.
It remains historical `needs-review` context, updated October 13 with review
due October 14; current evidence and owner instructions take precedence.
