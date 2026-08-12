# Elfie Brain internal architecture conformance

> Temporary gap register for the [Brain internal architecture
> contract](../contracts/brain). It records current implementation facts and
> closure evidence without reducing the target.

These rows decompose the still-open aggregate gaps rather than creating a
second migration truth: BRN-001/002/004 refine ELF-011; BRN-003 refines ELF-016;
BRN-005/010 refine ELF-014; BRN-006/007 refine ELF-010 and ELF-017; and
BRN-008/009 refine ELF-015. Closing a Brain row must update any aggregate row
whose closing condition becomes true.

## Current gaps

| ID | Severity | Status | Current deviation | Closure evidence |
| --- | --- | --- | --- | --- |
| BRN-001 | P0 | closed | Brain now admits Communication, Embodied and Internal inputs as separate typed `TurnFrame` values with authoritative `SourceDomain`, `InteractionScope` and `ResponseScope`; mixed-domain frames are rejected. | Focused domain, scope, ordering, deduplication and boundary-attack tests pass; different conversations, body generations and internal causes remain separate Turns; a Communication Turn asking for motion cannot commit a body directive; Elfie Lab exposes the resulting scope and receipts. |
| BRN-002 | P0 | closed | `BrainContextProvider` only composes bounded projections from independent owners. Conversation, Memory and Activity have dedicated readers/stores. Memory and Orientation changes are explicit candidates committed only by `TurnSettlement`, never hidden context-read writes. Orientation also includes current Body, location, conversation and Activity. | Focused context, Activity, Orientation and settlement tests prove cutoff/unknown/stale semantics, read-without-write behavior, versioned commit and duplicate reconciliation. |
| BRN-003 | P0 | closed | `ReasoningRun` now owns a bounded Model/Skill/Tool/Observation loop inside one Turn, with explicit budget, deadline, cancellation and terminal states. Model and cognition tools remain inside Brain and cannot add an external action lane. | Focused Brain/Lab tests pass (26 total); real Elfie Lab shows a local-file Tool Observation, rejects tool text as an external receipt, enters `failed/no_op` when the model is unavailable, and creates a separate urgent Turn after a stale long Run. Plain-text Provider `owner_message_fallback` is recorded as capability degradation only. |
| BRN-004 | P0 | closed | `TurnDecision` and `OutputRouter` now deterministically check source domain, response scope and current capabilities; embodied decisions carry Body ID/generation and Communication decisions cannot produce body directives. Persistent Activity remains the separate BRN-005 concern. | Stage-three Headless and real Godot paths pass; stale body generations, invalid response domains, duplicate submissions and physical execution failures have focused evidence; an accepted decision enters at most one external execution domain. |
| BRN-005 | P0 | closed | Brain owns a typed Persistent Activity Port and output boundary. An `ActivityDraft` undergoes inert Preflight inside its originating `ReasoningRun`, validating resolved actor/channel, capability revision, `ExecutionScope`, budget, deadline and permitted operation. Only the exact host-issued evidence may commit after convergence; missing facts return as same-run clarification observations. | Focused Activity, Reasoning, persistence and Lab tests cover same-run clarification, forged-evidence rejection, idempotency, wake-up, Scope, receipt-backed completion, restart recovery and no duplicate delivery. |
| BRN-006 | P0 | closed | Orientation and Selfhood are independent authoritative owners. Selfhood is anchored to immutable Profile revision and enforces multi-source evidence plus a per-commit personality delta limit. Emotion, Energy, Memory, Orientation, Selfhood, Motivation and Cognitive Consolidation are all included in the continuity checkpoint/restore facade. Physical removal of broad Profile fields remains tracked only by ELF-010. | State and cross-module recovery tests cover versioned restore, stale checkpoint/foreign Profile rejection, single-message personality/norm rewrite rejection, Activity/Body Orientation and stale-candidate protection. |
| BRN-007 | P1 | closed | Energy now owns normal cognitive budget, a durable emergency reserve and per-Turn reservation/settlement while deriving `long`/`normal`/`degraded`/`emergency` projections. Emergency mode grants only a minimal response budget and forbids long reasoning, tools and background Activity; normal Activity cannot spend the reserve. The Lab exposes normal, emergency and in-flight reserved budget separately. | Focused Energy, Coordinator, Activity and Lab tests cover normal reservation, completion/failure release, durable restore, low-energy degradation, emergency minimum response and background-cognition suppression. |
| BRN-008 | P1 | closed | Brain now owns one bounded Recovery Motivation drive. Low energy/fatigue can emit a stable, causal `RecoveryDriveCandidate` as an `InternalSignal.MOTIVATION`; pressure, blocked/cooldown/satisfied states, duplicate suppression and checkpoint restore prevent storms. The candidate must enter one Internal Turn and cannot create Activity or execute an external action directly. | Focused Motivation, Coordinator and Elfie Lab tests cover threshold evaluation, suppression, bounded Internal Turn, safe No-op settlement and checkpoint restore. Multiple drives, social initiative and direct Activity creation remain out of scope. |
| BRN-009 | P1 | closed | Brain now owns a bounded Cognitive Consolidation lifecycle. During sleep it admits at most a fixed batch of pending episodic memories, carries a checkpointed candidate through an Internal Turn, and only commits the existing Memory consolidator after a completed internal receipt. | Consolidation and Elfie Lab scenarios cover sleep gating, blocked/duplicate suppression, checkpoint restore, bounded consolidation and receipt-backed commit. The candidate has no external response scope, so it cannot send, move, create Activity or expand permission. Broader Activity/emotion/Selfhood night work remains out of scope. |
| BRN-010 | P0 | closed | Each production/Lab Elfie now receives one SQLite cognitive persistence Adapter. Its append-only Journal records Run start/terminal facts, accepted/rejected directives, execution receipts and Activity revisions; its latest checkpoint durably covers Emotion, Energy, Memory, Orientation, Selfhood, Motivation and Cognitive Consolidation. The workspace atomically persists uncommitted input, original ordering, its recent-event idempotency window and observable coalescing/drop evidence. Restart restores checkpoint and cognitive clock, converts unfinished Runs/directives into inert uncertainty events, and pauses in-flight Activity instead of replaying an external effect. | Focused Journal, SQLite, Workspace, Router, lifecycle and restart tests prove append order, idempotency-conflict rejection, Run/directive/receipt correlation, pre-Run input recovery, restart-safe deduplication, observable loss, durable checkpoint restore, Activity pause/reconciliation and no automatic side-effect replay. The Journal and checkpoint remain persistence mechanisms, not an eleventh cognitive owner. |

## Implementation ordering constraints

The detailed implementation plan is a separate approved artifact. It may split
these gaps into smaller vertical slices, but it must preserve this dependency
order:

1. BRN-001 and the minimal deterministic part of BRN-004 form a visible digital
   communication Turn closure.
2. BRN-002 and BRN-003 add truthful context and bounded Agent reasoning without
   adding a new external action route.
3. The embodied closure completes the body-facing part of BRN-004 while keeping
   Communication and Embodied Turns isolated.
4. BRN-006 and BRN-007 establish continuous state and recovery before autonomous
   behavior depends on them.
5. BRN-005 and the required BRN-010 persistence close before BRN-008 can emit an
   autonomous work candidate.
6. BRN-009 remains last and cannot directly perform external side effects.

Each implementation stage must provide one observable result, one boundary
attack, one failure or restart check and an explicit non-goal. Closing a row
requires product behavior and focused tests; contract text alone is not
implementation evidence.
