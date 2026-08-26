# Elfie Memory: Episodic Memory, Personal Knowledge Graph and Hybrid Retrieval

> Status: implementation target; source-first SQLite, consolidation, retrieval and migration paths are implemented on the current branch; remaining validation and production cutover status is tracked in Conformance.<br>
> Nature: cross-version target design for Memory semantics and access<br>
> Scope: this document is the authority for Memory semantics and its typed access contract; current code and the Conformance register are the authority for implementation status.

## 1. Core decision

Elfie Memory has two complementary memory representations and one access strategy:

1. **Episodic Memory / Episode Timeline** records complete, bounded experiences in time order.
2. **Personal Knowledge Graph** records the semantic structure that Elfie has derived from those experiences and approved knowledge.
3. **Hybrid Graph/Text Retrieval** recalls graph structure, text and source evidence together.

The first two are representations of memory. The third is a way to use them.

The central rule is source-first:

> An Episode always keeps the complete captured content. Consolidation extracts and merges knowledge from that content; it never replaces the Episode with a few extracted facts.

```text
closed event supplied by the upstream event boundary
        ↓
complete Episode (timeline, details and evidence)
        ↓  background / nightly consolidation
entity resolution, claim extraction, relation normalization and conflict handling
        ↓
Personal Knowledge Graph (semantic skeleton)
        ↓
hybrid retrieval
        ↓
graph subgraph + supporting Episodes + provenance
```

## 2. Memory boundary

Memory receives a bounded, already-formed event or an explicitly approved seed through the existing Brain boundary. It does not read Profile, communication history, world runtime state or another module's database directly. If such a source matters, the owning boundary supplies a sourced event or reference.

Memory owns:

- complete Episodes and their lifecycle;
- the personal graph of nodes, qualified relations and claims;
- evidence and provenance for graph assertions;
- graph/text/vector indexes used to recall those records;
- consolidation and retention semantics for Memory records.

Memory does not own current location, live body state, current emotion, active plans or commitments, permissions, or external actions. Those may be cited as evidence when an owning system supplies them, but they do not become Memory authorities merely because a model mentioned them.

## 3. Episodic Memory / Episode Timeline

An Episode is one meaningful, bounded event or closed scene, not one chat turn and not a short keyword summary. The upstream event boundary groups related turns or observations before Memory receives it.

An Episode may represent:

- a conversation or relationship moment;
- a learning session;
- an embodied or environmental experience;
- a perception containing text, audio, video or images;
- a meaningful emotional or social event.

The conceptual Episode record includes:

- stable ID and occurrence time or time range;
- participants, places, objects and surrounding context;
- the complete original text/transcript; large media may be held through a durable reference, but the captured learning or event content may not be omitted;
- media references and derived transcription/features when available;
- what Elfie observed, was told, inferred or felt, with attribution;
- source IDs, privacy scope, lifecycle/detail level and version.

“Today I learned Newton's first law” therefore creates a learning Episode containing the full explanation, teaching context and source. The law itself is then projected into the Knowledge Graph as a canonical knowledge object. If the seed is already approved and must be available immediately, an initial graph projection may be created at capture time, while the complete source Episode remains mandatory.

Full content is mandatory at capture and consolidation time. Later, Episode detail can be compressed, archived or forgotten according to retention policy, while an auditable source stub or digest is retained when the graph still depends on it. A summary or graph assertion does not erase the provenance needed to explain where it came from.

## 4. Personal Knowledge Graph

The graph is Elfie's personal, sourced understanding of its world. It is not an objective universal database and it must not silently inherit arbitrary model knowledge.

### 4.1 Nodes

Nodes are heterogeneous semantic anchors. Typical types include:

- Elfie, people, pets and groups;
- planets, places, facilities and objects;
- concepts, foods, species and cultural ideas;
- physical laws, theories and other reusable knowledge objects;
- emotions and subjective experiences;
- event or Episode references when graph navigation needs them;
- claim nodes for propositions that need their own identity.

A node has a stable identity, type, canonical label, aliases, descriptions and scope. A node can be broad or specific through `part_of`, `subtype_of`, `generalizes` and similar relations. The graph does not split every word into a node; it captures reusable semantic units and keeps the full wording in the node description or source Episode.

