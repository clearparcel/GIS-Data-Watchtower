# County outreach permission — open pull request

Implementer: Cursor Grok 4.7. Branch `cursor/county-permission-checks-1ba9`.
Base: `main` at `f0984c3` (v0.3.8 status record). The branch head is the commit
that contains this handoff. No independent review has run on this head.

## Objective

Make automated checks match the outreach promises: county-direct services are
not checked without affirmative permission or a terms assessment other than
`not-assessed`; a stop request skips every source for that county; a
details-and-count permission does not run queries beyond service metadata and
a record count. Public pages say so, and do not show the pause as an error.

## What changed

The existing county monitoring object is the permission record. Optional
fields: `contacted_date`, `reply`, `scope` (`none`, `details-and-count`,
`full`), `stop_requested`. `CountyPermission` decides the new skips.
`hold-for-terms` remains the existing parcel rule, including its item-metadata
skip. The permission gate applies only to a server the county operates.
`stop_requested` also covers a direct query of the county's ArcGIS Online
hosted feature or map service. MnGeo, Commons, and ArcGIS Online item
metadata are outside both new gates.

The private registry is not in this checkout. The public direct-feed audit
`county_direct_gac_schema.json` is the configured set used to name sources
whose checks change. County-owned ArcGIS Online hosted layers are the
county's published service, but Esri operates the host, so they are not
treated as the county's own server for the permission gate. A stop request
does skip a direct query of that hosted service.

## Checks

Rebased onto `aa11702` (official product name, #154). Python 3.12.
`python -W error::ResourceWarning -m unittest discover -s tests -q`:
802 tests, exit 0, about 30 seconds. `compileall` for `clearparcel`, `tests`,
and `scripts` passed. `python scripts/sync_current_status.py --check` passed.
`git diff --check` passed. Node on this machine is 22.23.4, so the JavaScript
behavior tests skipped; CI runs those with Node 24.

Windows CI once failed `test_concurrent_invocations_send_each_event_once`
with `PermissionError` 13 (Access is denied) and passed on rerun. That is a
sharing violation: a reader still has the ledger open while another thread
replaces it, and `os.replace` / `open` were not retried. The lock and the
atomic replace now retry that Windows error. The concurrency test is unchanged.

## Gates

Merge and deployment require the owner's approval. This change does not poll
a provider, edit a schedule, or deploy. No independent review has run.
