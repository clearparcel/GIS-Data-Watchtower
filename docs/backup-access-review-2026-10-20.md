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

Recommended changes (pending owner decision, none made):

1. Give the read-only private dashboard its own read-only identity instead of
   the provider job's (which can write state and read the registry).
2. Narrow the project's default compute identity, which can read every bucket.
3. Add an independent backup: object versioning with a noncurrent-version
   lifecycle rule, and/or a daily copy to another region or project.
4. Move the alert delivery configuration from a job environment variable to
   Secret Manager.
5. Remove a retired integration account's Cloud Run viewer access.
6. Enable Data Access audit logs for Secret Manager and Cloud Storage.
7. Longer term, separate Watchtower from unrelated integrations in the same
   project.
8. Housekeeping: disable superseded registry versions, remove October 4
   validation leftovers, and add lifecycle rules to build-source buckets.
