# County directory contract, version 1

The first implementation slice defines the editable public content and its
publication allowlist. The routes, persistence, migration, attachments, and
public consumers described below are integration requirements for subsequent
slices.

## County identity and public content

Resolve five-digit county FIPS, slug, and name from the existing county profile
identity. Only FIPS is carried in an editable record. The server supplies the
identity to `project_public_county` and checks that the record matches it. List
all 87 counties alphabetically even when they have no contacts.

| Section | Editable input | Public projection |
| --- | --- | --- |
| Contacts | Stable opaque `id`, `removed`, name, role, department, phone, email, website, source URL and verification date | Active contact fields only. An active contact needs a name or department. |
| Access | Independent `parcel_polygons`, `road_centerlines`, and `address_points` objects | Each has `classification`, `methods`, `restrictions`, and an optional `county_direct_note`. |
| Policy | `text`, optional official `url`, optional private attachment ID | Only the manually reviewed public text and URL. |
| Correspondence and history | Stable event and contact IDs, historical recipient, subject, sent and optional reply timestamps, notes, attachment IDs, read-only CRM reference, and editor audit history | Excluded. |

Each access classification is `open`, `fee`, or `unknown`. Open requires at
least one unique method from `mngeo_open`, `direct_rest`, `direct_download`,
and `other`. A method carries an evidence URL, date, and scope. Other also
requires a description. Non-open selections publish an empty methods list.
Restrictions use `unreviewed`, `reviewed_none`, or `restricted`. Restricted
requires public details and supports a source URL. Reviewed states can carry a
review date. Render reviewed-none as “No use restrictions recorded; confirm
provider terms.” Unreviewed carries no finding.

The editable road and address sections start Unknown with no methods and
unreviewed restrictions. Retain their existing published observations, counts,
standards, and evidence in the monitoring/research snapshot. Parcel migration
must preserve the evidence basis and county-direct scope, including cases
where a county fee and a separate open MnGeo product coexist. Record uncertain
items in an import exceptions report. The editor owns its directory fields.
Packaged research and monitoring retain their existing ownership, including
permission, terms holds, polling cadence, and worker provenance.

## Save and publication

- A county write uses a server-resolved identity, expected private revision,
  and opaque idempotency key scoped to the county. An identical replay returns
  the recorded result. Reject reuse with a different payload. Retain request
  results through the supported retry window, including after newer saves.
- Validate before the conditional private write. Save the private revision
  and pending publication intent in the same object. Private-only saves leave
  the public revision unchanged and preserve an existing pending intent.
- Store each private county record separately. The sanitized public directory
  uses a separate object from both private storage and the routine monitoring
  aggregate. Each public county entry adds a public revision and publication
  time to the allowlisted content. On a directory write conflict, reread and
  merge only the target county if its public revision is still older. Read
  back the result before confirming it.
- The authenticated status response distinguishes validation failure,
  revision conflict, private-only save, pending publication, and confirmed
  publication. Until confirmation, retain a retryable intent. If a write
  landed but readback failed, reconcile the stored revision on retry.
- Compose the public profile and PDF with one confirmed directory revision
  and one identified public monitoring/research snapshot. Key PDF caching
  by county, public revision, snapshot identity, freshness bucket when used,
  and template version. Escape editable text for the output format. Apply,
  status reads, and PDF downloads have no provider polling dependency.

## Attachments and private endpoints

The existing trusted-frontend dashboard requires read-only mode. Keep that
invariant. Add an independently authorized write path with verified
administrator identity, origin and CSRF checks, and bounded request bodies.
Cover directory reads, writes, status, uploads, and downloads with explicit
authorization. Keep attachment
objects and metadata in protected storage, identified by opaque IDs. Bind each
read to its county and record and verify authorization before returning data.
Start with the specification's proposed 20 MB per-file PDF limit. Validate
content server-side, quarantine until scanning succeeds, and keep failures and
pending files private. Confirm storage isolation and scanning before enabling
uploads. Record correspondence times with a UTC offset and display them in
America/Chicago. Recording a correspondence event never sends mail.

## Synthetic checks

`tests/test_county_directory.py` exercises all 87 identities, empty contacts,
an inactive contact, a direct fee alongside a statewide open product, missing
classifications, long policy text, and private markers at multiple nesting
levels. Later slices must exercise durable replay, simultaneous editors,
stale publishers, restart recovery, authorized attachment reads, maximum
standards tables, and HTML, JSON, CSV/XLSX, PDF, and log privacy.
