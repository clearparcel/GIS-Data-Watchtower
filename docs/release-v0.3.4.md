# GIS Data Watchtower v0.3.4 (provider job only)

**Deployed to the daily provider job October 20, 2026 (America/Chicago).**
The owner approved merging the certifi fix (#119) and the v0.3.3 release record
(#118), then rebuilding and redeploying the provider job. The public and
private dashboards stay on v0.3.2 and the public publisher job on v0.3.0.
First scheduled-run evidence is pending.

## Scope

v0.3.4 is a security maintenance release for the provider job. Its only
change from [v0.3.3](release-v0.3.3.md) is certifi 2026.10.19
([#119](https://github.com/clearparcel/GIS-Data-Watchtower/pull/119), merged
`b28f43f`), which removes the emSign roots affected by
[GHSA-6q48-6c7w-9gw2](https://osv.dev/vulnerability/GHSA-6q48-6c7w-9gw2).
The advisory was published between CI runs on October 20 and failed the
dependency audit on main; the v0.3.3 image was built before it appeared.
Watchtower's provider polling uses the container's system CA store; certifi is
used by the Google client libraries for storage traffic.

The dashboards (v0.3.2) and the publisher job (v0.3.0) still carry the old
certifi pin. Rebuilding them is a separate coordinated release.

## Source and checks

- Deployed source: merged `main`
  **`64fd26b9fdda6ecfdaa00e502427a69d2dd41545`**
  ([#120](https://github.com/clearparcel/GIS-Data-Watchtower/pull/120)).
- PR CI passed all eight checks on #119, #118 and #120, including the
  dependency audit.
- Local release validation on GERTKEN-PC at `64fd26b`: 660 tests, 3 platform
  skips, required Node behavior tests; compile and status sync passed.
- Mandatory live version preflight passed: v0.3.2 to v0.3.4.

## Build

Cloud Build **`b8ddb5e9-1023-446f-8d8d-e44c667ca720`** passed all 8 steps from
a committed-only archive of `64fd26b`, building only the `watchtower` image:
identity `0.3.4` / full SHA / `production`; in-image alert delivery (44), run
evidence (23), alert routing (10) and operations triage (13) tests; an
in-image check that certifi is 2026.10.19; and a CLI smoke check. The build
source upload was removed afterwards. Image:
`watchtower@sha256:d5b097353e1af7dd5f77d342cec37a92b40370d81a1b89ba87f485546eaf8a31`.

## Provider job update

Only the provider job image changed, from the v0.3.3 digest to the one above.
Readback confirmed every other setting unchanged, including the v0.3.3
receipt setting (`WATCHTOWER_RUN_RECEIPTS=1`) and private delivery
configuration (`delivery.enabled` false), retries, timeout, service account,
secret mounts and the daily scheduler (`0 5 * * *`, America/Chicago,
enabled). The job was not executed; no provider was polled.

## Pending first-run validation

Unchanged from v0.3.3: at the next ordinary scheduled run, confirm its exit
code, sources and provenance, the private `runs/receipts.json` object, and one
`watchtower_alert_delivery` dry-run log line.

## Rollback

Restore the provider job image to v0.3.3
`watchtower@sha256:18c77b2337ff0aa8ade8b2f1305fe795a7ead5974dcccc26e276fae447b80e80`
(same environment), or to v0.3.0 as described in the v0.3.3 record. Rollback
was prepared, not exercised.
