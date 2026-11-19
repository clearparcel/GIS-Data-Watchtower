# GIS Data Watchtower v0.6.2

Deployed November 19, 2026, from source commit `f66846cdbd158d6cd66562ef7d8d41a69d0859f7`.

Watchtower asks curl to treat each configured provider URL literally. Braces and
brackets in the path now identify a single resource in both curl-preferred and
fallback requests. See [PR #291](https://github.com/clearparcel/GIS-Data-Watchtower/pull/291).

## Verification

The [release CI run](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/44568105045) passed. The installed production image passed
its application identity and source hash checks and ran 446 tests. The real-curl regression recorded exactly one GET for the literal configured path.

The public dashboard, internal dashboard, county editor, cloud worker, public
publisher and weekly digest use the verified image. Live checks covered worker provenance, source health,
all 87 county profiles, a county PDF and the statewide workbook. The v0.6.1
image and service revisions are the rollback targets.
