# Versioned public UI release — October 7, 2026

After reviewing the isolated preview, the user explicitly approved production deployment. The public website now serves product commit `cf06a07cc60265bea402aaf5a8fbf42c0009614c` with the approved [browser feedback changes](browser-feedback-2026-10-07.md) and application identity **v0.1.0.dev0 · build cf06a07 · Production**. The full commit is available in the footer tooltip. The package remains pre-1.0; this deploy does not create a semantic release tag or merge PR #47.

## Build and rollout

Cloud Build `1d601471-525e-4655-8fb1-d770dee85798` succeeded from a clean tracked archive of the same product commit validated in preview. Only the baked build environment changed from preview to production. The build asserted the installed package version, full source commit, environment and rendered footer.

Production public revision `gis-data-watchtower-public-00009-tbt` is Ready at 100% traffic, pinned to `sha256:a54d7a123b4ba4b5dfd15a9d406d08b311b27b0006cd64c19af825a9c4e2959f`. Prior revision `gis-data-watchtower-public-00008-lzd` remains available for rollback. The candidate was created without traffic and verified before promotion. Verification normalized Cloud Run's traffic `latestRevision` marker and generated revision-only container name; runtime settings otherwise matched the prior serving revision exactly, except image.

[Open the live site](https://gis-watchtower.clear-parcel.com/).

## Verification and scope

- Fresh local validation passed 254 ResourceWarning-strict tests, compilation and whitespace checks. The product commit's six CI jobs passed.
- Overview, county index, Aitkin and MN GAC pages returned 200 with the Production identity and full commit tooltip. The overview rendered the clarified check/publication labels and mandatory-field metric; Aitkin displayed 42,996 records. Browser verification confirmed the visible footer with no horizontal overflow.
- `/healthz` returned 200; `/refresh` POST remained 405. The public state passed forbidden-field validation. Its 35 stored OK sources, worker provenance (cloud 31, local 4), source observations and worker observations matched the pre-release snapshot. This is stored monitoring evidence, not a new provider-health check.
- Production public runtime pod settings, IAM and ingress were preserved. Preview `00011-hkl` and private dashboard `00013-fnn` specifications, revisions, traffic and IAM were unchanged. Jobs, schedules, provider holds and data destinations were not modified. No provider or publisher job was executed, and no production data write was performed.
- Task-owned Cloud Build source upload and local build scratch were removed after verification. The prior preview task's separately documented policy-blocked cleanup remains pending.

The stale provider-observation pipeline remains a separate operational follow-up. The existing sanitized publisher continues its normal schedule; publishing fresh UI code does not refresh GIS-provider observations.
