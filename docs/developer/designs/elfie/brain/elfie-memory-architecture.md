# Elfie Memory Architecture

> Status: target design. This document is the authority for Memory semantics and its typed access contract. Code and the Conformance register describe implementation status.
>
> Scope: durable subjective experiences, sourced personal knowledge and deterministic recall. It does not define Event Workspace or the Reasoning Context Workspace, nor another module's state.
>
> Contract alignment: 2026-09-25, ADR-0033 and Elfie 2.3. Creation inputs and full Genesis manifests are ephemeral; Memory retains only its final records, evidence and atomic completion markers.

> Design relations: **Owner:** Elfie / Brain / Memory; **Parent:** [Brain
> ten-system architecture](./elfie-brain-ten-system-architecture.md); **Children:**
> none; **Normative contracts:** [Brain contract](../../../contracts/brain.md);
> **Current architecture:** [Cognitive information flow](../../../architecture/cognitive-flow.md);
> **Conformance:** [Memory conformance](../../../conformance/elfie-memory.md);
> **Domain sources:** Genesis owner-state inputs.

## 1. Purpose, boundary and authority

### 1.1 What Memory solves

Memory gives one Elfie a durable, source-grounded personal memory. It keeps a complete, already
processed story unit and a higher-level semantic note built from those units. Both can be recalled
by wording, time, people, emotion, topic and relationships.

The semantic model has exactly two layers:

1. **Episode** — a complete, bounded topic, story or learning unit prepared before it enters Memory.
2. **Node–Assertion** — the knowledge note and relationship graph extracted from Episodes and
   approved Genesis input. It may contain entities, explicit relations, reusable knowledge and
   patterns.

Recall searches and combines these two layers. A graph result may be returned directly when the
question asks for a relationship or an abstracted rule; an Episode may be returned for the full
topic context. Evidence explains how either result was derived. Raw conversation logs, videos and
other upstream materials are outside this two-layer Memory surface and are not default Recall
content.

This remains **source-first within Memory**: Node–Assertion is derived from Episode, but it is not
merely a locator and does not have to be replaced by the Episode in every answer.

### 1.2 What Memory does not own

Memory receives an already-closed, already-processed Episode; it does not decide where a topic or
story begins or ends. It does not own Profile, immutable identity, current location, live body
state, live emotion, active plans, commitments, permissions or external actions. It does not
directly read Profile, raw Communication history, raw media, world runtime state or another
module's database. Upstream references may be retained for provenance, but they are not an
additional Memory retrieval layer.

Every semantic state owned by Memory is durable. Memory does not narrate a
reply and owns no transient conversation tail, context summary, Run observation
buffer or complete Reasoning context. It returns bounded, sourced material
through its typed Recall contract; request-local retrieval structures are
protocol payloads or implementation caches, not another memory state.

### 1.3 Memory and Brain / Cognitive Consolidation

Normal Memory capture accepts only a complete, sourced `ClosedEpisode`. The cross-system `Cognitive Consolidation` scheduler is only a background entry point: when its target is Memory, it invokes or budgets `Memory Maintenance`. Memory owns the durable write, graph projection, recall and lifecycle maintenance; no other scheduler or owner creates a second Memory write path.

`Memory Maintenance` is the Memory-owned operation. It is related to, but distinct from, the cross-system `Cognitive Consolidation` scheduler.

### 1.4 Core source rule

For the live Memory model, there are only two input forms:

- normal runtime: a complete, closed `ClosedEpisode` that already represents one topic, story or learning unit;
- one-time initialization: a complete, versioned `ApprovedSeedSource`.

Every durable Assertion must point to an Episode or approved seed Evidence. A model proposal,
summary, cache entry or ungrounded profile value is not evidence. Runtime learning is
Episode-first. Genesis stores every KnowledgeSeed and EpisodeSeed as a complete Episode first;
only the explicitly sourced identity and relationship skeleton may be committed directly at
creation, while knowledge and episode-derived graph facts wait for Consolidation.

## 2. Durable memory model

### 2.1 Episode Timeline

An Episode is one meaningful, bounded, closed topic, story or learning unit—not one chat turn,
raw transcript or keyword summary. The upstream context boundary may group many related turns or
observations, and may compact older turns, before Memory receives it. The Episode itself is the
first-layer memory object and a normal retrieval unit.

An Episode may be a conversation or relationship moment, a learning session, an embodied or environmental experience, a perception with text/audio/video/images, or a meaningful emotional/social event.

It retains:

- stable ID, occurrence range and precision, and a registered `event_kind`; when relevant, a historical `life_stage`/`temporal_label` (for example `youth` or `before_arrival`), kept separate from write time;
- participants, places, objects and context;
- the original Episode text and durable upstream/media references. Optional `summary_text` is a concise,
  source-grounded synopsis that may be generated during summarization and used as a read-only display
  headline; it is not a separate title, may be empty, and never replaces or truncates original text;
- derived features when available;
- what Elfie observed, was told, inferred or felt, with attribution;
- source references, privacy scope, `importance`, `retention_profile`, `half_life_days`, `detail_level`, `lifecycle`, version and content hash.

`event_kind` is the registered experience kind, rendered with a localized label in user-facing tools.
The initial core vocabulary is `conversation` (a bounded discussion), `activity` (a shared activity
that is not primarily an outing or learning session), `outing` (a trip or visit), `learning` (study,
practice or discovery), `life_event` (a meaningful transition or milestone), `observation` (a
meaningful perception of the world or body), and `reflection` (a bounded reflective or emotional
experience). `unclassified` is a reserved fallback only when the source cannot support a known kind;
it is not an experience category and must not be silently defaulted to `interaction`. Initialization,
reset/reseed, scheduler or extraction state, and provenance labels such as Genesis are not experience
kinds. Genesis provenance is carried by source references and linked Evidence; epistemic attribution
(`observed`, `told`, `inferred` or `felt`) remains a separate dimension. A Genesis `KnowledgeSeed` that
represents knowledge acquired through learning uses `learning`; a personal `EpisodeSeed` is classified
by the experience it describes, never by the fact it was initialized.

Runtime learning is written as a complete Episode before graph projection. For example, learning
Newton's first law stores the explanation, teaching context and any source reference in one
Episode; later maintenance projects reusable knowledge from it. Genesis seed content remains
complete in its approved source, with personal biography seeds represented as complete Episodes.

An Episode has no universal semantic character count. Its boundary is one topic that can be read as
one unit. The implementation still needs a configurable transport/admission ceiling: when a topic
would exceed it, the upstream owner must split at a topic boundary or leave the close pending for a
retry; it must never silently truncate the Episode. Memory does not introduce a third semantic
Segment layer. A later implementation may use an internal text slice for indexing an unusually
large Episode, but that slice is not an independent memory object and never creates its own Node or
Assertion.

The `Topic` in the Reasoning Context Workspace is that upstream boundary and grouping cue; it is not
a third persisted Memory layer.

Later maintenance may change detail from `full` to `compressed` or `digest`, and may archive the record as a separate lifecycle state. A summary never replaces the last auditable source required by the graph.

### 2.2 Personal Knowledge Graph

The graph is Elfie's sourced, subjective understanding. It is not an objective universal database
and does not silently import model knowledge. It is a higher-level knowledge note that can be
rebuilt and reconciled from Episodes, approved seed sources and their Evidence. It is also a
valid Recall result: a relationship, reusable fact or Pattern may answer a query without first
returning the whole Episode. A projection revision identifies the Episode versions it reflects.

#### 2.2.1 Nodes and domain slices

A domain slice (also called a type group) is a registered semantic view, not a Node type or a
second storage layer. Every canonical Node has exactly one primary leaf type and belongs to one
primary slice. Cross-slice facts link the same canonical Node IDs; they never clone an object into
multiple slices.

The primary slice determines a Node's native type filter and ownership. A slice projection may still
include a referenced Node from another slice as a contextual endpoint or Claim component without
changing that Node's primary type or cloning it. For example, Earth remains a `celestial_body` in
Space, while a General-Knowledge Claim about Earth's motion can include the same Earth Node as
context.

