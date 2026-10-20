# GIS Data Watchtower v0.3.2

**Deployed October 20, 2026.** Both dashboards serve 100% traffic from the
verified v0.3.2 images. The private GAC county selector, standard/scope
navigation and standard-specific exports passed bounded authenticated acceptance.

## Source, authority and checks

The owner explicitly requested deployment of the reviewed selector fix.
[PR #108](https://github.com/clearparcel/GIS-Data-Watchtower/pull/108) merged as
**`3c078d8963228c3bfa6239acf7cb2aaf008045c8`**, the deployed application source.
Later release-receipt documentation commits are not deployed application code.
The accepted bounded CCE review of fix `eb5a4f9` found no actionable issues;
it reviewed supplied code evidence, not production. See the
[implementation handoff](ai/handoffs/2026-10-20-private-gac-selector.md).

- Local release validation: 583 tests, 3 platform skips, required Node behavior
  tests enabled; compile, status sync, whitespace and staged hygiene passed.
- PR CI [39445637973](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39445637973)
  passed all eight checks on head `284ca3bbcac1188629c0ee74d8f301a2ea7d75c5`.
  Postmerge CI [39446006969](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39446006969)
  passed on the deployed source.
- Mandatory live version preflight passed: v0.3.1 to v0.3.2.
- Cloud Build **`9d6fc776-b5f0-441f-94d6-47268856ca6e`** passed all 12 steps.
  Its committed-only archive bound the application identity to the source above.
  Both images passed identity, projection and route checks against installed
  image code. The actual migrated Handler passed synthetic checks with cloud
  bootstrap excluded; this did not trigger provider requests.

## Wrapper migration and immutable artifacts

The retained wrapper discarded GAC county, standard and view query parameters.
The guarded migration changed only the three GAC routes to call the shared
package dispatcher. Original wrapper SHA-256:
`786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.
Verified migrated wrapper SHA-256:
`bf6e99865f12cc3ee6dbe3968fe5e7211f1383aefa724319016a60bca2586cb0`.
The private image also passed wrapper import/attribute checks.

Registry prefix is deployment-private:
`<region>-docker.pkg.dev/<project-id>/<artifact-repository>/`.

| Surface | Immutable image | Revision | Traffic |
| --- | --- | --- | --- |
| Public | `watchtower@sha256:d4318b033153bf52ce732772989dfeb9387898bc3a89aff343ea22cf24ea5042` | `gis-data-watchtower-public-00035-gib` | 100% |
| Private | `dashboard@sha256:a30b43e5342053e27df95526fbac37be0134786fae5aa3c94af07e59fd1199a8` | `gis-data-watchtower-dashboard-00037-teh` | 100% |

Both candidates were Ready with zero traffic before acceptance. Promotion
rechecked captured predecessor traffic and non-image settings before each write.

## Bounded production acceptance

Public verification completed at **2026-10-20T15:28:04Z**. Ten routes covering
overview, counties, Cass, Brown, GAC, state, JSON, CSV, XLSX and health returned
200. Footers reported v0.3.2; applicable security headers retained hash-based
CSP without unsafe-inline and nosniff. Cass STATE_PIN showed Present / Scanned,
51,689 populated of 51,689 (100.00%) in county and GAC views. Saved provider
observation times/status and worker last-success values were unchanged.
The public tagged URL is unavailable under existing load-balancer-only ingress;
normal-domain checks were performed immediately after promotion instead.

Authenticated private candidate checks passed Cass/Douglas form selection,
Cass map navigation, parcel/address/road switching, retained county selection,
statewide scope, invalid-county rejection and the corrected Cass scan labels.
The actual candidate CSV download contained 73 road fields beginning ROADSEG_ID,
ROUTE_ID and ROUTE_SYS; JSON independently identified the road standard.
The browser download tooling took several minutes. Production traffic stayed
on the predecessor during that check.

After promotion, the normal signed-in private URL passed Cass form selection,
all three standards, statewide scope retaining Cass, and road JSON with the
same 73-field inventory. CSV was downloaded from the exact candidate image
subsequently promoted; no second post-promotion CSV download is claimed.
A bounded last-hour ERROR-log query for both new revisions returned zero entries.
These checks do not establish every county/route or future provider health.

At **2026-10-20T15:28:53Z**, independent readback confirmed both service IAM
policies and provider/publisher job specifications unchanged. Service runtime,
IAP/ingress and other non-image controls were also compared and preserved.
No schedules, source assignments, registry, credentials or provider state were
modified; no provider or publisher job was invoked. Jobs retain their v0.3.0
image. The previously observed Todd source error and multi-day operations
acceptance remain outside this selector release. Preview was not updated.

## Rollback

Retained v0.3.1 predecessors and captured allocations:

- Public: `gis-data-watchtower-public-00033-mak`, previously 100%.
- Private: `gis-data-watchtower-dashboard-00035-vom`, previously 100%.
- Immutable digests and source: [v0.3.1 receipt](release-v0.3.1.md).

On a release-caused failure, restore the affected predecessor allocation and
independently verify its normal URL. Rollback was retained, not exercised.
