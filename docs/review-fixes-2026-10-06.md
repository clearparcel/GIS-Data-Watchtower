# Manual review follow-up fixes

These corrections are submitted for review on a feature branch. They have **not been deployed**. The recorded application release remains `32852a8`; deployment facts live in [current status](current-status.md). This follow-up used manual code inspection and offline regressions, without Deep Scan or GIS-provider requests.

## Corrected findings

| Finding | Correction |
| --- | --- |
| Late worker reports overwrite newer health/heartbeats | Validate report timestamps; ignore duplicate/older worker reports; preserve newer source records and fleet time. |
| Built-in private refresh ignores source profiles | Require a valid profile for assigned sources and pass it to the worker filter. |
| Overlapping public publishers replace newer observations | Read destination generation and use conditional uploads, retrying conflicts and rejecting timestamp rollback. |
| Removed sources remain active indefinitely | Complete reports retire omitted sources belonging to that worker; filtered/legacy reports remain additive. |
| Run-lock age permits overlapping checks/old-owner deletion | OS-owned persistent lock files; age never steals ownership; closing only releases the owning descriptor. |
| Concurrent local writes collide on shared scratch | Unique temporary files beside the destination, followed by atomic replacement. |
| Crashed local CAS writer leaves a blocking directory | OS locks release on process exit; legacy directory locks fail closed pending reconciliation. |
| WMS/WFS URLs corrupt existing query parameters | Parse/merge queries, replace protocol parameters case-insensitively, preserve provider selectors and remove fragments. |

Worker timestamps assume reasonably synchronized clocks. Future timestamps are not silently rewritten; investigate clock problems before forcing state changes. Same-time reports are idempotent; distinct observations require distinct timestamps.

## Validation

The original 230-test baseline passed. Eleven initial regressions reproduced the defects before implementation. Additional regressions cover invalid timestamps, duplicates and retirement, component-level publication ordering, profile validation, lock ownership, legacy-directory refusal, same-worker overlap and bounded publication retries. Independent bounded code review identified an additional mixed-writer gap: unconditional local uploads could interrupt a CAS write. A regression reproduced that gap and both local write APIs now share the same lock. Process-termination and event-controlled concurrency tests run against the actual local backend. Required validation includes the full ResourceWarning-strict unit suite, compilation and whitespace checks, plus hosted Windows/Linux CI before merge.

No fresh Cloud Run or IAM validation is claimed: local gcloud authentication requires reauthentication. This task makes no credential, deployment, provider-policy or scheduling changes.

Local final validation on Python 3.14: **250 tests passed** with `-W error::ResourceWarning` (8.901 seconds); `python -m compileall -q clearparcel tests` and `git diff --check` passed. Hosted CI runs Python 3.12/3.13/3.14 on Windows and Linux, including the kernel-lock crash/concurrency cases. Its results must pass before merge.

## Upgrade and release validation

1. Obtain separate merge/deployment authorization. Verify publisher destination read and generation-conditional replacement permissions, scoped to the existing public object; do not grant raw private aggregate access to the public service.
2. For local workers, stop **all** old-version worker processes and disable overlapping starts during upgrade. The previous exclusive-create run lock and directory CAS lock do not interoperate with the new OS lock. Confirm no process is still writing before reconciling old lock artifacts. Remove a legacy CAS lock directory only after that confirmation; the new code deliberately refuses it.
3. Keep new lock files in place permanently. Do not unlink or replace them while a process may be holding a lock. `run_lock_stale_seconds` is retained for compatibility but no longer expires ownership. Verify filesystem lock/atomic-replacement support, especially on network shares.
4. Configure the private built-in dashboard's cloud/local profile before restart when sources are assigned. Keep existing authentication, provider holds and rate controls intact.
5. Validate approved execution profiles, individual source outcomes, worker provenance, full versus filtered retirement and rendered metrics. Test public publisher overlap/generation conflicts with sanitized fixtures before a production release. A successful container exit alone is insufficient.

Rollback also requires stopped local workers before switching lock protocols. Preserve a validated aggregate and normal backups; older merge/publisher code lacks these ordering protections, so do not run mixed versions concurrently. Do not roll back by deleting live lock files or weakening conditional writes.