### 4.2 Relations and claims

A simple fact can be a typed directed relation:

```text
Earth --has_shape--> sphere
Owner --helped--> Elfie
```

The relation or Claim also carries qualifiers such as time, context, viewpoint, polarity, epistemic status, confidence, validity interval and conflict group.

When a proposition has its own conditions, descriptions, versions or evidence, it becomes a claim/knowledge node rather than a forced sentence-sized edge:

```text
NewtonFirstLaw --part_of--> ClassicalMechanics
NewtonFirstLaw --related_to--> Inertia
NewtonFirstLaw --has_condition--> NetForceIsZero
```

The node can retain the complete wording, formula and conditions. A simple fact and a qualified Claim use the same graph, so the model does not need a second “knowledge type” for every special case.

### 4.3 Evidence and multiple descriptions

Evidence is a first-class link from a graph assertion to its source. It records the Episode or seed ID, source modality, text span or media pointer, time, speaker/viewpoint, extraction method and support/contradiction direction.

Many descriptions of “Newton's first law” resolve to one canonical node with aliases, descriptions and multiple evidence links. They do not create seven unrelated nodes. Repeated independent support may raise a derived support score; use frequency alone is never truth.

If two sources disagree, retain separate qualified Claims or relation versions with their own evidence, perspective and validity. A missing edge means “not recorded”, not “false”.

### 4.4 Experience, media and emotion

An Episode remains the place for narrative detail and raw sensory material. The graph may expose a projected event node and links such as:

```text
Episode E42 --involves--> Owner
Episode E42 --felt--> Calm
Owner --helped--> Elfie       [supported by E42]
```

The `Calm` node can connect many historical Episodes, enabling associative retrieval. Soft similarity is better supported by vector/text indexes; explicit emotional, causal or social links belong in the graph. Current live emotion is not rewritten into a historical Episode without an owning event and source.

### 4.5 Mind-map views

A mind map is a presentation of a selected graph neighborhood, not another source of truth. It can show “my home planet” or “my relationship network” as a focused hierarchy, while the underlying graph keeps cross-links, cycles, qualifiers, conflicts and evidence. No separate persistent mind-map fact store is required.

## 5. Consolidation: Episode first, graph second

For a closed Episode, consolidation performs the following semantic work:

1. preserve the complete Episode and its source references;
2. extract mentions, events, concepts and candidate claims from the complete content;
3. resolve aliases, coreference and entity identity;
4. normalize predicates and choose the appropriate direct relation or Claim node;
5. merge compatible assertions, retain independent evidence and record conflicts;
6. update derived summaries and rebuildable retrieval indexes.

This is a pipeline, not a keyword gate. A language model may propose extraction, disambiguation or a summary in background processing; deterministic code owns IDs, scope, constraints, evidence attachment, revision and the final write. Hot retrieval does not require a language-model call.

Nightly consolidation is a useful deep batch, but it is not the only moment at which Memory may update. An Episode must be bounded and retained as soon as the upstream boundary closes it; approved seed knowledge may receive an immediate graph projection, while ordinary semantic merging can run asynchronously.

The graph is a durable, versioned projection that can be reconciled from Episodes and evidence. It is not permission to discard the source line.

## 6. Hybrid Graph/Text Retrieval

The retrieval vocabulary is a set of query strategies, not storage layers:

- **Basic/Text Search** finds exact names, rare terms, original wording, detailed stories and source/media references using lexical, full-text and optional vector indexes.
- **Local/Graph Search** starts from a matched entity or claim, follows bounded typed paths and returns nearby people, places, concepts, events and supporting Episodes.
- **Global/Community Search** answers broad questions over the Elfie's graph, such as the shape of a homeland or a long-term relationship pattern, using derived topic/community summaries that remain grounded in graph claims and Episodes.

Not every query needs all three. Basic and Local are the minimum useful combination; Global is added when the graph has enough material for meaningful thematic summaries. A router may run more than one strategy and fuse the results.

The result consumed by an upper layer is a bounded `RecallBundle` containing:

- relevant graph nodes, relations and qualified Claims;
- supporting Episode excerpts and media references;
- timestamps, viewpoint, confidence and conflict status;
- source IDs and provenance sufficient to audit each important assertion.

Graph traversal is used for explicit relationships and multi-hop association. Text and vector retrieval cover wording variation, rare details and information that has not yet been fully canonicalized. Neither replaces the other. Retrieval itself remains deterministic and index-driven; generation is a separate concern.

## 7. Persistence and runtime principles

The logical model is independent of the physical database. A graph can be implemented with an embedded relational store containing indexed node, edge, Episode and evidence records; a dedicated graph engine is not a prerequisite.

The durable store is the source of truth. RAM holds only bounded working sets:

- hot nodes and adjacency pages;
- recent query neighborhoods;
- full-text/vector index caches;
- small derived summaries.

Episodes, graph assertions and evidence survive restart. Media and large raw payloads are loaded on demand. A cache miss reloads from the durable store; losing the cache must not lose a memory.

For the first implementation, keep the physical choice simple and local: an embedded durable database plus full-text and optional vector indexes, with indexed adjacency for bounded graph traversal. Evaluate a dedicated embedded graph store only after representative traversal and growth benchmarks. Do not load the entire lifelong graph or all media into RAM, and do not build a graph database engine from scratch.

## 8. Non-negotiable invariants

1. Every learned item is fully present in its source Episode before extraction.
2. Every durable graph assertion has provenance; model output alone is not evidence.
3. Canonicalization merges identity, not contradictory viewpoints or unrelated entities.
4. Conflicting claims remain visible with their source, time and perspective.
5. Graph summaries and vector matches never outrank the source evidence without an explicit status.
6. Episodes are the detailed historical line; the graph is the structured semantic projection.
7. Active plans, commitments, permissions and live state stay with their owning systems.
8. Memory never reads Profile or communication history directly and never invents current-world facts.

## 9. First implementation design: SQLite

This section is the implementation-ready target for the existing SQLite Adapter. It fixes the
minimum physical shape and operational contracts without exposing SQL to the domain or upper
layers. The Adapter may use SQL, recursive CTEs or an internal query language; callers use typed
Memory Ports only.

### 9.1 Physical source of truth

The following are durable fact tables. JSON is allowed only for bounded, non-queryable metadata;
it is not used to hide graph edges or source evidence.

| Table | Required role and fields |
| --- | --- |
| `episodes` | One closed experience: `episode_id`, unique `idempotency_key`, `occurred_from`, `occurred_to`, complete `content_text`, derived `summary_text`, `event_kind`, source/media references, `importance`, `detail_level`, `lifecycle`, `consolidation_state`, retry and lease fields, content hash, timestamps. |
| `nodes` | Canonical semantic anchors: `node_id`, flexible `node_type`, canonical and normalized labels, derived description, scope, status, confidence, optional bounded properties, `merged_into`, timestamps. |
| `node_aliases` | Alternate names used for resolution and search: node, alias, normalized alias, scope, source evidence and confidence. Ambiguous aliases are allowed; they are never force-mapped by text alone. |
| `node_descriptions` | Distinct sourced descriptions of one node: node, text, language/kind, evidence reference, confidence and timestamp. The canonical description is derived from these records, not a replacement for them. |
| `episode_mentions` | Episode-to-node mentions: episode, nullable resolved node, resolution state, role, surface text/span and confidence. This is the bridge for finding source experiences from a graph node while keeping ambiguous mentions. |
| `assertions` | Qualified directed facts or claim links: subject, predicate, either object node or typed literal (with optional unit), polarity, epistemic status, viewpoint/context, validity interval, confidence, support score, conflict group, fingerprint, lifecycle and timestamps. There is no unique constraint on a bare subject/predicate/object triple. |
| `evidence` | Source grounding: episode or approved seed reference, excerpt/media locator, modality, span, speaker/viewpoint, capture time and extraction-run metadata. |
| `assertion_evidence` | Many-to-many assertion/source link with `supports`, `contradicts` or `context` stance. |

