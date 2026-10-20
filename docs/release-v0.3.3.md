# GIS Data Watchtower v0.3.3 (provider job only)

**Status: release candidate.** The owner approved merging #115 and #116 and
deploying through the normal release process with run receipts enabled and
alert delivery disabled (logged dry run only). This record is completed with
build, deployment and first-run evidence after rollout.

## Scope

v0.3.3 changes only the `cloud-job` path used by the daily provider Cloud Run
Job. It adds:

- the disabled-by-default alert delivery ledger and transport candidate (#115);
- optional private run receipts and the delivery stage over them (#116).

Provider polling, storage, aggregation, transport and the runtime data files
are byte-identical to the job's current v0.3.0 image apart from the version.
The public and private dashboards stay on v0.3.2 and the public publisher job
stays on v0.3.0; none of their code paths change.

## Planned rollout

1. Merge this version bump after CI.
2. Run `python scripts/check_release_version.py` (expect v0.3.2 to v0.3.3).
3. Build from a committed-only archive of merged `main`, following the v0.3.2
   Cloud Build pattern, with in-image delivery and run-evidence tests.
4. Update only the provider job image to the new `watchtower` digest and add
   `WATCHTOWER_RUN_RECEIPTS=1` plus a private
   `WATCHTOWER_ALERT_DELIVERY_CONFIG` whose `delivery.enabled` is false.
   Preserve every other job setting; do not change the schedule.
5. Do not execute the job. The next ordinary scheduled run is the first
   validation: confirm its exit code and sources as usual, the receipt object,
   and one `watchtower_alert_delivery` dry-run log line.

## Rollback

Restore the provider job image to v0.3.0
`watchtower@sha256:3df9fe0ce9373509ba1d80d1008e240274014626848c052cf8104eecd90f8f76`
and remove the two environment variables. The receipt and ledger objects are
private and may be left in place.
