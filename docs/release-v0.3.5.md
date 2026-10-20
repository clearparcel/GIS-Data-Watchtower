# GIS Data Watchtower v0.3.5 (coordinated release)

**Status: release candidate.** The owner approved completing the remaining
alert-delivery steps: a coordinated rebuild of every surface with certifi
2026.10.19, a test delivery, enabling delivery, and five ordinary cycles.
This record is completed with evidence after rollout.

## Scope

- All four surfaces move to one source: the provider job (from v0.3.4), the
  public publisher job (from v0.3.0), and the public and private dashboards
  (from v0.3.2). This removes the old certifi pin
  ([GHSA-6q48-6c7w-9gw2](https://osv.dev/vulnerability/GHSA-6q48-6c7w-9gw2))
  everywhere.
- New `watchtower alert-test` command for the owner-approved synthetic
  delivery test (see [alert routing](alert-routing.md)). It never polls a
  provider and uses its own ledger.

Dashboard, publisher and provider-polling code are otherwise unchanged from
the deployed releases.

## Planned rollout

1. Merge after CI; run the live version preflight (v0.3.2 to v0.3.5).
2. Build both images from a committed-only archive following the v0.3.2
   pattern (retained private wrapper verified by hash) with in-image tests and
   a certifi check.
3. Dashboards: deploy candidates at zero traffic, verify, then promote,
   preserving all non-image settings. Jobs: update images only.
4. Create the log-based alert policy for the provider job's delivery digests,
   run one synthetic failure and one recovery test, and confirm both emails.
5. Set `delivery.enabled` true. Ordinary daily runs then deliver; observe five
   cycles without changing provider cadence.