`episodes_fts` and `nodes_fts` are rebuildable lexical projections, not facts. The current Adapter
uses indexed candidate filtering plus deterministic Unicode-aware scoring; a future SQLite FTS5 or
vector index may replace the projection without changing the Memory Port. Search projections index
the original normalized text and never duplicate media payloads or unbounded metadata. Large media
stays behind durable references and is loaded on demand. No subtype table is authoritative for a
semantic node; `node_type` plus validated properties covers people, places, concepts, laws, emotions
and other node kinds.

These three child/bridge tables are split by cardinality, not by an extra semantic layer:

| Cardinality | Physical choice |
| --- | --- |
| one node → one current canonical summary | keep it on `nodes.description` |
| one node → many aliases or sourced descriptions | `node_aliases` / `node_descriptions` |
| many Episodes ↔ many nodes | `episode_mentions` bridge |

An alias or description is stored only when it is a distinct, meaningful value. Normalized
duplicates are ignored (or linked to their existing row), and the raw Episode remains the place for
all wording that is not promoted to a semantic description. `episode_mentions` records semantic
mentions, roles and spans rather than every token; an initial per-Episode cap of 128 is an
operational guard, and overflow is reported while the complete source text remains searchable.

The first SQLite type convention is deliberately small: IDs and normalized labels are `TEXT`,
canonical UTC timestamps are `TEXT`, scores are bounded `REAL`, booleans are `INTEGER`, and
bounded metadata is validated JSON text. Complex assertion objects become Claim/knowledge nodes;
arbitrary nested JSON is not used as an unsearchable substitute for graph structure.

### 9.2 Constraints and indexes

- `episodes.idempotency_key` is unique; complete source content is non-null and its hash is
  recorded. Replaying the same closed event returns the existing receipt.
- An assertion must have exactly one object form (node or typed literal). Its fingerprint includes
  normalized subject, predicate, object, qualifiers, polarity and viewpoint; an exact fingerprint
  is idempotent, but it never collapses different time ranges or conflicting perspectives.
- The predicate registry is versioned in the Memory domain code. A predicate outside the registry
  is rejected or retained as an unresolved candidate; it is not silently normalized to a generic
  edge.
- Foreign keys use restrictive deletion by default. Forgetting is a lifecycle transition; source
  evidence is retained or replaced by an auditable digest while a graph assertion depends on it.
- A node that is merged keeps its original row, aliases and evidence and points through
  `merged_into`; physical deletion is not used for identity resolution.
- `node_aliases` is indexed by normalized alias for reverse lookup and may map one surface form to
  multiple scoped nodes. `node_descriptions` is deduplicated by node/language/kind/content hash;
  `nodes.description` remains only the current derived summary.
- `episode_mentions` has a stable mention ID and may keep `node_id` null while
  `resolution_state=unresolved`; unresolved text remains searchable and is eligible for a later
  consolidation pass.
- Required indexes are: episode lifecycle/next-attempt and time; node normalized label/type/status;
  alias normalized value; assertion subject/predicate and object/predicate; conflict group;
  episode mentions by node and episode; evidence by episode; assertion evidence by assertion.
- FTS indexes cover complete Episode text, Episode summaries, canonical node text, aliases and
  sourced descriptions. Every derived index declares its source and rebuild command.

SQLite schema version is recorded in `PRAGMA user_version`. The Adapter owns an explicit Unit of
Work for multi-record writes; Repository methods do not commit while a caller still needs the same
transaction. File-backed databases enable foreign keys, WAL and a bounded busy timeout; there is
one serialized writer and read queries never wait for a model or another external service. FTS
updates are part of the same transaction as their source row, or a rebuild marker is written before
the transaction is acknowledged.

### 9.3 Typed Memory Port surface

Only these semantic operations cross the Memory boundary in the first implementation:

- `record_episode(ClosedEpisode) -> EpisodeReceipt`: source-first, idempotent capture;
- `recall(RecallRequest) -> RecallBundle`: bounded Basic/Local retrieval and provenance;
- `run_consolidation(ConsolidationRequest) -> ConsolidationReceipt`: an internal background job
  entry that returns counts and failed Episode IDs, never external effects;
