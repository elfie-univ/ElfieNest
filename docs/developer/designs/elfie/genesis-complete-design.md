# Complete Genesis design

> Status: accepted target design, version 1.0, 2026-09-25. The two phases, three preparation steps and five individual-generation steps remain intact. Implementation and verification gaps are tracked in ELF-019; acceptance of this design does not assert implementation completion.

**Design relations:**

- Owner module: Elfie / Genesis.
- Parent design: [Elfie top-level module design](./elfie-top-level-module-design.md).
- Child designs: none.
- Normative contracts: [Elfie](../../contracts/elfie.md), [System](../../contracts/system.md), [Configuration management](../../contracts/configuration-management.md), [Application](../../contracts/application.md).
- Current architecture: [Architecture index](../../architecture/index.md).
- Conformance: [Elfie, ELF-019](../../conformance/elfie.md).
- Domain sources: registered source IDs `elfaria-generation-rules`, `elfaria-geography-source`, `elfaria-resident-knowledge`, and the species and appearance sources bound by the published package.

**Reading order:** sections 1–3 explain the complete flow; sections 4–5 define boundaries and acceptance. Section 6.4 specifies package compilation, 6.5 individual-generation algorithms, and 6.6–6.7 determinism and admission recovery.

## 1. Overall flow and final results

Genesis prepares reusable generation material and then creates an individual whose identity, appearance, personality and past are consistent.

~~~text
Phase one: prepare once, reuse across adoptions
1. Author foundational material
   World setting + species material + appearance rules/assets
2. Organize generation sources
   Resident knowledge + spatial, species, appearance and individual-generation sources
3. Compile, compare, validate and publish
   One version-bound GenesisSourcePackage under config/genesis/

Phase two: generate one individual per adoption
1. Resolve user choices and generate candidates
2. Accept a candidate and freeze identity, appearance and personality anchors
3. Establish a life structure and feasible activities (LifeContext)
4. Generate personal knowledge, relationships, episodes and self (PersonalGenesisPlan)
5. Validate jointly, submit and complete admission
   Profile + Selfhood + Memory and other final-owner results
~~~

The phases communicate only through a **published package**. Phase two does not read unpublished sources; a committed Elfie no longer depends on creation material.

| Final owner | Stored result |
| --- | --- |
| Profile | Stable identity, names, species, applicable sex, age/origin anchors and final virtual appearance |
| Selfhood | Immutable identity core and bounded personality, values and interaction/expression tendencies |
| Memory | Knowledge actually acquired, personal facts, known people, relationships, experiences and supporting evidence |
| Corresponding Body/Brain owners | Contract-required bodily/perceptual constraints and initial capabilities; life skills do not grant tool permissions |

Genesis does not own ordinary learning, live Nest state, continuing experience generation, or Godot geometry, movement and rendering.

## 2. Phase one: prepare and publish generation material

### 2.1 Step one: author foundational material

Creators define three kinds of material:

- **World:** regions, settlements, places, roads, nature, society, history, Earth-departure context and unknown boundaries.
- **Species:** bodies, perception, life cycles, living conditions and capability limits.
- **Appearance:** life stages, proportions, faces, colors/markings, supported parameters and assets.

Maps, tables and pictures can accompany these sources. Facts affecting generation need provenance and review ownership. This step does not author a particular Elfie's family, vocation, personality or memories.

### 2.2 Step two: organize generation sources

Organize the material into four human-readable responsibilities, primarily Markdown:

| Source | Required content |
| --- | --- |
| Resident knowledge | Concrete knowable facts and distinctions among hearsay, experience and the unknown |
| World and spatial rules | Legal birthplaces, homes and routes; maps, species regions, roads and travel-time evidence |
| Species, life-stage and appearance rules | Valid identity/age/appearance combinations and required assets |
| Individual-generation parameters and constraints | World-specific kinship ages, learning durations, departure conditions, probabilities and budgets; this design owns the overall algorithm |

These are content responsibilities, not a requirement for exactly four files. Knowable world/species/appearance facts enter resident knowledge. Parameters and constraints enter their rule source. Sources do not repeat the whole generation algorithm. Resolve missing conditions and contradictions here.

| Artifact | Responsibility |
| --- | --- |
| This design | Two-phase flow, generation algorithms, ownership, dependency order and acceptance |
| `elfaria-generation-rules` | Human-readable values and conditions, distinguishing registered rules from parameters awaiting compilation |
| `elfaria-geography-source` | Reviewed places, spatial relations, grids and routes |
| `elfaria-resident-knowledge` | Original knowledge units, eligibility conditions and difficulty |
| `program.yaml` and members | Validated, version-bound machine configuration; the only input package for phase two |

**Resident knowledge uses one complete unit per paragraph or list item, with bracketed labels only when restrictions are needed.**

Every independent paragraph or list item in resident-facing content is a complete knowledge unit, labeled or unlabeled. Headings, authoring instructions and provenance appendices are not knowledge. Write facts directly. When different eligibility conditions cannot describe the complete unit, the author splits it; the compiler does not split sentences into fragments.

Use the existing place, route, vocation, experience and mastery-difficulty labels. No label means no additional restriction. Multiple conditions are conjunctive; alternatives must be explicit. Distinguish exterior from interior and partial from complete routes. Human-readable labels become machine fields in step three.

Deliver sources, attachments and a provenance/coverage description. Bind creator material by source section and resident knowledge by content unit. Explain unknown or excluded content. This description owns stable anchors and their ID correspondence under 6.4.5. Do not generate YAML yet.

### 2.3 Step three: compile, compare, validate and publish

1. **Compile:** map each resident unit to knowledge YAML; compile spatial, species, appearance and individual rules with provenance and stable IDs.
2. **Compare:** check foundational material → human-readable source → configuration coverage, with no missing or duplicate units, altered facts or expanded knowledge scope.
3. **Validate:** check fields, units, references, unknown and access boundaries. Prove a legal life and Earth-departure path for each adoptable species/life stage. Empty schema fields without geographic/rule data are insufficient.
4. **Publish:** freeze versions, member inventory and digests into an immutable logical package. Changes require a new package version.

The entry is `config/genesis/program.yaml`; its manifest references every other YAML member and asset. Shared policy values, budgets and versions belong to entry rules; geography, knowledge, species and appearance data belong to their members. Genesis implements the algorithm defined here. Configuration contains neither executable code nor prompts nor an individual's generated family/life.

There is no implicit source-Markdown scan. Source paths support provenance; runtime consumes compiled package data only. Section 6.4 specifies packaging and publication.

## 3. Phase two: generate an individual

### 3.1 Step one: user choices and candidates

Each batch targets five distinguishable candidates with feasible subsequent lives, based on the published package and user preferences. The user then invites one to three; invitation count is not candidate count.

**Resolve choices before generating the actual individual.** Validate species, life stage, sex, appearance direction/priorities and registered extensions. Resolve “any” into actual values here. Unregistered free text cannot become a rule. Explain an infeasible combination rather than changing a hard choice.

Determine actual species, age/stage, sex, supported appearance, personality anchors and native name in that order. Appearance uses the same actual age. Candidates differ in supported appearance parameters and personality directions, not merely random seeds. If bounded generation yields fewer than five, show that number or report no solution.

Age is an integer local year satisfying `2 ≤ a ≤ T−4`, where T is the species' life endpoint. With no stage preference, use youth-weighted stage probabilities normalized over stages with valid ages. With an explicit stage, sample only its legal intersection; an empty intersection is unavailable, not a reason to substitute another stage. The four-year reserve limits adoption age, not relatives' lifespans. Stage weights come from `elfaria-generation-rules` §11.1.

The five interaction questions only derive controlled candidate-personality anchors. They do not directly determine birthplace, family resources or social class. After acceptance, downstream stages receive frozen anchors, not raw answers. Personality cannot bypass age, training or vocational qualifications.

**Prove feasibility before display without generating a biography.** Each candidate needs at least one legal birth, care and departure path. A selected education or vocation requires its own feasibility proof; young candidates need not already have graduated. Display only established identity, appearance and personality directions, not ungenerated families or jobs. Section 6.5.1 covers appearance and naming checks.

### 3.2 Step two: accept and freeze anchors

The user invites candidates, confirms replies and names the accepted individual. These interactions remain inside this step.

Existing Adoption deterministic matching decides “willing” or “still considering”; the model phrases the reply only. A retry reuses the same reply, and a published reply cannot be redrawn. Section 6.5.1 specifies matching and absent valid replies. Acceptance does not establish years of trust.

Acceptance atomically checks candidate expiry, digest, package availability and adoption eligibility, then creates one reservation freezing:

