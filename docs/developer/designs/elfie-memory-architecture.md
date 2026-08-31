# Elfie Memory Architecture

> Status: target design. This document is the authority for Memory semantics and its typed access contract. Code and the Conformance register describe implementation status.
>
> Scope: durable subjective experiences, sourced personal knowledge and deterministic recall. It does not define Event Workspace or Reasoning's complete context policy, nor another module's state.

## 1. Purpose, boundary and authority

### 1.1 What Memory solves

Memory gives one Elfie a durable, source-grounded personal memory. It keeps the detail of what happened and a semantic structure that can be recalled by wording, time, people, emotion, topic and relationships.

The design has three inseparable parts:

1. **Episode Timeline** — complete, bounded experiences in time order.
2. **Personal Knowledge Graph** — semantic nodes and relations projected from those experiences and approved Genesis knowledge.
3. **Hybrid Graph/Text Retrieval** — lexical/text and bounded graph retrieval returned with source evidence.

This is the **source-first** design: the graph is a projection of the historical source, not a replacement for it.

### 1.2 What Memory does not own

Memory receives an already-closed event; it does not decide where an event begins or ends. It does not own Profile, immutable identity, current location, live body state, live emotion, active plans, commitments, permissions or external actions. It does not directly read Profile, Communication history, world runtime state or another module's database. A relevant fact must be supplied by its owner as a sourced event or reference.

Memory does not narrate a reply or define Brain's working memory or the complete Reasoning context. It returns bounded, sourced material through its typed Recall contract.

### 1.3 Memory and Brain / Cognitive Consolidation

Normal Memory capture accepts only a complete, sourced `ClosedEpisode`. The cross-system `Cognitive Consolidation` scheduler is only a background entry point: when its target is Memory, it invokes or budgets `Memory Maintenance`. Memory owns the durable write, graph projection, recall and lifecycle maintenance; no other scheduler or owner creates a second Memory write path.

`Memory Maintenance` is the Memory-owned operation. It is related to, but distinct from, the cross-system `Cognitive Consolidation` scheduler.

### 1.4 Core source rule

For the live Memory model, there are only two source forms:

- normal runtime: a complete, closed `ClosedEpisode`;
- one-time initialization: a complete, versioned `ApprovedSeedSource`.

Every durable Assertion must point to an Episode or approved seed Evidence. A model proposal, summary, cache entry or ungrounded profile value is not evidence. Runtime learning is Episode-first; only the approved Genesis path may project initial Nodes/Assertions directly.

## 2. Durable memory model

### 2.1 Episode Timeline

An Episode is one meaningful, bounded, closed event or scene—not one chat turn and not a keyword summary. The upstream event boundary groups related turns or observations before Memory receives it.

An Episode may be a conversation or relationship moment, a learning session, an embodied or environmental experience, a perception with text/audio/video/images, or a meaningful emotional/social event.

It retains:

- stable ID, occurrence range and event kind; when relevant, a historical `life_stage`/`temporal_label` (for example `youth` or `before_arrival`), kept separate from write time;
- participants, places, objects and context;
- complete original text/transcript and durable media references;
- derived features when available;
- what Elfie observed, was told, inferred or felt, with attribution;
- source references, privacy scope, `importance`, `retention_days`, `detail_level`, `lifecycle`, version and content hash.

Runtime learning is written in full before graph projection. For example, learning Newton's first law stores the explanation, teaching context and source in one Episode; later maintenance projects reusable knowledge from it. Genesis seed content remains complete in its approved source, with personal biography seeds represented as complete Episodes.

Later maintenance may change detail from `full` to `compressed` or `digest`, and may archive the record as a separate lifecycle state. A summary never replaces the last auditable source required by the graph.

### 2.2 Personal Knowledge Graph

The graph is Elfie's sourced, subjective understanding. It is not an objective universal database and does not silently import model knowledge. It is a durable projection that can be rebuilt and reconciled from complete Episodes, approved seed sources and their Evidence; a projection revision identifies the source version it reflects.

#### 2.2.1 Nodes

Nodes are heterogeneous semantic anchors: Elfie, people, pets, groups, planets, places, facilities, objects, foods, species, concepts, cultural ideas, physical laws, theories, emotions, subjective experiences, event references and Claim/knowledge objects.

A Node has stable identity, `node_type`, canonical label, scope, status, `importance`, `retention_days` and `confidence`. Aliases and sourced descriptions are associated with the Node. Broad and specific concepts use typed relations such as `part_of`, `subtype_of` and `generalizes`. Not every word becomes a Node; reusable semantic units are canonicalized while full wording remains in descriptions or Episodes.

#### 2.2.2 Assertions / Relations

An Assertion is a sourced proposition. A simple proposition is a typed directed relation:

```text
Earth --has_shape--> sphere
Owner --helped--> Elfie
```

It may include a node or typed literal as object, polarity, epistemic status, time range, viewpoint, context, validity interval, conflict group, `importance`, `retention_days` and `confidence`.

For a social tie or another domain-specific degree (for example familiarity or trust), the Assertion carries a typed qualifier; its `importance` is the default edge significance used for recall and maintenance. Evidence rows and their stances provide the support record; no third semantic score is stored.

When a proposition has its own conditions, versions, descriptions or evidence, it is represented by a Claim/knowledge Node and related Assertions instead of forcing a sentence into one edge:

```text
NewtonFirstLaw --part_of--> ClassicalMechanics
NewtonFirstLaw --related_to--> Inertia
NewtonFirstLaw --has_condition--> NetForceIsZero
```

A missing relation means “not recorded”, not “false”.

#### 2.2.3 Evidence

