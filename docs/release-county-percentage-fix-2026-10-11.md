# GIS Data Watchtower v0.2.0 — County percentage clarity deployment

Deployment date: **2026-10-11** (America/Chicago). Production environment: Google Cloud project `dark-bit-503017-j7`, region `us-central1`.

## Source and approval

The user explicitly approved merging [PR #67](https://github.com/clearparcel/GIS-Data-Watchtower/pull/67) and proceeding with a guarded production deployment. PR #67 merged as `bbc364d29398a7bc19dfb235c23cbb24d3f08712` on `main`. The package version remains **v0.2.0**, with the full source commit baked into all new dashboard images. The pre-release audit is [preserved separately](county-percentage-audit-2026-10-11.md).

The published county comparison now defaults to population across **all 91 MN GAC parcel fields** rather than just the seven Mandatory fields. The seven-field rate remains visible and selectable. Address and Road retain the Mandatory-only routine metric. Shared percentage classes are `p<30`, `30<=p<50`, `50<=p<=70` and `p>70`; missing/invalid values remain distinct from zero. Neither population percentage is a compliance grade.

## CI, build and integrity

- Exact merged source validated on GERTKEN-PC: **343/343** strict offline tests, `compileall`, generated-status synchronization and Git diff checks passed.
- PR #67 CI: **7/7** Linux/Windows/security jobs passed on the approved feature commit before merging.
- Regional Cloud Build **`df3c86dc-dc0d-4a3d-af3c-da30874d2d04`**, SUCCESS at `2026-10-11T20:46:16Z`.
- Its context contained **53 tracked public application files**, plus the temporary build manifest, without private configuration or test scratch.
- Eight build/verification steps passed: preview and production package identity, exact `bbc364d...` revision and environments, and the private authenticated derivative. The latter reused the already-deployed private image's observation-only `/app/dashboard_app.py` wrapper and verified SHA-256 **`786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`**.

## Immutable artifacts, revisions and rollback

| Service | New 100% Ready revision | New immutable digest | Previous revision retained |
| --- | --- | --- | --- |
| Public dashboard | `gis-data-watchtower-public-00015-cjp` | `sha256:44e6259bffe14b9be9e0b0264f1eff8a1f62c09d0c666ff1dc3f228f6b3e351f` | `gis-data-watchtower-public-00014-jsr` |
| Private/IAP dashboard | `gis-data-watchtower-dashboard-00022-pts` | `sha256:f763d514cf9aed63d5ded008a3fa6de424b31ce13eaf0df76e8e5841d3d3a176` | `gis-data-watchtower-dashboard-00021-hr8` |
| Isolated public preview | `gis-data-watchtower-public-v2-preview-00020-qds` | `sha256:07f9955913a34734ed7ae7f805143bea296da8306c73f69f4e333c57309e3268` | `gis-data-watchtower-public-v2-preview-00019-x5b` |

The retained predeployment images are, respectively: public `sha256:d613d2bbbd57ed25b08e01dbe4a87be9bed5112343838f95e90682aee0c4833d`; private `sha256:24002f249e2808a463e699a14803de1270bb898838d82d6dc160911e63a4dae3`; preview `sha256:88fda5f0f55d4d7c22705039a8b93b6b4f1a28a5c2e1e831f9f51386bb21a5f1`.

Each candidate revision was initially deployed at **0% traffic**. Ready state, exact image digest, ingress/invoker settings and a SHA-256 comparison of the complete non-image service spec against the predeployment baseline passed before promotion. Each service was then promoted to **100%**; subsequent checks reconfirmed all conditions, unchanged non-image specs, and rollback revision identity.

## Production acceptance

- Public URL: **https://gis-watchtower.clear-parcel.com**. `/healthz` returned `status: ok`. The footer reports `v0.2.0 · build bbc364d · Production`.
- Public parcel county, statewide, Address and Road pages passed HTTP 200 and content checks. Aitkin: **33.19% all-field**, **57.14% Mandatory**, **43,024 parcel records**. Fillmore: **15.24% all-field**, same **57.14% Mandatory**.
- The public observation parity comparison returned **zero differences** for 35 source status/check/success records and 59 county parcel rate/count records. The 91-field scan is intact. The observed **34 OK / one warning / zero errors** remains unchanged.
- Exports passed: **87** county CSV rows; **91** MN GAC parcel field CSV rows; a **1,111,212-byte** XLSX opens as a valid ZIP with 16 entries and `xl/workbook.xml`.
- Real Chrome automation against production passed at **1440px desktop** and **390px emulated mobile**: county selection, source-accurate all-field and Mandatory labels and ring values, 87 interactive SVG counties, legend cutoffs, equal map/pane heights, no horizontal overflow and **zero uncaught JavaScript exceptions**.
- Private anonymous access continues to return **HTTP 302** redirect to `accounts.google.com`. The private service remains Ready with its audited wrapper and original auth/security configuration. **Signed-in private rendering was not exercised**; that is an explicit acceptance limit.
- Enabled schedules remain `0 5 * * *` daily provider polling and `3,13,23,33,43,53 * * * *` sanitized publishing, both in `America/Chicago`. No Cloud Run Job image, scheduler, worker source registry, IAM/IAP policy, credentials, DNS, raw parcel data or production snapshot was changed by this UI release. No GIS provider job or publisher job was manually triggered.

## Rollback and remaining gates

If a regression requires reversal, first verify the active revision and receive the appropriate rollback approval. The retained revisions can be restored independently without changing data or schedules:

```powershell
gcloud run services update-traffic gis-data-watchtower-public --project dark-bit-503017-j7 --region us-central1 --to-revisions gis-data-watchtower-public-00014-jsr=100
gcloud run services update-traffic gis-data-watchtower-dashboard --project dark-bit-503017-j7 --region us-central1 --to-revisions gis-data-watchtower-dashboard-00021-hr8=100
gcloud run services update-traffic gis-data-watchtower-public-v2-preview --project dark-bit-503017-j7 --region us-central1 --to-revisions gis-data-watchtower-public-v2-preview-00019-x5b=100
```

Existing operational follow-ups stay open: provider use/terms (#1/#2), the incomplete five-day cloud observation study (#20), dormant privacy-gated PostHog analytics (#50), and any separately triaged CodeQL alerts. The Windows offline suite showed intermittent temporary-file permissions errors in separate runs: an earlier atomic replacement during snapshot replay and, during this documentation reconciliation, `test_local_uploads_use_independent_temporary_files` reported one `PermissionError`. The targeted regression module subsequently passed **29/29**, and the full ResourceWarning-strict suite passed **343/343** on rerun. No storage implementation was changed speculatively; investigate file-lock/antivirus timing separately if the issue recurs.

**Release disposition: DEPLOYED AND VERIFIED**, with signed-in private-IAP rendering unverified. The GitHub [PR #67 release evidence comment](https://github.com/clearparcel/GIS-Data-Watchtower/pull/67) is an additional immutable discussion record.
