# GIS Data Watchtower v0.3.5 (coordinated release)

**Deployed to every surface October 20, 2026 (America/Chicago); alert
delivery enabled.** The owner approved completing the remaining delivery
steps: a coordinated rebuild with certifi 2026.10.19, a synthetic test
delivery, enabling delivery, and observing five ordinary daily cycles. The
five-cycle observation runs October 21–25 and is recorded separately.

## Scope

- All four surfaces now run one source, removing the old certifi pin
  ([GHSA-6q48-6c7w-9gw2](https://osv.dev/vulnerability/GHSA-6q48-6c7w-9gw2))
  everywhere.
- New `watchtower alert-test` for owner-approved synthetic delivery tests
  ([#122](https://github.com/clearparcel/GIS-Data-Watchtower/pull/122)).

## Source and checks

- Deployed source: merged `main` **`48124dc47357d2857b13af998cfee22a241abcde`**.
  PR CI passed all eight checks; a bounded Claude review of #122 found no
  defects.
- Local release validation on GERTKEN-PC: 665 tests, 3 platform skips,
  required Node behavior tests; compile and status sync passed.
- Live version preflight passed: v0.3.2 to v0.3.5.

## Build

Cloud Build **`54708f9f-03be-4a06-a26e-b64b5267e5e7`** passed all 18 steps
from a committed-only archive of `48124dc`:

- both images: identity `0.3.5` / full SHA / `production` and certifi
  2026.10.19;
- private wrapper copied unchanged from the v0.3.2 image and verified by
  SHA-256 `bf6e9986…a2586cb0`; imports and dashboard attributes resolve;
- in-image tests: alert delivery (44), run evidence (23), alert routing (10),
  operations triage (13), alert test (5), county scan projection and private
  GAC routes on both images; actual private Handler acceptance; CLI smoke.

| Surface | Image | Predecessor |
| --- | --- | --- |
| Public dashboard | `watchtower@sha256:e5200d8c…99a55` (revision `gis-data-watchtower-public-00037-yoy`, 100%) | `00035-gib` (v0.3.2) |
| Private dashboard | `dashboard@sha256:9dd2d265…2d037` (revision `gis-data-watchtower-dashboard-00039-wif`, 100%) | `00037-teh` (v0.3.2) |
| Provider job | `watchtower@sha256:e5200d8c…99a55` | v0.3.4 `d5b09735…` |
| Publisher job | `watchtower@sha256:e5200d8c…99a55` | v0.3.0 `3df9fe0c…` |

## Rollout and acceptance

- Dashboards were deployed as zero-traffic candidates with all non-image
  settings and traffic verified, then promoted.
- Public: before (v0.3.2) and after (v0.3.5) acceptance passed on the normal
  domain: ten routes 200, v0.3.5 footer, hash-based CSP without unsafe-inline,
  nosniff, Cass STATE_PIN 51,689/51,689 (100.00%), and provider observations
  unchanged during rollout.
- Private: signed-in checks on the candidate and again on the normal URL
  after promotion: Cass parcels with STATE_PIN 100%, road and address
  standards, statewide scope, road JSON, invalid county 400, overview 200.
- Jobs: images only; all other settings and both schedulers unchanged. The
  publisher's first v0.3.5 run succeeded.

## Alert delivery

- A log-based alert policy routes delivery digests from the provider job to
  the existing email channel (5-minute notification limit, 30-minute
  auto-close). A separate policy already emails on provider-job failure.
- Synthetic tests ran as one-off provider-job executions with only the
  arguments overridden (`alert-test`); no provider was polled. The failure
  digest was emailed about 40 seconds after it was written and the recovery
  digest about 100 seconds after; both carried the full digest body and the
  `TEST - ` prefix. The recovery email arrived while the first alert was still
  open, as a follow-up notification. Both events were acknowledged in the
  private test ledger after mailbox receipt was verified.
- Delivery was then enabled on the provider job (`delivery.enabled` true,
  `structured_log`). Routing and all other settings are unchanged; the job was
  not executed. Ordinary daily runs now deliver.

## Rollback

- Delivery only: set `delivery.enabled` false (or remove the variable) and
  disable the digest policy. Ledger and receipts may stay.
- Dashboards: restore the predecessor revisions above to 100%.
- Jobs: restore the predecessor images above.

Rollback was prepared, not exercised.
