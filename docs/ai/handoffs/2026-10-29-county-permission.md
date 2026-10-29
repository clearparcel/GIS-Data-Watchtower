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

The existing county monitoring object in
`minnesota_county_parcel_access.json` is the permission record. Optional
fields: `contacted_date`, `reply`, `scope` (`none`, `details-and-count`,
`full`), `stop_requested`. `CountyPermission` in `parcel_access.py` is the
single decision point for the checker, item-metadata reads, alert scope, and
public labels. No parallel permission file was added. Current research rows
are unchanged, so every `not-assessed` county is treated as having no
affirmative permission.

Shared-memory ID `gis-data-watchtower` was not retrieved in this cloud
session. The October 20 monitoring-authority evidence in the repository is
the local source for the count of 14 not-assessed county-direct sources.
That private registry is not in this checkout, so the county list below is
every county whose terms decision is `not-assessed`.

## Checks

Python 3.12. `python -W error::ResourceWarning -m unittest discover -s tests -q`:
794 tests, exit 0, about 30 seconds. `compileall` for `clearparcel`, `tests`,
and `scripts` passed. `python scripts/sync_current_status.py --check` passed.
`git diff --check` passed. Node on this machine is 22.23.4, so the JavaScript
behavior tests skipped; CI runs them with Node 24.

## Gates

Merge and deployment require the owner's approval. This change does not poll
a provider, edit a schedule, or deploy. No independent review has run.
