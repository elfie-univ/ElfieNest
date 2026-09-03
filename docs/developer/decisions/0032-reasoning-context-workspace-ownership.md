# ADR-0032: Reasoning owns the Context Workspace; Memory owns durable memory

**Status:** Accepted
**Date:** 2026-08-31
**Scope:** Reasoning context, Memory boundary and one-Turn Agent loop

## Context

The accepted Brain documents used "working memory" in the Memory system while
the Memory architecture denied ownership of complete Reasoning context and the
source already kept bounded conversation history under `elfie/brain/reasoning/`.
The same word "workspace" also referred both to the top-level Event Workspace
and informally to model context. This left three conflicting interpretations:
Memory might own current dialogue, Event Workspace might be a general cognitive
scratchpad, or every model call might receive a caller-owned Conversation.

Those interpretations create duplicate authorities and make context
compaction, repeated Recall, receipt-backed reply history and restart recovery
impossible to specify consistently.

## Decision

Adopt the
[Reasoning Core single-Turn Agent design](../designs/elfie/brain/elfie-reasoning-core.md)
and revise the Brain contract to 1.4.

1. `Event Workspace` remains system 1 and keeps `workspace/`; it owns event
   lanes, admission and immutable single-domain `TurnFrame` construction only.
2. `Reasoning Context Workspace` is an internal component of system 8. It owns
   bounded recent alternating dialogue, active-topic state, source-linked
   context summaries, current-Run Observations, pending Memory handoffs and its
   own bounded recovery checkpoint.
3. Memory owns durable Episodes, knowledge, people, relationships, provenance,
   retrieval and lifecycle maintenance. It owns no transient conversation tail,
   context summary, Run scratch state or generic working buffer.
4. Reasoning receives a `TurnFrame` and read-only owner snapshots rather than a
   caller-assembled complete Conversation. It reads the relevant conversation
   partition from its own Context Workspace.
5. Every Turn performs baseline Recall. The Agent loop may request additional
   Recall through a Memory Bridge; queries in one Run bind to one Memory
   revision. Reasoning chooses query intent and timing while Memory owns
   retrieval, conflicts, validation and commit.
6. Prompt compaction produces a Reasoning-owned, source-linked
   `ContextSummary`. Durable capture is a separate handoff of complete
   `ClosedEpisode` sources and typed candidates; a lossy model summary is not a
   Memory fact.
7. Reasoning is a bounded Agent for one Turn. `DIRECT` and `DELIBERATE` are
   reasoning-depth choices; Food supplies model roles and fallback, and
   cognitive capabilities are independent stage gates. P0 owner chat enables
   Memory but disables Skill, Tool and Worker.
8. A reply enters Context Workspace only after a completed delivery Receipt.
   The Run ends at one `TurnDecision`; external execution and settlement never
   reopen it. Anything that must wait across Turns belongs to Persistent
   Activity.

## Consequences

- Brain has one event workspace and one Reasoning-internal context workspace;
  neither is renamed into the other and no eleventh mental system is created.
- Conversation continuity, prompt budgeting and compaction have a single owner
  without treating durable Memory as a token buffer.
- Memory remains reusable by every Reasoning depth and cannot be hidden behind
  an "assisted" mode.
- The bounded history, context compiler, Recall reader and `ReasoningRun` were
  migrated in place into the completed P0 owner-chat path. Context summaries,
  per-step rebuild, revision-pinned on-demand Recall, chat complexity routing
  and semantic completion are protected by permanent focused tests and the
  retired-register deny-return gate. Later Skill, Tool or Worker capabilities
  remain outside P0 and require their own scoped design and conformance work if
  adopted.
- This governance change does not rename source directories or implement Tool,
  Activity or runtime behavior.

## Rejected alternatives

Rejected alternatives are a separate Memory-owned working-buffer module;
putting recent conversation and prompt summaries in durable Memory; turning
Event Workspace into general Agent scratch state; passing a complete mutable
Conversation into every Reasoning call; letting a model read/write Memory
directly; treating compaction text as a durable fact; and coupling
`DIRECT/DELIBERATE` to a Food allow-list.
