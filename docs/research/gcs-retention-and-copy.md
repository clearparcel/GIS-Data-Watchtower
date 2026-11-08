> Historical research from November 3, 2026, preserved during v0.5.1 review.
> Recommendations are not authorization or a statement of current deployed state.
> See the [review disposition](../review-remediation-v0.5.1.md).

# Research: Cloud Storage retention, versioning and an independent second copy

Issue: [#190](https://github.com/clearparcel/GIS-Data-Watchtower/issues/190).
Researched 2026-11-03 against Google Cloud documentation (linked inline).
Historical context: [backup and access review](../backup-access-review-2026-10-20.md)
found the state bucket protected only by the default 7-day soft delete in one
region, with no versioning, retention policy or independent copy. State writes
use generation-match compare-and-swap (`upload_if_version` and
`download_versioned` in `clearparcel/datawatch/storage.py`). No settings were
changed for this research.

## How the features interact

| Feature | What it does | Reversible? |
| --- | --- | --- |
| [Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning) | Replacing or deleting a live object (without naming its generation) keeps the old bytes as a *noncurrent* version. Each noncurrent version "is charged at the same rate it was when it was live." It "does not provide protection against bucket deletions." | Yes |
| [Bucket retention policy](https://docs.cloud.google.com/storage/docs/bucket-lock) | Objects "cannot be deleted or replaced until they reach the age you define"; attempts fail with `403 retentionPolicyNotMet`. Applies retroactively. Maximum 100 years. | Yes, while unlocked |
| [Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock) (locking that policy) | "Locking a bucket's retention policy is an irreversible action." The period can be increased, never reduced or removed. The bucket can't be deleted until every object meets the period, and a lien blocks deleting the project. | **No** |
| [Object Retention Lock](https://docs.cloud.google.com/storage/docs/object-lock) | Per-object retain-until time. `Unlocked` mode can be changed by authorized users; `Locked` mode can only be extended. When an object has both this and a bucket policy, it is kept until both are satisfied. | Enabling it on a bucket is **not** reversible; `Locked` object settings are **not** reversible |
| [Object holds](https://docs.cloud.google.com/storage/docs/bucket-lock) | Event-based or temporary hold blocks deletion while set. Removing an event-based hold restarts the object's retention period. | Yes |
| [Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete) | Keeps deleted *and overwritten* objects 7 to 90 days (default 7; 0 disables). Billed as normal storage. Soft-deleted objects can be listed or restored only. Described as "an additional layer" on top of Bucket Lock and Object Retention Lock. | Yes |
| [Lifecycle rules](https://docs.cloud.google.com/storage/docs/lifecycle) | `Delete` does nothing while an object has a hold or an unmet retention policy. `daysSinceNoncurrentTime`, `numNewerVersions` and `isLive: false` target noncurrent versions. | Yes |

Two interactions matter most:

- **Versioning plus retention.** The Bucket Lock page says that in a versioned
  bucket "a live object version that has a retention expiration date in the
  future can still be made noncurrent," and that versions already there are
  also protected. So with versioning on, a retained name can get a newer live
  version, while the old generation stays protected until it meets the period.
  The overview pages don't spell out the overwrite case, so verify it in a
  throwaway bucket before relying on it.
- **Overwrite needs delete permission.** `objects.insert` requires
  `storage.objects.delete` "only if the request causes an object with the same
  name to be overwritten"
  ([IAM for JSON methods](https://docs.cloud.google.com/storage/docs/access-control/iam-json),
  footnote 7). A writer with only `storage.objects.create` (Storage Object
  Creator) can add new objects but can't overwrite or delete them.

## Evidence bucket: never overwritten or deleted, new versions allowed

Recommended combination:

1. **Write-once names.** Each document version is a *new object name* (for example
   a run ID or content hash), written with `ifGenerationMatch=0` so it is
   create-only. "New version" means a new object, not a new generation of
   the same name. A mutable index belongs in the state bucket, not here.
2. **Bucket retention policy, versioning off.** With no versioning, the policy
   blocks every replace and delete with a 403, which is the simplest
   behavior to test. For "kept indefinitely," use a very long period (the
   100-year maximum). A locked policy can be extended later but not shortened.
3. **IAM.** The writer identity gets only Storage Object Creator on this bucket.
   Readers get Storage Object Viewer. No Watchtower identity gets
   `storage.objects.delete`, `setRetention` or bucket admin.
4. **Soft delete at 90 days.** This only matters after a retention period ends
   or if the bucket is deleted, but it costs nothing at rest for objects
   that are never deleted.
5. **Lock last.** Run with the policy unlocked first. Confirm that replace and
   delete return `retentionPolicyNotMet` and that new objects still succeed.
   Then ask the owner to approve Bucket Lock.

Object Retention Lock is the alternative when documents need different
retention periods. It adds a per-object `setRetention` step and permission,
and enabling it can't be undone. A single bucket-level policy fits a uniform
"keep forever" rule better.

## State bucket: versioning versus generation-match writes

**No conflict.** Preconditions compare against the *live* generation:
`ifGenerationMatch` "makes the operation conditional on whether the object's
current generation matches," and `0` succeeds "only if there are no live
versions of the object"
([objects.insert](https://docs.cloud.google.com/storage/docs/json_api/v1/objects/insert)).
Noncurrent versions don't affect the check. Create-only writes and the
create-only restore still refuse an occupied live name. Each successful
compare-and-swap leaves the previous generation as a noncurrent version.
One caveat: deleting with an explicit generation removes that version
permanently (to soft delete), bypassing versioning.

**Do not** put a retention policy on the state bucket. Without versioning it
would reject the compare-and-swap overwrites of young objects with
`403 retentionPolicyNotMet`.

Recommended: turn on Object Versioning, add a lifecycle `Delete` rule on
noncurrent versions with `daysSinceNoncurrentTime: 90` (optionally capped
with `numNewerVersions`), and raise soft delete to 30–90 days. History files
are rewritten whole on each run, so every noncurrent version is a full copy.
At MB scale that is still pennies a month.

## An independent second copy

| Option | Independence | Notes | Rough cost at 1–5 GiB |
| --- | --- | --- | --- |
| [Dual- or multi-region bucket](https://docs.cloud.google.com/storage/docs/availability-durability) | Region outage only. Same bucket, IAM and project, so deletes and overwrites hit both copies. | Default RPO 12 h, turbo 15 min (dual-region only). | Standard about $0.022–0.026/GiB-month plus $0.02/GiB replication ([pricing](https://cloud.google.com/storage/pricing)): under $0.25/month |
| [Cross-bucket replication](https://docs.cloud.google.com/storage/docs/using-cross-bucket-replication) (Storage Transfer Service, event-driven) | Another region or project. "Object deletions in the source bucket are not replicated." | Copies new and updated objects asynchronously, with no RPO. A versioned destination keeps overwritten copies as noncurrent. | STS agentless transfers are free ([STS pricing](https://cloud.google.com/storage-transfer/pricing)). You pay $0.02/GiB North America inter-region transfer, Class A rewrite operations and destination storage: well under $1/month |
| [Scheduled STS copy](https://docs.cloud.google.com/storage-transfer/docs/create-transfers), daily, cross-project | Strongest. Pull job owned by a separate backup project whose identities Watchtower can't use. | Leave [`deleteObjectsUniqueInSink`](https://docs.cloud.google.com/storage-transfer/docs/reference/rest/v1/TransferOptions) off. Use `overwriteWhen: NEVER` for evidence and `DIFFERENT` into a versioned sink for state. The agent needs `storage.objects.delete` on the sink only when overwriting or deleting ([sink access](https://docs.cloud.google.com/storage-transfer/docs/sink-cloud-storage)). | Same as above: under $1/month |
| [Backup and DR Service](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-dr) | n/a | Supported workloads are Compute Engine, disks, Filestore, VMware Engine, Cloud SQL, AlloyDB and self-managed databases. Cloud Storage buckets appear only as a backup *target*. **Not an option** for backing up bucket data. | — |

Recommended: a **daily scheduled STS job in a separate backup project**,
pulling both buckets into a single-region destination in another US region.
The destination for state is versioned with a noncurrent lifecycle rule. The
destination for evidence gets the same retention policy as the source
(and later Bucket Lock), with `overwriteWhen: NEVER`. Dual-region is optional
on top. It does not count as the independent copy.

## Irreversible or approval-gated steps

These need explicit owner approval (they are production configuration writes
under `AGENTS.md`). The first three can't be undone:

1. **Locking a bucket retention policy** on either evidence bucket (source or
   backup). The bucket and its objects stay until each object reaches the
   period, a lien blocks project deletion, and the period can only grow.
2. **Enabling Object Retention Lock** on a bucket, or setting any object
   retention in `Locked` mode, if that route is chosen.
3. **The retention period itself after lock.** Choose it before locking:
   100 years cannot be shortened later.
4. Reversible but still gated: enabling versioning, lifecycle rules, soft
   delete changes, creating the backup project, bucket and STS job, and IAM
   grants.

## Open points

- Test in a disposable bucket whether a versioned, retained bucket accepts an
  overwrite (old generation becoming noncurrent) or returns 403. The
  recommendation above doesn't depend on the result, because the evidence
  bucket runs with versioning off.
- The STS documentation does not say whether noncurrent source versions are
  copied. Assume only live objects are.
