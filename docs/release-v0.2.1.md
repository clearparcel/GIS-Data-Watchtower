# GIS Data Watchtower v0.2.1 — Production release

**Deployment:** October 12, 2026 (America/Chicago). **Disposition: DEPLOYED AND VERIFIED**, with an explicit private sign-in acceptance limitation.

**Approved source:** [PR #71](https://github.com/clearparcel/GIS-Data-Watchtower/pull/71) merged into `main` as `9dbf6597f76aacf64e2ecbe55ba62d5757185921`. This is the exact commit baked into the release images. The release also carries earlier merged review corrections from PR #69.

## Public changes

- Replaced the lengthy Overview *Public data boundary* panel with a concise **About this project** section.
- Approved introductory wording begins: **GIS Data Watchtower is an open-source ClearParcel project**, and describes public dataset availability, source monitoring, county access research, and Minnesota GAC field-population insights.
- Included a short disclaimer and a **View on GitHub** link to this repository.
- Simplified all public footers to display **v0.2.1** rather than a build SHA and production/preview tags. Immutable image identity and internal build metadata are still retained.
- Introduced a read-only, fail-closed `scripts/check_release_version.py` preflight. The production v0.2.0 → candidate v0.2.1 check passed before release; after deployment, the unchanged candidate v0.2.1 correctly fails because a future release must increment its version.

## Tests, build, and provenance

- GERTKEN-PC working tree was clean and synchronized with the approved source commit.
- **359/359** strict unit tests, Python compilation, generated-status synchronization, and whitespace checks passed.
- GitHub main/PR CI and security checks passed for the approved source.
- Google Cloud Build **`c4be7733-8784-4d3b-ba7e-b1c06097af6d`**: SUCCESS, eight build/verification steps. The source context contained 53 packaged application inputs from a 54-file allowlist (a Cloud Build ignore rule removed one), about 2.2 MiB before compression.
- Release build config SHA-256: `702d5659f9367e11630278c70a018a6e7d40bb1eaf3e55019ade341510651396`. This build reused the earlier Cloud Build wrapper-copy pattern and validated private wrapper SHA-256 `786cccc200f4e27996a6983c7c05e0d034a88db22ae041360789bd511fb5e72a`.

## Immutable images, Cloud Run revisions, and rollback baseline

| Service | v0.2.1 revision — 100% Ready | Immutable image digest | Previous 100% revision retained |
| --- | --- | --- | --- |
| Isolated preview `gis-data-watchtower-public-v2-preview` | `00021-747` | `sha256:146a9fb9a9cd30dedf02e325db60ee4ffa150e813d19364eeb370a30b5e190f5` | `00020-qds` |
| Public dashboard `gis-data-watchtower-public` | `00016-dck` | `sha256:a38dbf5a589bfa02b705d9dde4c4b66a1a58a741e31b7ddbeed5fb6974e65990` | `00015-cjp` |
| Private/IAP dashboard `gis-data-watchtower-dashboard` | `00023-2h9` | `sha256:a39e57aaad3d39d095ac0bda63e44bb518d4767ba92be44891f785a8a59b3d0d` | `00022-pts` |

All three candidates were first created at **0% traffic**. The preview was promoted and checked before the public and private services. Each candidate revision was inspected for readiness and exact digest; independent checks confirmed the same non-image container spec, environment, service account, startup settings, ingress/security annotations, and command/arguments as the preceding revision. Cloud Run automatically refreshed only the client-generated revision nonce/operation ID, which were excluded from the non-image equivalence comparisons. Promotion then assigned 100% to the verified revision.

Prior release digests retained for rollback:

- Preview `00020-qds`: `sha256:07f9955913a34734ed7ae7f805143bea296da8306c73f69f4e333c57309e3268`
- Public `00015-cjp`: `sha256:44e6259bffe14b9be9e0b0264f1eff8a1f62c09d0c666ff1dc3f228f6b3e351f`
- Private `00022-pts`: `sha256:f763d514cf9aed63d5ded008a3fa6de424b31ce13eaf0df76e8e5841d3d3a176`

## Live acceptance and limitations

- Production: [gis-watchtower.clear-parcel.com](https://gis-watchtower.clear-parcel.com/). Overview and MN GAC returned HTTP 200, and `/healthz` returned HTTP 200 after promotion. The About message, GitHub link, and **version-only v0.2.1** footer rendered correctly.
- Isolated preview: Overview, Counties, and MN GAC rendered v0.2.1 with the same About message. Both current preview host aliases returned HTTP 200. Direct Cloud Run `/healthz` returned Google frontend 404, consistent with the previously recorded reserved-path behavior; it is not claimed as a successful direct preview health endpoint.
- Production and preview exports both returned **35 monitored source rows**, **87 county profile rows**, **350 parcel-source rows**, and valid Excel workbooks with 16 ZIP members and `xl/workbook.xml`. JSON exposed 35 source entries. Export schemas and page-level rendering remained consistent.
- Private anonymous requests to both previous and new Cloud Run hostnames returned **HTTP 302** redirect to `accounts.google.com`, preserving the existing sign-in boundary. **Authenticated private page rendering was not independently exercised**, and must not be claimed as passed.
- Existing schedules were read back unchanged and enabled: **`gis-watchtower-daily-providers`** at `0 5 * * *` and **`gis-watchtower-public-publish`** at `3,13,23,33,43,53 * * * *`, both in `America/Chicago`. No provider job, publisher job, provider registry, IAM binding, credentials, or source snapshot was intentionally changed for this UI release.

## Rollback

Keep the previous revisions intact. If a regression requires rollback, inspect live traffic and obtain the appropriate rollback authorization before issuing exact traffic changes. Previous revisions:

```powershell
gcloud run services update-traffic gis-data-watchtower-public --project dark-bit-503017-j7 --region us-central1 --to-revisions gis-data-watchtower-public-00015-cjp=100
gcloud run services update-traffic gis-data-watchtower-dashboard --project dark-bit-503017-j7 --region us-central1 --to-revisions gis-data-watchtower-dashboard-00022-pts=100
gcloud run services update-traffic gis-data-watchtower-public-v2-preview --project dark-bit-503017-j7 --region us-central1 --to-revisions gis-data-watchtower-public-v2-preview-00020-qds=100
```

Historical rollback information for the v0.2.0 baseline is preserved in [the October 11 release record](release-county-percentage-fix-2026-10-11.md). Provider-policy issues #1/#2, five-day observation study #20, and privacy-gated PostHog issue #50 remain independent follow-ups.
