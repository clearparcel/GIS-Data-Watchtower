# County editor sources in regular Watchtower checks

Prepared implementation; production registry access and rollout require approval.

The county editor can enroll a direct GIS service or data file in the existing
regular worker run. Public access links remain useful without enrollment. A new
check requires an explicit **Include this source in regular checks** selection,
open data access, reviewed use restrictions, a public provider terms link and
review date, confirmation that the terms allow recurring checks, and affirmative
county permission for the limited check. The permission response date and private
reference are required. A public permission link is optional.

Supported service links identify a numbered ArcGIS FeatureServer or MapServer
layer. Browser `f=json` and `f=pjson` parameters are removed from the polling
endpoint; filters and other query parameters are rejected. The worker reads
layer metadata and one record count. It does not query feature attributes or
geometry. Direct file links must end in `.zip`, `.gpkg`, `.geojson`, `.json`, or
`.csv`; their check uses HEAD for update headers without downloading the file.
Viewer pages, generic portals, service roots, credential-bearing URLs and
nonpublic URLs cannot be enrolled through this path.

## Save and check flow

1. The authenticated editor validates and saves its private county draft.
2. The server synchronizes that county's sources into the separate private
   object `county-directory/v1/monitoring/sources.json`. Each county entry carries
   its saved private revision and a bounded source list. Conditional writes
   preserve concurrent changes to other counties. Empty entries retain removals;
   an older request cannot restore a source after a newer save disables it.
3. The assigned `cloud` or `local` worker reads that object at the beginning of
   each normal check and includes its sources alongside the deployment registry.
   Existing profile assignments, dispatch spacing, terms holds, county stop and
   decline decisions, and provider 429 backoff still apply. A source approval
   cannot lift a packaged `hold-for-terms` decision.
4. The worker publishes observations through the existing aggregate merge. The
   public publisher includes source health, check dates, counts or file update
   details, and a fixed limited-check label. Parcel sources also join the county
   monitoring profile. Road and address sources appear in the public source list;
   they do not increase parcel monitoring coverage.

Save and status requests make no GIS provider requests. Enrollment takes effect
on the next assigned worker run; public results follow its next snapshot
publication. The saved private record owns enrollment even when publishing the
public directory needs a retry, so disabling a check does not depend on public
publication succeeding. A failed registry sync is shown separately and can be
retried with **Retry updates** or a subsequent authenticated status read.

Terms review and permission evidence remain private in both the draft and the
enrollment object. They are excluded from the public directory, worker results,
public snapshots and public exports. Ordinary source configuration cannot supply
the private enrollment approval.

A missing, unreadable, invalid or older enrollment registry never proves that an
administrator removed a source. Once local worker state includes enrolled
observations, a missing or older county entry stops the run before polling or
publication. The prior aggregate remains available and can become overdue.
Disable sources in the editor and publish the resulting worker retirement before
intentionally disconnecting registry access. Do not delete empty county entries.

## Deployment wiring

The hosted county editor writes the object in its existing private county bucket.
Provider workers opt in with **one** of these settings:

| Setting | Use |
| --- | --- |
| `WATCHTOWER_COUNTY_MONITORING_BUCKET` | The editor's private GCS bucket; only the exact enrollment object is read. |
| `WATCHTOWER_COUNTY_MONITORING_ROOT` | A local storage root, normally the synthetic or local editor's private root. |

The object key is fixed; neither setting changes the normal worker's state,
history or aggregate storage. Configure both worker profiles that administrators
may select. A local worker using GCS needs the optional `gcs` dependency and its
approved existing identity. Keep these settings off public dashboards and the
sanitized publisher, which read observations and do not need enrollment evidence.

Production IAM must grant the worker only `storage.objects.get` for this object.
Use a bucket IAM condition equivalent to:

```text
resource.name == 'projects/_/buckets/PRIVATE_COUNTY_BUCKET/objects/county-directory/v1/monitoring/sources.json'
```

Scope an object viewer role with this condition, or a custom role containing only
`storage.objects.get`. Do not grant unconditional access to the private county
bucket: it also contains contact drafts, correspondence and private attachments.
The worker needs no list or write permission on that bucket. The existing editor
identity continues to own conditional writes. Preserve its authentication,
scanner and public-directory permissions.

Rollout must deploy the editor and worker code, grant this object read, set the
worker registry location, and deploy the public publisher/dashboard code that
recognizes the limited-check label. These are approval-gated operational steps.
They do not require changing the existing provider schedule or running a provider
job immediately. After rollout, verify the next authorized regular run and public
publication, including worker provenance and the enrolled source's result.

## Offline validation

`tests/test_county_monitoring.py` runs the authenticated editor save, private
registry, real bounded adapter with mocked transport, aggregate publisher, public
publisher, source page and county profile entirely in temporary local storage.
It also covers permission/terms failures, worker assignment, CAS conflicts,
revision replay, retirement, malformed registries and privacy. No test contacts a
GIS provider. The admin and Node suites cover pending saves, removal retries and
the regular-check controls.
