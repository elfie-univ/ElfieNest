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
- source references, privacy scope, `importance`, `detail_level`, `lifecycle`, version and content hash.

Runtime learning is written in full before graph projection. For example, learning Newton's first law stores the explanation, teaching context and source in one Episode; later maintenance projects reusable knowledge from it. Genesis seed content remains complete in its approved source, with personal biography seeds represented as complete Episodes.

Later maintenance may change detail from `full` to `compressed` or `digest`, and may archive the record as a separate lifecycle state. A summary never replaces the last auditable source required by the graph.

### 2.2 Personal Knowledge Graph

The graph is Elfie's sourced, subjective understanding. It is not an objective universal database and does not silently import model knowledge. It is a durable projection that can be rebuilt and reconciled from complete Episodes, approved seed sources and their Evidence; a projection revision identifies the source version it reflects.

#### 2.2.1 Nodes

Nodes are heterogeneous semantic anchors: Elfie, people, pets, groups, planets, places, facilities, objects, foods, species, concepts, cultural ideas, physical laws, theories, emotions, subjective experiences, event references and Claim/knowledge objects.

A Node has stable identity, `node_type`, canonical label, scope, status, `importance` and `confidence`. Aliases and sourced descriptions are associated with the Node. Broad and specific concepts use typed relations such as `part_of`, `subtype_of` and `generalizes`. Not every word becomes a Node; reusable semantic units are canonicalized while full wording remains in descriptions or Episodes.

#### 2.2.2 Assertions / Relations

An Assertion is a sourced proposition. A simple proposition is a typed directed relation:

```text
Earth --has_shape--> sphere
Owner --helped--> Elfie
```

It may include a node or typed literal as object, polarity, epistemic status, time range, viewpoint, context, validity interval, conflict group, `importance` and `confidence`.

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

`importance` is the durable semantic significance of an Episode, Node or Assertion to Elfie, in `[0, 1]`. It is distinct from evidence count and confidence. New independent evidence, owner emphasis, emotional salience, relationship role, recurrence, novelty and consequences may raise it. A deterministic, versioned maintenance policy may cap and combine these contributions; its coefficients and decay curve are policy data, not additional stored scores.

The Lifecycle Stage directly lowers `importance` for eligible records according to the aging policy. Important records therefore start from, and retain, a higher significance; no separate lifecycle score is needed.

Eligibility is determined from occurrence, last reinforcement/review and the record's availability state (persisted or deterministically derived from Evidence), not from a hidden score.

#### 2.3.2 confidence

`confidence` is the reliability of an identity or proposition. It is derived from source quality, independent supporting/contradicting Evidence, epistemic status and unresolved conflict. Time passing alone does not lower confidence. A low-confidence assertion can still be important, and a high-confidence routine fact can be unimportant.

#### 2.3.3 Lifecycle eligibility (no additional score)

Lifecycle eligibility is a predicate, not a stored score. Lifecycle Stage selects Episodes and Assertions by their `lifecycle`, Nodes by `status`/merge state, due review/age and `importance`; `confidence` remains an epistemic/retrieval signal and source-safety guard. Child aliases, descriptions and mentions follow their parent/source dependency and have no separate lifecycle score. The design defines no additional lifecycle score.

#### 2.3.4 detail level

`detail_level` describes content resolution: `full`, `compressed` or `digest`. `lifecycle` describes availability: `active`, `archived` or `forgotten`. Archiving is a state transition, not a fourth content level; an archived Episode may still retain a full, compressed or digest representation. Assertions may be active, superseded or forgotten, but an Assertion's last auditable Evidence cannot be removed by detail compression. A historical `life_stage` records the Elfie's developmental phase at the time of an experience; `temporal_label` is its relative period (for example `before_arrival`). Neither is `Lifecycle Stage`, `lifecycle` or `detail_level`. For Nodes, `status` and merge state govern identity availability; maintenance may lower Node importance but does not erase a canonical Node still referenced by Assertions.

## 3. Runtime flows

```text
One-time Genesis
ApprovedSeedSource ──► Genesis manifest
                         └─ atomic complete-package commit ──► all Memory outputs + marker

Normal runtime
Workspace closes ClosedEpisode ── capture transaction ──► complete Episode + source references
                                                           │
                                                           ▼
                                                   Memory Maintenance
                                                   ├─ Consolidation Stage
                                                   │  Episode ► graph projection + score updates
                                                   └─ Lifecycle Stage
                                                      due records ► importance decay + detail policy

Episodes + Nodes + Assertions + Evidence ──► Hybrid Recall ──► bounded RecallBundle
```

