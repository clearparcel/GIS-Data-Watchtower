# Isolated aggregate restore rehearsal

Run the synthetic rehearsal from the repository root:

```text
python scripts/rehearse_isolated_restore.py --output restore-receipt.json
```

Use a new receipt path. Exit 0 means all local checks passed and temporary
storage was removed; exit 2 means a check, cleanup or output operation failed.
Existing output files are never overwritten. Retain the receipt with the
tested Git commit and test results; do not commit generated receipts.

The command creates its own temporary local storage and fixed synthetic cloud
and local worker reports. It accepts no registry, backup, bucket or storage
destination. It does not use deployment backend environment settings, contact
providers, create cloud clients, send notifications or change schedules.
The only retained output is the requested receipt.

## What it measures

- A captured version token matches the exact downloaded aggregate bytes.
- A damaged backup fails its checksum before any destination write.
- Restoration into an empty destination preserves the aggregate byte for byte.
- Create-only restoration refuses an occupied destination.
- A restore using a stale token cannot overwrite a newer worker result.
- Two independent local backend instances read the same version before either
  can write. Actual conditional uploads produce one conflict; the existing
  aggregate publisher reloads and retries, preserving both worker updates.
- Worker provenance, failed-check versus previous-success clocks, availability
  timestamps and a source retirement tombstone survive restore and publication.
- A delayed worker report cannot roll back the recovered state.
- The original object and backup remain unchanged, and publisher scratch is
  removed. The rehearsal's temporary storage is removed before success returns.

The receipt includes measured conflict count, backup/final aggregate hashes,
UTC execution times and hashes of the rehearsal, aggregate, storage and locking
implementation files. The fixture's observation dates are deliberately fixed
historical dates; the execution time does not refresh those observations.
Negative tests disable CAS, suppress retries and lose a worker update to ensure
these regressions cannot produce a passing rehearsal.

## Limits and operational acceptance

This is an aggregate-only **local synthetic rehearsal**. It does not recover a
real backup or test GCS generations, bucket versioning, service identity, IAM,
network filesystems, process termination or production traffic. It does not
restore worker-local state/backoff records, history archives, public snapshots,
private registries or secrets. The receipt explicitly leaves GCS and production
restore verification false and grants no activation authority.

Before an operational restore, inventory all required private artifacts and
their independent backup provenance/hashes; define a consistent recovery point,
writer coordination, destinations, IAM and rollback. Rehearse those exact
artifacts and GCS generation preconditions in separately approved isolated
storage. Preserve backoff, holds, tombstones and observation times; never turn a
restored old observation into a new provider check. A matching checksum proves
byte integrity against the recorded checksum, not trust in the backup's origin.

Do not replay this internal fixture restore helper against production.
An operational restore needs a reviewed exact change and explicit approval.
Alert delivery, effective IAM assessment and five ordinary daily cycles remain
separate acceptance gates. See [operations triage](operations-triage.md) and
[hybrid aggregation](hybrid-aggregation.md).
