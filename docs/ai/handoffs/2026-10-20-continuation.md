# Watchtower continuation checkpoint — October 20, 2026

Prepared by Codex from current GitHub merge/CI state and recorded deployment
evidence. Latest verified implementation main:
`1c3b3ed62389c36c3d2e61db60715509cb430076`. Revalidate main and preserve dirty
work before continuing. Later documentation commits do not change this
application checkpoint. No live production readback was repeated for this note.
The current [GitHub tracker](https://github.com/clearparcel/GIS-Data-Watchtower/issues/113)
records completed slices and remaining acceptance gates.

## Completed versus unverified

| Work | Verified result | Remaining limitation |
| --- | --- | --- |
| WT-01 display semantics | PR #102 merged; deployed with v0.3.1 | Bounded acceptance, not all possible real-world cases |
| Private GAC selection | PR #108 source `3c078d8`, v0.3.2 deployment recorded in PR #109 | Dashboard release does not replace v0.3.0 provider/publisher jobs |
| Operations triage | PR #103 merged; original evidence validation and recovery matching | Not an alert sender or proof of all scheduled runs |
| Monitoring-authority matcher | PR #104 merged | Does not grant monitoring authority |
| Synthetic restore | PR #105 merged | Local aggregate only; complete backup/GCS/IAM restoration unverified |
| WT-15 diagnosis | PR #110 merged as `f2ca5c0` | Missing original reports, formal recovery and owner dispositions remain |
| WT-02 actual inventory | PR #111 merged as `c7ade29` | 22 county approval gaps, 2 separate parcel scopes, 2 held rows, 9 non-parcel rows outside scope |
| Alert-routing preview | PR #112 merged as `1c3b3ed` | No transport, durable delivery ledger, sent messages, activation or delivery acceptance |

PRs #110, #111 and #112 each passed all eight PR checks. Their post-merge CI
runs also succeeded:

- [WT-15 run](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39453546261)
- [WT-02 run](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39457339315)
- [Alert-routing run](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/39461133624)

Latest application validation: 593 ResourceWarning-strict tests, three platform
skips, required Node 24 behavior tests, compilation, status synchronization and
whitespace checks passed. Bounded CCE review of alert application `50afe77`
found no actionable findings; `e433a9d` adds only its review receipt.
These reviews used supplied context and did not independently inspect production.

The owner knows of no separate approval ledger. Existing Aitkin/Morrison issue
constraints remain evidence, not complete current dated scope/cadence records.
Preserve all data-driven holds; missing records alone do not prove unlawful use.
Do not close issues #1 or #2 on the basis of the merged tools.

## Next task: prepare real alert delivery

1. Read AGENTS.md, docs/ai/WORKFLOW.md, STATUS.md, docs/alert-routing.md,
   docs/operations-triage.md and the routing implementation/tests.
2. Inspect existing notification routing read-only before choosing or adding a
   transport. Do not assume that the offline rehearsal inspected cloud channels.
3. Reuse the validated preview/triage semantics. Implement a disabled-by-default
   delivery path and durable accepted/sent/acknowledged state. Define provider
   idempotency, ambiguous-result handling, bounded retries, repeat policy and
   rollback before activation. Preserve source controls and rate-limit backoff.
4. Test failures, age alerts, recovery, replay, concurrent claims and interrupted
   delivery using synthetic inputs and injected transports. No real sends.
5. Prepare exact private destination/message and deployment/activation changes
   for owner review. The owner selected a private email recipient and escalation
   owner for a draft only. Obtain their values from the owner-local private
   handoff; do not place them or private configuration in public Git.
6. Run required checks, offer bounded CCE review of the concrete candidate,
   and use a feature branch/PR. Sending test mail, merge, deployment, routing
   activation and production configuration require their respective approvals.

No credentials, capabilities or CCE workflow authority transfer with this note.
Begin an independent CCE workflow on the new connection; re-read the relevant
published shared-memory record. Never treat this document as an operational
permission grant or an instruction to replace an active chat.

## Remaining plan and estimates

Planning ranges assume one engineer, prompt decisions and no major new findings.
They are not delivery promises or evidence that work is complete.

| Watchtower remainder | Engineering effort |
| --- | ---: |
| Alert transport, durable state and approved delivery acceptance | 1–3 days |
| WT-02 scoped decisions and combined cadence evidence | 1–2 days plus external responses |
| Complete-backup inventory and isolated GCS restore rehearsal | 1–2 days |
| Effective IAM and any separately approved obsolete-binding change | 0.5–1 day |
| WT-15 disposition/recovery evidence and operational acceptance | 0.5–1.5 days plus five ordinary daily cycles |

Overall Watchtower planning range: approximately 5–10 engineering days,
typically 2–3 calendar weeks with timely approvals. No added provider checks
or schedules are authorized to accelerate the five-cycle observation gate.
Issue #20 remains open until applicable ordinary-cycle evidence is accepted.
Existing PostHog issue #50 is an optional analytics item, not proof of activation.

The broader owner plan also includes county evidence/contact qualification
(2–4 days initially), CRM capacity/case safeguards (3–5 days), replies/evidence
and production authorization/provider integration (7–14 days), and controlled
release/pilot (3–5 engineering days plus approvals/observation). CRM state was
not revalidated here; preserve its local work and reassess before implementation.
These estimates are planning carryovers, not a CRM completion assessment.
The bounded implementation plus initial pilot is roughly 6–10 calendar weeks.
Optional optimization requires a 30-day measurement period, which may overlap,
then 2–4 days of justified work. All-county permission/contact completion has
no defensible fixed date before external response times are known.

## Shared context

Record `gis-data-watchtower`, published revision
`34bb01ef001eb4950fd72b8806c20098950d2461`, SHA-256
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`,
was re-read for this checkpoint. It remains historical `needs-review`, updated
October 13 and review due October 14. Current owner decisions and verified
evidence take precedence.

## Copyable continuation prompt

Continue GIS Data Watchtower from the authoritative checkout identified in
AGENTS.md. Read this checkpoint and reconcile current GitHub main, open PRs and
dirty work first. The verified application checkpoint is merge `1c3b3ed` from
PR #112; alert previews are merged, but real delivery is not implemented.

Begin an independent CCE workflow and read the required repository workflow.
Proceed with the next-task steps above: inspect existing alert routing read-only,
then implement a disabled delivery candidate with durable duplicate prevention
and synthetic acceptance tests. Preserve health/freshness distinctions and all
provider controls. The selected recipient is approved only for the private
draft. Do not send notifications, activate routes, merge, deploy, mutate
production/IAM/schedules, or conduct extra provider polling without the applicable
explicit approval. Keep private routing/configuration/evidence out of public Git.

Complete the required tests, compilation, generated-status and whitespace
checks; prepare a concrete reviewable candidate and offer bounded CCE review.
Report actual results and remaining gates. Do not claim WT-02, live alerting,
GCS restore, IAM, five-cycle acceptance or CRM complete from merged tooling.
