# Elfie Memory Debug Workspace: Final Design

> Status: design baseline reviewed in this cycle; this does not claim current source conformance
> Version: v1.2
> Updated: 2026-09-25
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

- the top toolbar groups search/filter and memory operations on the left, and graph controls on the right, with flexible space between;
- search and filter stay adjacent but separate: search runs Recall, filter opens graph conditions, and Add Episode and manual Consolidation remain distinct actions;
- the search field and Search Results drawer share the same desktop width; the filter button stays immediately after the search field, and the top operation group remains left-aligned;
- the Episode rail remains in its normal position below the toolbar and horizontally scrollable; drawers overlay the graph, with the left operation drawer offset just beyond the first Episode card with a visible gap, while staying on the left side, and the right detail drawer staying on the right;
- Add Episode uses an add icon and manual Consolidation uses an action/trigger icon;
- the graph remains the central, full workspace canvas;
- a closable left overlay contains Search/Recall results or Add Episode and its result;
- a separate closable right overlay contains selected-object Detail only;
- selecting a left-side result highlights the graph and opens its Detail on the right while keeping the result list open;
- the left and right overlays can be closed independently, and filters and highlights stay shared;
- the workspace can open standalone or from Elfie Lab Turn Debug;
- Elfie Lab remains authoritative for the actual Turn, Prompt Context, and final context order.

This document freezes semantics, boundaries, interaction, and acceptance criteria. It does not mandate a particular graph library or require WebGL 3D.

## 2. Semantic model

The display model has two semantic layers plus provenance:

| Layer | Meaning | Display |
| --- | --- | --- |
| ClosedEpisode | Complete, already-processed topic, story or learning unit | Episode source rail and direct text-memory result |
| Evidence | Provenance for a Node or Assertion | Provenance connector and detail, not an ordinary node |
| Node / Assertion | Higher-level note, entity, reusable knowledge or explicit relationship derived from Episodes | Graph node/edge and direct Recall result; the detail panel shows subject, object, readable relation semantics, direction, predicate, confidence and lifecycle |

RecallBundle is the result of one query, not a permanent graph entity. A Recall may return an
Episode, a Node/Assertion, or both; it does not need to return raw upstream conversation or media.
Every Node and Assertion must be traceable through Evidence to its source Episode or approved seed. Lifecycle,
importance, retention, confidence, conflict, and supersedes remain distinct fields.

The graph uses the injected Memory ontology rather than a second UI taxonomy. Its five registered
groups and leaf types are Social relations (`elfie`, `person`, `group`), Entities (`organism`,
`object`, `material`), Space geography (`cosmic_entity`, `place`), Events (`event`) and General
knowledge (`concept`, `claim`, `theory_or_model`, `principle_or_law`, `pattern`,
`rule_or_guideline`, `method_or_procedure`, `viewpoint`). `type_group` is derived from the active
leaf type and is never stored on a Node. A claim is an ordinary general-knowledge Node, without a
dedicated payload/table. Event Nodes remain optional reusable identities, not per-Episode or
execution-process records. The self-model is a derived sixth graph slice selected from registered
outgoing stance Assertions on the real `elfie` Node; it is not a Node type or a virtual anchor.

The graph views include registered, source-grounded Assertions and their source links according to
the Memory slice projection. Generic `about`,
`knows`, `knows_boundary` and `related_to` edges are not generated; a concept relation must use a
registered, source-grounded predicate. Every graph edge exposes its Assertion
identity and can open the attached Evidence and Episode; a projection that drops that identity is
incomplete.

### 2.1 Relation display contract

The relation graph renders canonical predicates from the Memory registry. Symmetric relations are
shown once with a neutral two-endpoint sentence; directed relations show the subject role and the
reverse role explicitly. The detail panel must show the predicate, readable sentence, endpoint
direction when meaningful, confidence, importance and Evidence. `kin_of` is displayed as “family
(specific relation unknown)”. Multiple relations between the same two nodes are separate rows and
edges, ordered by importance only for presentation. A missing edge or a co-occurring pair is never
rendered as a relationship.

### 2.2 Inspector detail projection

Detail is a read-only projection over the existing Memory records. The UI does not assemble a
second fact source from raw rows. Every selection uses the same compact order:

1. **Header:** semantic type, canonical label, one-line summary, status, importance and confidence;
2. **Primary content:** the type-specific attributes or readable assertion sentence;
3. **Connections:** grouped relations, attribute facts, affected objects or concept links, ordered
   by importance with a bounded initial count;
4. **Source:** Episode, Evidence, excerpt, time, viewpoint, attribution and media references;
5. **Technical details:** IDs, hashes, policy versions, raw qualifiers and projection metadata in a
   collapsed section.

