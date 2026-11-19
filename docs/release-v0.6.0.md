# GIS Data Watchtower v0.6.0

Deployed November 19, 2026, from source commit `ecfd83206370e6a3bb8dc65bbe5dd51feaef1910`. This release includes the sixth-review fixes from [PR #285](https://github.com/clearparcel/GIS-Data-Watchtower/pull/285).

- The public dashboard can show healthy updates while withholding observations with unreliable clocks. A worker's first failure after a clock correction is visible. A rebuilt worker preserves the original measurement and its reporting history.
- A source whose retirement time is unknown can return only after a genuine provider check newer than the last accepted aggregate showing it retired. Unrelated sources continue to publish during recovery.
- Public records pass the field allowlist after recovery. Unrecognized worker assignments and blank check times no longer make sources appear current.
- ArcGIS service discovery retains the chosen layer's GAC evidence. Statistics batches reconcile excluded groups, malformed county participation rows preserve the last good evidence, and parcel completeness settings agree with preflight.
- Extent comparisons use the coordinate system of the bounds. Catalog dates and timestamps use consistent UTC precision, and implausible future history cannot extend a source's expected update interval.

## Verification and rollout

- The [release CI run](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/44508215036) passed. The local suite ran 1,334 tests with four skips. The installed production image ran 435 tests with six skips, and its application identity and source hashes matched the released commit.
- The private registry and aggregate passed compatibility checks. Synthetic staging checks exercised retirement, unrelated-source updates, recovery after a valid provider check, county publication and attachment handling.
- All three production services passed readiness checks at zero traffic before promotion. The public dashboard, internal dashboard and county editor now serve the release. The regular cloud worker, public publisher and weekly digest use the same image. Runtime settings, service access and scheduler configurations were verified after rollout.
- The first ordinary scheduled publisher execution succeeded. The public dashboard showed v0.6.0 with fresh publication health. Verification covered source observations, worker provenance, all 87 county profiles, the Aitkin PDF and the statewide workbook. The previous v0.5.9 revisions and image remain the rollback targets.
