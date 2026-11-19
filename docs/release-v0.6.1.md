# GIS Data Watchtower v0.6.1

Deployed November 19, 2026, from source commit `908b80fc5575b8814e3301d0a3d4d81bf1ec280a`.

Watchtower honors a provider's HTTP 429 and `Retry-After` if curl is interrupted
after receiving the response headers. A saved worker run stops requests to the
affected host and retains the backoff across subsequent runs.
See [PR #288](https://github.com/clearparcel/GIS-Data-Watchtower/pull/288).

## Verification

The [release CI run](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/44545612142) passed. The installed production image passed
its application identity and source hash checks and ran 445 tests. In staging,
a fresh worker read the two-hour backoff from storage and made zero transfers
to the synthetic provider.

The public dashboard, internal dashboard, county editor, cloud worker, public
publisher and weekly digest use the verified image. Live checks covered worker provenance, source health,
all 87 county profiles, a county PDF and the statewide workbook. The v0.6.0
image and service revisions are the rollback targets.