Node detail uses the attributes registered for its leaf type. The derived group label comes from the
same ontology; the self-model slice links back to its real Nodes and Assertions rather than exposing
a synthetic Node. Assertion detail shows one readable sentence, endpoint roles,
direction or symmetry, valid time, polarity, epistemic status, importance, confidence, conflicts
and Evidence. Episode detail shows a non-empty `summary_text` as a concise, read-only display
headline, then the complete original content, time and precision, provenance, experience type,
consolidation progress, detail level, participants/place/context, and affected Nodes and Assertions.
When no summary is available, a content excerpt may be used as the display headline; it is not a
stored or editable title and never replaces the full content. Evidence detail leads with the
excerpt or media preview and then shows its source and supported, contradicted or contextual
Assertions. A reusable graph `event` Node links back to its supporting Episode and never duplicates the full story.

The projection has a typed selection union (`NodeDetail`, `AssertionDetail`, `EpisodeDetail` or
`EvidenceDetail`) with common header/source fields and type-specific sections. It is a Developer
Tools read model; the upper Memory/Recall interface and the SQLite authority remain unchanged.
Unknown fields are shown as unknown or in technical details, never guessed. The canvas legend
names semantic Node types and source/relationship meaning; it does not explain primitive shapes as
the primary legend.

### 2.3 Episode source-card hierarchy

Episode source cards have three information levels:

1. **Card:** show the Episode's evidenced occurrence/acquisition time first, following Memory's
   time meaning and precision; display unknown time as unknown rather than inventing a date. Use
   non-empty `summary_text` as the concise display
   headline; otherwise use a bounded excerpt of the original content. The next line shows the
   localized experience type and observed consolidation progress as separate values. Do not put
   Memory lifecycle status on the card, and do not expose raw enum identifiers or invent a second
   UI taxonomy.
2. **Hover/focus:** reveal the full summary and content, time/precision, experience type,
   provenance/source attribution, consolidation progress and content detail level. This must also
   be reachable through keyboard focus. Missing values remain explicitly unknown or unavailable.
3. **Selected detail:** retain all of the above and add linked people, places, topics, Nodes,
   Assertions and Evidence, plus persisted importance/emotion or other supported attributes.
   Technical IDs and hashes remain collapsed. Only facts present in the read-only projection may
   be shown.

The summary is a display synopsis, not a separate Episode title field, and the UI never edits it.
Memory's summarization step should normally provide a concise summary when supported by the source;
an absent summary remains valid, and the UI must not invent one.
Experience type describes what happened or how knowledge was acquired; Genesis or another source
attribution is provenance, not an experience type. Consolidation progress is operational state,
not Episode meaning or Memory lifecycle. The rail displays only Episodes supplied by the current
library/Recall projection and does not independently decide Recall eligibility. Memory Architecture
owns the experience-type vocabulary, stored field semantics, and Recall lifecycle policy; this
workspace defines only their read-only presentation.

## 3. Layout and interaction

The graph uses the full workspace behind two optional overlays. The top toolbar places search/filter and memory operations on the left, graph controls on the right, and leaves flexible space between the groups. Search runs Recall; filter opens the current graph's conditions; Add Episode and manual Consolidation remain separate actions.

The central canvas contains:

1. a horizontally scrollable Episode source rail in its normal position below the toolbar. Drawers remain overlays on the graph rather than moving below the rail; the left operation drawer is offset just beyond the first Episode card, not toward the canvas center, and the right detail drawer stays on the right;
2. a Node/Assertion knowledge graph;
3. counts and current filter/highlight status.

The default view is the whole knowledge base. The ontology-backed type-group and leaf-type selectors
are linked: choosing a group limits leaf options to that group, choosing a leaf selects its group,
and changing to an incompatible group clears the leaf selection. These selectors filter circular
Node glyphs only; Assertions are reprojected only when their visible endpoints remain available.
They affect this graph projection only, never Recall candidates, ranking, result lists or Elfie Lab
context. Other graph filters retain their separately defined behavior. The graph supports pan, zoom,
node dragging, selection, related highlighting, long-label truncation with full detail on the right,
and level-of-detail behavior for large libraries. 2D/2.5D/3D is an implementation choice; the graph
must not become a Godot physics authority.

During Recall, the default graph still shows the whole knowledge base: positively scored returned
Nodes and endpoints of returned Assertions are emphasized, unrelated content is dimmed, and
zero-score Nodes are not treated as relevant hits. Returned Nodes without a score remain visible
as unscored results; the UI must not invent a relevance value. A zero-score Node that is also an
endpoint of a returned Assertion may still be emphasized as that relation's endpoint. The Episode
rail shows only Episodes in the RecallBundle and does not expand when the graph switches between
the full library and the optional result-only projection.

Visual encoding is fixed: Node radius represents only Node `importance`; semantic Assertion width
represents only the relation's `importance`. Confidence, familiarity, and connection count do not
change those two scales and belong in detail, opacity/badges, or layout metadata. Episode source
cards use fixed UI dimensions, provenance traces use a fixed thin line, and selection changes color
or halo without drawing a bounding rectangle.

The right overlay contains only:

- Detail: complete facts for a selected Episode, Node, Assertion, or Evidence.

The left overlay is opened from the existing top toolbar and switches between two modes:

