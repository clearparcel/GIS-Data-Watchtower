# Backup check and access review — October 20, 2026

Owner-approved, read-only check of the deployed Watchtower storage and cloud
access (about 7:10 PM America/Chicago). Nothing in production was changed; the
restored copy was made in temporary local storage and deleted. Exact bucket,
identity and object details stay in private evidence.

## Backup and restore

| Check | Result |
| --- | --- |
| Snapshot of every operational object at pinned generations | Sizes and checksums match; generations unchanged during the copy |
| Parse with Watchtower's own readers | All JSON objects and every history line parse; state and aggregate agree on 33 sources |
| Restore into empty isolated storage | Byte-identical; create-only restore refuses an occupied destination |
| Publisher replay from the restored aggregate | Reproduces the live public snapshot exactly (except publish time) |
| Point-in-time recovery | Soft delete held the previous 7 daily generations of the aggregate, state and history |

Protection today is the storage provider's 7-day soft delete in one region.
There is no object versioning, retention policy or independent copy, so a loss
discovered after 7 days could not be recovered from storage. The private
registry keeps every Secret Manager version.

This complements the synthetic [isolated restore rehearsal](isolated-restore-rehearsal.md)
with the real artifacts; it is not an operational restore.

## Access

Confirmed: Watchtower buckets enforce public access prevention and uniform
bucket-level access; each Watchtower identity has only the bucket roles it
needs; no user-managed service-account keys exist; the private registry is
readable only by the provider job; the private dashboard is behind
Identity-Aware Proxy for the owner only; the jobs can be started only by the
scheduler identity and the owner.

Recommended changes (owner decisions recorded below; evidence is in the
private record for #181):

1. Give the read-only private dashboard its own read-only identity instead of
   the provider job's (which can write state and read the registry).
   *Approved by the owner on 2026-10-31; applied with the v0.3.10 deployment on
   2026-11-03 (read access to Watchtower storage and the mounted registry,
   no write access). Signed-in check passed the same day.*
2. Narrow the project's default compute identity, which can read every bucket.
   *Done 2026-11-03 (#181): it keeps build access and reads only the two
   build-source buckets; a probe build passed.*
3. Add an independent backup: object versioning with a noncurrent-version
   lifecycle rule, and/or a daily copy to another region or project.
   *Pending owner decision (#181); the approach is set out in
   [#190](https://github.com/clearparcel/GIS-Data-Watchtower/issues/190).*
4. Move the alert delivery configuration from a job environment variable to
   Secret Manager.
   *Done 2026-11-03 (#181): byte-identical value, readable only by the provider
   job's identity.*
5. Remove a retired integration account's Cloud Run viewer access.
   *Done 2026-11-03 (#181).*
6. Enable Data Access audit logs for Secret Manager and Cloud Storage.
   *Done 2026-11-03 (#181). Storage reads by the two read-only dashboards are
   exempt, so their routine polling doesn't drown out other access.*
7. Longer term, separate Watchtower from unrelated integrations in the same
   project. *Moved to its own ticket (#205).*
8. Housekeeping: disable superseded registry versions, remove October 4
   validation leftovers, and add lifecycle rules to build-source buckets.
   *Done 2026-11-03 (#181): superseded registry versions disabled (current
   version unchanged), the retired October preview service, bucket and identity
   removed, and build uploads now expire after 30 days.*
