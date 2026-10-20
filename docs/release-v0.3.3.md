# GIS Data Watchtower v0.3.3 (provider job only)

**Deployed to the daily provider job October 20, 2026 (America/Chicago).**
The owner approved merging #115 and #116 and deploying through the normal
release process with run receipts enabled and alert delivery disabled (logged
dry run only). The public and private dashboards stay on v0.3.2 and the public
publisher job stays on v0.3.0. First scheduled-run evidence is pending.

## Scope

v0.3.3 changes only the `cloud-job` path used by the daily provider Cloud Run
Job:

- the disabled-by-default alert delivery ledger and transport candidate
  ([#115](https://github.com/clearparcel/GIS-Data-Watchtower/pull/115),
  merged `cb9a17a`);
- optional private run receipts and the delivery stage over them
  ([#116](https://github.com/clearparcel/GIS-Data-Watchtower/pull/116),
  merged `c6a360e`);
- the version bump
  ([#117](https://github.com/clearparcel/GIS-Data-Watchtower/pull/117),
  merged **`1b30dbda89cbcfc34a8298191c79bf288334e1fa`**, the deployed source).

Provider polling, storage, aggregation, transport and the runtime data files
are unchanged from the job's v0.3.0 image apart from the version.

## Source, authority and checks

- Post-merge CI passed for #115 and #116; PR CI passed all eight checks on
  #115, #116 and #117.
- Local release validation on GERTKEN-PC at `1b30dbd`: 660 tests, 3 platform
  skips, required Node behavior tests; compile and status sync passed.
- Mandatory live version preflight passed: v0.3.2 to v0.3.3.
- Bounded Claude reviews of #115 and #116 are recorded in their handoffs.

## Build

Cloud Build **`a590ab0b-7f9c-45cf-85d0-86a59de025e2`** passed all 7 steps from
a committed-only archive of `1b30dbd`, building only the `watchtower` image:

- image identity verified as `0.3.3` / full SHA / `production`;
- in-image synthetic acceptance against installed code: alert delivery (44),
  run evidence (23), alert routing (10) and operations triage (13) tests;
- CLI smoke check.

The build source upload was removed afterwards. Image:
`watchtower@sha256:18c77b2337ff0aa8ade8b2f1305fe795a7ead5974dcccc26e276fae447b80e80`
(registry prefix is deployment-private).

## Provider job update

Only the provider job was updated: its image moved from v0.3.0 to the digest
above, and two environment variables were added:

- `WATCHTOWER_RUN_RECEIPTS=1`;
- `WATCHTOWER_ALERT_DELIVERY_CONFIG`, private JSON with `delivery.enabled`
  false and complete routing (values are not recorded here).

Readback confirmed the image digest, the two values, and that arguments,
service account, secret mounts, all existing environment variables, retries
(0), task timeout (900 s) and task count are unchanged. The only other
differences were Cloud Run bookkeeping (client version, update nonce,
operation id, update time). The daily scheduler (`0 5 * * *`,
America/Chicago, enabled) is unchanged. The job was not executed; no provider
was polled. The job identity already holds object access on its own bucket,
so no IAM change was needed.

A separately approved Cloud Monitoring policy now emails the existing alert
channel when a provider job execution does not succeed.

## Pending first-run validation

At the next ordinary scheduled run, confirm as usual its exit code, source
results and aggregate provenance, plus the private `runs/receipts.json`
object and one `watchtower_alert_delivery` dry-run log line (or a
`watchtower_alert_pipeline_error` line to investigate). Delivery stays disabled;
enabling it, a test delivery and five ordinary cycles remain separate gates.

## Rollback

Restore the provider job image to v0.3.0
`watchtower@sha256:3df9fe0ce9373509ba1d80d1008e240274014626848c052cf8104eecd90f8f76`
and remove `WATCHTOWER_RUN_RECEIPTS` and `WATCHTOWER_ALERT_DELIVERY_CONFIG`.
The private receipt and ledger objects may be left in place. Rollback was
prepared, not exercised.
