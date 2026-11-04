# ClearParcel GIS Data Watchtower v0.3.13 (provider terms)

**Deployed November 3, 2026, from GERTKEN-PC** to the public and private
dashboards and the provider, public-publisher and weekly-digest jobs.
Deployment evidence is in the private deployment record, per the
[release policy](release-policy.md#what-a-public-release-record-may-contain).

## Scope

| PR | Change |
| --- | --- |
| [#201](https://github.com/clearparcel/GIS-Data-Watchtower/pull/201) | Provider terms view and digest follow-ups from the CRM (#185) |
| [#203](https://github.com/clearparcel/GIS-Data-Watchtower/pull/203) | Version bump to 0.3.13 |

## Source and checks

- Deployed source: merged `main` **`d1ee22d132018b9f0c686b306eb48b9e857609f2`**, tagged `v0.3.13`.
- CI passed on both PRs. The release-version preflight passed (v0.3.12 → v0.3.13).
- The image build passed every acceptance step, including the new
  `test_provider_terms.py`.
- #201 had an independent model review. Its findings were fixed before merge;
  see the review record on the PR.

## What changed in deployment

- **Provider terms, turned on with the owner's approval:**
  - The private CRM issued Watchtower its own read-only access credential,
    allowed one route only. Its secret was rotated by the owner and stored in
    Secret Manager without passing through chat, logs or the repository.
  - Only the private dashboard's identity and the digest job's identity can read
    that secret. Both gained three settings (terms URL, client ID, secret); see
    [configuration](configuration.md#provider-terms).
- The public dashboard, provider job and publisher job changed only their image.
  Schedules, the 23-hour spacing guard and the execution profile are unchanged.

## Acceptance

- The public site shows v0.3.13 and its health check passes. The private
  revision serves behind sign-in.
- **End-to-end:** a manual digest run succeeded and its digest included the
  provider-terms line (21 open inquiries, none overdue), so the CRM was read
  through the new credential.
- The provider job's first daily run on v0.3.13 is the next 5:00 AM Central run.

## Known limitations

- The cached terms copy lasts for the life of a dashboard instance; a new
  instance that starts while the CRM is down shows no terms until its first
  successful read.
- Overdue tracking needs follow-up dates on the CRM inquiries; none were set at
  release time.
