# ClearParcel GIS Data Watchtower v0.3.12 (coordinated release)

**Deployed November 3, 2026, from GERTKEN-PC** to the public and private
dashboards, the provider and public-publisher jobs, and a new weekly-digest job.
Deployment evidence is in the private deployment record, per the
[release policy](release-policy.md#what-a-public-release-record-may-contain).

## Scope

| PR | Change |
| --- | --- |
| [#197](https://github.com/clearparcel/GIS-Data-Watchtower/pull/197) | Data freshness model and weekly digest (#183) |
| [#198](https://github.com/clearparcel/GIS-Data-Watchtower/pull/198) | Version bump to 0.3.12 |
| [#199](https://github.com/clearparcel/GIS-Data-Watchtower/pull/199) | Digest alert policy for a dedicated digest job (render script only; not in the image) |

## Source and checks

- Deployed source: merged `main` **`4b8f02b4b8378aa4a05234eed71b9d226acbb30b`**, tagged `v0.3.12`.
- CI passed on every PR. The release-version preflight passed (v0.3.11 → v0.3.12).
- The image build passed every acceptance step, including the new data-freshness
  and weekly-digest tests and a `weekly-digest --help` smoke check.
- #197 had an independent model review. Its findings were fixed before merge;
  see the review record on the PR.

## What changed in deployment

- The public dashboard, the private dashboard and both existing jobs changed only
  their image. Schedules, the 23-hour spacing guard and the execution profile are
  unchanged.
- **Weekly digest, turned on with the owner's approval:**
  - A dedicated Cloud Run job runs only `weekly-digest`, with fixed arguments.
    It uses the same image, registry and storage settings as the provider job,
    with no provider settings. It reads saved state and makes no provider requests.
  - A new schedule starts it on Mondays at 7:45 AM Central. The scheduler
    identity holds only run permission on that job, not permission to override a
    job's arguments.
  - A new informational alert policy emails the digest's subject and body to the
    existing alert channel ([configuration](configuration.md#weekly-digest)).

## Acceptance

- The public site shows v0.3.12 and its health check passes. The private revision
  started after its storage sync and serves behind sign-in. Publisher runs on the
  new image succeeded.
- **End-to-end digest test:** the new schedule was fired once, and the job was
  run once by hand.
  - Both runs succeeded and logged one digest line with no warnings: 24 sources,
    6 current, 2 stale, 16 with no publisher time, and no overdue checks.
  - The first run came before the new policy took effect. The second opened a
    digest alert whose extracted body (645 characters) arrived whole.
- The provider job's first daily run on v0.3.12 is the next 5:00 AM Central run.

## Known limitations

- Provider-terms follow-ups join the digest with the CRM-backed terms view
  ([#185](https://github.com/clearparcel/GIS-Data-Watchtower/issues/185)).
- Many sources have no publisher update time: imagery, WMS and some county
  services publish none. They show as "data age unknown" and are never treated
  as current.
- Sources checked only by the local worker learn no interval in the digest.
- The digest body is capped at 900 characters. Delivery was verified at 645.