| Domain slice | Core Node types | Boundary |
| --- | --- | --- |
| Social relations | `elfie`, `person`, `group` | `group` covers families, teams, organizations and communities; family/team are group subtypes or attributes, while parent/friend/member are relations or roles. |
| Entities | `organism`, `object`, `material` | People and Elfies remain in Social relations; physical parts, objects and materials use composition/source relations. |
| Space | `cosmic_extent`, `celestial_body`, `place` | Universe/galaxy and Earth/planet are spatial anchors. One `place` type covers regions, towns, homes and rooms using scale and containment; do not split region/place/room without a demonstrated semantic need. |
| Events | `event` | A reusable occurrence may be a Node. An Episode is the person's sourced experience/record, not automatically an Event Node. Participation, witnessing and learning-about are sourced relations. |
| General knowledge | `concept`, `claim`, `theory_or_model`, `principle_or_law`, `pattern`, `rule_or_guideline`, `method_or_procedure`, `viewpoint` | These types describe semantic form, not school subject. Philosophy and other disciplines use the same types plus a registered domain/facet; abstractions such as time are concepts, while an event's time is a qualifier. A named, reusable worldview may be a `viewpoint`; an individual proposition is a `claim`. |

`claim` is a first-class knowledge Node for an addressable proposition; `fact` is an epistemic
assessment, not a separate Node type. `belief` is a subject's stance relation to a Claim Node, not a
knowledge subtype. A Claim Node is required when a proposition must itself be believed, doubted,
supported, contradicted, derived from, versioned or conditioned. Ordinary simple relations may
remain direct Assertions when no higher-order relation needs to target them.

Initialization/reset/reseed runs, extraction jobs, progress, failures and execution audit entries
belong to their owning workflow or operational record store. They are not semantic Nodes, Assertions
or Episodes and never enter graph traversal or Recall. Memory may retain only the bounded,
non-recallable checkpoints, leases and idempotency receipts needed to operate its own writes.

Self-model is not a sixth Node-type group and does not persist a `self_model` Node. It is a derived
view over sourced self-stance Assertions and the Claim Nodes they reference. The view is scoped to an
Elfie's cognitive perspective; selection uses registered stance predicates and, where needed, the
Assertion's viewpoint/context, not every edge incident
to the Elfie Node, so social relations do not leak into it. This does not equate the physical body,
immutable Profile and modeled self-understanding. Sourced self-stance Assertions use the existing
Elfie Node as their subject; no separate virtual-self Node is created. A separate virtual-self
endpoint is reconsidered only if it must itself be an addressable object in other propositions or
relations, with an explicit semantic link to the Elfie.

A Node has stable identity, canonical `node_type`, one registered primary slice, domain-derived
type metadata, canonical label, scope, status, `importance`, `retention_profile`, `half_life_days`,
`confidence` and bounded structured properties. The type registry is the only authority for the
domain, allowed subtype, default views and valid source requirements; arbitrary non-empty strings
are not valid semantic types. Aliases, sourced descriptions and user-visible properties are all
part of the Node's searchable surface. A property remains a property when it describes the Node
itself (for example sourced observations of appearance, personality or species); it is not converted into an Assertion
only to make it searchable. Broad and specific concepts use typed relations such as `part_of`,
`subtype_of` and `generalizes`. Not every word becomes a Node; reusable semantic units are
canonicalized while full wording remains in descriptions or Episodes.

For a reusable knowledge Node, the canonical label is a source-grounded short title (at most 40
characters). A Claim Node owns a typed proposition payload: its normalized subject, predicate,
object/value, applicable conditions and scope/time qualifiers. A title or prose description alone
is not the claim. If the payload uses canonical Node references, those are typed content components
of the Claim, not traversable graph edges. A rendered subject-predicate-object edge is a projection
of the payload, not a second persisted Assertion. Ordinary one-off wording remains searchable
through its source Episode, and the deterministic local fallback never promotes it to a Claim Node.

The physical store remains one `nodes`/`assertions`/`evidence` substrate. Semantic slices are
read-only projections over that substrate. Claim Nodes use the same Node identity space and can be
the object of a normal Assertion, such as `Elfie --believes--> Claim`. Every Node and Assertion must
trace to its own source Evidence and then to an Episode or approved Genesis input. A presentation
anchor such as the current Elfie is a view reference to the real `elfie` Node, never a second
source record.

#### 2.2.1.1 Typed attributes and storage ownership

Attributes are a typed Memory capability, not an unbounded JSON escape hatch and not a second
semantic layer. Each registered attribute declares its owner Node types, value type, cardinality,
temporal behavior, source requirement, search visibility and default presentation priority. An
unknown key is rejected from canonical admission or retained only as source wording until a later
registry revision validates it.

Each attribute key has exactly one authoritative storage class:

| Storage class | Use | Examples |
| --- | --- | --- |
| Node property | Stable identity or structural classification; one bounded structured value | `species`, `place_scale`, `object_kind`, `material_kind`, `group_kind` |
| Node description | Sourced human-readable prose, with language/kind/version and Evidence | observed/reported appearance or personality, place introduction, tool usage, family summary |
| Attribute Assertion | A value that is temporal, multi-valued, independently evidenced, conflicting or relational | residence, current object state, a landmark, a typed trait |

`nodes.properties_json` is the validated projection for the first class and bounded searchable
property values approved by the registry; it must not mix technical namespace metadata with user-
visible semantics. `nodes.description` is only the bounded canonical summary. Long or alternate
sourced descriptions belong in `node_descriptions`. Attribute Assertions use the same Assertion /
Evidence contract as relationships and must not be duplicated in `properties_json`. A property is
not converted into an Assertion merely to make it searchable; the registry decides the class, and
the lexical projection indexes only approved user-visible values, descriptions, aliases and
source wording—not IDs, hashes or adapter metadata.

Intrinsic, time-varying and relationship facts therefore remain distinguishable without creating
another fact store. Any Memory description of Elfie's personality is fallible, source-backed evidence,
not a second authority for Selfhood's `adaptive_self`. UI projections may group these records under
“attributes” or “relations”, but a displayed value always points to its authoritative Node property,
Description, Assertion or Episode source.

#### 2.2.2 Assertions / Relations

An Assertion is a sourced, qualified relation record between Node identities and is normally
rendered as a directed graph edge:

```text
Earth --has_shape--> sphere
Owner --helped--> Elfie
```

An Assertion has its own stable record ID and may include a Node or typed literal as object,
polarity, epistemic status, time range, viewpoint, context, validity interval, conflict group,
`importance`, `retention_profile`, `half_life_days` and `confidence`. It is not itself an endpoint
in the current Node-to-Node relation form.

When the proposition itself must be the target of another relation, represent its content as a
first-class `claim` Node. For example:

```text
Claim C42: effort --increases_chance_of--> outcome, when condition C holds
Elfie --believes (conviction=strong)--> Claim C42
```

`Claim C42` is the point that belief, doubt, support, contradiction or derivation can target; the
`believes` relation is an Assertion edge. Claim identity and the typed proposition payload are
canonical in the Claim Node. Any compact edge drawn for its subject-predicate-object content is a
derived rendering, not a duplicate active Assertion. Claim-content Evidence and the Assertion
Evidence that Elfie holds a belief are separate: evidence for the belief does not by itself prove
the proposition true. Conviction (how strongly the subject holds the belief), Claim confidence
(support for the proposition) and Assertion confidence (confidence that the stance was correctly
extracted) are distinct.

For a social tie or another domain-specific degree (for example familiarity or trust), the
Assertion carries a typed qualifier; its `importance` is the default edge significance used for
recall and maintenance. A missing relation means “not recorded”, not “false”.

#### 2.2.2.1 Type and relation registries, direction and multiplicity

