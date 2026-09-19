# Elfie Memory Debug Workspace: Final Design

> Status: design baseline reviewed in this cycle; this does not claim current source conformance
> Version: v1
> Updated: 2026-09-18
> Owner: Elfie / Brain / Memory / Developer Tools
> Parent design: [Brain ten-system architecture](./elfie-brain-ten-system-architecture)
> Child design: none
> Normative contracts: [Memory architecture](./elfie-memory-architecture), [Brain contract](../../../contracts/brain)
> Current architecture: [Cognitive flow](../../../architecture/cognitive-flow)
> Conformance ledger: [Memory conformance](../../../conformance/elfie-memory)
> Domain sources: Memory source-first design, Brain observability boundaries, the Memory Audit design discussion, and the current Developer Tools implementation.

> Design relations: **Owner:** Elfie / Brain / Memory / Developer Tools; **Parent:** [Brain ten-system architecture](./elfie-brain-ten-system-architecture.md); **Children:** none; **Normative contracts:** [Memory architecture](./elfie-memory-architecture.md), [Brain contract](../../../contracts/brain.md); **Current architecture:** [Cognitive flow](../../../architecture/cognitive-flow.md); **Conformance:** [Memory conformance](../../../conformance/elfie-memory.md); **Domain sources:** Memory source-first design, Brain observability boundaries, the Memory Audit design discussion, and the current Developer Tools implementation.

## 1. Decision summary

Memory Debug Workspace is a developer debugging surface, not a user memory-management page and not a second Memory implementation.

It answers three questions:

1. What is currently in the whole knowledge base?
2. How did a complete Episode become knowledge, and what did it affect?
3. Why did a Recall return these items?

The workspace has one shared interaction model:

- a large left canvas shows the whole memory structure;
- a smaller right panel contains Detail, Add Episode, and Search/Recall tabs;
- selection, filters, and highlights are shared in both directions;
- the workspace can open standalone or from Elfie Lab Turn Debug;
- Elfie Lab remains authoritative for the actual Turn, Prompt Context, and final context order.

This document freezes semantics, boundaries, interaction, and acceptance criteria. It does not mandate a particular graph library or require WebGL 3D.

## 2. Semantic model

The display model is source-first:

| Layer | Meaning | Display |
| --- | --- | --- |
| Event / Turn | Runtime fact or Brain turn | Detail or Elfie Lab context, not a knowledge node |
| ClosedEpisode | Durable completed experience source | Episode source rail |
| Evidence | Provenance for a Node or Assertion | Provenance connector and detail, not an ordinary node |
| Node | Entity, concept, or knowledge unit | Graph node |
| Assertion | Directed semantic relation | Graph edge |

RecallBundle is the result of one query, not a permanent graph entity. Every Node and Assertion must be traceable through Evidence to its source Episode. Lifecycle, importance, retention, confidence, conflict, and supersedes remain distinct fields.

## 3. Layout and interaction

The default layout is a left canvas taking roughly two-thirds to three-quarters of the window and a right panel taking the remainder.

The left side contains:

1. an Episode source rail;
2. a Node/Assertion knowledge graph;
3. counts and current filter/highlight status.

The default view is the whole knowledge base. Filtering dims unrelated content by default instead of deleting all context. The graph supports pan, zoom, node dragging, selection, related highlighting, long-label truncation with full detail on the right, and level-of-detail behavior for large libraries. 2D/2.5D/3D is an implementation choice; the graph must not become a Godot physics authority.

The right side contains:

- Detail: complete facts for a selected Episode, Node, Assertion, Evidence, or operation step;
- Add Episode: a complete Episode, validation, dry-run/isolated execution, real observed steps, affected objects, replay and failure details;
- Search/Recall: query normalization, candidates, scores, matched terms, kept/excluded decisions, budget truncation, final RecallBundle, and graph highlights.

The actual order of material entering the model context belongs to Elfie Lab Context/Turn Debug. The Memory page explains Memory selection, not Prompt order.

