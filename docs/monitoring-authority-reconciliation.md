# Offline monitoring-authority reconciliation

This WT-02 tool matches private source, approval and cadence records to current
county parcel research. It does not authenticate an approval, decide whether a
provider permits access, edit research, enable monitoring, or contact providers.
A receipt always has `activation_authorized: false` and
`live_configuration_verified: false`.

The [October 20 evidence assessment](monitoring-authority-evidence-2026-10-20.md)
applies the matcher to the actual private inventory and distinguishes existing
operating constraints from complete current approval/cadence records.

## Capture inputs

Keep the original private registry and the operator's approval/cadence evidence
in untracked private storage. The registry must contain a `sources` list with
unique IDs. The CLI reads the repository's validated parcel-access research and
canonical county names/slugs; it does not retrieve a production registry.

```text
python scripts/reconcile_monitoring_authority.py --registry PRIVATE_REGISTRY.json --as-of 2026-10-20 --output NEW_PRIVATE_RECEIPT.json
```

Without evidence files, eligible sources appear with missing-approval gaps.
Rows include source/research hashes to identify the exact material requiring
review. Do not fill an approval record from these hashes without reviewing the
actual source, official terms and intended scope.

For enabled parcel sources, a missing county slug is unresolved scope, including
statewide parcel sources needing separate classification. Non-parcel categories
are outside this tool's scope. Source IDs and classification must be checked
against the authoritative registry before relying on coverage totals. Disabled
sources remain disabled. `hold-for-terms` counties remain held even if an input
approval claims otherwise; `not-appropriate` research requires a hold review.
The tool never applies that hold or changes the runtime registry.

## Reviewed evidence records

Supply JSON lists with one current approval and one cadence record per eligible
source. The following are synthetic examples; the hash placeholders must match
the reviewed inputs:

```json
[
  {
    "source_id": "sample-parcels",
    "county_slug": "sample",
    "decision": "approved",
    "source_sha256": "<exact-source-hash>",
    "research_sha256": "<exact-research-hash>",
    "execution_profiles": ["cloud"],
    "reviewed_on": "2026-10-19",
    "review_due": "2026-11-19",
    "reviewer_ref": "private-reviewer-record",
    "approval_ref": "private-scoped-owner-decision",
    "terms_ref": "private-official-terms-evidence",
    "minimum_interval_hours": 24
  }
]
```

The source hash binds the entire source definition, including endpoint/query
and options. The research hash binds the entire county record. Changes require
reconciliation; a health result or `candidate-low-frequency` research decision
cannot substitute for an approval. A separate reviewed approval can coexist
with `not-assessed` research without rewriting the public research status.

Duplicate approval records are ambiguous, including a grant beside a revocation.
Duplicate JSON fields and non-finite numeric values are rejected before writing.
Select the authoritative current record through human review and preserve its
history privately. `hold`/`revoked`/unknown decisions cannot match an approval.
Dates must satisfy `reviewed_on <= as_of < review_due`; the due date is already
stale. Evidence references are checked for presence, not fetched or verified.

```json
[
  {
    "source_id": "sample-parcels",
    "source_sha256": "<exact-source-hash>",
    "execution_profiles": ["cloud"],
    "reviewed_on": "2026-10-19",
    "review_due": "2026-10-25",
    "evidence_ref": "private-combined-dispatch-review",
    "minimum_interval_hours": 24,
    "covers_all_dispatch_paths": true
  }
]
```

Cadence evidence must cover the minimum spacing across **all** assigned workers
and manual/ad-hoc dispatch paths. Two workers each running daily do not prove
a combined daily interval. Average frequency is insufficient to establish
minimum spacing. The tool compares recorded assertions; the operator must
verify actual schedules and dispatch controls separately.

Only explicit `cloud`/`local` assignments are supported for a matched receipt.
Wildcard, missing or duplicate assignments remain unresolved rather than
silently assuming worker scope. Cadence profiles must exactly match both source
and approval scope. An interval shorter than 24 hours requires an additional
`cadence_exception_ref` in the approval, backed by reviewed provider terms and
operational need. Observed spacing cannot be shorter than the approved minimum.

```text
python scripts/reconcile_monitoring_authority.py --registry PRIVATE_REGISTRY.json --approvals PRIVATE_APPROVALS.json --cadences PRIVATE_CADENCES.json --as-of 2026-10-20 --output NEW_PRIVATE_RECEIPT.json
```

## Interpret and retain the receipt

`documented` means supplied records match; it is not a live authorization or
legal determination. `reconciliation_complete` describes only the supplied
inventory. Check status counts: disabled, held and outside-scope rows are not
documented active sources. Unknown IDs in evidence and duplicate records are
reported instead of silently selecting a winning entry.

Exit 0 means no reconciliation gaps in the supplied nonempty inventory;
1 means gaps or an empty inventory; 2 means invalid input/output. Existing
input and output files cannot be overwritten. The receipt omits raw URLs,
reviewer and terms references but retains source IDs and fingerprints, so it
must remain private. Public reports should contain only separately reviewed
summaries. No provider secrets or private registry should enter Git.

Prioritize Aitkin/Morrison evidence and preserve every current data-driven hold.
Real authority reconciliation remains open until current private evidence is
matched and reviewed. Changes to sources, holds, cadence or deployments require
a separate concrete change and owner approval. Continue historical source
diagnosis using the [operations triage runbook](operations-triage.md).
