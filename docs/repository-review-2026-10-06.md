# Repository review — 2026-10-06

Subsequent user-approved merge and deployment: the reviewed fixes were released from merged commit `32852a8`. See [release verification](release-2026-10-06.md). The review-stage statements below describe the earlier, undeployed audit snapshot.

This review covers repository security, correctness, documentation and GitHub hygiene. It made no provider requests, live exploit attempts, deployment or production changes, merge, main push or scheduling change. The latest recorded preview `00007-zfh` serves `5aac504` and predates these fixes.

## Baseline and implemented fixes

The sealed static scan of `22b344b6dad564326f14a98a5fda331368a52b6e` reviewed 62 tracked files and established one medium and two low findings; it established no critical/high finding. That original report remains a baseline snapshot, not a claim about this later head or a security guarantee.

- `1d83322`: bounded public accepted sockets; validated-address redirect binding with original Host/TLS SNI/certificate verification; total provider request deadlines; optional/fallback HTTP 429 propagation and HTTPError closure. Also restored an existing test hidden by a duplicate method name.
- `3fe4096`: disabled curl configuration for every command; preserved a proven final 429 even after transfer failure, oversized/truncated responses or timeout. Redirects remain off by default, protected hops reject effective proxies, and private redirected hosts require explicit existing allowlisting.
- `e357096`: reporting freshness follows report/check timestamps rather than old success; historical source success and source health remain separate. Zero records/fields render as zero. Publisher scratch directories are unique and cleaned after success, validation failure and upload failure, including concurrent invocation. Both GCS clients share process application default credentials; deployment owns service identities.

A fresh Task 1 review identified two additional issues beyond the sealed three-finding baseline: P1 initial curlrc could bypass configured redirect/TLS controls, and P2 a proven HTTP 429 could be discarded after nonzero transfer exit. Both were fixed in `3fe4096` and passed scoped rereview.

The latter reporting, display, rate-limit, test-discovery and scratch defects include correctness issues beyond the calibrated baseline security findings. No dependency was added. Documentation/hygiene reconciliation is committed separately on the same feature branch.

## Verification

Task 1 ran the full ResourceWarning-strict suite: 219 tests passed before its follow-up. Its follow-up ran 29 transport and 95 monitor tests. Task 2 ran 69 targeted tests. These used local fixtures, mocks and loopback sockets, never real providers.

Combined final local validation on 2026-10-06: `python -W error::ResourceWarning -m unittest discover -s tests -q` passed **230 tests in 8.753s**. `python -m compileall -q clearparcel tests` passed. Local Markdown validation checked **86 references across 22 files**, including local target files and anchors, with no failures. `git diff --check` passed after whitespace cleanup. The staged diff was inspected for private material before the documentation commit.

The offline research JSON semantic screen checked structure and invariants; it is not independent verification of every research assertion. Dated deployment/browser and provider-policy evidence is retained in [status history](status-history-2026-10-06.md), [detailed status history](current-status-history-2026-10-06.md), [deployment history](google-cloud-deployment.md) and [access audit](county-parcel-data-access-audit.md).

## GitHub maintenance recorded by the root review

Issue [40](https://github.com/clearparcel/GIS-Data-Watchtower/issues/40) was closed after all original 35 classifications were verified complete. Issues [1](https://github.com/clearparcel/GIS-Data-Watchtower/issues/1), [2](https://github.com/clearparcel/GIS-Data-Watchtower/issues/2) and [20](https://github.com/clearparcel/GIS-Data-Watchtower/issues/20) remain open; issue 20's old counts were labeled historical. Active PRs [39](https://github.com/clearparcel/GIS-Data-Watchtower/pull/39) and [42](https://github.com/clearparcel/GIS-Data-Watchtower/pull/42) remain. The remote inventory contained only main and two active feature branches; no stale branch deletion was warranted.

User-approved main protection was applied and read back: PRs required, zero required approving reviewers, six strict GitHub Actions matrix checks, resolved conversations, admins enforced, force push and deletion blocked. Secret scanning, push protection and Dependabot updates were enabled, with empty alert results. Code scanning returned 404/no analysis available; this does not prove absence of vulnerabilities. Historical preview heads had successful Actions runs; CI for the final repository-review head must be checked after its feature push. No final-head CI success is claimed here.

## Limits and operational boundaries

Only local Windows/Python 3.14 execution was available in this review; CI covers Python 3.12–3.14 on Windows/Ubuntu. Native DNS calls cannot be forcibly cancelled: at most eight process-local daemon resolver workers retain capacity until completion, with saturated callers failing closed. Socket deadlines interrupt blocked I/O, not CPU computation. Protected redirects cannot prove peer binding through an effective proxy and fail closed. Curlrc settings are unsupported; initial environment proxy behavior remains supported.

The public service must read sanitized public state only. Publisher cadence is independent of provider cadence. Eleven research holds and provider restrictions remain; neither technical reachability nor an offline schema check authorizes unattended monitoring. Multi-day hybrid validation and explicit approval are still required before authoritative cloud provider scheduling. No live coverage, current service health, new deployment validation or unconditional security assurance follows from this repository review.

## Final branch review and documentation clarification

The independent whole-branch review on 2026-10-06 examined exact head `14be516608ef00520eb7acac623f17293881bba9` against the sealed baseline. Code quality/correctness passed; the changed security code had no new substantiated actionable vulnerability. Its sole P3 finding was ambiguous inherited SECURITY guidance referring to the public renderer's storage access as the shared aggregate. This documentation clarification now specifies read-only access only to the sanitized destination; private source-aggregate read and sanitized destination write access belong to the separate publisher, with neither process receiving provider registry/credentials. This was a guidance defect, not evidence of a live misconfiguration. Scoped rereview and final feature-head CI remain pending; no deployment or provider request occurred.