Core type groups, Node types, predicates, endpoint constraints, direction, symmetry/inverse rules,
qualifiers and source requirements are defined in a reviewed, versioned YAML registry. Infrastructure
loads the bundled registry and injects an immutable typed view; domain code does not read YAML.
Controlled database extensions may add scoped types or predicates without editing the core file.
Extensions cannot shadow core meanings and must record owner/scope, lifecycle (`candidate`, `active`
or `deprecated`), endpoint constraints, direction/symmetry, required qualifiers, source policy and
registry revision. New Node types have a stricter admission bar than new predicates because they
also change filters, attributes and projections. A stable extension may be promoted into the YAML
core only by reviewed version change. Frequency alone never promotes a vocabulary item: repeated
instances reinforce data; only a distinct, reusable semantic meaning can justify a new type or
predicate.

The initial relation families are:

| Family | Core predicates | Direction rule |
| --- | --- | --- |
| Kinship | `parent_of`, `child_of`, `sibling_of`, `grandparent_of`, `grandchild_of`, `aunt_uncle_of`, `niece_nephew_of`, `cousin_of`, `spouse_of`, `partner_of`, `kin_of` | Parent/child, extended kin and role names are directed with declared inverses; sibling/cousin/coarse `kin_of` and spouse/partner are symmetric. Time-bounded unions retain validity. |
| Social and roles | `friend_of`, `classmate_of`, `colleague_of`, `neighbor_of`, `acquaintance_of`, `guardian_of`, `mentor_of`, `teacher_of`, `student_of`, `member_of`, `has_member` | Peer ties are symmetric; care, teaching, mentorship and membership are directed. |
| Entities | `part_of`, `has_part`, `composed_of`, `made_from`, `derived_from`, `produced_by`, `used_for`, `uses`, `owns`, `owned_by` | Directed with explicit inverse only where registered; material/composition and use are not inferred from proximity. |
| Space | `contains`, `within`, `adjacent_to`, `reachable_from`, `reachable_to`, `located_in`, `route_to` | Containment and reachability are directed; adjacency is symmetric. Distance, travel time, conditions and route alternatives are qualifiers, not Node types. |
| Events | `participates_in`, `witnessed`, `learned_about`, `occurred_at`, `before`, `after`, `causes`, `helped`, `involves` | Directed and time-scoped; participant, witness and learner roles are distinct. |
| Knowledge and self-stance | `subtype_of`, `contains`, `prerequisite_for`, `implies`, `supports`, `contradicts`, `derived_from`, `applies_when`, `believes`, `doubts`, `rejects`, `prefers`, `values`, `has_goal`, `has_trait`, `has_skill`, `has_habit` | Direction and endpoint types are explicit. Self-stance predicates target a Claim or registered semantic Node; they never mean generic `knows`/`about`. |

The stored binary Assertion has one `(subject, predicate, object)` identity. A symmetric relation has
one canonical Assertion and is traversable from either endpoint; a reverse UI view is derived and
does not create a second fact. A directed predicate has an inverse only when the registry defines
one. `kin_of` is valid when the source says “family/relative” but does not identify the exact tie.
No relationship is created from co-occurrence alone. Multiple predicates between the same endpoints
are independent facts and remain visible together. Cross-slice relations connect the original Nodes;
the integrator must not duplicate them into another slice.

`parent_of(parent, child)` renders each endpoint's role correctly. Peer ties such as `friend_of` and
`kin_of` render as mutual relationships. Relation words (`friend`, `family`, `parent`) are predicates
or roles, never Node types.

#### 2.2.3 Evidence

Evidence is a first-class source link. It identifies an Episode or `ApprovedSeedSource`, its
Episode-local excerpt/span or optional upstream media locator, modality, capture time,
speaker/viewpoint and extraction run. Evidence may support or contradict a Claim's proposition
content, or document a self-stance Assertion; these are separate meanings and must not be conflated.

A Claim or Assertion may have many independent Evidence links. Replaying the same source link is
idempotent. Evidence remains available when a description is compressed or a model proposal is
discarded.

#### 2.2.4 Aliases, Descriptions, Episode Mentions

Aliases, descriptions and mentions are separate child records because each Node can have many of them and each can retain its own source/locator, content or span, kind/resolution state and confidence. They have no independent importance score; their availability follows the parent/source retention policy. The Node row keeps only its canonical identity and bounded summary.

`episode_mentions` records semantically meaningful surface mentions, their role/span and resolution state (`resolved`, `ambiguous` or `unresolved`). It does not record every token. Unresolved mentions and Episode wording remain searchable, so a rare term can be found even before it becomes a canonical Node.

The initial implementation bounds semantic mentions per Episode (128 by default) and reports overflow; persisted Episode content is never silently truncated.

#### 2.2.5 Conflicts, viewpoints and Claim Nodes

Contradictory or perspective-dependent propositions remain distinct Claim Nodes when their scope or
content differs, connected by sourced `contradicts` relations; competing Evidence for one canonical
Claim remains separate with its polarity, epistemic status, validity time and viewpoint. Canonicalization
merges identity, not disagreement. No Claim or Assertion is admitted without a source link. A named
philosophical position is a reusable `viewpoint` Node; individual philosophical statements are
Claims in the same general-knowledge slice, not a new philosophy-only slice.

### 2.3 Scores and lifecycle states

#### 2.3.1 importance

`importance` (`I`) is the durable semantic significance of an Episode, Node or Assertion to Elfie, in `[0, 1]`. It is not freshness, familiarity, evidence count or retrieval frequency, and natural time never changes it. A qualified semantic event moves `I` toward a policy-owned target `T_I`:

```text
raise when T_I > I: I' = I + eta * (T_I - I)
lower when T_I < I: I' = I + eta * (T_I - I)
```

The `memory.v3` event classes are `routine` `(T_I=.35, eta=.10)`, `meaningful` `(.60, .20)`, `major` `(.85, .35)` and `core` `(1.0, .50)`. Auditable reappraisal uses `ordinary-lower` `(.30, .25)`, `major-lower` `(.10, .50)` or `revoked` `(0, 1)`. A model may propose an event class but cannot choose `T_I` or `eta`. Node and Assertion importance are independent and never propagate through graph adjacency.

For a relationship, `importance` is retrieval and maintenance salience, not truth. `confidence`
continues to represent support quality. A relation admission starts with a registry type prior and
may be adjusted by sourced evidence strength, repeated independent shared history, recency,
duration, emotional/consequence salience and an explicit Elfie correction. The policy keeps these
signals bounded and transparent; a repeated low-quality co-occurrence cannot turn `neighbor_of`
into `friend_of`. A practical initial weighting is `0.35` type prior, `0.25` evidence strength,
`0.15` independent frequency, `0.10` recency, `0.10` duration/shared history and `0.05`
emotion/consequence, clamped to `[0,1]`. Genesis may provide a sourced initial salience, but it
must pass through the same relation registry. Thus a childhood companion or explicit friend can
rank above a routine neighbor, while both facts remain present and separately supported.

Updates are idempotent by `(event_id, target_kind, target_id)`. Repeated signals for the same target, direction and class are collapsed once per ClosedEpisode. Across Episodes, raise and lower directions are aggregated separately into chronological 24-hour windows anchored by the first event in each window; only the highest accepted class in that direction/window contributes. Opposite directions remain distinct reappraisals and are folded in event-time order. Receipts retain source, occurrence time and policy version; late events are replayed in `(occurred_at, event_id)` order so arrival order cannot change the result. Expiry, disuse, recall failure and contradictory Evidence do not lower `importance` without a separate sourced reappraisal event.

#### 2.3.2 Retention and freshness

Each Episode, Node and Assertion stores `retention_profile`, `half_life_days` (`H > 0`), `last_reinforced_at` and a retention policy version. `H` is the time for freshness to fall from `1` to `.5`, not a remaining-day counter. Time alone never changes `H`. Current `freshness` (`F`) is derived and never persisted:

```text
t = max(0, now - last_reinforced_at)
F(t) = 2^(-t / H)
```

