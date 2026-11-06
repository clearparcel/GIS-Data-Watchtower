# County directory contract, version 1

The offline implementation provides the public projection, versioned private
saves, explicit publication, and a readback status. Routes, migration,
attachments, and public dashboard and PDF integration remain subsequent work.

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

- `CountyDirectoryStore.save` takes a complete private draft, server-resolved
  identity, expected private revision, and opaque request ID scoped to the
  county. A missing record starts at revision 0. Each successful new save
  advances the private revision. The last 128 receipts per county support
  identical replay after newer saves and reject reuse with a different
  expected revision or draft. The editor must use a fresh ID for a new action.
- The save validates the public projection before the conditional private
  write. The same object holds the draft, receipt, and durable desired public
  revision and fingerprint. A private-only change advances only the private
  revision and preserves any pending public intent.
- Store each private county record separately. The sanitized public directory
  uses a separate object from both private storage and the routine monitoring
  aggregate. Each public county entry adds a public revision and publication
  time to the allowlisted content. The injected storage backends must use
  separate namespaces. Deployment must restrict public readers to the
  public object and reserve public writes for the county publisher.
- `publish` reconstructs the allowlisted content from the saved draft and
  verifies the fingerprint before writing. On a directory write conflict,
  reread and merge only the target county if its public revision is still
  older. Confirm only a readback with the desired public revision and the
  expected content. `read_public_directory` needs only the public backend.
- The future authenticated Apply handler should call `save` and then request
  `publish`. It must handle validation failure, revision conflict, private-only
  save, pending publication, and confirmed publication. Use the receipt's
  public revision to distinguish a confirmed save from a superseded one.
  A publisher or operator can call `publish` again after an interrupted save
  or readback. The store retains the desired revision and derives pending
  status from the public object. The offline store has no background worker.
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
authorization. Keep attachment objects and metadata in protected storage,
identified by opaque IDs. Bind each
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
levels. `tests/test_county_directory_store.py` exercises durable replay,
interleaved editors and publishers, restarts, ambiguous writes, and the
public JSON boundary with local storage. Later slices must exercise authorized
attachment reads, maximum standards tables, and privacy in integrated outputs
and logs.