Evidence is a first-class source link. It identifies an Episode or `ApprovedSeedSource`, its source version, excerpt or media locator, modality, text span, capture time, speaker/viewpoint and extraction run. An Assertion–Evidence link has one stance: `supports`, `contradicts` or `context`.

One Assertion may have many independent Evidence links. Replaying the same source link is idempotent. Evidence remains available when a description is compressed or a model proposal is discarded.

#### 2.2.4 Aliases, Descriptions, Episode Mentions

Aliases, descriptions and mentions are separate child records because each Node can have many of them and each can retain its own source/locator, content or span, kind/resolution state and confidence. They have no independent importance score; their availability follows the parent/source retention policy. The Node row keeps only its canonical identity and bounded summary.

`episode_mentions` records semantically meaningful surface mentions, their role/span and resolution state (`resolved`, `ambiguous` or `unresolved`). It does not record every token. Unresolved mentions and raw wording remain searchable in the Episode, so a rare term can be found even before it becomes a canonical Node.

The initial implementation bounds semantic mentions per Episode (128 by default) and reports overflow; the complete source text is never truncated.

#### 2.2.5 Conflicts, viewpoints and Claim Nodes

Contradictory or perspective-dependent propositions remain separate Assertions in a conflict group. Polarity, epistemic status, validity time and viewpoint are preserved; canonicalization merges identity, not disagreement. A Claim Node is used when the proposition itself needs conditions, versions or multiple descriptions. No Assertion is promoted without a source link.

### 2.3 Scores and lifecycle states

#### 2.3.1 importance

`importance` (`I`) is the durable semantic significance of an Episode, Node or Assertion to Elfie, in `[0, 1]`. It is not freshness, familiarity, evidence count or retrieval frequency, and natural time never changes it. A qualified semantic event moves `I` toward a policy-owned target `T_I`:

```text
raise when T_I > I: I' = I + eta * (T_I - I)
lower when T_I < I: I' = I + eta * (T_I - I)
```

The `memory.v2` event classes are `routine` `(T_I=.35, eta=.10)`, `meaningful` `(.60, .20)`, `major` `(.85, .35)` and `core` `(1.0, .50)`. Auditable reappraisal uses `ordinary-lower` `(.30, .25)`, `major-lower` `(.10, .50)` or `revoked` `(0, 1)`. A model may propose an event class but cannot choose `T_I` or `eta`. Node and Assertion importance are independent and never propagate through graph adjacency.

Updates are idempotent by `(event_id, target_kind, target_id)`. Repeated signals for the same target, direction and class are collapsed once per ClosedEpisode. Across Episodes, raise and lower directions are aggregated separately into chronological 24-hour windows anchored by the first event in each window; only the highest accepted class in that direction/window contributes. Opposite directions remain distinct reappraisals and are folded in event-time order. Receipts retain source, occurrence time and policy version; late events are replayed in `(occurred_at, event_id)` order so arrival order cannot change the result. Expiry, disuse, recall failure and contradictory Evidence do not lower `importance` without a separate sourced reappraisal event.

#### 2.3.2 Retention and freshness

Each Episode, Node and Assertion stores `retention_days` (`D > 0`), `last_reinforced_at` and a retention policy version. `D` is the span from a fresh state to the ordinary-recall boundary, not a half-life or a remaining-day counter. Current `freshness` (`F`) is derived and never persisted:

```text
t = max(0, now - last_reinforced_at)
F(t) = 1 / (1 + 9 * (t / D)^2.6)
```

Therefore `F(0)=1`, `F(D/2)~=0.4` and `F(D)=0.1`. Runtime admission uses versioned initial spans: transient detail `2` days, ordinary memory `7` days and salient/major experience `30` days. Strong sourced emotional or sensory salience may select the 30-day admission class through bounded deterministic appraisal; it does not automatically raise importance or confidence, and a later emotion/sensory Recall hit is not reinforcement. Every Genesis-created Episode, Node and Assertion starts at `3650` days. The global bound is `36500` days.

Only an active record with `F >= .1` may be reinforced, and only after one of these sourced outcomes: an exact prior use is explicitly confirmed helpful/correct, an action using it succeeds, a deliberate review/rehearsal completes, or new independent Evidence directly revisits it. Merely completing a chat answer is not confirmation. Candidate generation, RecallBundle/Prompt inclusion, graph adjacency, emotion/sensory hits, maintenance, model self-certification and failed/rejected/unknown outcomes do not qualify. A correction is handled as new Evidence: it may strengthen retention while lowering confidence. For one unique qualified event:

```text
q = (1 - F) / .9
D' = min(36500, D * (1 + q^2))
last_reinforced_at = event.occurred_at
```

The update is target-scoped and idempotent. Target-serialized receipts are replayed in event-time order so late delivery cannot reset the clock to processing time. Receipt times use authoritative UTC; an event beyond a bounded future-skew tolerance is rejected, a small negative read delta is clamped to zero, and a missing original occurrence time is not replaced by processing time. When `F < .1`, the record is archival and the expired `D` cannot be reinforced. Encountering the same content is relearning: write a new Episode/Evidence, use the normal write-side identity resolver's bounded lookup across archived/forgotten fingerprints, reuse a resolved Node/Assertion identity, reset `D` to the new admission span and set freshness to one. This lookup is not ordinary Recall or a second Retriever. A non-superseded match may return to `active`; a superseded Assertion requires a sourced reappraisal/reversal and never reactivates merely because it was mentioned.

#### 2.3.3 confidence

`confidence` (`C`) exists on Nodes and Assertions only. A Node's value expresses identity-resolution reliability; an Assertion's value expresses proposition reliability. Episode attribution and provenance remain explicit but an Episode has no confidence score. Time, importance, recall and retention reinforcement do not change `C`.

