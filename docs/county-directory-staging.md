# County directory staging acceptance

The hosted editor runs as a separate Cloud Run service. The existing hosted
private dashboard keeps its read-only command and identity. The county editor
receives neither monitoring credentials nor the provider registry.

## Candidate images

Build the application from the exact candidate commit with
`WATCHTOWER_BUILD_ENVIRONMENT=preview` and the full
`WATCHTOWER_BUILD_REVISION`. Build the scanner with
`docker build -f Dockerfile.county-scanner`. Record both image digests and
use those digests for staging. Run application smoke checks with `--help`,
`county-admin-hosted --help`, and a synthetic fixture. The image's default
command runs the provider job, so always specify the intended command.

## Staging bindings

Use a dedicated staging editor hostname behind IAP and a separate Cloud Run
service. Verify that the app's configured hostname is the Host forwarded by
the proxy and that direct service access is restricted. Use the signed JWT
audience from the configured IAP resource. Grant IAP access to the staging
editors and set the same editors' exact signed subject identifiers in the app.

| Setting | Value to supply |
| --- | --- |
| Editor container argument | `county-admin-hosted` |
| `WATCHTOWER_COUNTY_ADMIN_ORIGIN` | Exact `https://` staging origin without a trailing slash |
| `WATCHTOWER_COUNTY_ADMIN_IAP_AUDIENCE` | Exact Cloud Run service or load-balancer backend audience |
| `WATCHTOWER_COUNTY_ADMIN_SUBJECTS` | Comma-separated signed IAP subject IDs |
| `WATCHTOWER_COUNTY_ADMIN_CSRF_SECRET` | Secret Manager-backed base64 encoding of 32 random bytes, shared by the editor replicas |
| `WATCHTOWER_COUNTY_PRIVATE_BUCKET` | Staging-only private records and attachment bucket |
| `WATCHTOWER_COUNTY_PUBLIC_BUCKET` | Separate staging-only sanitized directory bucket |
| `WATCHTOWER_COUNTY_SCANNER_URL` | Exact staging scanner service HTTPS `run.app` URL, used as the ID token audience |
| Scanner service arguments | `county-scanner-hosted` for the application container |
| Scanner sidecar | Pinned county scanner image in the scanner service instance, TCP bound to `127.0.0.1:3310` |
| Public dashboard setting | Set only `WATCHTOWER_COUNTY_PUBLIC_BUCKET` for the directory. Supply a separate sanitized synthetic aggregate through its existing configuration. |

Give the editor service account object read and conditional create/replace
permissions on the private records, private attachments, and sanitized directory
objects only. Grant that account Cloud Run invoker on the scanner service.
Require IAM on the scanner service and remove anonymous invoker bindings.
Run the scanner and its sidecar under a separate account without county
storage access. The editor sends the bounded file bytes with a metadata-issued
ID token and accepts only a clean or rejected response. The scanner service
does not persist file bytes.

The staged public dashboard receives read access to the directory
object and the synthetic public monitoring aggregate. Apply bucket-level public
access prevention and keep the attachment bucket out of public service IAM.
Give the scanner sidecar network access to the signature update service. It
needs neither a bucket mount nor an HTTP ingress port. Check attachment volume
retention and deletion before storing real records.

The editor accepts a scan verdict only when the daemon reports a signature
database at most 72 hours old. Before opening the HTTP listener, the scanner
waits up to 90 seconds for a clean empty-stream scan with current signatures;
each readiness attempt has a two-second deadline. The existing TCP startup
probe therefore cannot pass while ClamAV is still loading. The editor allows
120 seconds for the scanner response, covering startup plus the bounded scan.
A failed startup exits without accepting traffic. Scanner signature updates or scan
failures leave files in quarantine. The Retry scan control is available for
linked pending attachments. Encrypted and over-limit files produce a rejection.

## Verify before promotion

1. Download a recent public `/snapshot.json` export from the authoritative
   deployed dashboard and run `watchtower county-migration-verify --snapshot
   <saved-public-export>`. Record the snapshot and seed hashes. A mismatch
   lists the county and field for reconciliation. Keep observation differences
   separate from evidence used to seed access classifications.
2. Verify direct and unsigned requests fail, a permitted IAP editor succeeds,
   a signed non-editor fails, and a cross-origin Apply fails. Confirm separate
   service identities and test that the public reader cannot read private
   objects.
3. Apply synthetic contacts and policy edits. Exercise conflicting writes,
   identical request replay, a pending publication and retry, and revision
   readback. Check the public HTML, JSON, CSV, XLSX, and PDF for private
   sentinels. Measure the already-open public county refresh.
4. Check a clean synthetic PDF, an EICAR fixture, and a stopped or stale
   scanner. Verify clean files download only through the editor and that
   rejected and pending files stay unavailable after restart.
5. Record required CI, image digests, staging results, and rollback. Roll back
   traffic to the last tested service revision while retaining the versioned
   private and public objects for recovery. The existing aggregate publisher
   and provider schedules remain separate from this feature.

Official references cover [IAP signed headers](https://cloud.google.com/iap/docs/signed-headers-howto),
[Cloud Run containers](https://docs.cloud.google.com/run/docs/configuring/services/containers),
[service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service),
and [ClamAV container operations](https://docs.clamav.net/manual/Installing/Docker.html).