- Candidate identity, age, appearance, personality anchors and final display name.
- Elfie/reservation IDs, adoption relationship reference, idempotency key and time anchors, including the birth period required by rules.
- Package, policy, compiler and initialization-mapping versions, seed and private creation workspace.

Technical inputs belong only to `GenesisCompileEnvelope`. Repeated clicks, recovery and retries continue this reservation; they do not change the candidate or redraw identity. Raw questionnaires and invitations enter neither LifeContext nor narrative-model input nor durable personal memory.

### 3.3 Step three: establish a life structure and feasible activities

Build a feasible structure from the four frozen inputs, then realize events chronologically.

| Input | Downstream use |
| --- | --- |
| Species | Birth eligibility, life cycle, appearance and cultural attraction; no fixed vocation |
| Sex | Identity and terms for self, relatives and partner; no predetermined vocation, relocation or exploration tendency |
| Actual age | Family generations, life status, learning years, accumulated contact and travel opportunities |
| Big Five | Selfhood mapping and social/exploration/risk tendencies; not skills or permissions |

**Birth/home → unique family graph and care → living/learning context and contact opportunities → purposeful visit opportunities, routes and stays → Earth-departure arrangements.**

Establish family time anchors first. Vocations, contacts and friendships dependent on actual study/travel remain unrealized. Step four may extend a newly important friend's family within limits and revalidate the structure without changing frozen inputs or established facts.

**Birthplace affects opportunities.** Uniformly choose an allowed region for the selected species, then uniformly choose a habitable grid cell within it. The allowed-region list is a hard constraint. Do not weight town centers, villages or cell populations. Bind the public region/settlement and a legal private home. These are Elfaria locations, not the user's real location.

Birthplace supplies local family, facility, education and labor opportunities. These and age constrain subsequent choices; birthplace does not directly set personality/vocation or grant an entire region's knowledge. Section 6.5.2 covers sampling, private places and routes.

**Life must fit time and space.**

- Create a deduplicated family graph and life dates first. Learning and work require reachable places, real teachers and sufficient years. Ineligible individuals remain learners or without a vocation.
- Relocation needs a reason and continuous chronology. Do not place simultaneous study and work far apart. Capability follows species boundaries and actual training, not model assignment.
- Reachability is not visitation. Distinguish hearsay, exterior observation, entry and use, and partial/complete routes. Contact facts require supporting activities or trips.
- Departure requires age at least two, valid care, personal consent and one simple three-local-day preparation. Do not invent a course/module system. Real admission, room, current location and later actions are not pre-generated.

Age uses a simplified one-to-one convention: five years lived in Elfaria means age five, without converting local day length. After Earth arrival, each Earth year adds one year of age. Local calendars order life/travel events but do not redefine age. Preserve unknown birthdays; any displayed derived date is an “age projection.”

`LifeContext` contains established identity/family anchors, residence and care, plus constrained study/vocation, activity/travel and departure plans and event slots. Distinguish unrealized plans from validated facts. Slots constrain time, places, people, prerequisites and outcomes; they are not proof of visiting or graduation. See 6.5.

### 3.4 Step four: personal knowledge, relationships, experiences and self

Follow chronological **knowledge/prerequisite checks → event/contact realization → knowledge/relationship/friendship updates → merged factual timeline → personal-history selection → detailed stories and self projections → final knowledge review**.

Produce actual stories and knowledge, not just people and timeline points. Step-three plans do not automatically become episodes.

**Acquire complete eligible knowledge units.** Unconditional, difficulty-free knowledge is guaranteed. Check actual life evidence before eligibility and then apply fixed mastery probability if needed. A unit is either acquired in full or not acquired; do not generate shortened variants. Each unit uses one stable random value, not repeated draws across retries/events. Preserve hearsay, legends and unknown boundaries. Difficulty is not factual confidence.

Track acquisition time. Events use only previously known information; new knowledge becomes usable after learning/events. An event's outcome cannot satisfy its own prerequisite. Present knowledge does not imply childhood proficiency. Mandatory training and required knowledge cannot be probabilistically omitted.

Failure to acquire capability needed by a later vocation invalidates that dependency and triggers bounded step-three recomputation. Additional prose cannot rescue an impossible vocation.

**People and episodes arise from actual life.** People come from family, neighborhood, learning, work and departure contact slots; ages, places, capabilities and relationship directions must agree. Familiarity is not trust; knowing about a person does not imply personal acquaintance. Unknown family details remain unknown. Stories use validated time, people, places and causes, without new access, expertise or relationships.

Training, departure, arrival and adoption form full Episodes in their actual order, each with time/place/people, process, outcome and impact. Normally provide at least five episodes, fewer for young lives where appropriate, without a fixed maximum. Non-narrative residence/learning facts must also survive and cannot replace required Episodes.

**Handle self and introduction separately.** Selfhood receives complete identity core and bounded personality/value/expression tendencies through its owner's reviewed deterministic mapping. Stories, questionnaires and current emotions do not belong there; accepted personality anchors cannot be rewritten. Experiences and changing life understanding belong to Memory.

The introduction answers who I am, where I come from, who I lived with, one real past experience and why I arrived. Omit inapplicable parts for young individuals. Generate a canonical summary first; optional model wording must be validated. Adopted episode wording is stored with its Episode, while the welcome introduction temporarily projects committed facts without a second biography store.

`PersonalGenesisPlan` collects knowledge, people/relationships, events, Selfhood and submission evidence. See 6.5 for fields, knowledge chronology and Memory handoff.

### 3.5 Step five: joint validation, submission and admission

**Validate the whole life before making it visible.** Jointly check frozen identity, spatial/temporal feasibility, people/relationships, knowledge eligibility/acquisition time, event causality and final ownership. Then construct one `GenesisBundle` for Profile, Selfhood, Memory and registered other owners. Memory's official entrance receives three Seed responsibilities: knowledge, relationships and episodes. Places and personal propositions must fit those responsibilities, not introduce another database-writing entrance.

Generation completion is not admission completion. Admission coordinates three durable results: final individual files, Adoption relationship/quota, and Nest admission/bed allocation. Only when all three are confirmed and owner data can be reopened may it mark `committed`, welcome the Elfie and enable interaction. Account quota and Nest beds are distinct.

Published final files without Nest admission remain “admission in progress.” Only an already committed admission followed by a runtime connection failure can display “admitted, connecting,” with recovery from final owners.

One reservation drives a recoverable background task after acceptance. The frontend shows its stage and resumes the same creation after reopening. Failures distinguish retryable from terminal; retry cannot mean generating another individual. After success or definite termination, remove questionnaire, envelope, life plans, Seeds and source-package bindings. Preserve final facts/evidence and the minimal technical receipt only. Section 6.7 covers publication, cancellation and crash windows.

## 4. Shared boundaries

### 4.1 Versions and determinism

A reservation fixes inputs, identity/time anchors, package, policy, compiler, owner-mapping versions and seed. It yields the same structured facts or failure. Wording cannot decide facts; recovery reuses staged wording. Bounded backtracking changes only unfrozen choices, not identity or hard user constraints. See 6.6.

New packages affect future candidates only; retain old versions until their reservations end. Stop on digest mismatch or unavailable required versions, rather than substituting packages. Section 6.7 serializes revocation and final activation: earlier revocation prevents activation and triggers compensation; earlier activation preserves the committed Elfie without refresh, regeneration or deletion.

### 4.2 Models express facts rather than decide them

Each model call receives one approved narrative view, allowed facts and references. Do not send the whole plan, seed, hidden coordinates/weights, unselected knowledge, raw invitations or other Elfies' data. User strings and source prose are data, not instructions.

Check output entities, numbers, times, references and prohibited facts individually. Discard unsupported details and use the canonical summary on failure. Models do not decide identity, life, knowledge, relationships, parameters or permissions. Keyword checks are not a substitute for factual validation.

### 4.3 Final owners are authoritative after commitment

App profile display may read Profile. Ordinary Brain reads Selfhood, Memory and current state, **not Profile, Canon or creation inputs**. Use the formal Memory → RecallBundle → Reasoning path, preserving source, time and unknown boundaries.

Recovery must work after removal of the creation workspace and old source package. Durable Memory Evidence survives temporary-input cleanup. Ordinary restart validates the current legitimate snapshot, not the birth manifest against memories that have since changed. The existing asset resolver resolves final appearance; missing assets are an error, not permission to redraw appearance.

Without real perception, tool results or action receipts, the Elfie does not know its current position, weather, today's activities or other Elfies' state. Generated stories cannot supply those live facts.

