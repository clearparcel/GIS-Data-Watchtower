# WT-15 sign-off record: October 16–20 provider runs

Prepared October 20, 2026. Extends the
[historical diagnosis](operations-diagnosis-2026-10-20.md) to the October 20
run and records what can and cannot be certified. Read-only: no provider was
polled, no job was executed for this record, and no schedule or control changed.
Exact execution IDs, source IDs and diagnostics stay in private evidence.

## Runs

| UTC run date | OK / warning / error | Non-OK sources | Next OK observation |
| --- | --- | --- | --- |
| October 16 | 32 / 0 / 1 | FEMA flood hazard: connection reset after 2 attempts | October 17 |
| October 17 | 31 / 1 / 1 | Beltrami direct parcels: ArcGIS query error 500 after 2 attempts; Hennepin 2026 imagery fingerprint warning | Beltrami October 18; Hennepin October 19 |
| October 18 | 32 / 1 / 0 | Hennepin 2026 imagery fingerprint warning (reverted) | October 19 |
| October 19 | 33 / 0 / 0 | none | — |
| October 20 | 32 / 0 / 1 | Todd direct parcels: provider wall-clock deadline exceeded after 2 attempts (about 61 s) | pending next ordinary run |

The October 20 row comes from the persisted worker history, as the earlier
rows did. Todd answered in roughly 0.3–0.7 s on every recorded run from
October 6 through October 19; October 20 is its first failure. No provider
rate-limit hold is active.

## What cannot be certified

The original per-run worker reports for October 16–20 are not recoverable.
Each run printed its report to stdout, but Cloud Logging returns lines written
in the same instant in an unstable order, so none of the five reports
reassembles as valid JSON (3,079–5,276 lines each). The persisted history
omits per-source check times and rate-limit/backoff flags. Under the
[triage rules](operations-triage.md), recovery for these runs therefore
cannot be formally certified, and the history is not used as a substitute.
The later OK observations above are recorded facts, not certified recovery.

From October 21 the provider job records a private receipt per run (exit
code, timing and minimized original report; see
[alert routing](alert-routing.md#scheduled-run-evidence)), so recovery and
failure are certifiable going forward, and alert delivery is enabled.

## Dispositions

| Item | Disposition |
| --- | --- |
| FEMA flood hazard (Oct 16) | Transient upstream connection reset. Accept as historical; keep existing retry and backoff controls; no change. |
| Beltrami direct parcels (Oct 17) | Transient provider query error. Accept as historical; no change. |
| Hennepin 2026 imagery (Oct 17–18) | Reversible upstream fingerprint drift; upstream explanation unresolved. Accept as historical; warnings remain intended behavior. |
| Todd direct parcels (Oct 20) | Single provider timeout after a long OK record. Do not change cadence, deadline or retries. Confirm recovery from the next ordinary run's receipt; if it fails again, delivery will email the owner and it is re-assessed then. |
| Uncertifiable Oct 16–20 recovery | Close the historical certification requirement as not achievable from retained evidence, superseded by per-run receipts from October 21. |
| Responsible operator | Shawn (owner and escalation contact). |

## Owner acceptance

On October 20, 2026 (about 4:30 PM CT) the owner accepted the FEMA,
Beltrami, Hennepin and historical-certification dispositions and the
responsible-operator assignment above, and chose to **keep Todd direct
parcels open** until a receipt-backed ordinary run shows it recovered. The
Todd item closes only on that evidence; no cadence, deadline, retry or
backoff change is authorized by this acceptance.
