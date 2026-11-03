# ClearParcel GIS Data Watchtower v0.3.11 (coordinated release)

**Deployed to all four surfaces November 3, 2026, from GERTKEN-PC:** the
public and private dashboards and the provider and public-publisher jobs.
Deployment evidence is in the private deployment record, per the
[release policy](release-policy.md#what-a-public-release-record-may-contain).

## Scope

| PR | Change |
| --- | --- |
| [#194](https://github.com/clearparcel/GIS-Data-Watchtower/pull/194) | Hosted private dashboard from the repository; aggregate alert status; complete run history |
| [#195](https://github.com/clearparcel/GIS-Data-Watchtower/pull/195) | Version bump to 0.3.11 |

## Source and checks

- Deployed source: merged `main` **`21eecb7536b72c9e741612b73ef8238476a47e56`**, tagged `v0.3.11`.
- CI passed on both PRs; the release-version preflight passed (v0.3.10 → v0.3.11);
  the private source-registry check passed.
- The image build passed every acceptance step, including the private-dashboard
  tests. The brand-asset and county-profile export checks that used to run on the
  separate dashboard image now run on the Watchtower image.

## What changed in deployment

- The private dashboard now runs the standard Watchtower image with the
  argument `private-dashboard` ([configuration](configuration.md#hosted-private-dashboard)).
  The separate dashboard image and its out-of-repo wrapper are retired. Its
  identity, environment and access are unchanged.
- The public dashboard and both jobs changed only their image. Schedules, the
  23-hour spacing guard and the execution profile are unchanged.
- The private dashboard has no default Cloud Run address, so it was promoted
  and then checked through its sign-in-protected address.

## Acceptance

- The public site shows v0.3.11 and its health check passes.
- The private revision started only after its first storage sync and serves
  behind sign-in.