## 4. Shared projection and state

The page consumes four read-only projections:

- LibrarySnapshot: versioned counts, sources, nodes, assertions, evidence, lifecycle, confidence, conflicts, and graph hints;
- DetailProjection: the selected object and complete traceable associations;
- OperationTrace: run id, ordered steps, versions, observations, affected objects, errors, and replay state;
- RecallExplanation: query id, candidate-level scoring, ranking, kept/excluded reason, limits, character budget, final RecallBundle, and the Elfie Lab link.

The UI keeps one shared selection, filter, highlight, operation, and recall state. A left-side selection updates Detail; a right-side operation highlights affected objects; a Recall decision highlights returned, related, and candidate-but-excluded objects. Missing observations are shown as unknown, never inferred.

## 5. Safety and Elfie Lab integration

The same workspace component serves two entry points:

- standalone, opening the whole library;
- embedded from Elfie Lab with turn/query/operation identifiers and a return link.

Memory Debug Workspace explains what Memory persisted, organized, and selected. Elfie Lab explains the Brain Turn and actual context. Context Workspace explains what actually entered context and in what order. Neither surface creates a duplicate Memory source.

Production data is read-only by default. Add Episode experiments use an isolated data root or dry-run. A future real commit requires an explicit confirmation, target/version check, idempotency key, and rollback boundary. Developer Tools must not write production ELFIE_HOME directly.

All operation states are explicit: idle, preview, running, paused, succeeded, partial, failed, stale snapshot, conflicted, or truncated by budget. A failure includes the failed step, input version, completed effects, replayability, and required follow-up.

## 6. Current implementation and migration decision

The current implementation already provides reusable source-first persistence, read-only inspect/recall boundaries, statistics, a Detail/Add/Recall shell, and typed recall selection observations. It still lacks a scalable global graph, complete provenance highlighting, real Add Episode operation traces, candidate-level Recall explanation, and Elfie Lab integration.

The decision is to preserve the current Memory back end, projections, and tests, and implement the new workspace behind the independent `/elfie/memory-debug` route. Keep `/elfie/memory-audit` and its legacy styles as the unchanged baseline until the new workspace passes acceptance. Do not build a second Memory authority.

Recommended order:

1. freeze this design, keep `/elfie/memory-audit` as the legacy baseline, and create the independent `/elfie/memory-debug` entry;
2. define the four shared read-only projections and shared view state;
3. replace the left graph with the full-library source/graph view;
4. complete Detail and provenance navigation;
5. expose existing recall-selection observations candidate by candidate;
6. add isolated Add Episode tracing and replay;
7. embed the same workspace in Elfie Lab;
8. retire the fixed legacy layout only after acceptance.

## 7. Evaluation

The design scores approximately 8.8/10 against the developer debugging goals: 9/10 for whole-library understanding, provenance, Recall explanation, issue localization, bidirectional interaction, and architecture alignment; 7/10 for large-library scalability until LOD and clustering are implemented; and 8/10 for process credibility until consolidation and lifecycle observations are more granular.

The decisive improvement is not visual decoration. It is the closure of three evidence chains:

- source Episode → Evidence → Node/Assertion;
- Add Episode step → observed effect → affected graph objects;
- Recall candidate → selection decision → RecallBundle → actual Elfie Lab context.

## 8. Acceptance criteria

- The default view shows the current library and can trace any selected Node/Assertion to Evidence and Episode.
- A complete Episode can be replayed in isolated/dry-run mode with versioned, observable steps and accurate affected-object highlights.
- Recall shows candidate scoring, exclusion reasons, limits, budget truncation, final bundle, and returned/related/excluded graph highlights.
- The same workspace works standalone and from Elfie Lab without duplicating Memory authority.
- Production viewing remains read-only; experiments are isolated; unknown observations are marked as unknown.
- The legacy implementation is retired only after the new workspace passes these criteria.