## 5. Acceptance and implementation readiness

### 5.1 Evidence required at each step

| Scope | Acceptance focus and counterexamples |
| --- | --- |
| Source authoring/organization | Bind foundational source sections to the four source responsibilities and check resident units; include unlabeled lists but exclude instructions |
| Compilation/publication | Unit correspondence, stable IDs and closed references/versions/assets; reject omissions, rewrites and invented unknown content |
| Candidates | Respect hard choices and prove a legal life; do not display unsupported appearances, uncared-for young candidates or impossible departure combinations |
| Acceptance | Stable replies and anchors; concurrent clicks, package changes and duplicate invitations cannot change candidates or consume extra quota |
| Life structure | Birth distribution and spatial/temporal constraints; no defaults concealing zero weights, disconnected routes, insufficient time, absent facilities or incompatible kinship ages |
| Personal content | No unauthorized, repeatedly sampled or temporally reversed knowledge; teacher contact is not mastery of every skill and events cannot prove their own prerequisites |
| People/narrative | Protagonist belongs to the parents' shared children set; no duplicate parents or ancestry cycles; consistent ages, deaths, birth order, bounded expansion and knowledge; stories introduce no facts |
| Final handoff | Selfhood stored state and official output agree; APSO episode/knowledge and relationship initialization actually finish; public spatial relations and required knowledge are complete without index/Evidence leaks |
| Admission/recovery | All three durable results precede visibility; lists, authorization, Nest recovery and Recall honor activation; revocation, cancellation and crash windows do not regenerate, wrongly delete or double-consume |
| Runtime/source removal | Formal Recall retrieves knowledge, people, places and episodes; source removal/new publication does not rewrite existing Elfies |

Validate these counterexamples in package validation, Genesis, final owners, Admission or formal Recall as appropriate, rather than delegating them all to prompts.

### 5.2 Required material and implementation

| Requirement | Behavior when missing |
| --- | --- |
| Source-section and knowledge-unit correspondence; exact place/route contact, vocation and simple departure conditions | Block the affected package version; broad labels cannot grant eligibility |
| Reviewed maps, birth cells, road times and home/facility connections | Do not publish affected birth/life paths |
| Family, single-teacher apprenticeship duration, vocational thresholds, names, relationships, events and probability/budget data | Do not invent courses, people or universal vocations |
| Appearance assets, Selfhood mapping, Memory inputs and local evidence contracts | Block incomplete individual submission |
| One loading path, in-place Genesis/Admission evolution, required governance and focused acceptance | Do not claim implementation; see 6.3 |
| Stage duration, P95/failure rate, timeout/retry intervals and waiting/cancellation experience | Do not promise unmeasured latency |

The published Program v5 compiles the currently bound subset of section-6.5 policy: candidate age/budget, family child-count and lifespan parameters, relationship importance, and visit rates, attraction, personality and Poisson sampling. Other source values do not become active merely because their digest is present. Remaining unbound policy and end-to-end evidence stay in ELF-019; updating source digests does not activate them.

### 5.3 Completion evidence

- **Coverage:** every published species × allowed life stage × at least three fixed seeds; also age endpoints, explicit/any choices, probability zero/one, zero weights and conditional counterexamples. All structural constraints pass; unauthorized knowledge and duplicate submissions are zero.
- **Distribution and experience:** prereview sample sizes/tolerances for birthplace distributions, candidate diversity and knowledge proportions. Do not adjust thresholds after measurement. Separately test performance, cold start, cancellation, concurrency and every publication crash window.
- **Memory closure:** follow the three Seed classes to durable records/Evidence and formal Recall, including paraphrases, rare knowledge, people/place references and chronology, not just exact-text search. Source-removal tests preserve runtime assets; missing assets receive their own diagnostic test.
- **Evidence and privacy:** publication preserves inventories, digests and bidirectional coverage. Isolated tests retain synthetic inputs, versions, seeds, stage digests and recovery/Recall results. Real creation retains only final facts and minimal receipts after termination; no questionnaire, plan or seed in logs, backups or error attachments.
- **Closure:** record target, inventory, references, verification and residuals in Conformance. Accepted design, publishable material and verified implementation/runtime are three distinct states.

### 5.4 Elfie Lab review surfaces

Lab displays three final-owner results from the same initialization, with source-to-result comparison during creation review:

| Panel | Review content |
| --- | --- |
| Profile | Actual age, sex and origin on the identity card; 3D appearance rather than duplicate long appearance prose |
| Selfhood | Keep “Edit” at the Big Five panel's upper right and add “Selfhood”; the dialog defaults to complete stored state including Big Five, with an output action showing officially assembled text |
| Memory | Episode/story list, people and place graphs, full knowledge text; unit eligibility, probability, selection/rejection reason and actual materialization |
| Generation process | Family expansion/life status, failed-trip reasons, counts/stays, timeline selection and coverage gaps linked to rules |

Lab uses official creation and owner projections, not another generator. Inspect both inputs/plans and actual written memories; planned counts do not prove a populated graph. These are target surfaces, not a claim that every UI function exists. Full process tracing is limited to isolated experimental data. Real terminal creation cleanup still follows 4.3/6.7; debugging does not justify permanent envelopes.

## 6. Detailed design

### 6.1 Creation artifacts and lifetime

| Artifact | Purpose and lifetime |
| --- | --- |
| `CreatorWorldSkeleton` / human-readable sources / `GenesisSourcePackage` | Preparation facts and published result; reusable for creation, not ordinary Brain input |
| `AcceptedGenesisReservation` / `GenesisCompileEnvelope` | Frozen reservation and technical inputs, only while creation remains incomplete |
| `LifeContext` / `PersonalGenesisPlan` | Life conditions and personal-content plan, removed after projection to final owners |
| `GenesisBundle` / `InitializationManifest` | One-time payload and output completeness manifest, removed after commitment or termination |
| `GenesisCommitReceipt` | Minimal idempotency/completion receipt, neither recallable nor sufficient to reconstruct a life |
| Final-owner data / Memory Evidence | Committed facts, retained and evolved under owner contracts |

Adoption owns relationships and member quotas; Genesis owns life semantics; Admission coordinates publication/recovery across owners. Infrastructure loads/saves typed values and does not become a second creator. Separate product consent records remain with their existing owner and do not justify retaining questionnaires or plans.

### 6.2 Source and contract dependencies

Section 2.2 assigns world facts and parameters. These formal boundaries take precedence over this design:

| Dependency | Constraint |
| --- | --- |
| [Genesis ADR](../../decisions/0033-one-time-genesis-and-final-owner-isolation.md), [Elfie contract](../../contracts/elfie.md) | One-time materialization, final-owner isolation and input cleanup |
| [System contract](../../contracts/system.md), [Configuration contract](../../contracts/configuration-management.md) | Ownership, loading boundaries and the single configuration source |
| [Species asset contract](../../contracts/species-asset-package.md) | Species eligibility, supported appearance and runtime assets |
| [Selfhood design](./brain/elfie-selfhood-and-fixed-model-header.md) | Identity core, personality state and fixed text projection |
| [Memory architecture](./brain/elfie-memory-architecture.md) | Official inputs, APSO, Evidence, extraction and Recall |
| [Application contract](../../contracts/application.md) | Adoption, admission coordination and Nest acceptance |

### 6.3 Implementation boundary

The current creation-package entry is `config/genesis/program.yaml`, with basic rules, resident knowledge, geography and species members. This document is not a second runtime-status ledger. [ELF-019](../../conformance/elfie.md) owns current gaps and evidence.

The family graph, age ceiling, social probabilities, visit opportunities, history selection and coverage checks completed here are targets. Source §11 is not registered machine coverage and requires compilation and implementation before activation can be claimed. Reorganization or source-digest synchronization changes neither package rules nor acceptance status.

Evolve the existing Adoption → Admission → Genesis → final owners → Runtime path. Permanent Schema, official entrance or ownership changes require their applicable governance; this design cannot independently authorize a contract change. Algorithms and defaults now constitute an implementable baseline. Distribution calibration belongs to acceptance; changing defaults requires a policy-version change and cannot alter confirmed constraints such as the four-year age reserve or child-count distribution. Section 6.5 and parameter source `generation#11` specify role, purpose, culture and public-geography mappings.

The published source now treats Earthbound Transit Station as an independently hosted facility inside Mistyville territory. Its route to the town center is explicit, but the station is not a child of the town center; ordinary departure therefore does not grant town-center contact. The resident source, geography member, Program bindings and Genesis checks must remain synchronized when this fact changes.

### 6.4 Phase-one compilation specification

#### 6.4.1 Package structure

