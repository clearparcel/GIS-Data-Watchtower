# Codex Cloud readiness review — 2026-10-08

The development environment has been prepared and published, but fresh-task
restoration is blocked by provisioning. Further migration is principally about
making that environment usable and validating its lifecycle, rather than moving
provider credentials or the production database into a coding workspace.

Google Cloud operational connectivity and Codex Cloud development are separate.
The [county migration](county-cloud-migration-2026-10-08.md) puts all 35 configured
providers in the Cloud Run profile. That does not provision a Codex Cloud VM,
grant it Google Cloud credentials, refresh the public aggregate, or transfer
authoritative scheduling.

## Evidence reviewed

- Local feature revision `9f70876d222d863fd89176d321789cb0fdf9c17f`; main is
  `3ca334a84c5277e28a203ce106c69120427a3045`. Cloud preparation remains in
  [draft PR #56](https://github.com/clearparcel/GIS-Data-Watchtower/pull/56).
- [CI run 37771252626](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/37771252626)
  passed Ubuntu/Windows on Python 3.12–3.14 and the security job. The Ubuntu
  3.13 lane exercises Linux bootstrap, shell syntax, synthetic fixture generation
  and static dashboard construction. Container/security/supply-chain checks
  remain in CI. Local required validation passes 308 tests.
- Repository bootstrap, constraints, package metadata, synthetic generator,
  loopback launcher, tests, hybrid receipt validation and aggregate freshness
  implementation were read. No broad dependency or GIS SDK migration is needed
  for the current stdlib-oriented application.
- Supplied setup/launcher records under `.codex-remote-attachments/cloud-migration/`
  record private **ClearParcel Watchtower Development**, published with the exact
  revision above, Python 3.13.15 and Node 24.19.0. Preparation passed 308 tests
  with zero skips, dependency checks, static build and synthetic preview
  stop/restart, health/API/summary/HTML checks. These are setup results.
- The existing task **Validate environment restoration**
  (`01a11bce-eae0-7383-86f4-8256a61780d6`) was read directly. Its latest completed
  turn reports desired running / observed pending, connectivity offline,
  current observations at spec revision 4, failure null and no exposed retry
  action. Filesystem/shell never became available; HEAD, tests and preview
  restoration remain unperformed. This is the latest recorded task result,
  not a live runtime query from this local chat.
- The desktop launcher did create that task. Earlier web-only launcher failure
  therefore is not the primary remaining blocker. The catalog's Unknown
  repository label remains an unexplained symptom, not a proven root cause.
- Current official [OpenAI cloud-environment documentation](https://learn.chatgpt.com/docs/environments/cloud-environments)
  describes isolated task workspaces from a published filesystem, automatic
  repository refresh, and republishing setup changes for new tasks. The older
  [legacy environment documentation](https://learn.chatgpt.com/docs/environments/cloud-environment)
  describes a different setup/cache lifecycle. Apply the lifecycle of the
  actual published environment instead of assuming legacy scripts fix it.

## Follow-up implementation — 2026-10-08

PRs #55, #56 and #57 have since merged with explicit user approval and passing
checks. GitHub main contains the county label, synthetic cloud setup and this
migration evidence; the merged remote branches are removed. The published
pilot's recorded source pin has not been republished from current main.

Repository follow-up now implements active-profile-only receipts, explicit
worker retirement with archived history and CAS safety, and a separate opt-in
offline importer for sanitized public snapshots. See
[worker retirement](hybrid-aggregation.md#explicit-worker-retirement) and
[public replay](codex-cloud-development.md#optional-offline-public-snapshot-replay).
These changes do not perform production retirement, saving provider cycles,
deployment, cloud provisioning or scheduling. The findings below describe the
reviewed baseline; implementation closes the code gaps in operational items 2
and 3, while deployment and acceptance remain pending.

## Review baseline: remaining work, in priority order

| Priority | Work | Acceptance evidence |
| --- | --- | --- |
| 1 — blocks use | Resolve provisioning of the existing selected published environment/task through supported runtime/support controls. Preserve its source pin and prepared filesystem; do not rewrite repository IDs or broaden networking speculatively. | Observed running state, usable shell/filesystem, actual HEAD and installed tool versions. |
| 2 — governance | Establish a real callable, authority-bound CCE MCP connection in a fresh cloud coding task. Setup reports did not expose CCE attachment capability. Installing an SDK or adding a VPN is insufficient by itself. | Begin/refresh/record/finish through the same live authorized connection, with no copied bearer/session authority. |
| 3 — lifecycle | Repeat offline acceptance in a fresh task and after reopening/restoring that task. Test both source refresh and dependency reuse against the actual published lifecycle. | Exact revision; Python/Node versions; pip check; all 308 tests with no unintended skips; compileall; status sync; CLI smoke; static build; preview stop/restart and health/API/summary/HTML metrics. |
| 4 — repository baseline | Review and merge PR #56 through the existing explicit merge boundary, then deliberately choose whether to keep the pilot pin or republish a verified main revision. Preserve this review/change record separately. | Approved merged commit and a matching tested published version. A branch snapshot works for a pilot but is not current main. |
| 5 — developer workflow | Verify cloud task edits, Git diff preservation, reconnect/reopen, branch/PR submission and desktop review end to end. Local GitHub CLI access does not prove cloud task GitHub permissions. | Small reversible repository change, reviewed diff and successful supported PR workflow from the real cloud task. |
| 6 — representative data | Keep synthetic offline data for setup. If realistic UI debugging is needed, design a separate opt-in importer of the already-sanitized public snapshot, stored as an ignored local fixture with observation timestamps and revision recorded. This needs a scoped policy/configuration decision under current synthetic-only instructions. | No private registry, operational GCS access or provider polling; public schema/size validation; explicit refresh; preserved observation/publication distinction; deterministic offline replay. |

The temporary Watchtower-only CCE exception is recorded in the existing pilot's
user request and setup instructions for its synthetic validation. It is not a
general waiver for production, broad cloud coding, private CCE access or model
escalation, and this review does not extend it. Default repository CCE requirements
remain. This local investigation used CCE normally. No other task was messaged,
recreated, reset or reconfigured by this review.

Network configuration should remain limited to verified development needs.
The prepared pilot records package-manager networking, no extra domains, no
configured secrets or outbound identities. Once provisioning works, inspect the
current effective network policy before assuming readiness. The saved startup
must explicitly select the intended virtualenv/Python and safely regenerate
synthetic fixtures without overwriting files; timestamp freshness from the
published snapshot must not be mistaken for a fresh provider check.

## Separate work to replace local operational execution

All sources now being assigned to cloud removes the previously assumed
network blocker, but operational activation is not complete:

1. Validate a complete 35-source saving candidate cycle and end-to-end private
   aggregate/public projection before scheduling. The four scoped connectivity
   tests did not refresh the aggregate. Use an identical approved candidate
   package/configuration, source-level results, CAS protections and observation
   timestamps. Coordinate any checks with the existing daily local task.
2. Update cloud-only validation receipts. `candidate_manifest` always emits both
   cloud and local inventories; `validation_receipt` currently requires identity,
   report time and aggregate/public worker records even when local inventory is
   empty. `scripts/validate_hybrid_observations.py` also requires a local report.
   Cloud-only activation must support the intended active worker set without
   manufacturing local heartbeats or weakening inventory/provenance checks.
3. Add an explicit inactive-worker lifecycle. `merge_states` preserves prior
   worker records, and `with_freshness` counts all retained workers. After sources
   move to cloud, the old local worker can remain stale even when it owns no
   current sources. Retire it with preserved historical provenance and ordering/
   concurrency safeguards; do not manually erase shared aggregate fields.
4. Complete the separately authorized multi-day validation gate and prepare
   failure/backoff, alerting, rollback, storage destinations, package identity,
   schedule timing and recovery evidence. Then obtain the specific activation
   decision to replace the GERTKEN-PC task with authoritative cloud scheduling.
   The 10-minute public publisher remains independent of provider cadence.

Keep production service identities, Secret Manager registries, operational
storage, IAP, scheduler identities and deployment pipelines in the operational
Google Cloud environment. They do not need to be copied into Codex Cloud for
coding. Windows CI remains useful until local retirement and for compatibility;
the currently green Linux lanes already support development portability.

## Review limits

This review confirms repository/CI evidence and the existing cloud-task report,
not a newly functioning managed executor. Managed runtime/configuration tools
are not exposed to this local chat. No further environment provisioning action,
CCE attachment, fresh/restored tests, merge, deployment or authoritative schedule
activation is claimed. No support communication was sent. The next actionable
blocker is provisioning the already-published environment, followed by actual
restoration acceptance; moving additional production resources into it would
not resolve that blocker.
