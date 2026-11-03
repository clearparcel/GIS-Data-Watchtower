# ClearParcel GIS Data Watchtower v0.3.10 (coordinated release)

**Deployed to all four surfaces November 3, 2026, from GERTKEN-PC:** the
public and private dashboards and the provider and public-publisher jobs.
Deployment evidence (build, image digests, revisions, identities, policy IDs)
is in the private deployment record, per the [release policy](release-policy.md#what-a-public-release-record-may-contain).

## Scope

Changes on the deployed `main` after v0.3.9:

| PR | Change |
| --- | --- |
| [#157](https://github.com/clearparcel/GIS-Data-Watchtower/pull/157) | A declined county reply and a limited scope constrain dispatch |
| [#158](https://github.com/clearparcel/GIS-Data-Watchtower/pull/158) | Save a provider 429 backoff as soon as it is signaled |
| [#159](https://github.com/clearparcel/GIS-Data-Watchtower/pull/159) | Validate public output before replacing it; refuse publisher aliasing |
| [#160](https://github.com/clearparcel/GIS-Data-Watchtower/pull/160) | Future publication, check and report times are unknown, not current |
| [#161](https://github.com/clearparcel/GIS-Data-Watchtower/pull/161) | Truncated ArcGIS results and malformed state are not treated as complete |
| [#162](https://github.com/clearparcel/GIS-Data-Watchtower/pull/162) | Local build inputs, accessible link names, release discovery |
| [#163](https://github.com/clearparcel/GIS-Data-Watchtower/pull/163) | Update pyasn1 to 0.6.5 for four ASN.1 decoding advisories |
| [#164](https://github.com/clearparcel/GIS-Data-Watchtower/pull/164) | Write a shared embargo the moment a provider 429 arrives |
| [#165](https://github.com/clearparcel/GIS-Data-Watchtower/pull/165) | Prune settled alert-ledger records after 180 days |
| [#166](https://github.com/clearparcel/GIS-Data-Watchtower/pull/166) | Keep deployment evidence out of public release records; tag from v0.3.10 |
| [#167](https://github.com/clearparcel/GIS-Data-Watchtower/pull/167) | Version bump to 0.3.10 |
| [#177](https://github.com/clearparcel/GIS-Data-Watchtower/pull/177) | Configure engineering agent skills (docs only) |
| [#192](https://github.com/clearparcel/GIS-Data-Watchtower/pull/192) | Alert on tool failure and missing provider runs (provider-run watchdog) |

## Source and checks

- Deployed source: merged `main` **`6be9f09470314664835627275c4ee69ed06101bf`** (#192),
  tagged `v0.3.10`.
- CI: all seven required checks passed on that commit.
- Release-version preflight passed (live v0.3.9 → candidate v0.3.10).
- The private source-registry check passed.
- The image build passed every acceptance step, including new steps for the
  provider-run watchdog, the alert policies and the publisher. The private
  dashboard wrapper was carried over unchanged and hash-verified.

## Deployment boundaries

- Schedules, the 23-hour dispatch spacing guard, execution profiles and
  provider cadence are unchanged.
- Both dashboards were deployed without traffic, checked for unchanged runtime
  settings, then promoted. The jobs changed only their image; the publisher
  also gained `WATCHTOWER_WATCHDOG_WORKERS=cloud`.
- The private dashboard now runs under its own **read-only identity** instead
  of the provider job's (access-review recommendation 1, approved 2026-10-31):
  read access to Watchtower storage and the registry it already mounted, no
  write access.

## Provider-run alerting activated

Per the [activation runbook](provider-run-alerting-proposal.md):

- Three policies were created: tool failure (exit 3), no provider run reported
  in 26 hours (publisher watchdog), and publisher absent for 1 hour.
- The exit-3 log text and the `result="succeeded"` label were confirmed before
  relying on them.
- Synthetic tests opened both log-based incidents: a one-off provider-job run
  with a missing config file (exit 3 before any provider request, dispatch slot
  or receipt), and one publisher run with a 1-minute staleness window (normal
  publication).
- The original "provider job execution did not succeed" policy is disabled, not
  deleted; re-enabling it is the rollback.

## Acceptance

- The public site shows v0.3.10 and its health check passes.
- The first scheduled publisher run on v0.3.10 published normally; the watchdog
  checked the cloud worker and found it current.
- The owner's signed-in check of the private dashboard passed on the read-only
  identity: the overview rendered current data with no permission errors.
- Remaining: the first daily provider run on v0.3.10.
