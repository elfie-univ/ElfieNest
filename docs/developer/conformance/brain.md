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
| BRN-002 | P0 | open | `BrainContext` now carries Orientation, Selfhood, immutable Profile anchors, versioned Memory state and a versioned Motivation snapshot with provenance, revisions, unknown fields and current-turn cutoffs. Activity is authoritative in its Brain-owned Store and visible in the Lab projection, but is not yet part of the unified BrainContext snapshot; the existing owner-memory compatibility write remains open. | Context assembly reads all versioned owner snapshots without hidden writes, distinguishes facts/inferences/unknowns, and records all snapshot cutoffs used by one Turn. |
| BRN-003 | P0 | closed | `ReasoningRun` now owns a bounded Model/Skill/Tool/Observation loop inside one Turn, with explicit budget, deadline, cancellation and terminal states. Model and cognition tools remain inside Brain and cannot add an external action lane. | Focused Brain/Lab tests pass (26 total); real Elfie Lab shows a local-file Tool Observation, rejects tool text as an external receipt, enters `failed/no_op` when the model is unavailable, and creates a separate urgent Turn after a stale long Run. Plain-text Provider `owner_message_fallback` is recorded as capability degradation only. |
| BRN-004 | P0 | closed | `TurnDecision` and `OutputRouter` now deterministically check source domain, response scope and current capabilities; embodied decisions carry Body ID/generation and Communication decisions cannot produce body directives. Persistent Activity remains the separate BRN-005 concern. | Stage-three Headless and real Godot paths pass; stale body generations, invalid response domains, duplicate submissions and physical execution failures have focused evidence; an accepted decision enters at most one external execution domain. |
| BRN-005 | P0 | closed | Brain now owns a typed Persistent Activity Port and output executor. Activity drafts undergo side-effect-free Preflight and idempotent Commit, durable waiting/running state emits typed `ACTIVITY` Internal events, and real child receipts settle the current step with revision and progress. SQLite and Lab adapters remain outside Brain. | Focused Activity/persistence/Lab tests cover validation, idempotency, wake-up, communication Scope, receipt-backed completion, restart recovery and no duplicate delivery. |
| BRN-006 | P0 | open | Orientation and Selfhood have authoritative in-memory snapshots with candidate/validation/commit/recovery guards; Emotion, Energy and Memory now provide versioned snapshots/checkpoints and a Brain continuity restore facade, while Profile still carries broad personality/capability/limit mappings awaiting physical migration. | Versioned Orientation, Selfhood, Emotion, Energy and Memory state restore coherently; Profile remains immutable; one message or short emotion cannot rewrite personality; stale candidates cannot overwrite newer state. |
| BRN-007 | P1 | open | Energy now derives `long`/`normal`/`degraded`/`emergency` cognitive projections and passes per-Turn token/model/tool/step budgets into the cortical worker; durable reserve accounting and a user-visible degraded-response policy remain open. | Deterministic tests cover normal, bounded-long, degraded and emergency modes; emergency reserve forbids long/background cognition while preserving minimal response and recovery. |
| BRN-008 | P1 | closed | Brain now owns one bounded Recovery Motivation drive. Low energy/fatigue can emit a stable, causal `RecoveryDriveCandidate` as an `InternalSignal.MOTIVATION`; pressure, blocked/cooldown/satisfied states, duplicate suppression and checkpoint restore prevent storms. The candidate must enter one Internal Turn and cannot create Activity or execute an external action directly. | Focused Motivation, Coordinator and Elfie Lab tests cover threshold evaluation, suppression, bounded Internal Turn, safe No-op settlement and checkpoint restore. Multiple drives, social initiative and direct Activity creation remain out of scope. |
| BRN-009 | P1 | closed | Brain now owns a bounded Offline Cognition lifecycle. During sleep it admits at most a fixed batch of pending episodic memories, carries a checkpointed candidate through an Internal Turn, and only commits the existing Memory consolidator after a completed internal receipt. | `test_offline_cognition.py` and the Elfie Lab offline-cognition scenario cover sleep gating, blocked/duplicate suppression, checkpoint restore, bounded consolidation and receipt-backed commit. The candidate has no external response scope, so it cannot send, move, create Activity or expand permission. Broader Activity/emotion/Selfhood night work remains out of scope. |
| BRN-010 | P0 | open | Activity now has durable revisioned state, causal/idempotency identity and receipt reconciliation, but Brain still lacks a unified durable Journal/State/Checkpoint/causal-trace contract across mental state, Runs, directives and Activities. | Restart restores only committed state, reconciles in-flight directives and Activities by causal/idempotency identity, rejects obsolete body generations and exposes traceable failure without making cognitive infrastructure a decision owner. |

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
