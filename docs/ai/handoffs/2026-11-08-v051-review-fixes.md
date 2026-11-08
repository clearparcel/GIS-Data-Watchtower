# v0.5.1 review fixes

- Objective: correct the November 8 repository findings and deploy v0.5.1.
- Base: `8661beaf65a0017d2c47c97d300fa535567d76d5`.
- Branch: `codex/release-v051-review-fixes`; implementer: Codex.
- Includes existing PR #230 head `0c4396f8ef779d7418886c77f82c1c1938b55fc7`.
- Shared CCE tools/memory unavailable; no revision, hashes or freshness claimed.
  The owner explicitly approved a task-specific exception on November 8 for
  these fixes and deployment using independent security review and required CI.
- The owner requested correction and v0.5.1 redeployment. Production scheduling
  and unrelated owner-deferred infrastructure projects remain outside this work.
- Acceptance: security triggers rejected, legitimate operator/IAP behavior
  preserved, corrupted state retained safely, bounded storage operations,
  private atomic actor audit, full CI, immutable-image validation, staging and
  verified production identity with rollback retained.
- Actual review/check results and final SHA belong in the release PR and record.
  See `docs/review-remediation-v0.5.1.md` for finding and branch dispositions.
- Operational checkout contains unrelated dirty work. It is preserved; rollout
  uses an isolated checkout and private evidence outside the public repository.

Independent investigation and one candidate review were completed. The reviewer
found nested private snapshot validation still admitted renderer-crashing data;
that finding was reproduced and corrected with aggregate/history/archive
regressions. The final correction was verified by the implementer. Local full
suite: 1,081 passed, Node required, ResourceWarning errors; compileall, dependency
consistency, status/source-version check and diff check passed. CI and rollout
evidence remain in the PR/release record.

Release completed November 8: implementation PR #231 merged at `93f8a5c`,
artifact source `f7e82fe` (identical tree). Both candidate and main CI passed;
148 installed-image tests, source identity, runtime inventories, staging storage
and production public checks passed. All five application surfaces use v0.5.1;
IAM/runtime settings and schedules match baselines. See the release record for
verification limits. Manual publisher execution was rejected by automatic approval
review and was not performed; no provider job was invoked. Historical draft PRs
#209/#213 were closed, six obsolete branch tips archived before ref retirement,
and the fee feature retained as deferred.

The next normal scheduled publisher execution completed successfully on the
verified v0.5.1 image. No manual invocation or schedule modification was made.