- `get_episode(EpisodeId)` and `get_evidence(EvidenceId)`: bounded source inspection for Memory
  owners and diagnostics, not a raw table/edge API and not a bypass for normal recall limits.

Retention and index rebuild are Adapter/maintenance operations, not upper-layer graph CRUD. No
caller receives SQL rows, table names, embedded edge JSON or an unbounded graph object.
The listed operations are the external semantic surface; consolidation may use an Adapter-private
Unit of Work internally without widening the Port with raw node/edge CRUD.

### 9.4 Write and consolidation contract

1. The upstream event boundary supplies one validated, closed `ClosedEpisode`; Memory does not
   decide whether raw turns belong to an event.
2. `record_episode` validates and commits the complete Episode, idempotency key and source
   references in one transaction, then updates the rebuildable text projection. It never calls a
   model and never writes a graph fact from an incomplete payload.
3. A bounded worker atomically claims pending Episodes using state, `lease_owner` and
   `lease_until` fields. Expired leases are reclaimable. It reads the complete source outside the
   write transaction. Model calls, when enabled, return candidate mentions, descriptions and
   assertions with source spans; they are proposals, not facts.
4. Deterministic validation checks spans, types, scope, object shape and allowed predicates.
   Resolution uses canonical/normalized names, aliases, compatible type and scope. One clear
   candidate may merge; ambiguity creates an unresolved mention or new candidate, never a blind
   merge.
5. One write transaction inserts/updates nodes, descriptions, mentions, assertions and evidence.
   Compatible assertions share a fingerprint and gain evidence; contradictory assertions remain
   separate in a conflict group. The Episode becomes `consolidated` only after this transaction
   commits. A failed attempt leaves the Episode and source intact with retry metadata.
6. Batches run continuously with a bounded size and a nightly catch-up. No transaction waits for
   a model, network, device or world runtime. A retry is idempotent; raw model output need not be
   durable in the first version.

Without a model, capture and FTS still work and approved seeds may be projected; ordinary
semantic assertions wait for a later consolidation attempt. A model failure never falls back to a
keyword gate and never turns an ungrounded proposal into a fact. An explicit owner correction is
stored as a sourced Episode and may supersede an older assertion only through the same qualified,
auditable conflict policy.

### 9.5 Retrieval contract

The upper layer calls a typed `recall(RecallRequest) -> RecallBundle`. The request may contain
text, seed node IDs, node types, relation allowlists, a time window, retrieval mode and limits;
it never contains SQL or GQL. The first implementation uses these safe defaults, subject to the
evaluation fixture rather than ad-hoc tuning:

| Limit | Default |
| --- | ---: |
| lexical seed hits | 20 |
| seed nodes | 8 |
| graph hops | 2 |
| neighbors per expanded node | 12 |
| total graph nodes / assertions | 40 / 80 |
| supporting Episodes / evidence items | 8 / 24 |
| rendered bundle | 12,000 characters (hard cap) |

The deterministic route is:

1. Basic/Text search uses FTS for exact names, aliases, rare terms and original wording;
2. matched nodes and Episode mentions become seeds;
3. Local graph search expands only allowed relation types and directions within the hop and count limits;
4. source Episodes and evidence are fetched for the selected assertions;
5. results are ranked by exact alias/text match, then path length, evidence support/confidence,
   recency/importance and stable ID tie-breaker; conflict status is never hidden.

Traversal maintains a visited set, never revisits a node in one path, and returns explicit paths so
an ambiguous alias or competing relationship can be shown rather than silently selected. Episode
excerpts are cut only at source boundaries and the bundle also has a character/token budget; a
truncated result reports `truncated=true` and keeps its source IDs.

Global/community search is a later mode and cannot be required for the first vertical slice.
Optional vectors improve wording variation but never replace FTS, graph edges or source evidence.

`RecallBundle` has stable sections for focus nodes, qualified assertions, paths, Episode excerpts,
evidence and uncertainties/conflicts, plus query limits and source IDs. A deterministic renderer
uses a stable labeled format so prompt caching remains possible. It does not recreate a fictional
story from graph nodes: the graph supplies structure, Episodes supply detail and evidence supplies
grounding; the reasoning layer supplies the final narration.