Therefore `F(0)=1`, `F(H)=.5` and `F(2H)=.25`. One versioned Memory admission policy maps record kind, registered Node type or Assertion predicate, authorized source class and bounded salience signals to a policy-owned `retention_profile` and initial half-life `H0`; callers and models never choose a numeric value. The profiles are: transient detail `.5` day, ordinary runtime Episode `2` days, salient Episode `9` days, reusable semantic Node/Assertion `30` days, Pattern/generalization `60` days, stable person/identity/long-lived relation `365` days and authorized Genesis `3650` days. Event/context Nodes and episodic Assertions such as `involves`, `temporal` and `felt` follow their source Episode profile. For one record kind, overlapping matches resolve deterministically in this order: `genesis > stable_identity > pattern > semantic > salient > ordinary > transient`. The selected profile, policy version and admission reason are persisted. Strong sourced emotional, sensory or consequence salience may promote a runtime Episode to `salient`; it does not automatically raise importance or confidence. Reinforcement changes `H` but preserves the profile as admission provenance; sourced relearning may resolve a new profile and `H0`. Every authorized Genesis record selects `genesis`: its ten-year value is a half-life (`F=.5` after ten years), not an archive deadline; Lifecycle independently owns archive and forgetting decisions. The global `H` bound is `36500` days.

A record may be reinforced only after a sourced qualified outcome or direct learning event: an exact prior use is explicitly confirmed helpful/correct, an action using it succeeds, a deliberate source-hidden review is independently verified, or new independent Evidence directly revisits the exact record through the normal Consolidation path. Authoritative re-exposure after failed retrieval follows the separate relearning rule below and does not receive the successful-use multiplier. Merely completing a chat answer is not confirmation. Candidate generation, RecallBundle/Prompt inclusion, graph adjacency, emotion/sensory hits, maintenance, model self-certification and failed/rejected/unknown outcomes do not qualify. Reinforcement is continuous over `0 < F <= 1` and has no Lifecycle threshold gate. Archived/forgotten records are not Recall candidates; only new authoritative sourced evidence can relearn an archived, non-forgotten record, without the successful-use multiplier. For one unique qualified event:

```text
difficulty = 1 - F
multiplier = 1 + 2 * difficulty = 3 - 2F
H' = min(36500, H * multiplier)
last_reinforced_at = event.occurred_at
```

The multiplier is `1` at `F=1`, `2` at the half-life `F=.5` and approaches the hard cap of `3` as `F` approaches zero. Under the initial versioned scheduling calibration `p_success(F)=F`, the success-weighted relative gain is `G(F)=p_success(F)*(multiplier-1)=2F(1-F)`, whose unique maximum is `G(.5)=.5`; the half-life is therefore the default efficient review target without making it a hard eligibility threshold. `G` is a derived scheduling/evaluation surrogate, not a persisted score or a second reinforcement input. Empirical calibration may replace `p_success` in a later policy version without silently changing stored `H`. Importance may choose which records receive a scarce deliberate-review opportunity, but it never changes this formula or `H` directly.

The update is target-scoped and idempotent and resets freshness to one for a qualified active target. Archived/forgotten records never enter Recall; an archived, non-forgotten record can be reactivated only through authoritative sourced relearning, not through a successful Recall outcome. Target-serialized receipts are replayed in event-time order; reinforcement eligibility is evaluated at `event.occurred_at`, so maintenance timing cannot change the result. Receipt times use authoritative UTC; an event beyond a bounded future-skew tolerance is rejected, a small negative read delta is clamped to zero, and a missing original occurrence time is not replaced by processing time. A failed retrieval without authoritative feedback changes neither `H` nor its anchor. Failed retrieval followed by authoritative re-exposure is relearning: write a new Episode/Evidence, use the normal write-side identity resolver's bounded lookup across archived/forgotten fingerprints—not ordinary Recall or a second Retriever—reuse a resolved Node/Assertion identity, set `H` to `max(current H, newly resolved H0)` and reset the anchor without applying the successful-retrieval multiplier. A repeated real-world occurrence is a new Episode, not a rewrite of an old Episode. A correction follows the sourced Evidence/conflict path and may restore clarity while lowering confidence; a superseded Assertion requires sourced reversal and never reactivates merely because it was mentioned.

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

Time and `H` produce `F`; `F` drives lifecycle eligibility. The versioned Lifecycle policy exclusively owns compression, archive and forgetting thresholds. Reinforcement contains no such thresholds, while Recall consumes lifecycle state rather than redefining them. Lifecycle never lowers `F` and never changes `I`, `H` or `C`. Child aliases, descriptions and mentions follow their parent/source dependency. The design stores no freshness or composite retrieval score.

#### 2.3.5 detail level

`detail_level` describes Episode content resolution: `full`, `compressed` or `digest`. Episode `lifecycle` describes availability as `active`, `archived` or `forgotten`. Archiving is a state transition, not a fourth content level; an archived Episode may still retain a full, compressed or digest representation. Assertion lifecycle may be `active`, `superseded`, `archived` or `forgotten`, but an Assertion's last auditable Evidence cannot be removed by maintenance. A historical `life_stage` records the Elfie's developmental phase at the time of an experience; `temporal_label` is its relative period (for example `before_arrival`). Neither is `Lifecycle Stage`, `lifecycle` or `detail_level`. For Nodes, `status` and merge state govern identity availability; maintenance may archive a cold Node but cannot alter its importance or erase a canonical Node still referenced by Assertions.

## 3. Runtime flows