The policy recomputes `C` from the complete set of unique Evidence rather than applying arrival-order increments:

```text
C = (prior_weight * initial_confidence + sum(support_weight))
    / (prior_weight + sum(support_weight) + sum(conflict_weight))
```

Evidence weights come from a versioned source policy. Repeated IDs are ignored. Correlated sources share an `independence_key`; within one `(independence_key, stance)` group only the highest source weight contributes, while support and contradiction remain separate stances. `context` Evidence does not affect `C`. Assertion confidence uses its `assertion_evidence`; Node confidence uses unique sourced identity observations attached through aliases, descriptions and mentions, never scores propagated from adjacent Assertions. Corrections preserve the old low-confidence/superseded Assertion, create the corrected Assertion and connect the history. New contradicting Evidence may reinforce retention while lowering confidence; remembering a former belief clearly does not make it true.

The sourced admission establishes immutable `initial_confidence`, `prior_weight` and confidence-policy version metadata for each Node/Assertion; these are replay inputs, not additional live scores. The admission source is represented by that prior and is not counted again in the support sum. Genesis may provide its approved initial confidence; runtime admissions receive a prior from their fixed source-reliability class, never from an unconstrained model float. A policy upgrade requires an explicit versioned recomputation and cannot silently rescore records on reopen.

#### 2.3.4 Lifecycle eligibility (no additional score)

Time and `D` produce `F`; `F` drives lifecycle eligibility. Lifecycle never lowers `F` and never changes `I`, `D` or `C`. Child aliases, descriptions and mentions follow their parent/source dependency. The design stores no freshness or composite retrieval score.

#### 2.3.5 detail level

`detail_level` describes Episode content resolution: `full`, `compressed` or `digest`. Episode `lifecycle` describes availability as `active`, `archived` or `forgotten`. Archiving is a state transition, not a fourth content level; an archived Episode may still retain a full, compressed or digest representation. Assertion lifecycle may be `active`, `superseded`, `archived` or `forgotten`, but an Assertion's last auditable Evidence cannot be removed by maintenance. A historical `life_stage` records the Elfie's developmental phase at the time of an experience; `temporal_label` is its relative period (for example `before_arrival`). Neither is `Lifecycle Stage`, `lifecycle` or `detail_level`. For Nodes, `status` and merge state govern identity availability; maintenance may archive a cold Node but cannot alter its importance or erase a canonical Node still referenced by Assertions.

## 3. Runtime flows

```text
One-time Genesis
ApprovedSeedSource ──► Genesis manifest
                         └─ each submission: atomic commit ──► its Memory outputs + marker

Normal runtime
Workspace closes ClosedEpisode ── capture transaction ──► complete Episode + source references
                                                           │
                                                           ▼
                                                   Memory Maintenance
                                                   ├─ Consolidation Stage
                                                   │  Episode ► graph projection + score updates
                                                   └─ Lifecycle Stage
                                                      due records ► freshness-driven detail/lifecycle policy

Episodes + Nodes + Assertions + Evidence ──► Hybrid Recall ──► bounded RecallBundle
```

Genesis is a one-time side entrance. The normal path never writes graph facts from an incomplete event, and capture does not wait for maintenance.

### 3.1 Genesis initialization

