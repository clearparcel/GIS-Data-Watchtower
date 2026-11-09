# ClearParcel GIS Data Watchtower v0.4.1

Deployed to the public dashboard on November 6, 2026 (Central time).
Source: `365b747ade701e86e04c7292a7c7ce74f2a64aad`.

## Changes

- [#216](https://github.com/clearparcel/GIS-Data-Watchtower/pull/216) makes
  published county settings consistent across the county page, county list,
  map/overview profile, and export summaries.
- Retained parcel-access research is clearly labeled separately from the
  editable settings. Existing JSON research fields remain available, with
  provenance metadata; CSV and Excel add published access summaries.
- [#217](https://github.com/clearparcel/GIS-Data-Watchtower/pull/217) advances
  the visible application version to 0.4.1.

## Verification

The release-version preflight passed from 0.4.0 to 0.4.1. All required CI
checks passed on the release PR and [merged source](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/42323542416).
The local suite passed 1,011 tests with three platform skips and Node 24
required; compile, status synchronization, and whitespace checks passed.
The production image passed installed-container regression tests, its
source/version identity check, and a PDF-rendering check without network access.

Live Aitkin HTML, county-list summary, map/overview profile, JSON, CSV, Excel,
and PDF checks passed. The published county record and monitoring content
matched their predeployment hashes. The service runtime configuration and
access policy were unchanged. The public site displays v0.4.1.

Only the public dashboard changed. Private dashboard/editor/scanner services,
provider jobs, schedules, county records, monitoring permissions, and IAM were
not changed. The predecessor remains available for rollback; no rollback was
needed. Operational identities and artifact evidence are retained in the
private deployment receipt under the release policy.