```text
One-time Genesis
ApprovedSeedSource ──► ephemeral GenesisMemorySubmission
                         └─ atomic commit ──► final Memory outputs + marker

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

`ApprovedSeedSource` is an immutable, versioned and hashable creation-time value. An ephemeral `GenesisMemorySubmission` accepts exactly three seed families: `KnowledgeSeed[]` (known world/knowledge, each materialized as a complete source Episode), `EpisodeSeed[]` (the individual's past, each materialized as a complete Episode) and `RelationshipSeed[]` (typed relationship Assertions linked to Episodes or creation Evidence). There is no fourth biography or relationship memory category: biography is the Episode materialization and relationships are the explicitly sourced RelationshipSeed projection. Adoption Genesis must create the owner as an independent `person` Node; the “adoption household” may coexist as a separate `group` Node and must not replace the owner through an alias or be typed as a person. Knowledge and episode-derived Nodes/Assertions are deferred to Consolidation; the identity and relationship skeleton may be committed directly because it is an explicit creation input. Final outputs carry Memory-owned creation Evidence, not the source-package binding or replay seed.

Genesis uses a submission-level completion contract. A Genesis submission is one complete, immutable set of Memory outputs supplied to Memory for one atomic commit. Genesis may call Memory any number of times; Memory does not choose the number, size, order, grouping, scheduling or meaning of those submissions (for example, core versus enrichment or foreground versus night work). Each submission has its own stable submission/idempotency identity and content hash, even when several submissions belong to one higher-level Genesis operation.

For one valid submission, every expected authoritative and child record—identity/relationship Nodes and Assertions, source Episodes, their creation Evidence, and that submission's completion marker—must be durable and visible as one completed unit. Knowledge and episode-derived graph projections are deliberately not part of this atomic creation set; they are later retryable Consolidation output. Atomicity means “accept only the current submission”: validation happens before any write; the Unit of Work either commits every output and the marker or commits none of them. A failed call returns only a failed or retryable result and never `committed`. Retrying the same submission identity and hash is idempotent; reusing an identity with a different hash is rejected. Previously committed submissions remain valid when a later submission fails.

The Genesis caller owns batching, ordering, retry timing and the decision about when adoption is published. Memory only exposes completed submissions inside the still-unpublished creation workspace; App admission controls final workspace visibility. Memory does not report an overall Genesis operation as complete. A committed Elfie has no Genesis reinitialization path; an approved migration or a real learning event must operate on final-owner state. Cross-owner adoption publication remains its own contract and is not a fictitious cross-store transaction. Genesis accepts explicit initial Episode/Node/Assertion `importance` and Node/Assertion `confidence`; its authorized admission selects the common `genesis` profile, giving every Genesis-produced semantic record `retention_profile=genesis` and `half_life_days=3650`. It does not simulate conversations or manufacture importance with emotion intensity. Direct graph projection is forbidden for normal runtime callers.

Genesis admission is serialized per Elfie. The completion marker is the sole visibility gate for Genesis rows: no reader or maintenance pass may use a row from that submission before its marker is present. Genesis accepts any valid complete submission, including a submission containing only a subset of the approved seed families. It does not require every seed family in every submission and does not infer a caller's batching policy.

After final creation commit or terminal abort, the `ApprovedSeedSource`, submission payload, source-package binding and generation seeds are deleted. The Memory database keeps only final Episodes, Nodes, Assertions, Evidence and the minimal submission completion/idempotency marker required by its own atomicity contract. That marker cannot regenerate the submission and is never Recall content.

Genesis does not turn its submission or initialization procedure into an Episode experience. Seed
provenance remains on source references/Evidence, the experience kind describes the learned or lived
content, and an acquisition/occurrence time is set only when the source supports it. Bundle creation
and submission timestamps are operational timestamps, not assumed knowledge-acquisition times.

### 3.2 Normal runtime write

The upstream Workspace closes and validates an event, then supplies a complete `ClosedEpisode`. The capture transaction writes the Episode, idempotency key, source references and content hash. It does not call a model and does not update Nodes/Assertions from incomplete content. Graph Evidence links and projection happen later in Consolidation Stage; the text projection is rebuildable and is not a second source.

### 3.3 Memory Maintenance

Memory Maintenance is one bounded operation. It may run in small continuous batches and use idle/sleep time to catch up. It has two ordered stages and one budget policy. Checkpoints, leases and retry attempts are operational control state outside authoritative Memory fact records; they are not a semantic memory type, a recallable queue or a second fact source.

Per-Episode consolidation progress shown by Developer Tools is a read-only projection of the owning
Maintenance operation/checkpoint and its source-version-bound success receipt. Both the receipt and
queued/running/failed state belong to Maintenance operational state, not the Episode fact row. If the
owning projection provides no status, report it as unknown/unobserved rather than inferring it from
`event_kind`, `detail_level` or Memory lifecycle.

#### 3.3.1 Consolidation Stage

For complete Episodes with no success receipt for the current source version/content hash in
Maintenance operational state (including a prior failed attempt), Consolidation has six logical extraction responsibilities: five
domain extractors (Social relations, Entities, Space, Events, and General knowledge) plus a Self-model
projector. A shared cross-slice integrator and relation pass
connects their outputs; these are responsibilities within one Consolidation stage, not separate
Memory owners, databases, or required model calls.

1. Each domain extractor identifies only important/reusable Nodes, explicitly sourced relations and
   reusable knowledge in its slice; other wording stays in the Episode or as an unresolved mention.
2. A shared resolver canonicalizes identity, aliases and coreference across slices, then validates
   endpoint types, registered predicates and source Evidence. It may emit an explicitly sourced
   cross-slice relation, but must not infer one from co-occurrence or invent a new fact.
3. The Self-model projector first selects sourced stance Assertions (such as `believes`, `prefers`,
   `values`, `has_goal` or `has_trait`) for the Elfie's cognitive perspective. It then includes the
   referenced Claim/semantic Nodes and only bounded, relevant Claim-to-Claim relations, conditions
   and Evidence needed to explain those stances. It does not pull every incident edge, create a
   `self_model` Node, or add generic `knows`/`about` edges. Evidence-backed outputs are proposals
   for the Selfhood and Orientation owners; they independently decide whether and how to update
   their models. Memory does not write either owner's state directly.
4. Merge compatible Assertions, retain independent Evidence and represent disagreements without
   collapsing distinct Claim content or viewpoints.
5. Recompute Node/Assertion `confidence` from unique Evidence, emit only qualified sourced importance
   events, and reinforce only exact records directly revisited by new independent Evidence.
6. Commit all validated outputs through the existing Consolidation Unit of Work and record the
   source/projection and registry revisions in a Maintenance operational receipt keyed by Episode
   ID, source version and content hash—not on the Episode fact row. Optional cross-slice statistics
   are derived diagnostics only; they do not generate Nodes or Assertions.

Predicates come from a versioned vocabulary. An unknown predicate stays an unresolved candidate until validated; it is never silently promoted to a fact. Co-occurrence alone is not a relation. A local attribute remains a Node property or typed literal unless it has an independently reusable identity.

A model may propose extraction, disambiguation or a summary outside the write transaction. Deterministic code validates spans, types, scope, predicates, IDs, Evidence and revisions, and performs the final write. Without a model, Episode capture and FTS remain usable; semantic projection waits for a later attempt. There is no keyword gate and no ungrounded fact fallback.

#### 3.3.2 Lifecycle Stage

For any Episode or Assertion with active `lifecycle`, or Node with active `status` and no canonical merge target, whose derived freshness threshold is due—independent of capture date—apply the versioned transitions in §6.3 without mutating `importance`, `retention_profile`, `half_life_days`, `confidence` or `last_reinforced_at`. These thresholds are operational Lifecycle parameters, not reinforcement or Recall constants.

An Episode without a successful projection for its current source version retains enough complete source for projection. Automatic forgetting is logical: a minimal digest, hash and provenance remain; physical deletion is outside `memory.v3`. Low confidence is never a deletion reason. An old record is found by its calculated `next_review_at`, not by the current capture batch, and one unsafe target does not block other bounded records.

### 3.4 Hybrid Recall

Recall is deterministic and index-driven on the hot path; it does not require a model call.

#### 3.4.1 Basic / Text Search

Lexical/full-text search (and an optional vector index) finds Episode wording, Node names, aliases,
sourced descriptions, user-visible Node properties, rare terms, detailed stories and source
references. A query can therefore find a person from an attribute such as appearance even when the
canonical name is forgotten. Structured property filters may add exact or range constraints when a
caller knows the property path. This is the direct Episode/Node candidate path, not a search over
raw upstream conversation logs.

#### 3.4.2 Local / Graph Search

Starting from text hits or supplied Node/Claim IDs, bounded typed traversal follows relationships to people, places, concepts, emotions, events and related Episodes. Traversal keeps a visited set, does not revisit a Node within one path, and returns explicit paths; hop, neighbor and result limits are hard caps. Person, time, place, historical emotion, topic and cause facets constrain or rank the same candidates.

#### 3.4.3 Global Search (later capability)

Broad thematic or community search is deferred until the graph has representative density. A graph
summary or Pattern may be a direct Recall result, but it must remain traceable to Assertions and
Episodes and is not a new fact source.

#### 3.4.4 RecallBundle

The minimum route is Basic/Text → Episode and/or Node–Assertion candidates → bounded Local/Graph expansion → selected Episodes/Evidence when context is useful. Privacy and namespace filters run before ranking. Ordinary Recall returns active records only; archived and forgotten records are never Recall candidates, including for historical-text or exact-ID queries. A separate, explicit maintenance/audit inspection is not Recall and cannot add those records to a `RecallBundle`. Query relevance `R` combines lexical/semantic match, graph path and requested time/facets; Memory then derives `A=.65F+.35I`. Eligible Nodes/Assertions rank by `R*A*(.25+.75C)`, while Episodes, which have no confidence, rank by `R*A`. Superseded/conflicting Assertions use a separate `R*A` lane so low confidence does not hide history. Each kind lane has a bounded quota and stable-ID tie-breaker; `H` is not scored again because it already determines `F`. Retrieval alone is not reinforcement; archived records can be relearned only through new authoritative sourced evidence under the Lifecycle policy, never by Recall itself.

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

Input is a complete, already-processed `ClosedEpisode` with a stable ID or idempotency key, occurrence range and precision, registered experience `event_kind`, Episode content, attribution, provenance references and hash. An Episode has no separate title field; optional `summary_text` is a source-grounded synopsis, may be empty, and never replaces the original content. The hash covers the persisted Episode payload and referenced-source versions, not a later graph projection. Output is a receipt containing the durable Episode ID and state. The operation is atomic and idempotent; it never creates graph facts from partial content.

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

Node–Assertion supplies high-density structure and reusable knowledge; Episodes supply the complete
topic context; Evidence explains the derivation; and the consuming layer supplies narration. A
Recall result does not have to include raw upstream conversation or media.

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

### 5.1 Persistent fact and operational tables

SQLite is the first physical implementation. One Memory Adapter/database is bound to one Elfie namespace; a caller cannot query another Elfie's rows. The tables below include semantic fact tables and explicitly marked operational/registry state; only semantic fact rows are the remembered graph/source authority. JSON columns are bounded metadata only and never hide graph edges or provenance.

| Table | Required responsibility |
| --- | --- |
| `episodes` | Complete processed Episode content, optional source-grounded `summary_text` synopsis (never a separate title and never a replacement for content), registered experience `event_kind`, occurrence range (nullable when unknown) and occurrence precision, historical `life_stage`/`temporal_label`, separate write time, attributed context/media/upstream references, privacy scope and version, `importance`, `retention_profile`, `half_life_days`, reinforcement/lifecycle metadata, `detail_level`, Memory `lifecycle`, idempotency key and content hash. Episodes have no title, provenance-label, consolidation-progress, successful-projection receipt or confidence column. |
| `memory_maintenance` | Operational work state for Episode consolidation and lifecycle: pending/processing/completed/failed/skipped state, attempts, retry time, lease owner/expiry, error and checkpoint, plus the source version/hash and projection revision that bind a receipt to the exact Episode source. It is not a semantic Node or Episode field. |
| `nodes` | Canonical identity, type/label, scope/status, bounded summary and structured properties, `importance`, `retention_profile`, `half_life_days`, `confidence`, immutable confidence-prior/policy provenance, reinforcement/lifecycle metadata and merge pointer. A `claim` type is an addressable semantic Node, not an Assertion row. |
| `claim_contents` | One-to-one typed proposition payload owned by a Claim Node: normalized subject, registered predicate, object/value, conditions and scope/time qualifiers. Optional Node references are validated content roles, not traversable graph edges; the payload is not hidden in arbitrary JSON and is not duplicated as an active Assertion. |
| `node_aliases` | Many scoped aliases with their own source and confidence. |
| `node_descriptions` | Many language/kind-specific descriptions, content hash and source link. |
| `episode_mentions` | Episode-to-Node links, roles/spans and resolved/ambiguous/unresolved state. |
| `assertions` | Subject, predicate, Node or explicitly typed-literal object (type/value/unit), qualifiers, polarity, epistemic status, viewpoint/context, validity, `importance`, `retention_profile`, `half_life_days`, `confidence`, immutable confidence-prior/policy provenance, reinforcement/lifecycle metadata, conflict group, lifecycle state and fingerprint. |
| `evidence` | Episode or seed source locator, source version, excerpt/media span, modality, speaker/viewpoint, capture time, `independence_key`, source-reliability class/policy version and extraction metadata. |
| `assertion_evidence` | Many-to-many Assertion/Evidence stance: `supports`, `contradicts` or `context`. |
| `claim_evidence` | Many-to-many Claim Node/Evidence stance for the proposition itself: `supports`, `contradicts` or `context`; distinct from Evidence that supports the subject's `believes` Assertion. |
| `registry_extensions` | Controlled additive type/predicate registrations and their scope, lifecycle and revision; operational vocabulary state, never Recall content. |
| score event receipts | Adapter-private, non-recallable, source-linked importance and qualified-use/retention events used for idempotency, aggregation and event-time replay. They are authoritative policy inputs/audit state, not a semantic memory type or second source of remembered claims. |

These dimensions reuse the existing Episode storage concepts: `summary_text`, `event_kind`, occurrence
time/precision and durable source references/Evidence. The current-source projection receipt is kept
in Maintenance operational state, keyed by Episode ID/source version/content hash. No separate title,
provenance-label or consolidation-progress column is added. `event_kind` is narrowed
from an arbitrary non-empty string to a key in the reviewed experience-kind registry, and
`summary_text` is accepted as a display synopsis only when source-grounded. This is a persisted value
contract change: Memory schema v8 enforces the registered `event_kind` values and rejects a v7
database before mutation; there is no migration or fallback reinterpretation of old values.
Consolidation progress comes from the owning operational read model, outside Episode fact rows.

Each Genesis submission's ID/version/hash and completion marker are durable package metadata owned by the Memory Adapter, not a semantic Node/Assertion and not a retry queue. The marker lives in the same Memory SQLite database and is committed in the same transaction as that submission; its physical metadata record/table name is adapter-private and is not an additional semantic memory table. The marker is written only after every expected Memory row, including child rows, is ready for the commit. Every Genesis-produced row carries the submission identity, and readers ignore rows whose submission marker is absent. A retryable or interrupted submission is not an initialized Memory and is not recallable as one; its operational control state may be reconstructed from the immutable input. The marker records (or hashes) the expected IDs/counts for each output family so reconciliation proves more than the presence of Node rows. Derived FTS/vector indexes and RAM caches are not part of the fact-package completion check and may be rebuilt only after the complete commit. These records do not form a second mutable fact store. `importance` and Node/Assertion `confidence` are semantic scores; `retention_profile` and `half_life_days` are persisted policy state, while freshness and query rank are derived. Evidence rows and their stances remain the authoritative support record.

### 5.2 Derived indexes and cache

`episodes_fts` and `nodes_fts` are rebuildable full-text projections over original Episode text,
optional synopsis text, explicitly approved Episode `aliases`/`retrieval_terms`, labels, Node aliases,
sourced descriptions and approved user-visible Node properties. Episode retrieval hints improve
search but are not Episode prose, synopsis text or a second semantic fact.
Technical identifiers, submission metadata, provenance IDs and retention/scoring fields are not
ordinary property-search text. No separate semantic Segment layer is required by this design; an
internal slice for an unusually large Episode would be a rebuildable index detail only. An optional
vector index is a later optimization, never a first-implementation prerequisite, and is also
derived. Required lookup indexes cover lifecycle/status plus
`next_review_at`, Maintenance projection receipts by Episode/source revision/time/hash, Node normalized label/type/status,
aliases `(normalized_alias, scope)`, descriptions `(node_id, language, kind)`, mentions by Node and
Episode, Assertions by subject/predicate and object/predicate, conflict/supersession, Evidence
source/independence key, both directions of `assertion_evidence`, and unique score-event receipts.
Recall first obtains a bounded indexed candidate set and derives freshness/rank only for that set; it
never computes freshness across the whole database. Operational leases, retry attempts and
checkpoints are bounded controls and never returned by Recall. A non-null Maintenance projection
receipt is keyed to the Episode source version/content hash; absence, or a receipt tied to an older
source hash, means that the current projection has not been committed. Each index
exists for a bounded query and declares its rebuild source. The first implementation stays on the
embedded relational store; a dedicated graph engine is not a prerequisite.

Score receipts also have bounded operational growth. Within a versioned late-arrival safety window, complete receipts remain replayable. After the source outcome/Evidence is durable, all local outbox events through a target watermark are settled and the window expires, importance receipts compact to the highest class per direction/window and reinforcement receipts fold into a checkpoint that retains policy version, folded state, event count/hash and last event time. A receipt older than the settled watermark is rejected into observable reconciliation state; it never silently changes the score or substitutes processing time. This compaction applies only to score-control receipts, never to semantic Episodes, Evidence or conflict history.

RAM holds bounded hot Nodes, adjacency pages, recent neighborhoods and index pages. A cache miss reloads durable rows; it never constitutes memory loss. Media is loaded on demand.

### 5.3 Constraints, uniqueness and conflict preservation

Foreign keys are enabled and deletion is restricted by default. Episode idempotency keys and content hashes prevent duplicate capture. An Assertion fingerprint includes normalized subject, predicate, object, qualifiers, polarity, viewpoint and validity; it does not collapse distinct times, perspectives or conflicts. Evidence identity also includes source version, modality and locator/span, so the same locator in a new source version is a distinct source link. Exact replay is idempotent.

Aliases may be ambiguous across scope. Mentions may remain unresolved. Descriptions deduplicate by Node/language/kind/content hash while retaining separate sourced versions. An Assertion has exactly one Node object or one typed-literal object. Queryable assertion fields and qualifiers are columns or explicit indexed child records; a typed literal uses mutually exclusive node-ID versus type/value/unit fields, and bounded JSON is only non-queryable metadata. Node merges keep the old ID and point to the canonical ID. No bare-triple unique key may overwrite evidence or disagreement.

### 5.4 Transactions and Unit of Work

Genesis applies the completion guarantee in §3.1: it validates one complete submission before opening one submission-scoped transaction, writes every Memory output (Nodes, Assertions, Evidence, Episodes and child records) and that submission's marker in the same commit, and returns success only after the complete set is reconciled. A failed commit is not a completed state; the same immutable submission remains unpublished and can be retried with the same identity and hash. Earlier successful submissions are not rolled back by a later failure. Normal capture commits the complete Episode and its source references together; its derived text index may be updated in that transaction or rebuilt after commit. Maintenance validates model proposals outside the transaction, then commits graph changes, Evidence links, score updates, lifecycle and the source-version-bound projection receipt in one short Unit of Work. The receipt belongs to Maintenance operational state, not an Episode fact row; derived indexes are updated or rebuilt only after the fact commit and never decide whether the fact package completed. A transaction never includes model or network calls.

SQLite uses `PRAGMA user_version`, foreign keys, WAL, a bounded busy timeout and one serialized writer. Derived indexes can be deterministically rebuilt from authoritative tables.

### 5.5 Restart recovery

Episodes, Nodes, Assertions and Evidence survive restart. Maintenance claims bounded records with operational leases/checkpoints; an expired lease is reclaimable. A crash before a normal commit leaves the source unchanged; a crash after commit is recognized by the idempotency key/fingerprint. A crash before a Genesis submission commit leaves that submission unpublished; recovery checks the same immutable submission identity/hash and retries that submission. The `committed` state is valid only when every expected output, child record and that submission's completion marker are present. FTS and RAM caches are rebuilt when missing.

## 6. Lifecycle, recovery and fresh-store policy

### 6.1 Episode detail lifecycle

Lifecycle is the detail and availability state of an already stored record, not a new memory type. A due-time scan covers old and new records alike. `next_review_at` is the predicted wall-clock crossing of the next freshness threshold and is recalculated when `H` changes; maintenance frequency therefore cannot change freshness. Crossing a threshold creates due work, not an implicit state mutation: Recall observes the last committed lifecycle state until a bounded, observable maintenance transaction advances it. Lifecycle consumes derived `F` but never updates `I`, `H`, `C` or the reinforcement anchor. An Episode without a successful projection for its current source version keeps enough complete source for a future projection; a projected Episode may move from `full` to `compressed` or `digest`, while archiving is a separate availability state. Both changes require source and graph-dependency checks.

### 6.2 Source Evidence protection

An Evidence row that is the last auditable source for an active Assertion cannot be deleted. Compression may shorten an Episode's rendered detail, but it preserves a hash plus an excerpt, locator or digest sufficient to trace the Assertion. Seed sources and their versions remain immutable. Any destructive deletion is explicit, reversible during development and reported by ID. An explicit owner correction is a new sourced Episode/Assertion and may supersede an older Assertion; it never mutates the historical source in place.

### 6.3 Compression, archive, digest and forgetting

The initial `memory.v3` Lifecycle policy is:

| Due condition | One committed transition |
| --- | --- |
| `F <= .40` | eligible projected Episode: `full → compressed` |
| `F <= .20` | eligible projected Episode: `compressed → digest` |
| `F < .10` | eligible active record: `active → archived` |
| `F <= .01`, `I <= .10`, archived at least 90 days, dependencies safe | `archived → forgotten` |

These values are versioned operational parameters, not human-memory constants. One transaction advances at most one lifecycle stage per target. Episodes without a successful current projection retain their source. Forgetting keeps a minimal digest, hash, provenance, stable semantic/source fingerprint and the `retention_profile`, `H` and anchor required by bounded write-side identity resolution and sourced relearning; it never removes the last auditable Evidence. Archived and forgotten records are never returned by Recall. An archived, non-forgotten record may be reactivated only by authoritative sourced relearning, which preserves at least the previous `H`, may adopt a newly resolved higher `H0`, and never applies a successful-retrieval multiplier; it does not restore discarded detail. A repeated real-world occurrence is captured as a new Episode.

### 6.4 0.x fresh-store policy

Before the 0.5 data-compatibility baseline is frozen, Memory supports only a fresh database created by the current schema. An old or mixed database is rejected before any business write. Runtime does not import, replay, dual-write or fallback-read legacy Memory data. An operator may back up the exact data root and explicitly rebuild it; the application never deletes or overwrites an old database automatically.

The old `entities`, `events`, `entity_edges` and related tables are therefore discarded by policy, not transformed in place. A reset-required result identifies the database path and leaves the rejected file unchanged. Fresh initialization creates only the current Episode, graph, Evidence and operational tables.

## 7. Non-negotiable invariants

1. An Episode is a complete, already-processed topic/story unit before extraction; Genesis content is complete in its approved source before projection.
2. Every durable Assertion has Episode or seed Evidence; model output alone is never a fact.
3. Canonicalization merges identity, not contradictory viewpoints or unrelated entities.
4. Conflicting Assertions retain polarity, time, perspective and source.
5. Graph knowledge, vectors and scores cannot lose their Episode/Evidence provenance or silently become objective truth.
6. Episode and Node–Assertion are the only semantic Memory layers. A typed Claim payload is content owned by a Claim Node, not a third layer; it is addressable by relations such as `believes`, while an Assertion itself is not an endpoint.
7. Live state, plans, commitments, permissions and actions remain with their owning systems.
8. Memory never directly reads Profile, Communication history or world runtime state.
9. Genesis direct projection is limited to approved submissions and cannot become runtime CRUD.

## 8. Validation and stage gates

Each implementation round closes only with code and replayable evidence. The target design is not proof that the current implementation already conforms.

### 8.1 Source integrity

Verify complete Episode capture, content hashes, idempotency, atomic Genesis submission completion, retry behavior and reopen-after-restart. Gate: 100% of accepted fixtures preserve source hashes, every accepted submission reaches a complete marker with all expected child records, and no uncommitted submission output is visible.

### 8.2 Graph provenance

Verify mention resolution, canonicalization, Assertion/Evidence links, Claim payload validation, Claim/Evidence stances, and independent descriptions/conflict retention. Include a fixture where `Elfie --believes--> Claim` resolves to a Claim Node and the stance Evidence is not mistaken for evidence that the proposition is true. Gate: every fixture Claim and Assertion has a resolvable source; unsupported proposals are rejected.

### 8.3 Hybrid retrieval

Replay a rare term, a relationship-network query, a knowledge object, an emotion facet and a time-bounded experience. Verify Basic/Text fallback, bounded Local/Graph paths, RecallBundle provenance and explicit truncation. Initial targets: rare-term recall@5 ≥ 0.90 and relationship-path precision = 1.00.

### 8.4 Importance, retention, confidence and conflicts

Verify target-ceiling importance updates and 24-hour aggregation, event-time replay, checkpoint-compaction equivalence and pre-watermark late-event rejection, the frozen freshness vectors, monotonic reinforcement with `M(1)=1`, `M(.5)=2` and `lim(F→0+)M(F)=3`, the maximum of `2F(1-F)` at `.5`, active-only Recall with archived/forgotten exclusion, failed retrieval and sourced relearning, Evidence-order-independent Node/Assertion confidence, every versioned Lifecycle boundary, and the absence of Episode confidence. Time and Lifecycle must not mutate importance, retention or confidence; Recall candidates alone must not reinforce; contradictory Evidence remains visible and may lower confidence while restoring clarity through its sourced reappraisal path.

### 8.5 Performance and capacity

Measure both maintenance stages, bounded RAM, growth/retention behavior and database-only Basic + Local p95 ≤ 150 ms on a representative 10,000-Episode / 50,000-Node / 200,000-Assertion fixture. The endurance gate must also prove that an old or mixed database is rejected without mutation and that a fresh database can be rebuilt and reopened.

## 9. Resolved implementation decisions

This section closes implementation ambiguities identified during review. It is normative for the Memory implementation, but it does not assign Genesis batching, ordering or scheduling to Memory.

### 9.1 Source shape, namespace and privacy

- The Memory Adapter is constructed for one immutable `elfie_id`; every read, write, maintenance operation and Genesis submission is checked against that namespace. A caller cannot widen it through a request or raw identifier.
- `occurred_from` and `occurred_to` may be unknown. An explicit occurrence-precision value distinguishes an exact instant, a bounded range and an unknown time; unknown time is not replaced with a fake epoch and is excluded from time ranking unless the caller requests an unknown-time facet. For a Genesis knowledge Episode, these fields describe an evidenced learning/acquisition time, not the bundle, creation or submission timestamp; absent evidence remains unknown.
- Episode `event_kind` is a registered experience category and is distinct from both provenance and epistemic attribution. Provenance (for example, Genesis, conversation source or media) is grounded in durable source references and Evidence; `observed`, `told`, `inferred` and `felt` describe how the content is known, not where it originated. Participants, places and objects are represented by bounded `episode_mentions` roles; scene context is retained as bounded source context, not hidden graph edges.
- Source and media references carry version/locator/hash data. Privacy scope is enforced at the Memory boundary and is included in source inspection and Recall filtering; it is never inferred from a display label.
- Corrections create a new sourced Episode/Assertion. The historical source row and its version are not mutated in place.

### 9.2 Scores, review and lifecycle

- `importance` and Node/Assertion `confidence` are persisted semantic scores; `retention_profile` and `half_life_days` are persisted policy state. Episode has no confidence; freshness, success-weighted review gain and composite retrieval rank are derived and never persisted. There is no `support_score` compatibility field.
- Importance is folded in event-time order from idempotent, source-linked, aggregated semantic-event receipts. Confidence is recomputed from all unique Evidence and independence groups. Successful-use Retention is folded from idempotent, target-scoped qualified-outcome/review receipts using `H'=H*(3-2F)` with a global cap; failed retrieval changes nothing, while authoritative re-exposure uses the separate sourced relearning rule. A retry or maintenance pass cannot add a contribution twice.
- Episodes, Nodes and Assertions carry `retention_profile`, `half_life_days`, reinforcement/review timestamps and policy version. Lifecycle alone owns versioned compression, archive and forgetting thresholds. Ordinary Recall consumes active records only; archived and forgotten records are excluded from every Recall lane. Explicit audit/maintenance inspection is a separate capability, not Recall. Authoritative new Evidence may relearn an archived, non-forgotten record under the sourced relearning rule; retrieval itself never reactivates or strengthens it.
- Lifecycle transitions are guarded and ordered: preserve a source that lacks a successful current projection; then allow `full` → `compressed` → `digest`, archive separately, and forget logically only after freshness, importance, residency and dependency checks. Forgetting never removes the last auditable Evidence for an active Assertion.
- Consolidation leases, retry attempts, checkpoints, source-version projection receipts and rejected proposals are operational control data outside authoritative fact rows. One bounded Memory Maintenance Unit of Work owns the writer transaction; normal capture and Genesis submissions remain separate operations.