Genesis is a one-time side entrance. The normal path never writes graph facts from an incomplete event, and capture does not wait for maintenance.

### 3.1 Genesis initialization

`ApprovedSeedSource` is immutable, versioned and hashable. A Genesis manifest has exactly three seed families: `KnowledgeSeed[]` (known world/knowledge), `EpisodeSeed[]` (the individual's past, each materialized as a complete Episode) and `RelationshipSeed[]` (typed relationship Assertions linked to Episodes or seed Evidence). There is no fourth biography or relationship memory category: biography is the Episode materialization and relationships are the RelationshipSeed projection. World/knowledge and relationship seeds may be directly projected; every `EpisodeSeed` must remain a complete Episode, and its derived Nodes/Assertions may also be projected in the same complete package. All outputs carry seed Evidence.

Genesis has one completion contract for the Memory package. For a valid manifest, every expected authoritative and child record—Nodes, Assertions, Evidence, biography Episodes, aliases, descriptions and mentions—and the final completion marker must be durable and visible as one completed package. Atomicity means “accept only the complete package”: no partial output may be exposed or reported as initialized. Validation failure is rejected before any write. A crash or transient write failure is not a terminal initialization result: the package remains unpublished, and the recovery owner must retain or reconstruct the immutable input and retry the same manifest ID and hash as a whole until reconciliation confirms every expected output and the marker. Internal cleanup of an interrupted attempt is only a recovery mechanism, never the result. If an operational fault prevents the current attempt from finishing, it may return only an incomplete/retryable outcome (or no receipt), never `committed`; the recovery owner continues whole-package retries. Adoption remains unpublished and the package is not recallable until reconciliation succeeds. A committed Elfie cannot be silently reinitialized by a different manifest; an upgrade is a separate approved operation. The outer coordinator must withhold adoption publication until this Memory package is complete; cross-owner publication remains its own contract and is not a fictitious cross-store transaction. Replaying the same ID and hash is idempotent; reusing an ID with a different hash is rejected. Genesis accepts explicit initial `importance` and `confidence`; it does not simulate conversations or manufacture importance with emotion intensity. Direct graph projection is forbidden for normal runtime callers.

Genesis admission is serialized per Elfie. The completion marker is the sole visibility gate for Genesis rows: no reader or maintenance pass may use a row from that manifest before the marker is present.

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
5. update applicable Episode/Node/Assertion `importance` and Node/Assertion `confidence` from the new sourced Evidence;
6. commit the projection and record the successful source/projection revision.

Predicates come from a versioned vocabulary. An unknown predicate stays an unresolved candidate until validated; it is never silently promoted to a fact.

A model may propose extraction, disambiguation or a summary outside the write transaction. Deterministic code validates spans, types, scope, predicates, IDs, Evidence and revisions, and performs the final write. Without a model, Episode capture and FTS remain usable; semantic projection waits for a later attempt. There is no keyword gate and no ungrounded fact fallback.

#### 3.3.2 Lifecycle Stage

For any Episode or Assertion with active `lifecycle`, or Node with active `status` and no canonical merge target, whose review time is due—independent of when it was captured—apply the explicit aging policy:

- directly decay `importance` on eligible Episode, Node and Assertion records;
- decide whether Episode detail remains `full` (an Episode without a successful projection for its current source version keeps enough complete source for a future projection);
- for an Episode with a successful projection for its current source version, move `detail_level` to `compressed` or `digest`, and set `lifecycle` to archived when allowed;
- forget only when policy and source-dependency checks allow it.

This stage does not lower `confidence` merely because time passed, delete the last Evidence, or treat an old Episode as a new consolidation input. An old record is found by its due time, not by the current capture batch. If one record cannot be safely compacted, its lifecycle pass is skipped while other bounded records continue. Detail compression is maintenance of the historical line; it does not silently erase graph provenance.

### 3.4 Hybrid Recall

Recall is deterministic and index-driven on the hot path; it does not require a model call.

#### 3.4.1 Basic / Text Search

Lexical/full-text search (and an optional vector index) finds exact names, aliases, rare terms, original wording, detailed stories and source/media references. It is the fallback for details not yet canonicalized in the graph.

#### 3.4.2 Local / Graph Search

Starting from text hits or supplied Node/Claim IDs, bounded typed traversal follows relationships to people, places, concepts, emotions, events and supporting Episodes. Traversal keeps a visited set, does not revisit a Node within one path, and returns explicit paths; hop, neighbor and result limits are hard caps. Person, time, place, historical emotion, topic and cause facets constrain or rank the same source-grounded candidates.

#### 3.4.3 Global Search (later capability)

Broad thematic or community search is deferred until the graph has representative density. Any summary must remain traceable to Assertions and Episodes; it is not a new fact source.

#### 3.4.4 RecallBundle

The minimum route is Basic/Text → seed Nodes/Episodes → bounded Local/Graph expansion → source Episode/Evidence fetch. Active records are preferred; relevant superseded or conflicting records remain visible with status. Results are then ranked deterministically by match, path length, `importance`, `confidence`, time relevance and stable ID. The result contains graph structure, narrative excerpts, provenance and conflicts so the consuming Brain layer can narrate it.

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
  focus_nodes: [{id, type, label, description, importance, confidence}],
  assertions: [{id, subject, predicate, object, qualifiers, status,
                importance, confidence, evidence_ids}],
  paths: [{node_ids, assertion_ids, hop_count}],
  episodes: [{id, time_range, life_stage, temporal_label, excerpt,
              detail_level, importance, source_event_ids}],
  evidence: [{id, source_type, source_id, source_version,
              span_or_locator, stance}],
  conflicts: [{assertion_ids, reason}],
  limits: {requested, returned, truncated}
}
```

Graph supplies structure, Episodes supply detail, Evidence supplies grounding, and the consuming layer supplies narration.

### 4.3 Memory Maintenance

Input is a bounded batch/time budget and an operational maintenance checkpoint. The operation runs Consolidation Stage before Lifecycle Stage, commits only validated source-linked changes, records retryable failures in operational control state without losing the Episode, and returns counts/checkpoint/status. Model inference, if used, happens before the write transaction; it is never the authority for a final fact.

### 4.4 Source inspection

Authorized Memory callers and diagnostics may request one bounded Episode or Evidence record by stable ID, including its source content, detail state and provenance. Inspection is read-only and does not become an implicit chat-history or Profile read.

### 4.5 Idempotence, failure and budget constraints

Every write has a stable idempotency key or fingerprint. A Unit of Work is short, uses one serialized SQLite writer, and never waits for a model, network, device or world runtime. Leases/checkpoints make interrupted maintenance retryable; a failed attempt leaves source content and Evidence intact. Recall enforces limits on text hits, graph hops/neighbors, returned Assertions/Episodes/Evidence and rendered characters, and reports truncation explicitly.

## 5. SQLite physical implementation

### 5.1 Authoritative fact tables

SQLite is the first physical implementation. One Memory Adapter/database is bound to one Elfie namespace; a caller cannot query another Elfie's rows. The following tables are authoritative facts; JSON columns are bounded metadata only and never hide graph edges or provenance.

| Table | Required responsibility |
| --- | --- |
| `episodes` | Complete source content, occurrence range (nullable when unknown), historical `life_stage`/`temporal_label`, separate write time, context/media/source references, privacy scope and version, `importance`, `detail_level`, `lifecycle`, successful projection marker (revision bound to source version/content hash), lifecycle review metadata, idempotency key and content hash. |
| `nodes` | Canonical identity, type/label, scope/status, bounded summary, `importance`, `confidence` and merge pointer. |
| `node_aliases` | Many scoped aliases with their own source and confidence. |
| `node_descriptions` | Many language/kind-specific descriptions, content hash and source link. |
| `episode_mentions` | Episode-to-Node links, roles/spans and resolved/ambiguous/unresolved state. |
| `assertions` | Subject, predicate, Node or typed-literal object, qualifiers, polarity, epistemic status, viewpoint/context, validity, `importance`, `confidence`, conflict group, lifecycle state and fingerprint. |
| `evidence` | Episode or seed source locator, source version, excerpt/media span, modality, speaker/viewpoint, capture time and extraction metadata. |
| `assertion_evidence` | Many-to-many Assertion/Evidence stance: `supports`, `contradicts` or `context`. |

Genesis manifest ID/version/hash and its completion marker are durable package metadata owned by the Memory Adapter, not a semantic Node/Assertion and not a retry queue. The marker lives in the same Memory SQLite database and is committed in the same transaction as the package; its physical metadata record/table name is adapter-private and is not an additional semantic memory table. The marker is written only after every expected Memory row, including child rows, is ready for the final complete commit. Every Genesis-produced row carries the manifest identity, and readers ignore rows whose completion marker is absent. A retryable or interrupted manifest is not an initialized Memory and is not recallable as one; its operational control state may be reconstructed from the immutable package. The marker records (or hashes) the expected IDs/counts for each output family so reconciliation proves more than the presence of Node rows. Derived FTS/vector indexes and RAM caches are not part of the fact-package completion check and may be rebuilt only after the complete commit. These records do not form a second mutable fact store. Only `importance` and `confidence` are semantic scores; Evidence rows and their stances are the authoritative support record.

### 5.2 Derived indexes and cache

`episodes_fts` and `nodes_fts` are rebuildable full-text projections over source text, summaries, labels, aliases and sourced descriptions. An optional vector index is a later optimization, never a first-implementation prerequisite, and is also derived. Required lookup indexes cover Episode `lifecycle`/successful projection revision/review and time/hash (and historical stage labels when queried), Node normalized label/type/status, aliases `(normalized_alias, scope)`, descriptions `(node_id, language, kind)`, mentions by Node and Episode, Assertions by subject/predicate and object/predicate, conflict/supersession, Evidence by source, and both directions of `assertion_evidence`. Operational leases, retry attempts and checkpoints are kept outside these authoritative fact indexes; they are bounded controls and never returned by Recall. A non-null successful projection revision is a durable marker tied to the Episode source version/content hash; absence, or a revision tied to an older source hash, means that the current projection has not been committed, not that a retry state was written into the Episode. Each index exists for a bounded query and declares its rebuild source. The first implementation stays on the embedded relational store; a dedicated graph engine is not a prerequisite.

RAM holds bounded hot Nodes, adjacency pages, recent neighborhoods and index pages. A cache miss reloads durable rows; it never constitutes memory loss. Media is loaded on demand.

### 5.3 Constraints, uniqueness and conflict preservation

Foreign keys are enabled and deletion is restricted by default. Episode idempotency keys and content hashes prevent duplicate capture. An Assertion fingerprint includes normalized subject, predicate, object, qualifiers, polarity, viewpoint and validity; it does not collapse distinct times, perspectives or conflicts. Evidence identity also includes source version, modality and locator/span, so the same locator in a new source version is a distinct source link. Exact replay is idempotent.

Aliases may be ambiguous across scope. Mentions may remain unresolved. Descriptions deduplicate by Node/language/kind/content hash while retaining separate sourced versions. An Assertion has exactly one Node object or one typed-literal object. Queryable assertion fields and qualifiers are columns or explicit indexed child records; a typed literal uses mutually exclusive node-ID versus type/value/unit fields, and bounded JSON is only non-queryable metadata. Node merges keep the old ID and point to the canonical ID. No bare-triple unique key may overwrite evidence or disagreement.

### 5.4 Transactions and Unit of Work

Genesis applies the completion guarantee in §3.1: it validates the complete manifest before opening one manifest-scoped transaction, writes every Memory output (Nodes, Assertions, Evidence, Episodes and child records) and the final marker in that commit, and returns success only after the complete set is reconciled. A failed commit is not a completed state; the same immutable manifest remains unpublished and is resumed/retried as a whole until it can be committed. Normal capture commits the complete Episode and its source references together; its derived text index may be updated in that transaction or rebuilt after commit. Maintenance validates model proposals outside the transaction, then commits graph changes, Evidence links, score updates, lifecycle and successful projection revision in one short Unit of Work; derived indexes are updated or rebuilt only after the fact commit and never decide whether the fact package completed. A transaction never includes model or network calls.

SQLite uses `PRAGMA user_version`, foreign keys, WAL, a bounded busy timeout and one serialized writer. Derived indexes can be deterministically rebuilt from authoritative tables.

### 5.5 Restart recovery

Episodes, Nodes, Assertions and Evidence survive restart. Maintenance claims bounded records with operational leases/checkpoints; an expired lease is reclaimable. A crash before a normal commit leaves the source unchanged; a crash after commit is recognized by the idempotency key/fingerprint. A crash before the Genesis final commit leaves no accepted initialization; recovery checks the same immutable manifest ID/hash and retries the whole package. The `committed` state is valid only when every expected output, child record and the completion marker are present. FTS and RAM caches are rebuilt when missing.

## 6. Lifecycle, recovery and development migration

### 6.1 Episode detail lifecycle

Lifecycle is the aging and availability state of an already stored record, not a new memory type. A due-time scan covers old and new records alike. At review, the policy directly decays `importance` for eligible Episodes, Nodes and Assertions and refreshes lifecycle review metadata. `confidence` is not time-decayed. An Episode without a successful projection for its current source version keeps enough complete source for a future projection; a projected Episode may move from `full` to `compressed` or `digest`, while archiving is a separate availability state. Both changes require source and graph-dependency checks.

### 6.2 Source Evidence protection

An Evidence row that is the last auditable source for an active Assertion cannot be deleted. Compression may shorten an Episode's rendered detail, but it preserves a hash plus an excerpt, locator or digest sufficient to trace the Assertion. Seed sources and their versions remain immutable. Any destructive deletion is explicit, reversible during development and reported by ID. An explicit owner correction is a new sourced Episode/Assertion and may supersede an older Assertion; it never mutates the historical source in place.

### 6.3 Compression, archive, digest and forgetting

Lifecycle maintenance first reduces detail, then archives cold material, and only then may forget it when policy, importance and dependency checks allow. Episodes without a successful projection for their current source version are reviewed too, but their source is retained until a safe projection or an explicit source-retention rule exists. Forgetting detail does not automatically delete Nodes or Assertions; it may mark an Assertion superseded/forgotten only with an auditable replacement or retained source. An old Episode is reviewed by Lifecycle Stage; it is not reintroduced as a new consolidation input.

### 6.4 Development data migration

Migration is a development cutover, not a normal runtime path. Import into a fresh target database:

- complete legacy events/experiences → Episodes;
- entities → Nodes;
- edge records → Assertions;
- source links → Evidence and `assertion_evidence`;
- aliases/descriptions/mentions → their child tables.

Embedded duplicate edge JSON or source-less notes are diagnostics, not silently promoted facts. A legacy source row is migration-only and cannot ground an active target Assertion until it is converted to a verified Episode or approved seed source. Stop new writes, snapshot the old database, import, reconcile counts/hashes/Evidence and reopen after restart, then switch the injected Adapter. Keep the snapshot until acceptance; do not add long-term dual writes or a fallback reader. A failed check leaves the old Adapter active.

## 7. Non-negotiable invariants

1. Runtime content is complete in an Episode before extraction; Genesis content is complete in its approved source before projection.
2. Every durable Assertion has Episode or seed Evidence; model output alone is never a fact.
3. Canonicalization merges identity, not contradictory viewpoints or unrelated entities.
4. Conflicting Assertions retain polarity, time, perspective and source.
5. Graph summaries, vectors and scores cannot outrank source grounding without explicit epistemic status.
6. Episodes are the detailed historical line; the graph is its structured semantic projection.
7. Live state, plans, commitments, permissions and actions remain with their owning systems.
8. Memory never directly reads Profile, Communication history or world runtime state.
9. Genesis direct projection is limited to one approved manifest and cannot become runtime CRUD.

## 8. Validation and stage gates

Each implementation round closes only with code and replayable evidence. The target design is not proof that the current implementation already conforms.

### 8.1 Source integrity

Verify complete Episode capture, content hashes, idempotency, atomic Genesis completion, retry behavior and reopen-after-restart. Gate: 100% of accepted fixtures preserve source hashes, every valid Genesis reaches a complete marker with all expected child records, and no partial Genesis is visible.

### 8.2 Graph provenance

Verify mention resolution, canonicalization, Assertion/Evidence links, Claim Nodes, independent descriptions and conflict retention. Gate: every fixture Assertion has a resolvable source; unsupported proposals are rejected.

### 8.3 Hybrid retrieval

Replay a rare term, a relationship-network query, a knowledge object, an emotion facet and a time-bounded experience. Verify Basic/Text fallback, bounded Local/Graph paths, RecallBundle provenance and explicit truncation. Initial targets: rare-term recall@5 ≥ 0.90 and relationship-path precision = 1.00.

### 8.4 Weights and conflicts

Verify that new evidence updates `importance` and `confidence` once, repeated evidence is idempotent, importance decays directly in Lifecycle Stage, confidence is not age-decayed and contradictory evidence remains visible.

### 8.5 Performance and capacity

Measure both maintenance stages, bounded RAM, growth/retention behavior and database-only Basic + Local p95 ≤ 150 ms on a representative 10,000-Episode / 50,000-Node / 200,000-Assertion fixture. If migration is performed, also require 100% eligible source-hash reconciliation and an ID-level report for every skipped item.