A logical bundle has this shape (the concrete domain types are defined in code):

```text
RecallBundle {
  focus_nodes: [{id, type, label, description}],
  assertions: [{id, subject, predicate, object, qualifiers, status, evidence_ids}],
  paths: [{node_ids, assertion_ids, hop_count}],
  episodes: [{id, occurred_from, occurred_to, excerpt, detail_level}],
  evidence: [{id, source_id, span_or_locator, stance}],
  conflicts: [{assertion_ids, reason}],
  limits: {requested, returned, truncated}
}
```

This is the complete payload Memory promises. It does not redefine the other inputs or the
decision contract of the reasoning system.

### 9.6 Retention, recovery and migration

- The durable store is per-Elfie and survives process restart; RAM caches are bounded and disposable.
- Episode detail may later be archived or compressed only under an explicit retention policy. A
  graph assertion cannot outlive all of its auditable source without a retained source stub/digest.
- Development migration uses a fresh target database and a one-time importer: current event/episodic
  content is imported as Episodes first, current entities as Nodes, edge records as Assertions,
  and source links as Evidence. Embedded duplicate edge JSON is not a second authority.
- Import validation compares source counts, content hashes, ID mappings, evidence coverage,
  graph assertions and reopen-after-restart behavior. The old database is kept as a backup until
  validation passes; no long-term dual write or fallback reader is introduced.
- Current edge upserts may already have overwritten conflicting versions. The importer must report
  such unrecoverable history rather than invent it.

#### Current-to-target mapping

- `entities` maps to `nodes`; `aliases_json` becomes `node_aliases`, and subtype rows in
  `people`, `known_elfies`, `concepts` and `places` become validated `node_type`/property values.
- Complete rows in `events` and episodic memory nodes map to `episodes`. If a legacy row has only a
  summary and no complete source, it is imported as an explicitly incomplete legacy item and
  reported; it is never presented as a complete Episode.
- `entity_edges` maps to `assertions`. The old unique-triple overwrite cannot be reversed; lost
  versions are reported. Embedded `memory_edges` JSON is compared for diagnostics and then ignored
  as a duplicate representation.
- `source_evidence_links` maps to `evidence` and `assertion_evidence` when its target can be
  resolved. `memory_notes` is imported only when it has a durable source reference; otherwise it is
  retained as a migration report, not a graph fact.

The cutover sequence is: stop new Memory writes, snapshot the old database, import into a fresh
target file, run count/hash/evidence/reopen checks, switch the injected Adapter, and retain the
old snapshot until the acceptance report is signed. A failed check leaves the old Adapter active;
the importer never mutates the source database in place.

### 9.7 Stage gates

Each implementation round closes only with code plus replayable evidence:

1. Episode source preservation, idempotency and restart recovery;
2. sourced extraction, canonicalization, merge and conflict retention;
3. Basic + Local retrieval for a rare term, a person relationship network, a knowledge object and
   a time-bounded experience;
4. stable `RecallBundle` assembly with no unsupported assertion;
5. representative-size latency, bounded memory and retry/retention checks;
6. migration count/hash/evidence reconciliation.

The initial measurable gates are:

| Gate | First target |
| --- | --- |
| source integrity | 100% of accepted Episodes retain the original content hash after write, retry and reopen |
| graph grounding | 100% of durable Assertions in the fixture have at least one resolvable Evidence link; unsupported assertions are rejected |
| retrieval | rare-term Episode recall@5 ≥ 0.90; relationship-path precision = 1.00 on the fixture; all declared limits are respected |
| latency | Basic + Local database-only p95 ≤ 150 ms on a fixture of 10,000 Episodes, 50,000 Nodes and 200,000 Assertions |
| migration | 100% content-hash match for eligible source Episodes; every skipped/unrecoverable item is reported by ID |

Natural-language vividness is evaluated after these structural gates. It cannot close a storage or
provenance gap.

An unresolved P0 design question stops implementation. A P1 may be deferred only when the ledger
records its owner, reason, replacement trigger and evaluation gap.