`program.yaml` is the only entry. Explicit manifest references resolve members; directories are not implicitly scanned.

~~~text
config/genesis/
├── program.yaml             # inventory, shared rules, policies, source coverage
├── knowledge/
│   ├── elfaria.yaml         # resident units
│   └── geography.yaml       # single machine source for grid, places and roads
└── species/
    ├── catalog.yaml        # identity, status, member references
    └── <saevi|tovren|myelle>/
        ├── species.yaml    # shared body and perception boundaries
        ├── generation.yaml # life cycle, generation eligibility and priors
        ├── appearance.yaml # parameters, combination constraints, asset bindings
        └── assets/*.png    # presentation assets, at least portrait and full body
~~~

| Member | Required information |
| --- | --- |
| `program.yaml` | `document_kind / schema_version / program_id / program_version / status / sources / manifest / coverage / rules` |
| `knowledge/elfaria.yaml` | Document/knowledge version, status, source digest and `knowledge[]` |
| `knowledge/geography.yaml` | 10×10 partition, regional rules, places, road network, sampling/travel rules and provenance |
| `species/catalog.yaml` | Document/catalog versions, technical IDs, formal names, status and three member references |
| `species.yaml` | Version, identity, body/perception boundaries and semantic asset references |
| `generation.yaml` | Version, life stages, species birth eligibility and required priors |
| `appearance.yaml` / assets | Version, controls, combination constraints, distinguishable presentation assets and 3D semantic bindings |

Maps/roads belong to shared geography; general life policies belong to entry rules. Species members add species constraints without copying maps or personal facts. Do not move Godot geometry/navigation/rendering, Selfhood templates, Memory Retention, tool permissions, current Nest state or runtime defaults into this package.

The catalog uses formal names `saevi / tovren / myelle` and explicitly maps technical IDs `fox / dog / cat`, preserving Godot bindings.

#### 6.4.2 Knowledge fields and label conversion

~~~yaml
document_kind: resident_knowledge
schema_version: 2
knowledge_id: elfaria
knowledge_version: <version>
status: draft
source:
  path: <resident-knowledge-source>
  sha256: <source-digest>
knowledge:
  - id: <stable-id>
    topic: <reviewed-small-topic>
    description: <complete resident-facing fact>
    eligibility: <optional declarative rule>
    mastery_difficulty: <optional difficulty>
~~~

Each resident-content unit maps to one record, including unlabeled lists/paragraphs. `topic` is an explicit reviewed organization field; it never changes the source fact. `description` preserves the complete original text. Normalize line breaks, list markers and label prefixes only, without changing wording, facts or epistemic boundaries. Do not add titles or topic prose to `description`, empty properties, generated defaults or partial content.

| Human-readable label | Machine representation |
| --- | --- |
| Place or route, such as town center or town–Saevi tribal center | `place / route`: registered ID, required contact strength and road-section scope |
| Vocation or experience, such as healer or Earth departure | `vocation / experience`: actual trade/proficiency or activity-completion state; training is also experience |
| Multiple conditions / explicit alternatives | `all / any`; do not infer alternatives or merge distinct content |
| Moderate mastery difficulty | `mastery_difficulty`; versioned probability policy, not eligibility or Confidence |
| No label | Omit restriction fields |

`eligibility` supports declarative Boolean trees with only these four leaf categories. Names must uniquely resolve to registered IDs. Exterior, entry, use and partial/complete routes are distinct. Empty trees, unknown operators, dangling IDs, ambiguity, cyclic dependencies and unsupported difficulties block publication and return to source correction. Resident authors do not maintain machine condition programs.

#### 6.4.3 Required rules and data

Values and applicable conditions come from `elfaria-generation-rules`. Register existing rules separately from newly accepted parameters; only values bound by the published Program and consumed by a typed Genesis input are active, while uncompiled material is not published coverage. Every rule needs a stable ID, provenance/version, availability, units and verifiable references.

| Collection | Required content |
| --- | --- |
| World/map | Region–settlement–place hierarchy, terrain, habitation, known/unknown scope and map registration |
| Birthplace | Matrix, allowed species regions, uniform region/cell selection, place ownership and legal road attachment |
| Roads/travel | Land chains, ferries, local-path conditions, endpoints, modes, walking/water days, permissions and seasonal constraints |
| Family/care | Expansion bounds, child-count distribution, birth windows, life state, relocation and care constraints |
| Learning/vocation | One real teacher, one craft, duration, teacher confirmation, age/capability thresholds and workplace |
| Naming/people/relationships | Cultural name tables, ages/residences/capabilities, direction, parameter ranges and change evidence |
| Events/knowledge | Themes, prerequisites, duration/place/people/capability, outcome bounds and permitted knowledge/relationship changes |
| Earth departure | Age greater than one, personal consent, one three-local-day preparation, departure/arrival facts and Earth knowledge boundaries |
| Policy | Candidate age/count, random-domain versions, social/importance coefficients, visit/group probabilities, history/story weights, backtracking budgets and acceptance tolerances |

Birth regions strictly follow species allowlists; centers get no sampling bonus. Facilities confirmed only in town cannot be copied into every tribal center. Missing data rejects an invalid life path rather than inventing places, teachers or contacts.

#### 6.4.4 Geographic source, derivation and travel

`knowledge/geography.yaml` alone owns the regional matrix, places, roads and travel rules. `program.yaml` binds the member and policy references without copying the map. The reviewed `elfaria-geography-source` owns the grid matrix, 16 road chains, ferry inventory and concrete values.

The member contains metadata, partition matrix, regional rules, places, spatial relations, named route aliases, roads, sampling/travel rules and validation summary. `parent_id` is the public container hierarchy; explicit spatial relations such as “at center of” or “public entrance to” are separate edges. Regional rules derive terrain, habitation, birth eligibility and species lists. Places/route aliases/roads derive references, main-road nodes and ferries. `program.yaml` keeps only the references (`place_registry_ref` and `route_aliases_ref`) plus generation policy; it does not repeat place or route rows. Do not duplicate 100 population records. Distinct places in a cell remain distinct; area objects such as towns/lakes use regions or cell sets.

The graph combines ordered land chains, allowed local paths and waterways. Adjacency alone creates no road. Do not add edges using pixels, kilometers or straight-line distance. Each consecutive backbone pair is one hop; insert no undeclared cells. Water travel uses declared water-hop counts and ferry conditions.

Pathfinding resolves host cells/places, constructs the legal network, checks mode/permissions, and finds the shortest legal travel time. Stable edge IDs break ties. Return cells, edge IDs and walking/water days; otherwise return `unreachable` and a reason. Underground and Cloudcrown City entry cannot be derived from surface routes. Do not invent distances between places in the same cell.

Publication checks matrix completeness/uniqueness, species eligibility, place/node references, derived chain/ferry edge counts, reachability from every eligible birth cell, travel units and exceptional permissions. Expected values come from the reviewed geography version and receive manual map-overlay comparison; pictures cannot generate the graph in reverse.

Register map version, parent/coverage, coordinate units, boundaries/anchors, layers/assets and review status. Mark schematic maps non-measurable. Child maps cannot inherit the whole parent's bounds. Unknown regions stay unknown and cannot supply missing roads. Age follows 3.3; local travel/calendar units do not recalculate age or turn adoption day into a local birthday.


Distinguish public geographic containers, cultural areas and sampling subdivisions. Direct town districts follow the reviewed inventory. The town center and departure facility may share a residential district without containing one another. Technical region codes are not extra public districts; external regions are outside the town. Attach private hometowns/homes to their actual district or village. Each place has a stable ID, name, area/site kind, parent, description, extent or anchor, access conditions and provenance. Regions may add terrain, habitation eligibility and resident species; population and sampling reference existing rules. Unknown counts, areas and outlines remain unknown. Containment neither proves a visit nor grants knowledge of restricted interiors.

#### 6.4.5 Provenance, stable IDs and publication

`coverage` reuses the step-two description: creator source-section ID → rule/member reference, and resident knowledge-unit ID → source anchor → YAML unit → retained/unknown/excluded outcome. Creator bindings are section-level, not a claim of atomic-fact coverage. Do not create another ledger.

An adjacent invisible `<!-- unit:<stable-anchor> -->` comment anchors each resident unit without becoming prose, a label or knowledge. The compiler consumes only the reviewed anchor-to-ID table. Missing/duplicate/unlocatable anchors stop compilation; line numbers, paragraph positions and full-text hashes cannot recreate IDs. Reformatting/reordering preserves IDs. Semantic changes increment versions. Splits/merges/deletions record old-to-new correspondence in the same coverage description for future creations.

Publication proves both creator-section → rule/member and every resident unit → YAML. Classify full retention, equivalent organization, omission, distortion and justified exclusion. Source-to-YAML compilation does not rewrite wording. Missing, duplicate, orphaned, unbound or source-digest-mismatched entries block source publication. Production activation additionally requires typed consumers and semantic/feasibility acceptance.

The manifest explicitly lists relative paths, types, member versions, byte digests, provenance/coverage references and publication status. Binary assets bind to their member version. Versions may differ but Schemas must be compatible. Reject missing/duplicate members, undeclared required assets, absolute paths, `..` escapes, symlink escapes and runtime network downloads of missing members.

The total digest covers canonical entry content and sorted member digests, excluding itself; the entry is not its own recursive member. Source digests serve review provenance, while runtime package content must be self-contained. Acceptance freezes the whole package and every member digest, not merely knowledge.

Catalog maps technical species IDs to formal names. Source publication does not change adoptability. `draft` is not adoptable; `published` needs complete material, validation and presentation assets; `retired` disallows new adoptions while assets for existing Profiles remain resolvable.

### 6.5 Individual-generation algorithms and final handoff

This section expands the final three steps. Section 3.1 determines candidate age; 3.2 freezes the four inputs. Step three establishes family/life structure, step four chronologically realizes events, knowledge and stories, and step five checks actual materialized results. Formulas here define algorithms; probabilities, multipliers, counts and thresholds come from `elfaria-generation-rules` §11. Program v5 activates only the subset listed in 6.3; values without a Program binding and typed consumer remain target policy and are tracked in ELF-019.

#### 6.5.1 Candidates, names and invitations

Appearance uses the published support set and the same actual age, following [appearance generation](./embodiment/virtual-appearance-generation.md) and the species asset contract. Native-name sampling is stable; the user confirms the display name. Validate length, Unicode, control characters and reserved words. Names are data, not identity keys.

Preserve existing Adoption matching: invite one to three, use stable scores and the 0.8 threshold for willingness. If none qualify, use the stable fallback score before publication to choose one, bound to a policy version. The model phrases replies without emotional promises. Repeat invitations reuse their result; published “still considering” replies cannot change. Only valid accepted candidates reserve. Expiry, package revocation or absent valid willing candidates returns to selection rather than fabricating a fallback reply. Matching does not enter personal memory.

#### 6.5.2 Birth, life context and person attributes

Uniformly choose an allowed species region, then a legal cell within it. A combined draw must preserve “equal regions × equal cells within region,” not uniform cells across the whole map. Region, public parent place and private home must agree. Instantiate only allowed home prototypes; add no public village or road. An impossible care/life/departure combination triggers bounded backtracking, not snapping to the nearest place.

Each person has stable ID, name/address term, species, sex, birth time, life status and applicable death time, residence, kinship, acquaintance time and contact evidence. Important people receive stable traits and habits/goals; ordinary people receive brief descriptions. Generated exact facts and protagonist knowledge are distinct. An unfamiliar person may be known only by an age band or address term; unknown fields stay empty.

Life context provides residence, care, learning, labor and contact opportunities. Vocations require real teachers, sufficient learning time and capability evidence. Do not impose gender divisions or species-specific jobs. Section 3.3 assigns the four inputs; the source declares parameter units.

#### 6.5.3 Family graph, children and life status

**Use one family graph, rendered as a tree when useful.** Each parental pair shares one children set; siblings derive from it. Do not redraw children through father, mother or sibling entrances. The core comprises self, parents, siblings, partner and children. Expansion is bounded rather than recursively adding a core around every new person.

| Person relative to the protagonist | Expansion and stopping point |
| --- | --- |
| Self | Both parental identities are required; siblings derive from the shared set; partner/children depend on age and sampling; alive, known and co-resident are separate |
| Parents | Reuse children; optionally add grandparents, normally stopping upward when the parent is already elderly, except actual care/contact requirements |
| Instantiated grandparents | Complete that pair's children including the existing parent, yielding aunts/uncles; no great-grandparents |
| Own partner | Reuse shared children; instantiate parents/siblings only when actual contact requires them |
| Own siblings | Add eligible partner and children, stopping at nieces/nephews; no sibling-in-law family |
| Own children | Add eligible partner and children, stopping at grandchildren; no child's partner family |
| Aunts/uncles | Extend only a bounded set of actually contacted families to partner/children; cousins do not expand; others remain known summaries |
| Important friends | Add eligible partner/children only; parents/siblings default to known summaries without expansion |

Do not instantiate entire ancestral families merely to create cousins. A genuinely important shared-childhood cousin may use the shortest kinship connection within grandparent/grandchild bounds. A friend's mother who actually cared for the protagonist can enter as a caregiver without full-family expansion. Summary and concrete people reuse the same family facts; birth order, total children and identities are not resampled. Unknown does not mean absent or deceased. A generated family universe does not imply knowing everyone: distinguish acquaintance, hearsay and unknown.

**Draw one target child count per union, then assign birth years.** Draw Kdraw from the source's 1/2/3-child distribution. Let N be legal birth years through the present and m already registered children:

`K=max(m,min(Kdraw,N))`; add only `K−m` children.

A legal year requires at least one year of partnership, both parent–child age gaps, both parents alive and before old age, and at most one child per family/year. N includes years occupied by existing children and cannot exceed completed partnership years; concrete dates must also agree. If m>N, an existing year is illegal, or the three-child template is exceeded, backtrack unfrozen parental dates without changing protagonist age or deleting anchored children. Deceased children count; do not replace them to reach a living-child quota.

1. Freeze protagonist birth and insert the protagonist into the parents' shared set first.
2. Infer parental birth/union dates making that birth legal and require survival to anchored events.
3. Draw the target total and constrain it by actual lifespans; sample unused legal years without replacement, uniformly over legal year combinations.
4. Birth time determines order; sex determines sibling address terms. No two children in one year.
5. Mark that family set complete. Grandparent families likewise insert the existing parent before adding siblings.

Without anchored children, N=0 yields none; N=1 yields one; N=2 yields one/two with 40%/60%; N≥3 uses the target distribution. Thus this simplified template guarantees a child when a union has at least one legal birth year; this is a template choice, not a population claim. Validate acyclic ancestry and unique biological parents. Care uses separate relationships; direct ancestors/descendants and siblings cannot pair.

**Partners, life status and relocation.** Reuse existing partners. For an unpaired eligible person, apply the conditional probability per complete year until the first pairing. At most one partner at a time; the first template does not expand remarriage genealogies. Relocation needs legal residence, dates and routes, without sex-based assignment of who leaves.

First establish survival age L required by anchored births/care. Draw death age D once, conditioned on lifespan distribution F:

`F(D)=F(L)+u×(1−F(L))`, with u∈(0,1). L at or beyond the species endpoint is infeasible.

The protagonist is currently alive. Relatives' alive/deceased status derives from D and is not redrawn for stories. Memory includes death time/age only for deaths already occurred and known to the protagonist; a living person's future D is a transient generation constraint. Reverse parental construction incorporates anchored child births into L, then uses death dates to bound optional childbirth, partnership and travel.

Every childhood period needs an actual caregiver. Existing family fills gaps first; otherwise backtrack within budget. Distinguish distant residence, lost contact and death. Do not invent unknown causes of death. Names and personality details cannot change chronology.

#### 6.5.4 Contacts, friends and importance

Contacts arise through shared living, learning, work and activities. One person may hold multiple roles. Childhood peers/neighbors require actual shared life; teachers/peers require actual learning; travel companions require trips. Do not fill counts without valid age/time conditions. Extending a friend's family adds necessary relationships/contact only, not another full life-generation run.

Use cumulative contact for friendship:

`H=Σ[β×actual contact years×frequency multiplier×interest/purpose match multiplier×extraversion multiplier]`

`Pfriend=1−exp(−H)`

Frequency, match and Big Five values lie in 0–1. E/O/N are extraversion, openness and neuroticism. Accumulate exposure across periods; lower recent frequency does not erase historical opportunity. Fix u at first acquaintance; friendship starts when cumulative probability first exceeds u. Do not redraw cumulative probability yearly or backdate friendship. Select at most two important people among established friends by then-current importance, breaking ties by stable ID. No qualified friend means no forced addition.

Initial importance is `I0=R×exp[−λ(d−1)]`. d is a business relationship layer: core kin and direct acquaintances are layer one, people introduced through them layer two. Direct acquaintances have lower R; multiple paths use the maximum valid initial value.

The role mapping is fixed: parents/partner/children use the core baseline; siblings use the sibling baseline; childhood peers and teachers use their respective baselines. Other actually known classmates, colleagues, travel/exchange partners and non-kin caregivers use the ordinary direct-acquaintance baseline. Grandparents decay outward from parents, nieces/nephews from siblings, grandchildren from children, and side-branch partners/children from that branch's entrance. Friends' relatives decay from the friend baseline. Hearsay-only people do not participate in shared activities; unknown people form no initial relationship memories. Multiple roles use the maximum valid value.

Friendship promotion raises the baseline once. Shared events update `I_next=1−(1−I_prev)×exp(−w)`. Aggregate daily contact by year/period; count each fact once. Splitting prose adds no importance, and emotional polarity is separate.

Optional participation depends on feasibility, purpose match and importance before the event. Establish an opportunity, choose participants, record shared events, then update importance. Other people's marriages, births and deaths follow their life histories rather than protagonist importance. Added friend families are checked for factual compatibility without backfilling earlier friendship.

Use an age/extraversion-dependent soft acquaintance budget, limiting optional branches first. Do not fill the quota or remove essential core family. Explicitly retain unavoidable core overflow. Count generated people, actual acquaintances and hearsay-only people separately.

#### 6.5.5 Public geography and personal place knowledge

Separate containment, adjacency, actual routes and observational relationships. Derive a public resident view with public names, hierarchy and spatial relations, excluding hidden places, private coordinates, internal passages and restricted detail. Everyone acquires the eligible public baseline, at least knowing places exist. Local appearance, detailed routes and traditions remain subject to each knowledge condition.

Connect personal homes, birthplace and the actually reached Nest to the public network. Earth/new-home knowledge follows training/arrival chronology. Track hearsay, passing, seeing, entering and using evidence separately, plus count, duration, latest contact and episode references. Familiarity may rise with exposure but does not change contact category; repeated hearsay never becomes entry.

Geography, resident catalog and personal Memory share place identity. Genesis emits every published public place node and every reviewed place relation into the initial Memory graph, including containment (`located_in`) and registered spatial predicates. Each PlaceSeed carries a local familiarity importance: the public baseline remains present at low salience, while residence, mandatory departure and actual contact raise the individual value. A realized Episode also writes an evidenced `visits` edge to each actual place; the Episode remains the source of wording, time and route context. Route aliases used by a trip are retained in Episode metadata, while route geometry and cost remain in the geography owner. Genesis does not maintain another hand-written personal map or leak the complete generation map. Initial acceptance checks actual place nodes, relations, visit evidence and route references; source prose alone does not prove a complete graph.

The public baseline comprises public propositions in resident units A-01, A-01-02, B-01, B-02, B-03, B-05, B-05-02, B-05-03, B-06 and B-06-16, preserving each unit's full text and unknown boundaries. The expected network includes the home planet/Earth and their limited connection; Mistyville and the unknown outside; four residential regions; three tribal centers and town center; Skyreach Square, Skyreach Ancient Tree, Elder Council Hall, Learning and Healing Hall and Hundred Trades Street; Earthbound Transit Station; Undercity Gate/undercity; Firstroot Tree; Riverturn Hill/Riverturn Bend; Clearheart Lake/Lakeheart Isle; Skymirror Lake/Cloudfall Falls/Cloudcrown City. Create only containment, direction, observation and travel boundaries explicitly supported by those units. Do not copy the full road network, private homes, elders' house interiors or unregistered deep routes.

Add Earth-home instance facts through E-08-02/03 only after arrival. Represent unknown outside territory as unknown scope, not invented city nodes. Public nodes use registered place IDs. Missing necessary public propositions must first be added to sources and published; extractors cannot guess them.

#### 6.5.6 Visit opportunities, trips, frequency and stays

The four macro-regions are forest, plain, mountain and mixed residential area. Town center is a concrete place group; mixed-area residence does not imply living in town. Study may use a village teacher; treatment and public affairs do not force everyone into town. First determine purposes and possible destinations from life context; combined visits are handled within the same opportunity.

Ordinary center visits allocate opportunity among feasible market/exchange, relatives/social contact and sightseeing purposes. Initially weight them equally, set inapplicable purposes to zero and normalize the remainder; no applicable purpose means no opportunity for that scenario. Learning, treatment and public affairs receive dedicated slots only from actual life needs, not merely because a center exists. Their trips are not counted again as ordinary opportunities. Mandatory departure is separate. Natural attractions primarily use sightseeing, with accompanying relative visits/exchange as incidental purposes. Underground visits arise only from eligible activities. When center categories overlap for one destination, choose the sole applicable baseline in this order: town resident, visitor from outside town, local center, other center.

Cultural attraction maps Saevi family culture to Firstroot Tree, Tovren to Riverturn Hill/Riverturn Bend, and Myelle to the Skymirror Lake mountain group. This changes visit tendency only; species grants neither belief nor knowledge. Mixed-area residents retain their personal cultural background while distance is calculated separately. Riverturn Hill/Riverturn Bend forms a plain-attraction group using the source's plain-attraction row, sampled separately from the lake group.

Accumulate over residence/life periods:

`Λ=Σ[annual base rate×available years×age-related mobility feasibility×personality multiplier×cultural attraction×exp(−round-trip travel days/τ)]`

`opportunity count~Poisson(Λ)`; `probability of at least one opportunity=1−exp(−Λ)`.

Count is the sampled result; do not independently sample “ever visited.” Age contributes through available years and feasibility, without another age probability. Deduct time occupied by learning/work. Care-supported childhood travel can be feasible; partially available periods contribute proportionally. One center uses one base rate. Split the total among purposes rather than assigning every purpose the full rate. Use the primary-purpose personality multiplier and a separate species-cultural attraction multiplier, without repeatedly multiplying all traits.

Allocate sampled opportunities across periods by their contribution to Λ, then choose starts within available intervals; do not cluster everything at current age. Only after route, access, care and scheduling checks does an opportunity become a visit. Record unreachable/overlong opportunities as unrealized rather than retrying until success. Trips record start/end, multiple purposes, companions, actual edges, travel days, stay and contact level.

Count valid trips; one multi-purpose town trip counts once. Repeated routines may be grouped with counts and periods preserved. Optional cross-region tourism has a time cap. Relocation, long study and mandatory departure are separate but still conflict-checked.

| Place group | Within-opportunity handling |
| --- | --- |
| Town center | Execute the primary purpose; draw each incidental public point once using `q=1−exp(−r×available sightseeing days)`, then check activity/travel time; interiors require eligibility |
| Lake | Reach shore first, then draw a Lakeheart Isle opportunity and check ferry/stay; do not skip the prerequisite |
| Skymirror Lake mountain group | Skymirror Lake, Cloudfall Falls and distant Cloudcrown City may share one actual viewpoint, subject to visibility; no Cloudcrown City entry |
| Underground | Entrance observation is distinct from entry; entering needs activity window, training, permission and dedicated route |
| Mandatory departure | Current home → Earthbound Transit Station → preparation → actual departure/arrival; town center is not mandatory and other public facilities are not universally visited |

Add only places actually contacted on recorded route segments. Crossing a region is not visiting all attractions. Do not infer undeclared intermediate places from cross-cell lines. Town residence/study may generate repeated daily opportunities, but only actual free time counts as sightseeing. Exterior, entry and use have separate counts. Complete trips obey 6.4.4's single graph and units.

#### 6.5.7 Factual timeline and personal history

Family structure supplies candidate life events. Realize and merge actual contact, learning, labor, trips and departure chronologically. Step-three slots enter the factual timeline only after step-four prerequisite/outcome checks. A plan to visit does not prove a visit. Added friend families reuse established acquaintance facts and cannot change protagonist age or existing trips.

For each candidate history point:

1. Deduplicate by event identity and restrict occurrence to protagonist birth through the present.
2. Require an existing relationship at occurrence, except relationship-establishing boundaries such as first meeting or child birth; exclude a friend's earlier marriage/children before acquaintance.
3. Require personal experience, shared-life knowledge or an explicit informant; record later acquisition time separately. Own birth is an identity start, not a fabricated sensory memory.
4. Retain knowable necessary facts: first acquaintance, learning completion, partnership, own child birth, actual visits, care changes and departure/arrival.
5. Retain brief eligible marriage/birth/death or major relationship events for people meeting the source importance threshold.
6. Draw once for other events using final importance, event type and purpose relevance. Sort by occurrence while preserving acquisition time.

Pre-birth/pre-acquaintance events do not enter initial personal history. Knowing a parent's birthday is not experiencing their birth. Early events not directly rememberable need a valid later-information basis; attributes do not masquerade as experiences. Preserve causal order within a year. Participation uses pre-event importance; retrospective selection uses final importance.

#### 6.5.8 Knowledge acquisition and temporal feedback

World knowledge comes from the resident catalog. Personal knowledge comes from knowable family/life facts and validated events, not invented story content. Execute `known_before → prerequisite validation → actual event/learning → new knowledge and relationships`. Learning within an event also has order. Missing capability required by a later vocation invalidates dependencies and backtracks under 6.6; narrative cannot supply qualifications.

| Conditions / difficulty | Acquisition rule |
| --- | --- |
| Neither | Guaranteed; fix upstream audience conditions if inappropriate, rather than silently omit |
| Conditions only | Acquire when the complete condition holds |
| Difficulty only | Stable probability draw |
| Both | Same stable draw after conditions hold |

Check full text and eligibility per unit: actual residence for regional conditions; passing/seeing/entry/use and actual segments for places/routes; real learning/capability for vocations; distinct training, departure and arrival states for Earth/new-home facts. Titles, place-name mentions and keywords cannot grant eligibility. Apprenticeship completion is not mastery of all professional knowledge.

Each unit retains complete text, stable identity, source boundary, acquisition time or explicitly unknown time, and related person/place/episode references. Cover all unlabeled basic knowledge by admission completion; unknown-time knowledge cannot prove earlier skills. Difficulty values come from the source. One stable value per knowledge ID survives repeated visits, backtracking and story rewriting. Failed intermediate conditions invalidate dependencies without inventing a life to obtain desired knowledge.

History/stories can use knowledge available at the event's time. Recheck eligibility and text against final actual facts. Missing required initial knowledge cannot be deferred to nightly consolidation.


Personal knowledge retains atomic facts organized into reviewed small-topic buckets. Evaluate eligibility and acquisition time per unit first, then group acquired full text. Do not concatenate whole A/B chapters or infer topics from IDs. The resident compilation member declares bucket membership and order; Program references it. Every member retains its stable ID, full text, provenance, conditions, certainty, acquisition time and evidence. Titles and hierarchy are derived organization, not another fact authority.

Generation may submit bounded topic groups through the existing APSO entrance with explicit member boundaries. Memory must preserve fact-level evidence and topic membership. Split oversized groups at whole-member boundaries under configured limits; never truncate text, substitute summaries or redraw eligibility. Grouping cannot turn legends, uncertainty or conditions into certain facts, or backdate later knowledge into earlier experiences.

On a member hit, Recall expands relevant acquired siblings within its budget, deduplicating and retaining provenance. Return the whole group when it fits; otherwise return relevant complete members plus an omitted-member count/continuation reference. A hit does not guarantee unlimited context. Lab defaults to grouped reading with expandable eligibility, provenance and evidence per member. The current source-first implementation keeps one complete Episode per fact and records the declared bucket and member order; Recall expands only those acquired siblings and reports omissions without concatenating or truncating facts. Acceptance still covers large-group splitting, unacquired-member isolation, temporal filtering, idempotency and source-free reopen.

#### 6.5.9 Detailed stories, Selfhood and introduction

History determines what happened; stories express experience, feelings and effects:

1. Every retained point gets a brief narrative. Every actual visit and required relationship change has episode support; group repeated routines by period.
2. Choose applicable growth/care, relationship, learning/labor, representative-visit and departure/arrival themes, covering life stages and important people first. Normally at least five, fewer for young lives; cover necessary events without padding vocations, trauma or story count.
3. Rank remaining points by normalized event importance, related-person importance and purpose relevance. Use zero for person importance when no person is involved. Meet coverage first, then avoid concentrating all prose on one person/place.
4. Express frozen ages, people, places, actions, outcomes and knowledge sources using Big Five and stable character traits. Do not add facts changing relationships, capabilities, vocation or visits. A genuinely new event must return to factual validation.
5. Compare by episode_id/fact_id; brief and detailed versions share identity. Wording and splitting do not raise importance again.

Models are optional; canonical summaries remain usable independently. Validated wording is submitted with its Episode/Evidence. Recheck knowledge eligibility, life status and chronology before submission; polishing cannot introduce unknown ancestral tales or deceased travel companions.

Selfhood receives complete typed state under its owner's mapping version:

| Layer | Initialization |
| --- | --- |
| identity_core | ID, display name, formal species, source world/region and fixed resident role, consistent with Profile |
| adaptive_self | Bounded Big Five, interaction/coping/expression tendencies, norms/values and optional language markers through closed mappings |

Exclude episode text, encyclopedic knowledge, current relationships/emotions/energy, permissions, questionnaires, package bindings and final prompts. Add no runtime personality-growth channel. Missing fields, invalid ranges, unknown mappings or failed official projection block submission, without default 0.5, Profile rereads or model repair. Model-facing text is a derived Selfhood output.

The welcome introduction temporarily combines authorized final Profile, Selfhood and Memory projections: identity, origin, past household, one real episode and reason for arrival, omitting inapplicable parts. Projection versions/hashes bind the plan only during creation. Do not create another durable biography or allow ordinary Brain to bypass boundaries by reading Profile.

#### 6.5.10 Intermediate structures, Memory handoff and coverage

These are design responsibilities, not a claim that current types expose every field. Private IDs derive from Elfie ID and stable slots; public entities use registered IDs. Reference the adopter only through the product's real relationship; do not merge names or fabricate cross-instance friendships.

| Artifact | Required content |
| --- | --- |
| LifeContext | Frozen identity reference, birth/home, unique family graph/care, residence intervals, learning/vocation plans, travel opportunities/departure, permitted event slots |
| Event slot | Stable ID, time/duration, places/people, knowledge/capability prerequisites, permitted outcomes and dependencies; not a fact before realization |
| PersonPlan / RelationshipPlan | Unique people, life/residence/contact facts; both IDs, direction/roles, familiarity, Trust, Importance and change evidence |
| EpisodePlan | ID, occurrence age/interval, duration, time/place/people, actual route IDs, purpose/action/outcome, bounded feelings, effects, relationship before/after values, prerequisite/acquired knowledge, causal references and evidence |
| PersonalGenesisPlan | Validated knowledge/life facts, people/relationships, history/stories, Profile result, complete Selfhood, local evidence, submission mappings and semantic digest |
| GenesisBundle | ProfileDraft, SelfhoodState, three Memory Seed classes, other contract-required startup Seeds and InitializationManifest |

Mark inapplicable fields empty. Incomplete learning/vocations are not available capability; detail text does not copy all LifeContext. The three Seeds classify submission responsibilities: **knowledge and episodes use established APSO inputs; relationships initialize directly with APSO evidence retained**. Their names do not authorize new graph-write entrances. Memory owns extraction, deduplication and materialization; Genesis provides evidenced inputs.

| Content | Official input responsibility | Required result |
| --- | --- | --- |
| Selected resident knowledge | KnowledgeSeed: stable ID, full text, acquisition stage/category, local evidence | Facts and Evidence preserving conditions, legends and unknown boundaries |
| Known personal propositions | Personal KnowledgeSeed projection in a personal namespace | Subject/relation/object and temporal evidence for home, learning, self-understanding and related facts |
| People/relationships | RelationshipSeed: unique people, role/direction, familiarity, Trust, Importance, shared context | Person nodes, relationships and evidence; APSO backup shares identity without double counting |
| Key experiences | EpisodeSeed: complete summary/adopted wording, time/place/people, outcomes, effects and causes | ClosedEpisode and evidenced propositions |
| Known/contacted places | Stable ID, names/aliases, type, containment, public status and knowable description carried by the three inputs | Places and evidenced spatial/contact relations; hearsay creates no visit |

Personal propositions are not long biographies; experiences retain complete Episodes. PlaceSeed/SelfModelSeed, if compiler-internal, are not a fourth official input. If existing contracts cannot carry personal facts, complete the required formal design/implementation first instead of forcing old interfaces. Local source_ref points to Evidence/events surviving commitment; knowledge IDs are not runtime foreign keys back into packages. Evidence excludes condition trees, probabilities, random values, entire sources and unknown family members.

Genesis provides constrained Importance and applicable Confidence. Episodes have no Confidence; Trust is separate from Confidence. Memory owns formal Retention, indexing, reinforcement and decay. Its current versioned admission policy is `retention_profile=genesis`, `half_life_days=3650`; the Memory contract owns these values, and Genesis does not define retention days. Creation inputs must be removed after successful commitment or terminal failure. Ordinary Brain reads only Selfhood, Memory and current Brain state. Aliases, search terms, place descriptions, person capabilities and Evidence derive only from selected content, with no unacquired knowledge leaks.

InitializationManifest records expected owners, output IDs/counts/digests and checks. Package/policy/seed bind the Envelope rather than every Seed. Formal Memory submission writes records and completion marker in its own transaction; App cannot bypass its entrance to edit storage. Compare retained plans → actual episodes/relationships/places/knowledge → recallable facts. Incomplete extraction, missing or duplicate relationships block completion. Repair only corresponding input/materialization; do not change seed, regenerate life or invent visits to fill nodes. See 6.7.

### 6.6 Determinism and bounded failure

**Randomness and digests.** Fix the algorithm as `sha256-domain-v1`: SHA-256 over canonical JSON `[algorithm version, master_seed, domain, stable object/slot ID, domain-policy version, attempt_id, draw_counter]`. Use UTF-8, NFC, no extra whitespace and direct non-ASCII encoding. Interpret the digest as an unsigned big-endian integer. The seed is 32 bytes represented in lowercase hexadecimal; counters start at zero.

Candidate, age, appearance, personality, naming, birth, family, learning, vocation, relocation/travel, person, event and knowledge IDs use separate domains. Knowledge uses `attempt_id=0`; backtracking rechecks eligibility without rerolling mastery. Prohibit process-randomized hashes, unordered iteration and shared advancing global random streams.

Sort discrete choices by stable ID. Use nonnegative integer cumulative weights with `W∈[1,2^64−1]`. Accept digest integers below `2^256−(2^256 mod W)` before modulo W; otherwise increment only that draw counter, within its finite budget. Fixed probabilities use reviewed integer numerator/denominator through the same method; handle zero/one directly. Reject invalid/all-zero weights at publication. Section-6.5 exponentials, conditional lifespans and Poisson sampling additionally bind precision, probability quantization and sampler versions with fixed test vectors. Unpinned library defaults are forbidden. Activate semantic policy and deterministic implementation only after joint validation.

Canonical semantic digests use NFC, sorted object keys, ID-sorted sets, ordered timelines, declared integer precision/units and timezone/time precision, rejecting NaN/Infinity. Include frozen identity, learning/event business state and occurrence time. Exclude only the digest itself, nonsemantic task status/technical completion time, durations spent computing, machine paths, logs and model wording. Distinguish event time from database-write time. Name source-byte, semantic-content, model-projection and final-file digests separately. Model projections bind an immutable Plan and cannot affect IDs/facts.

**Backtracking and errors.** Try another legal option in the current slot, then directly upstream unfrozen choices, then the broader life structure. Invalidate only dependent trips, people, knowledge, events and self projections. Increase attempt_id stably within fixed budgets. Identity, age, appearance, personality anchors and hard user choices cannot backtrack; no temporary budget increase or seed replacement.

| Error | Response |
| --- | --- |
| Invalid input/candidate | Return actionable reasons before acceptance, without a reservation |
| Invalid package/version/reference/required knowledge | Identify member/rule and stop; no package substitution |
| Unsatisfiable constraints | After bounded backtracking, return conflicting conditions, rule IDs and stage; no default life |
| Invalid model projection | Discard prose and use canonical summary without rerolling facts |
| Temporary storage/process failure | Keep reservation identity; inspect completed results and resume |
| Owner validation/output conflict | Keep invisible; verify before resuming or terminating |
| Connection failure after complete admission | Preserve committed state and recover from final owners |

Users see stage, retryability and actionable cause. Logs contain redacted error codes/rule IDs; technical failures never become life events. Unavailable original compiler/mapping versions explicitly block recovery instead of silently using new versions.

### 6.7 Admission publication, recovery and cleanup

**Publication order:**

~~~text
reserved → compiling → staged → publishing → committed
~~~

1. **Reserve:** Adoption atomically reserves member quota; Nest reserves bed/admission capacity through its own boundary, both bound to the reservation. Failure of either cancels the other. Admission does not become the owner of their capacities.
2. **Stage:** generate owner data in a private workspace. Formal Memory submission commits expected records and completion marker atomically. This is not product admission.
3. **Verify:** reopen owners and validate references, chronology, knowledge, Selfhood projection and manifests/digests. Keep creation inputs separate from final files.
4. **Coordinate publication:** atomically publish the valid final file tree on one filesystem. Adoption idempotently finalizes relationship/quota; Nest, through nest_session, idempotently finalizes resident/bed and durable state. Confirmations bind the same Elfie/reservation/execution identity. File existence or one finalized owner is not activation.
5. **Activate:** after all three durable results are verified and no prior package revocation exists, Admission atomically writes `committed`. This is the sole product-visible point; welcome, assembly and Runtime start follow it.
6. **Clean up:** remove inputs/intermediates after success or definite termination. Pending recovery retains only necessary data in the restricted private workspace.

This is bounded cross-owner coordination, not a presumed transaction across databases. An uncertain call requires querying actual owner completion, not inferring failure from timeout. Nest owns acceptance facts, Adoption owns adoption facts, and App coordinates confirmations/compensation. Technical confirmations do not become a second business ledger.

Reservation/in-progress state lives in a separate reservation record. Final business tables contain only facts finalized by their owners, not misleading pending/draft completion. App gates lists, ownership authorization, official resident counts, Nest snapshot assembly/recovery, welcome, Recall and Runtime on `committed`. Unactivated results are coordinator-only for verification/compensation; unknown completion stays closed. Valid reservations consume capacity without counting as residents. Nest/Elfie do not read Admission in reverse; App supplies activated objects through existing boundaries. Directory scanning or direct local completion records cannot bypass activation.

Package revocation registration and the committed decision share one serializable boundary ordered by package-availability revision and reservation execution token. Do not check availability then commit unconditionally. Earlier revocation preserves invisibility and compensates finalized items; earlier activation permits recovery/cleanup without retroactively revoking the Elfie. Configuration publication owns availability. Reservation package bindings end at terminal state, not ordinary runtime.

Successful-admission propositions are pending while staged and become externally valid with Admission committed. Failure must not leave recallable “already admitted” memories. Room perception, body position and movement require real runtime facts; bed assignment is not walking to the bed.

**Concurrency, cancellation and recovery.** Each transition atomically compares reservation state and advances an execution token. Publication writes validate that token; stale executors cannot continue. Expired locks permit recovery of the same operation only. Reserve/consume/release quota and beds independently idempotently. Reject one in-progress key with a different input digest; committed keys return the original result.

| Interruption window | Recovery |
| --- | --- |
| Compilation incomplete | Resume the same Envelope/seed and versions without changing identity |
| Memory staged, other data incomplete | Check marker/manifest and finish the same Bundle, or remove confirmed invalid private staging |
| Final files published, relationship or Nest acceptance incomplete | Remain publishing, inspect files/owner receipts and complete missing items; this is not merely connection failure |
| Three results finalized, Admission not committed | Revalidate identity, Schema and completeness, then repeat serialized revocation/activation decision; commit only if unrevoked, otherwise compensate; partial receipts cannot activate |
| Runtime fails after committed | Reopen final owners without Envelope or new bed/quota consumption |
| Cleanup interrupted after commitment | Retain minimal cleanup-pending state and clean idempotently without rolling back the valid Elfie |

Before the publication fence, cancellation stops execution, removes private results and releases reservations. After the fence, first determine commitment. For confirmed uncommitted termination, owners compensate finalized relationships/quota/admission before incomplete data is removed or isolated. Unconfirmed compensation stays recoverable, not “cancelled.” Removing a committed Elfie is a separate product operation, not Genesis cancellation.

Exhausted retries distinguish resumable pause from definite termination; only termination removes inputs. Candidate expiry constrains pre-acceptance input, not the duration of recovery for an accepted reservation/publication. Isolate final paths of unknown integrity for verification rather than deleting, overwriting or creating another individual. If same-filesystem atomic publication is unavailable, report an environment error before publishing; do not expose file-by-file copying.

**Integrity and minimal receipts.** A Memory marker proves only atomic completion of its submission; Admission committed controls whole-product visibility. Cross-check them using reservation/output identities; the marker is not recallable.

Semantic digests cover declared business outputs and necessary asset references, excluding receipts/markers. Validate files separately; database-byte hashes are not semantic digests. The initial manifest serves unfinished-publication recovery, not an obligation for evolving Memory to remain a birth snapshot.

`GenesisCommitReceipt` contains only Elfie/reservation IDs, one-way idempotency-key digest, output IDs/digests/Schemas, compiler revision, completion state/time and necessary cleanup state. It excludes input digests, package bindings, Seeds, questionnaires and reconstructable life inputs. Ordinary recovery cannot use it to regenerate an Elfie.