### 9.3 Projection and predicate validation

- The reviewed, versioned YAML registry is the immutable-in-use core for slice groups, canonical Node types, Episode experience kinds, predicates, endpoint/direction rules, qualifiers and source requirements. Infrastructure loads it and injects a typed snapshot; domain code does not read YAML directly. Episode kind additions require a reviewed registry revision; provenance and operation names are not eligible kinds.
- An additive database extension registry may hold scoped `candidate`, `active` and `deprecated` types/predicates. Candidates are not valid for canonical writes; extensions cannot shadow core definitions and must pass endpoint, direction/symmetry, qualifier and source-policy validation. New Node types require stronger review than predicates. Stable core promotion requires a reviewed YAML revision; occurrence frequency alone is not a promotion rule.
- A combined registry revision is recorded with each successful projection. An unknown or inactive predicate/type remains a bounded candidate and is never silently promoted to a fact.
- An unknown or invalid model proposal is retained only as bounded diagnostic/retry data and is never inserted as an active Assertion. It can be retried after the registry or source validation changes.
- Maintenance operational state records `(episode_id, source_version, source_hash, projection_revision)` after a successful projection. Missing or stale receipt means the current source still needs projection; a retry does not create a second Episode, and the receipt is not stored on the Episode row.
- Runtime callers use only the source-first typed path. Legacy `add_edge`/bare-edge writes are removed after their callers are migrated; they are not a runtime or migration API.

