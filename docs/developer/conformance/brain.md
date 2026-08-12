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
| BRN-002 | P0 | open | `BrainContext` contains frame, emotion, homeostasis, conversation, memory and capabilities, but lacks authoritative Orientation, Selfhood, Motivation and Activity snapshots and complete source/version/unknown semantics. `ElfieContextSource` remains at the Elfie root and mutates conversation/memory compatibility state during context reads. | Context assembly moves under Brain, reads versioned owner snapshots without hidden writes, distinguishes facts/inferences/unknowns, and records all snapshot cutoffs used by one Turn. |
| BRN-003 | P0 | open | `CorticalWorker` performs one model generation and decode. There is no bounded multi-step Model/Skill/Tool Observation loop, verifier/completion judge, explicit cognitive budget or long/short Run interruption contract. | A `ReasoningRun` supports bounded cognitive steps and real Tool observations; budget, timeout, cancellation and stale-result tests terminate without fabricated success; a separate urgent Turn cannot contaminate an existing Run. |
| BRN-004 | P0 | open | `DecisionPlan` is a multi-intent DAG that may mix speech, message, motion and placeholder internal operations. `OutputRouter` is the effective decision/execution boundary but does not enforce the accepted single-domain Turn/response matrix or Persistent Activity request. | One `TurnDecision` is deterministically checked against source, response and execution scopes; at most one external domain commits; internal state candidates are settled separately; stale capability/body generation and duplicate commits are rejected. |
| BRN-005 | P0 | open | `DefaultInternalIntentSink` immediately marks `REMEMBER`, `SCHEDULE` and `REFLECT` complete. There is no durable Persistent Activity owner, preflight/commit split, typed wake-up, checkpoint or receipt reconciliation. | Validated Activities survive Turn and restart, incomplete requests clarify during the originating Turn, due work emits an Internal event, communication/body steps stay separate, and restart does not lose or duplicate side effects. |
| BRN-006 | P0 | open | Emotion, energy and memory have partial owners, while Orientation and Selfhood do not exist as authoritative systems. Profile still owns broad personality/capability/limit mappings, and mental state does not have one common candidate-validation-commit and recovery protocol. | Versioned Orientation, Selfhood, Emotion, Energy and Memory state restore coherently; Profile remains immutable; one message or short emotion cannot rewrite personality; stale candidates cannot overwrite newer state. |
| BRN-007 | P1 | open | Energy advances fatigue/energy and current Turn timing, but does not own a complete cognitive-mode policy, normal/emergency budget reservation, long-reasoning admission or degraded-response behavior. | Deterministic tests cover normal, bounded-long, degraded and emergency modes; emergency reserve forbids long/background cognition while preserving minimal response and recovery. |
| BRN-008 | P1 | open | Autonomous deadline/internal signals are placeholders rather than a fixed-drive Motivation system with pressure, satisfaction, saturation, cooldown, duplicate suppression and Activity-aware limits. | After BRN-005 closes, one low-risk fixed drive produces only bounded attention/goal/internal-trigger candidates and cannot self-wake, spam, create Activity or execute directly. |
| BRN-009 | P1 | open | Existing memory consolidation is a Memory helper, not an interruptible Cognitive Consolidation lifecycle with independent budget, checkpoint and no-external-side-effect scope. | A sleep/idle run can resume from checkpoint and submit validated memory/relationship/selfhood candidates or a later Internal trigger, but cannot send, move, create Activity or expand permission. |
| BRN-010 | P0 | open | Workspace, Turn, decision, output and receipts have partial persistence/metrics, but Brain lacks a unified durable Journal/State/Checkpoint/causal-trace/reconciliation contract across mental state, Runs and Activities. | Restart restores only committed state, reconciles in-flight directives and Activities by causal/idempotency identity, rejects obsolete body generations and exposes traceable failure without making cognitive infrastructure a decision owner. |

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