- Add Episode: a complete Episode, validation, dry-run/isolated execution, observed steps, affected objects, and failure details;
- Search/Recall: query normalization, candidates, scores, matched terms, kept/excluded decisions, budget truncation, final RecallBundle, and graph highlights.

Both overlays are optional and independently closable. Closing the left overlay preserves the selected-object Detail; closing Detail preserves the search results or Add Episode state. Clearing the search query clears its result highlights and closes the Search/Recall overlay without changing the toolbar layout. The desktop workspace is the target; no narrow-screen drawer layout is required.

The actual order of material entering the model context belongs to Elfie Lab Context/Turn Debug. The Memory page explains Memory selection, not Prompt order.

## 4. Shared projection and state

The page consumes four read-only projections:

- LibrarySnapshot: versioned counts, sources, nodes, assertions, evidence, lifecycle, confidence, conflicts, and graph hints;
- DetailProjection: the selected object and complete traceable associations;
- OperationTrace: run id, ordered steps, versions, observations, affected objects, errors, and replay state;
- RecallExplanation: query id, candidate-level scoring, ranking, kept/excluded reason, limits, character budget, final RecallBundle, and the Elfie Lab link.

The UI keeps one shared selection, filter, highlight, operation, and recall state. A left-overlay result updates the graph selection and right-side Detail without replacing the result list; an Add Episode operation highlights affected objects in the graph; Recall highlights returned scored or unscored Nodes and endpoints of returned Assertions, while zero-score Nodes and excluded candidates are not presented as relevant Node hits. A zero-score Node may still be emphasized when it is an endpoint of a returned Assertion. Missing observations are shown as unknown, never inferred.

## 5. Safety and Elfie Lab integration

The same workspace component serves two entry points:

- standalone, opening the whole library;
- embedded from Elfie Lab with turn/query/operation identifiers and a return link.

Memory Debug Workspace explains what Memory persisted, organized, and selected. Elfie Lab explains the Brain Turn and actual context. Context Workspace explains what actually entered context and in what order. Neither surface creates a duplicate Memory source.

Production data is read-only by default. Add Episode experiments use an isolated data root or dry-run. A future real commit requires an explicit confirmation, target/version check, idempotency key, and rollback boundary. Developer Tools must not write production ELFIE_HOME directly.

All operation states are explicit: idle, preview, running, paused, succeeded, partial, failed, stale snapshot, conflicted, or truncated by budget. A failure includes the failed step, input version, completed effects, replayability, and required follow-up.

## 6. Current implementation and migration decision

The current implementation already provides topic-oriented Episode capture, reusable source-first
persistence, read-only inspect/recall boundaries, statistics, a Detail/Add/Recall shell, and typed
recall selection observations. It still lacks a frozen Episode content/size contract, sparse
Node–Assertion admission, complete provenance highlighting, real Add Episode operation traces,
candidate-level Recall explanation, and Elfie Lab integration.

The decision is to preserve the current Memory back end, projections, and tests, and implement the new workspace behind the independent `/elfie/memory-debug` route. Keep `/elfie/memory-audit` and its legacy styles as the unchanged baseline until the new workspace passes acceptance. Do not build a second Memory authority.

Recommended order:

1. freeze the two-layer Episode/Node–Assertion contract and the Episode topic/size boundary, keeping `/elfie/memory-audit` as the legacy baseline;
2. register canonical Node types and normalize every writer to the registry;
3. narrow Consolidation admission so attributes and weak co-occurrences do not become formal graph facts;
4. define the four shared read-only projections and shared view state;
5. replace the left graph with the full-library Episode/Node–Assertion view;
6. complete Detail and provenance navigation, including Assertion identity on every edge;
7. expose existing recall-selection observations candidate by candidate and allow direct graph results;
8. add isolated Add Episode tracing and replay;
9. embed the same workspace in Elfie Lab;
10. regenerate development Memory data and verify type/source invariants;
11. retire the fixed legacy layout only after acceptance.

## 7. Evaluation

The design scores approximately 8.8/10 against the developer debugging goals: 9/10 for whole-library understanding, provenance, Recall explanation, issue localization, bidirectional interaction, and architecture alignment; 7/10 for large-library scalability until LOD and clustering are implemented; and 8/10 for process credibility until consolidation and lifecycle observations are more granular.

The decisive improvement is not visual decoration. It is the closure of three evidence chains:

- source Episode/approved seed → Evidence → Node/Assertion;
- Add Episode step → observed effect → affected graph objects;
- Recall candidate → selection decision → RecallBundle → actual Elfie Lab context.

## 8. Acceptance criteria

- The default view shows the current library and can trace any selected Node/Assertion to Evidence and Episode.
- A complete Episode can be replayed in isolated/dry-run mode with versioned, observable steps and accurate affected-object highlights.
- Recall shows candidate scoring, exclusion reasons, limits, budget truncation, final bundle, and returned/related/excluded graph highlights.
- The same workspace works standalone and from Elfie Lab without duplicating Memory authority.
- Production viewing remains read-only; experiments are isolated; unknown observations are marked as unknown.
- The legacy implementation is retired only after the new workspace passes these criteria.