`ApprovedSeedSource` is immutable, versioned and hashable. A Genesis manifest has exactly three seed families: `KnowledgeSeed[]` (known world/knowledge), `EpisodeSeed[]` (the individual's past, each materialized as a complete Episode) and `RelationshipSeed[]` (typed relationship Assertions linked to Episodes or seed Evidence). There is no fourth biography or relationship memory category: biography is the Episode materialization and relationships are the RelationshipSeed projection. World/knowledge and relationship seeds may be directly projected; every `EpisodeSeed` must remain a complete Episode, and its derived Nodes/Assertions may also be projected in the same complete package. All outputs carry seed Evidence.

Genesis uses a submission-level completion contract. A Genesis submission is one complete, immutable set of Memory outputs supplied to Memory for one atomic commit. Genesis may call Memory any number of times; Memory does not choose the number, size, order, grouping, scheduling or meaning of those submissions (for example, core versus enrichment or foreground versus night work). Each submission has its own stable submission/idempotency identity and content hash, even when several submissions belong to one higher-level Genesis operation.

For one valid submission, every expected authoritative and child record—Nodes, Assertions, Evidence, biography Episodes, aliases, descriptions and mentions—and that submission's completion marker must be durable and visible as one completed unit. Atomicity means “accept only the current submission”: validation happens before any write; the Unit of Work either commits every output and the marker or commits none of them. A failed call returns only a failed or retryable result and never `committed`. Retrying the same submission identity and hash is idempotent; reusing an identity with a different hash is rejected. Previously committed submissions remain valid when a later submission fails.

The Genesis caller owns batching, ordering, retry timing and the decision about when adoption is published. Memory only exposes committed submissions to readers and maintenance; it does not report an overall Genesis operation as complete. A committed Elfie cannot be silently reinitialized by a different manifest; an upgrade is a separate approved operation. Cross-owner adoption publication remains its own contract and is not a fictitious cross-store transaction. Genesis accepts explicit initial Episode/Node/Assertion `importance` and Node/Assertion `confidence`; every Genesis-produced semantic record starts with `retention_days=3650`. It does not simulate conversations or manufacture importance with emotion intensity. Direct graph projection is forbidden for normal runtime callers.

Genesis admission is serialized per Elfie. The completion marker is the sole visibility gate for Genesis rows: no reader or maintenance pass may use a row from that submission before its marker is present. Genesis accepts any valid complete submission, including a submission containing only a subset of the approved seed families. It does not require every seed family in every submission and does not infer a caller's batching policy.

### 3.2 Normal runtime write

The upstream Workspace closes and validates an event, then supplies a complete `ClosedEpisode`. The capture transaction writes the Episode, idempotency key, source references and content hash. It does not call a model and does not update Nodes/Assertions from incomplete content. Graph Evidence links and projection happen later in Consolidation Stage; the text projection is rebuildable and is not a second source.

### 3.3 Memory Maintenance

Memory Maintenance is one bounded operation. It may run in small continuous batches and use idle/sleep time to catch up. It has two ordered stages and one budget policy. Checkpoints, leases and retry attempts are operational control state outside authoritative Memory fact records; they are not a semantic memory type, a recallable queue or a second fact source.

#### 3.3.1 Consolidation Stage

For complete Episodes with no successful projection for the current source version/content hash (including a prior failed attempt):

1. extract events, mentions, concepts and candidate Claims from the source;
2. resolve aliases, coreference and entity identity;
3. normalize predicates and choose a relation or Claim Node;
4. merge compatible Assertions, retain independent Evidence and record conflicts;
5. recompute Node/Assertion `confidence` from unique Evidence, emit only qualified sourced importance events, and reinforce only the exact records directly revisited by new independent Evidence;
6. commit the projection and record the successful source/projection revision.

Predicates come from a versioned vocabulary. An unknown predicate stays an unresolved candidate until validated; it is never silently promoted to a fact.

A model may propose extraction, disambiguation or a summary outside the write transaction. Deterministic code validates spans, types, scope, predicates, IDs, Evidence and revisions, and performs the final write. Without a model, Episode capture and FTS remain usable; semantic projection waits for a later attempt. There is no keyword gate and no ungrounded fact fallback.

#### 3.3.2 Lifecycle Stage

For any Episode or Assertion with active `lifecycle`, or Node with active `status` and no canonical merge target, whose derived freshness threshold is due—independent of capture date—apply the lifecycle policy without mutating `importance`, `retention_days`, `confidence` or `last_reinforced_at`:

- `F <= .40`: an eligible projected Episode may move `full` to `compressed`;
- `F <= .20`: an eligible projected Episode may move `compressed` to `digest`;
- `F < .10`: an eligible active record becomes archival and leaves ordinary Recall;
- `F <= .01` and `I <= .10`: after at least 90 archived days, mark the record `forgotten` only when source and graph dependency checks allow it.

One transaction advances at most one stage. An Episode without a successful projection for its current source version retains enough complete source for projection. Automatic forgetting is logical: a minimal digest, hash and provenance remain; physical deletion is outside `memory.v2`. Low confidence is never a deletion reason. An old record is found by its calculated `next_review_at`, not by the current capture batch, and one unsafe target does not block other bounded records.

### 3.4 Hybrid Recall

Recall is deterministic and index-driven on the hot path; it does not require a model call.

#### 3.4.1 Basic / Text Search

Lexical/full-text search (and an optional vector index) finds exact names, aliases, rare terms, original wording, detailed stories and source/media references. It is the fallback for details not yet canonicalized in the graph.

#### 3.4.2 Local / Graph Search

Starting from text hits or supplied Node/Claim IDs, bounded typed traversal follows relationships to people, places, concepts, emotions, events and supporting Episodes. Traversal keeps a visited set, does not revisit a Node within one path, and returns explicit paths; hop, neighbor and result limits are hard caps. Person, time, place, historical emotion, topic and cause facets constrain or rank the same source-grounded candidates.

#### 3.4.3 Global Search (later capability)

Broad thematic or community search is deferred until the graph has representative density. Any summary must remain traceable to Assertions and Episodes; it is not a new fact source.

#### 3.4.4 RecallBundle

The minimum route is Basic/Text → seed Nodes/Episodes → bounded Local/Graph expansion → source Episode/Evidence fetch. Privacy, namespace and lifecycle filters run before ranking. Query relevance `R` combines lexical/semantic match, path and requested time/facets; Memory then derives `A=.65F+.35I`. Active Nodes/Assertions rank by `R*A*(.25+.75C)`, while Episodes, which have no confidence, rank by `R*A`. Superseded/conflicting Assertions use a separate `R*A` lane so low confidence does not hide history. Each kind has its own bounded quota and stable-ID tie-breaker; `D` is not scored again because it already determines `F`.

### 3.5 Deferred Memory Abstraction Loop

This capability is intentionally not implemented in the current baseline. Its complete future loop is:

```text
Node + Assertion → nightly graph-first grouping → model proposal + deterministic validation
                 → Pattern knowledge Node → scene-aware recall → Reasoning application
                 → outcome feedback
```

Grouping starts from related Nodes and sourced Assertions already in the graph. Episodes are consulted only to verify provenance and original context, not as the primary clustering surface. This is a future extension of Consolidation Stage, not a third Memory Maintenance stage or another entry point. An accepted Pattern is a reusable Claim/knowledge Node containing a canonical rule, applicability conditions and limitations/counterexamples. Its derivation must retain references to supporting Nodes, Assertions or lower Patterns and their underlying Evidence; the physical representation is deferred with the capability.

Pattern generation must not ship alone. The same vertical slice must accept a typed current-scene signature from its owner, retrieve applicable Patterns by direct match or upward graph traversal, preserve the rule, conditions, counterexamples and provenance in `RecallBundle`, let Reasoning decide whether to apply it, and capture the outcome as a new Episode that can later support, refute or narrow the Pattern. Until these paths and their evaluation exist together, Pattern abstraction is not a supported Memory behavior.

### 3.5 Deferred Memory Abstraction Loop

This capability is intentionally not implemented in the current baseline. Its complete future loop is:

```text
Node + Assertion → nightly graph-first grouping → model proposal + deterministic validation
                 → Pattern knowledge Node → scene-aware recall → Reasoning application
                 → outcome feedback
```

Grouping starts from related Nodes and sourced Assertions already in the graph. Episodes are consulted only to verify provenance and original context, not as the primary clustering surface. This is a future extension of Consolidation Stage, not a third Memory Maintenance stage or another entry point. An accepted Pattern is a reusable Claim/knowledge Node containing a canonical rule, applicability conditions and limitations/counterexamples. Its derivation must retain references to supporting Nodes, Assertions or lower Patterns and their underlying Evidence; the physical representation is deferred with the capability.

Pattern generation must not ship alone. The same vertical slice must accept a typed current-scene signature from its owner, retrieve applicable Patterns by direct match or upward graph traversal, preserve the rule, conditions, counterexamples and provenance in `RecallBundle`, let Reasoning decide whether to apply it, and capture the outcome as a new Episode that can later support, refute or narrow the Pattern. Until these paths and their evaluation exist together, Pattern abstraction is not a supported Memory behavior.

## 4. Typed access contracts

These contracts freeze semantic inputs, outputs and guarantees, not programming-language method names. Concrete names may change in the implementation and belong in code and Conformance records.

### 4.1 Episode capture

Input is a complete `ClosedEpisode` with a stable ID or idempotency key, occurrence range, content/media, attribution, source references and hash. The hash covers the complete persisted source payload and referenced-source versions, not a summary or derived projection. Output is a receipt containing the durable Episode ID and state. The operation is atomic and idempotent; it never creates graph facts from partial content.

### 4.2 Recall

`RecallRequest` may specify text, seed Node/Claim IDs, node types, relation allowlists, time range, person/place/historical-emotion/topic/cause facets, retrieval mode and limits. It never contains SQL or graph query language.

The Memory Port is bound to one Elfie namespace; the request cannot widen that scope.

Default hard limits are: 20 lexical hits, 8 seed Nodes, 2 graph hops, 12 neighbors per expanded Node, 40 Nodes, 80 Assertions, 8 Episodes, 24 Evidence items and 12,000 rendered characters. A caller may request lower limits; a higher request cannot bypass the Memory cap.

The output is a bounded `RecallBundle`:

```text
RecallBundle {
  focus_nodes: [{id, type, label, description, relevance,
                 importance, freshness, confidence}],
  assertions: [{id, subject, predicate, object, qualifiers, status,
                relevance, importance, freshness, confidence, evidence_ids}],
  paths: [{node_ids, assertion_ids, hop_count}],
  episodes: [{id, time_range, life_stage, temporal_label, excerpt,
              detail_level, relevance, importance, freshness, source_event_ids}],
  evidence: [{id, source_type, source_id, source_version,
              span_or_locator, stance}],
  conflicts: [{assertion_ids, reason}],
  limits: {requested, returned, truncated}
}
```

Graph supplies structure, Episodes supply detail, Evidence supplies grounding, and the consuming layer supplies narration.

### 4.3 Qualified use and outcome feedback

A completed answer, action or narrative may first record a bounded use proposal containing its occurrence time, exact Memory record IDs and the claim/action/narrative segments they supported. Model-produced references are proposals only: deterministic code accepts only IDs supplied in that turn, bound to the same Elfie namespace and Recall context revision, and enforces per-outcome bounds. A proposal is not a reinforcement event.

A typed reinforcement receipt is emitted only after an authoritative outcome: explicit user confirmation, deterministic action success, completed deliberate rehearsal, or new independent Evidence. It contains a stable event ID, the original use/review occurrence time, exact accepted targets, outcome kind and durable outcome/source reference. A model cannot certify its own success. Rejected, failed or unknown outcomes produce no generic reinforcement; a correction may instead produce contradicting Evidence.

The authoritative outcome is committed before feedback delivery. Memory consumes the receipt atomically and idempotently; a stable event ID makes a crash between the outcome store and Memory retryable without duplicate reinforcement. The receipt reinforces only the exact accepted targets and never graph neighbors.

### 4.4 Memory Maintenance

Input is a bounded batch/time budget and an operational maintenance checkpoint. The operation runs Consolidation Stage before Lifecycle Stage, commits only validated source-linked changes, records retryable failures in operational control state without losing the Episode, and returns counts/checkpoint/status. Model inference, if used, happens before the write transaction; it is never the authority for a final fact.

### 4.5 Source inspection

Authorized Memory callers and diagnostics may request one bounded Episode or Evidence record by stable ID, including its source content, detail state and provenance. Inspection is read-only and does not become an implicit chat-history or Profile read.

### 4.6 Idempotence, failure and budget constraints

Every write has a stable idempotency key or fingerprint. A Unit of Work is short, uses one serialized SQLite writer, and never waits for a model, network, device or world runtime. Leases/checkpoints make interrupted maintenance retryable; a failed attempt leaves source content and Evidence intact. Recall enforces limits on text hits, graph hops/neighbors, returned Assertions/Episodes/Evidence and rendered characters, and reports truncation explicitly.

## 5. SQLite physical implementation

### 5.1 Authoritative fact tables

SQLite is the first physical implementation. One Memory Adapter/database is bound to one Elfie namespace; a caller cannot query another Elfie's rows. The following tables are authoritative facts; JSON columns are bounded metadata only and never hide graph edges or provenance.

| Table | Required responsibility |
| --- | --- |
| `episodes` | Complete source content, occurrence range (nullable when unknown) and occurrence precision, historical `life_stage`/`temporal_label`, separate write time, attributed context/media/source references, privacy scope and version, `importance`, `retention_days`, reinforcement/lifecycle metadata, `detail_level`, `lifecycle`, successful projection marker, idempotency key and content hash. Episodes have no confidence column. |
| `nodes` | Canonical identity, type/label, scope/status, bounded summary, `importance`, `retention_days`, `confidence`, immutable confidence-prior/policy provenance, reinforcement/lifecycle metadata and merge pointer. |
| `node_aliases` | Many scoped aliases with their own source and confidence. |
| `node_descriptions` | Many language/kind-specific descriptions, content hash and source link. |
| `episode_mentions` | Episode-to-Node links, roles/spans and resolved/ambiguous/unresolved state. |
| `assertions` | Subject, predicate, Node or explicitly typed-literal object (type/value/unit), qualifiers, polarity, epistemic status, viewpoint/context, validity, `importance`, `retention_days`, `confidence`, immutable confidence-prior/policy provenance, reinforcement/lifecycle metadata, conflict group, lifecycle state and fingerprint. |
| `evidence` | Episode or seed source locator, source version, excerpt/media span, modality, speaker/viewpoint, capture time, `independence_key`, source-reliability class/policy version and extraction metadata. |
| `assertion_evidence` | Many-to-many Assertion/Evidence stance: `supports`, `contradicts` or `context`. |
| score event receipts | Adapter-private, non-recallable, source-linked importance and qualified-use/retention events used for idempotency, aggregation and event-time replay. They are authoritative policy inputs/audit state, not a semantic memory type or second source of remembered claims. |

Each Genesis submission's ID/version/hash and completion marker are durable package metadata owned by the Memory Adapter, not a semantic Node/Assertion and not a retry queue. The marker lives in the same Memory SQLite database and is committed in the same transaction as that submission; its physical metadata record/table name is adapter-private and is not an additional semantic memory table. The marker is written only after every expected Memory row, including child rows, is ready for the commit. Every Genesis-produced row carries the submission identity, and readers ignore rows whose submission marker is absent. A retryable or interrupted submission is not an initialized Memory and is not recallable as one; its operational control state may be reconstructed from the immutable input. The marker records (or hashes) the expected IDs/counts for each output family so reconciliation proves more than the presence of Node rows. Derived FTS/vector indexes and RAM caches are not part of the fact-package completion check and may be rebuilt only after the complete commit. These records do not form a second mutable fact store. `importance` and Node/Assertion `confidence` are semantic scores; `retention_days` is persisted policy state, while freshness and query rank are derived. Evidence rows and their stances remain the authoritative support record.

### 5.2 Derived indexes and cache

`episodes_fts` and `nodes_fts` are rebuildable full-text projections over source text, summaries, labels, aliases and sourced descriptions. An optional vector index is a later optimization, never a first-implementation prerequisite, and is also derived. Required lookup indexes cover lifecycle/status plus `next_review_at`, Episode successful projection revision/time/hash, Node normalized label/type/status, aliases `(normalized_alias, scope)`, descriptions `(node_id, language, kind)`, mentions by Node and Episode, Assertions by subject/predicate and object/predicate, conflict/supersession, Evidence source/independence key, both directions of `assertion_evidence`, and unique score-event receipts. Recall first obtains a bounded indexed candidate set and derives freshness/rank only for that set; it never computes freshness across the whole database. Operational leases, retry attempts and checkpoints are bounded controls and never returned by Recall. A non-null successful projection revision is a durable marker tied to the Episode source version/content hash; absence, or a revision tied to an older source hash, means that the current projection has not been committed. Each index exists for a bounded query and declares its rebuild source. The first implementation stays on the embedded relational store; a dedicated graph engine is not a prerequisite.

Score receipts also have bounded operational growth. Within a versioned late-arrival safety window, complete receipts remain replayable. After the source outcome/Evidence is durable, all local outbox events through a target watermark are settled and the window expires, importance receipts compact to the highest class per direction/window and reinforcement receipts fold into a checkpoint that retains policy version, folded state, event count/hash and last event time. A receipt older than the settled watermark is rejected into observable reconciliation state; it never silently changes the score or substitutes processing time. This compaction applies only to score-control receipts, never to semantic Episodes, Evidence or conflict history.

RAM holds bounded hot Nodes, adjacency pages, recent neighborhoods and index pages. A cache miss reloads durable rows; it never constitutes memory loss. Media is loaded on demand.

### 5.3 Constraints, uniqueness and conflict preservation

Foreign keys are enabled and deletion is restricted by default. Episode idempotency keys and content hashes prevent duplicate capture. An Assertion fingerprint includes normalized subject, predicate, object, qualifiers, polarity, viewpoint and validity; it does not collapse distinct times, perspectives or conflicts. Evidence identity also includes source version, modality and locator/span, so the same locator in a new source version is a distinct source link. Exact replay is idempotent.

Aliases may be ambiguous across scope. Mentions may remain unresolved. Descriptions deduplicate by Node/language/kind/content hash while retaining separate sourced versions. An Assertion has exactly one Node object or one typed-literal object. Queryable assertion fields and qualifiers are columns or explicit indexed child records; a typed literal uses mutually exclusive node-ID versus type/value/unit fields, and bounded JSON is only non-queryable metadata. Node merges keep the old ID and point to the canonical ID. No bare-triple unique key may overwrite evidence or disagreement.

### 5.4 Transactions and Unit of Work

Genesis applies the completion guarantee in §3.1: it validates one complete submission before opening one submission-scoped transaction, writes every Memory output (Nodes, Assertions, Evidence, Episodes and child records) and that submission's marker in the same commit, and returns success only after the complete set is reconciled. A failed commit is not a completed state; the same immutable submission remains unpublished and can be retried with the same identity and hash. Earlier successful submissions are not rolled back by a later failure. Normal capture commits the complete Episode and its source references together; its derived text index may be updated in that transaction or rebuilt after commit. Maintenance validates model proposals outside the transaction, then commits graph changes, Evidence links, score updates, lifecycle and successful projection revision in one short Unit of Work; derived indexes are updated or rebuilt only after the fact commit and never decide whether the fact package completed. A transaction never includes model or network calls.

SQLite uses `PRAGMA user_version`, foreign keys, WAL, a bounded busy timeout and one serialized writer. Derived indexes can be deterministically rebuilt from authoritative tables.

### 5.5 Restart recovery

Episodes, Nodes, Assertions and Evidence survive restart. Maintenance claims bounded records with operational leases/checkpoints; an expired lease is reclaimable. A crash before a normal commit leaves the source unchanged; a crash after commit is recognized by the idempotency key/fingerprint. A crash before a Genesis submission commit leaves that submission unpublished; recovery checks the same immutable submission identity/hash and retries that submission. The `committed` state is valid only when every expected output, child record and that submission's completion marker are present. FTS and RAM caches are rebuilt when missing.

## 6. Lifecycle, recovery and fresh-store policy

### 6.1 Episode detail lifecycle

Lifecycle is the detail and availability state of an already stored record, not a new memory type. A due-time scan covers old and new records alike. `next_review_at` is the predicted wall-clock crossing of the next freshness threshold and is recalculated when retention changes; maintenance frequency therefore cannot change freshness. Lifecycle consumes derived `F` but never updates `I`, `D`, `C` or the reinforcement anchor. An Episode without a successful projection for its current source version keeps enough complete source for a future projection; a projected Episode may move from `full` to `compressed` or `digest`, while archiving is a separate availability state. Both changes require source and graph-dependency checks.

### 6.2 Source Evidence protection

An Evidence row that is the last auditable source for an active Assertion cannot be deleted. Compression may shorten an Episode's rendered detail, but it preserves a hash plus an excerpt, locator or digest sufficient to trace the Assertion. Seed sources and their versions remain immutable. Any destructive deletion is explicit, reversible during development and reported by ID. An explicit owner correction is a new sourced Episode/Assertion and may supersede an older Assertion; it never mutates the historical source in place.

### 6.3 Compression, archive, digest and forgetting

Lifecycle maintenance first reduces Episode detail at `F <= .40` and `F <= .20`, then archives records at `F < .10`. Only an item with `F <= .01`, `I <= .10`, at least 90 archived days and safe source/graph dependencies may become logically forgotten. Episodes without a successful projection for their current source version retain their source. Forgetting keeps a minimal digest, hash and provenance and does not automatically delete Nodes, Assertions or the last auditable Evidence. Relearning an archival item is a new sourced event, not a maintenance transition or a continuation of the expired retention span.

### 6.4 0.x fresh-store policy

Before the 0.5 data-compatibility baseline is frozen, Memory supports only a fresh database created by the current schema. An old or mixed database is rejected before any business write. Runtime does not import, replay, dual-write or fallback-read legacy Memory data. An operator may back up the exact data root and explicitly rebuild it; the application never deletes or overwrites an old database automatically.

The old `entities`, `events`, `entity_edges` and related tables are therefore discarded by policy, not transformed in place. A reset-required result identifies the database path and leaves the rejected file unchanged. Fresh initialization creates only the current Episode, graph, Evidence and operational tables.

## 7. Non-negotiable invariants

1. Runtime content is complete in an Episode before extraction; Genesis content is complete in its approved source before projection.
2. Every durable Assertion has Episode or seed Evidence; model output alone is never a fact.
3. Canonicalization merges identity, not contradictory viewpoints or unrelated entities.
4. Conflicting Assertions retain polarity, time, perspective and source.
5. Graph summaries, vectors and scores cannot outrank source grounding without explicit epistemic status.
6. Episodes are the detailed historical line; the graph is its structured semantic projection.
7. Live state, plans, commitments, permissions and actions remain with their owning systems.
8. Memory never directly reads Profile, Communication history or world runtime state.
9. Genesis direct projection is limited to approved submissions and cannot become runtime CRUD.

## 8. Validation and stage gates

Each implementation round closes only with code and replayable evidence. The target design is not proof that the current implementation already conforms.

### 8.1 Source integrity

Verify complete Episode capture, content hashes, idempotency, atomic Genesis submission completion, retry behavior and reopen-after-restart. Gate: 100% of accepted fixtures preserve source hashes, every accepted submission reaches a complete marker with all expected child records, and no uncommitted submission output is visible.

### 8.2 Graph provenance

Verify mention resolution, canonicalization, Assertion/Evidence links, Claim Nodes, independent descriptions and conflict retention. Gate: every fixture Assertion has a resolvable source; unsupported proposals are rejected.

### 8.3 Hybrid retrieval

Replay a rare term, a relationship-network query, a knowledge object, an emotion facet and a time-bounded experience. Verify Basic/Text fallback, bounded Local/Graph paths, RecallBundle provenance and explicit truncation. Initial targets: rare-term recall@5 ≥ 0.90 and relationship-path precision = 1.00.

### 8.4 Importance, retention, confidence and conflicts

Verify target-ceiling importance updates and 24-hour aggregation, event-time replay, checkpoint-compaction equivalence and pre-watermark late-event rejection, the frozen freshness vectors, reinforcement eligibility/growth/cap, expiry and relearning, Evidence-order-independent Node/Assertion confidence, and the absence of Episode confidence. Time and Lifecycle must not mutate importance, retention or confidence; candidate-only Recall must not reinforce; contradictory Evidence remains visible and may lower confidence while strengthening retention.

### 8.5 Performance and capacity

Measure both maintenance stages, bounded RAM, growth/retention behavior and database-only Basic + Local p95 ≤ 150 ms on a representative 10,000-Episode / 50,000-Node / 200,000-Assertion fixture. The endurance gate must also prove that an old or mixed database is rejected without mutation and that a fresh database can be rebuilt and reopened.

## 9. Resolved implementation decisions

This section closes implementation ambiguities identified during review. It is normative for the Memory implementation, but it does not assign Genesis batching, ordering or scheduling to Memory.

### 9.1 Source shape, namespace and privacy

- The Memory Adapter is constructed for one immutable `elfie_id`; every read, write, maintenance operation and Genesis submission is checked against that namespace. A caller cannot widen it through a request or raw identifier.
- `occurred_from` and `occurred_to` may be unknown. An explicit occurrence-precision value distinguishes an exact instant, a bounded range and an unknown time; unknown time is not replaced with a fake epoch and is excluded from time ranking unless the caller requests an unknown-time facet.
- Episode attribution is typed as `observed`, `told`, `inferred` or `felt`. Participants, places and objects are represented by bounded `episode_mentions` roles; scene context is retained as bounded source context, not hidden graph edges.
- Source and media references carry version/locator/hash data. Privacy scope is enforced at the Memory boundary and is included in source inspection and Recall filtering; it is never inferred from a display label.
- Corrections create a new sourced Episode/Assertion. The historical source row and its version are not mutated in place.

### 9.2 Scores, review and lifecycle

- `importance` and Node/Assertion `confidence` are persisted semantic scores; `retention_days` is persisted policy state. Episode has no confidence; freshness and composite retrieval rank are derived and never persisted. There is no `support_score` compatibility field.
- Importance is folded in event-time order from idempotent, source-linked, aggregated semantic-event receipts. Confidence is recomputed from all unique Evidence and independence groups. Retention is folded from idempotent, target-scoped qualified-outcome/review receipts; expired-memory relearning is a new sourced admission, not a receipt against the old span. A retry or maintenance pass cannot add a contribution twice.
- Episodes, Nodes and Assertions carry `retention_days`, reinforcement/review timestamps and policy version. Lifecycle selection is a due predicate calculated from freshness, not another score.
- Lifecycle transitions are guarded and ordered: preserve a source that lacks a successful current projection; then allow `full` → `compressed` → `digest`, archive separately, and forget logically only after freshness, importance, residency and dependency checks. Forgetting never removes the last auditable Evidence for an active Assertion.
- Consolidation leases, retry attempts, checkpoints and rejected proposals are operational control data outside authoritative fact rows. One bounded Memory Maintenance Unit of Work owns the writer transaction; normal capture and Genesis submissions remain separate operations.

### 9.3 Projection and predicate validation

- Predicates are resolved against a versioned registry with explicit aliases and deprecations. The registry version is recorded with each successful projection.
- An unknown or invalid model proposal is retained only as bounded diagnostic/retry data and is never inserted as an active Assertion. It can be retried after the registry or source validation changes.
- A successful projection records `(source_version, source_hash, projection_revision)`. Missing or stale revision means the current source still needs projection; a retry does not create a second Episode.
- Runtime callers use only the source-first typed path. Legacy `add_edge`/bare-edge writes are removed after their callers are migrated; they are not a runtime or migration API.

### 9.4 Recall semantics

- Facets are positive constraints: different facet families combine with AND, values within one family combine with OR, and missing facet data does not become a negative fact. Historical emotion is read from the Episode's attributed source, never from live Emotion state.
- Ranking is deterministic and kind-specific: derive query relevance `R` and freshness `F`, then use `R*(.65F+.35I)*(.25+.75C)` for active Nodes/Assertions and `R*(.65F+.35I)` for Episodes and the conflict lane. Results remain separated by kind with stable-ID tie-breakers; policy components are bounded and versioned.
- Active Assertions are preferred, while relevant `superseded` and conflicting Assertions remain visible with explicit status and Evidence. Privacy and namespace filtering happen before ranking.
- Basic/Text and Local/Graph are the initial modes. Global/community and vector retrieval remain derived, later capabilities and are not advertised by the initial contract.

### 9.5 Fresh schema and compatibility boundary

- Schema changes create a fresh target schema and use an explicit version check. An old or mixed database is rejected before initialization mutates it; no importer, fallback reader or dual write exists before 0.5.
- The reset-required result identifies the exact database path and directs an operator to back up and explicitly rebuild the data root. The application never deletes, overwrites or silently repairs the rejected database.
- The current schema contains only source-first Episode, Node, Assertion, Evidence and operational tables. Legacy entity/event tables, legacy edges, `support_score` and `source_type='legacy'` are not accepted inputs.

### 9.6 Verification and observability

- Every write path has failure-injection coverage before and after its commit point, including concurrent duplicate submission, hash mismatch, restart, lease expiry and uncommitted-row visibility.
- Maintenance and Recall tests cover idempotent score updates, source protection, facet semantics, supersession/conflict visibility, namespace/privacy isolation and hard truncation limits. Fresh-store tests cover old/mixed-schema rejection without mutation, new-schema creation and reopen.
- Performance evidence records cold/warm initialization, per-Unit-of-Work time, SQLite lock wait, row counts, retry latency and Recall p95. The existing representative Recall target remains p95 ≤ 150 ms; Genesis batching policy is chosen from measured startup evidence, not from this Memory contract.
- After schema or transaction changes, rerun the persistence inventory, focused adapter/contract tests, quality checks and `git diff --check`; update the Conformance row with target, inventory, references, verification and residuals.