### 9.4 Recall semantics

- Facets are positive constraints: different facet families combine with AND, values within one family combine with OR, and missing facet data does not become a negative fact. Historical emotion is read from the Episode's attributed source, never from live Emotion state.
- Ranking is deterministic and kind-specific: derive query relevance `R` and freshness `F`, then use `R*(.65F+.35I)*(.25+.75C)` for eligible active Nodes/Assertions, and `R*(.65F+.35I)` for active Episodes and the conflict lane. Archived and forgotten records are not ranked into Recall results. Results remain separated by kind with stable-ID tie-breakers; policy components are bounded and versioned.
- Active Assertions are preferred, while relevant `superseded` and conflicting Assertions remain visible with explicit status and Evidence. Privacy and namespace filtering happen before ranking.
- Basic/Text and Local/Graph are the initial modes. Global/community and vector retrieval remain derived, later capabilities and are not advertised by the initial contract.

### 9.5 Fresh schema and compatibility boundary

- Schema changes create a fresh target schema and use an explicit version check. The narrowed Episode `event_kind`/`summary_text` value contract requires a new schema-version boundary even though it adds no Episode columns; the previous database is rejected before initialization mutates it. No importer, fallback reader or dual write exists before 0.5.
- The reset-required result identifies the exact database path and directs an operator to back up and explicitly rebuild the data root. The application never deletes, overwrites or silently repairs the rejected database.
- The current schema contains source-first Episode, Node, Assertion, Evidence, Node-owned Claim content, and bounded operational/registry tables. Claim payloads are addressable through their Claim Node but are not extra graph edges or a third semantic layer. Legacy entity/event tables, legacy edges, `support_score` and `source_type='legacy'` are not accepted inputs.

### 9.6 Verification and observability

- Every write path has failure-injection coverage before and after its commit point, including concurrent duplicate submission, hash mismatch, restart, lease expiry and uncommitted-row visibility.
- Maintenance and Recall tests cover idempotent score updates, source protection, facet semantics, supersession/conflict visibility, namespace/privacy isolation and hard truncation limits. Fresh-store tests cover old/mixed-schema rejection without mutation, new-schema creation and reopen.
- Performance evidence records cold/warm initialization, per-Unit-of-Work time, SQLite lock wait, row counts, retry latency and Recall p95. The existing representative Recall target remains p95 ≤ 150 ms; Genesis batching policy is chosen from measured startup evidence, not from this Memory contract.
- After schema or transaction changes, rerun the persistence inventory, focused adapter/contract tests, quality checks and `git diff --check`; update the Conformance row with target, inventory, references, verification and residuals.
