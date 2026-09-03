# Nest–Godot semantic-world contract

**Contract version:** 1.2
**Adopted:** 2026-08-13
**Amended:** 2026-09-02
**Scope:** `nest/`, the Godot semantic boundary, and affected App orchestration

> **Normative target.** This contract defines Nest internal fact ownership,
> semantic interaction with the authoritative Godot world, and unique event
> routing to Elfies. Current implementation gaps and their mandatory cleanup
> order are recorded in the temporary
> [Nest–Godot conformance register](../conformance/nest-godot-semantic-world).

The repository-wide owner and dependency direction remain governed by the
[System architecture contract](./system). This contract refines that boundary;
it does not create a new root module, physical authority, composition root or
lifecycle owner.

## Authority model

| Part | Owns | Does not own |
| --- | --- | --- |
| Elfie | individual intent, cognition, body-action initiation, perception, emotion, memory and response | household rules, 3D geometry or environment-object authority |
| Nest | household semantics, rules, time/environment intent, semantic interaction and Nest events | independent Elfie body intent, physical simulation or real Elfie objects |
| Godot | scene, position, physical body, navigation, collision, visibility, audibility, rendering and actual execution | homes, ownership, household rules, speech content or Elfie cognition |
| App | composition, cross-authority object lookup, Runtime lifecycle and recovery | a second world model, routine body control or Nest business decisions |

One running ElfieNest has exactly one Nest and one currently authoritative
Godot Runtime generation. One fact has one semantic owner. Other components may
retain only a typed, source-labelled and revision-bounded projection.

## Nest functional ownership

Nest has four first-level functional owners:

| Owner | Owns | Must not own |
| --- | --- | --- |
| Space and Facilities | the Nest ID; a coordinate-free semantic catalogue keyed by Godot-owned stable room/zone/anchor/object IDs; facility type, purpose, capability and the minimum discrete environment projection | creation of physical referent IDs, coordinates, collision shapes, paths, per-frame motion, resident ownership or dynamic visible surroundings |
| Household Living Rules | resident IDs, homes, ownership, sharing, reservation, occupancy, access, environment override and event-audience policy | real Elfie objects, physical reachability, speech payload storage or message transport |
| Time and Environment | Nest clock, pause/scale, life phases, scheduled environment rules and desired environment state | one Elfie's energy/sleep decision, render parameters, physics ticks or Actor commands |
| Elfie–Nest Interaction | short-lived observation, utterance and semantic-intent correlation; semantic vision, virtual hearing and semantic-action assembly | source facts owned by the other three owners, physical calculations, autonomous body decisions or concrete transport |

These are conceptual and behavioral owners. They do not require four packages,
processes, databases or pre-created directories. A physical module is introduced
only when it contains real state, contracts or behavior. The stable `Nest`
facade remains the aggregate inbound boundary and exposes typed use-cases rather
than mutable submodules.

Now that all four owners have real code, their canonical one-to-one repository
mapping is `space_facilities/`, `living_rules/`, `time_environment/` and
`elfie_interaction/`. The descriptive names prevent `space`, `rules` or
`interaction` from becoming generic catch-alls. This mapping does not require
one file per model or service, but it does prohibit broad technical containers
from becoming alternative ownership boundaries:

- Time and Environment owns its clock and driver. A generic `engine/` package
  is not a fifth owner and must not duplicate time advancement or be confused
  with Godot Engine.
- Aggregate composition stays behind `Nest` in `nest.py`; a broad public
  `NestState` compatibility shell is not a second inbound API.
- Owner-specific state, models and errors stay with their owner. A generic
  `state/` package must not collect unrelated facts from all four owners.
- Aggregate configuration and a technology-neutral Nest snapshot may live at
  the `nest/` root. The App-owned Nest state-store Port lives with the
  Orchestration consumer; concrete storage remains in root Infrastructure.
  Neither seam is a fifth Nest business owner.
- `events.py` may hold the common event mechanism. It remains cross-cutting
  plumbing and never becomes a fifth owner.

`nest/` stores resident IDs and Nest state only. It never holds or constructs a
real Elfie. Real Elfie instances and Nest state are composed only in App
Orchestration.

## Common Nest event mechanism

The event mechanism crosses all four owners and is not a fifth business module.

- The semantic owner of a fact creates the event.
- Household Living Rules resolve the audience only when household policy is
  needed.
- The event router receives an already classified event and delivers it once to
  explicit target IDs.
- Broadcast is an audience shape such as all active residents or an explicit
  resident set. It is never the default route for Runtime events.
- One semantic event has one delivery path. Distinct facts caused by one
  physical occurrence use distinct event IDs and types and may share a cause ID.
- Retries preserve event identity. Runtime generation and world revision reject
  stale physical input; they do not create replacement event identity.
- A typed outbox, stream or queue may implement delivery, but the same event
  must not also be copied into an untyped per-resident sensory queue. An event
  is not complete until a production consumer has delivered or durably accepted
  it according to its explicit targets.

A typed Nest event envelope carries, where applicable:

- stable `event_id`, event type, fact owner and occurrence time;
- optional `cause_id` and originating request/intent/utterance/observation ID;
- explicit target resident IDs or a policy audience selector awaiting rule
  resolution;
- source Runtime ID, generation and world revision for Godot-derived facts;
- bounded typed payload without protocol frames, coordinates or unvalidated
  dictionaries.

Examples of owner-created events include facility-state changes from Space and
Facilities, access-rule changes from Household Living Rules, quiet-hours changes
from Time and Environment, and `HeardUtterance`, `SemanticVisualScene` or
`SemanticActionResult` from Elfie–Nest Interaction.

Raw body receipts, tactile/proprioceptive input, raw `VisibleSet`, raw
environment facts and Runtime lifecycle frames are not Nest broadcasts.

## Semantic paths

| Path | Direction | Rule |
| --- | --- | --- |
| `NestQuery` | Elfie ↔ Nest | Pure household-semantic lookup; no physical execution |
| `DirectBodyChannel` | Elfie Body ↔ Godot | Known target and no current household-semantic resolution; receipts and body perception return through the owning Body and NervousSystem only |
| `SemanticAction` | Elfie → Nest → Godot → Nest → target Elfie Body | One authorized intent covers deterministic target resolution, physical execution and one semantic result; a targeted result re-enters Body/NervousSystem and does not require a second Brain Turn just for the receipt |
| `SemanticVision` | Elfie → Nest → Godot → Nest → target Elfie Body, or Godot → Nest → target Elfie Body | An active observation is one correlated request; Godot may also report a bounded significant change. Godot computes the physically visible entity set; Nest adds only household meaning and emits one targeted semantic visual perception through Body/NervousSystem |
| `SpeechBridge` | Elfie → Nest → Godot → Nest → target Elfie Body | Nest retains content and expressed emotion; Godot returns physical listener candidates to Nest; rules filter residents; Nest emits targeted hearing events through each target Body/NervousSystem |
| `EnvironmentChannel` | Nest ↔ Godot world objects | Nest sends desired environment commands; Godot returns actual discrete facts and command results |
| `RuntimeControl` | App Lifecycle ↔ Godot host/Gateway | startup, readiness, generation, health, disconnect and recovery only |

Whether an action needs pathfinding does not decide its route. Godot always owns
pathfinding. The route crosses Nest only when current household meaning—such as
my home, shared, available or allowed—must be resolved.

Nest may forward a resolved Actor target only when the command retains the
original Elfie intent identity, actor identity and authorization. A semantic
result targeted at an Elfie is delivered into that Elfie's Body input boundary
and then NervousSystem; it never jumps directly to Brain. If the result requires
a new actor-body command, that command is submitted again through NervousSystem
and Body before reaching Godot. Nest cannot create, schedule, resume or rewrite
Actor behavior independently. Time and household rules may independently
command environment objects such as lights or doors because those are Nest-owned
world intentions, not Elfie body intentions.

## Structured virtual perception

MVP virtual vision does not render one subjective camera viewport per Elfie and
does not use screenshot-to-VLM inference. Godot computes a bounded `VisibleSet`
from actor transform, field of view, distance, occlusion and current physical
state. Nest joins stable semantic IDs with facility meaning, ownership and rules
and emits one `SemanticVisualScene` to the corresponding Elfie. Nest never
persists a per-Elfie surrounding-object list or recomputes visibility.

MVP virtual hearing does not use a TTS → 3D audio → STT loop. Nest retains the
utterance text, expressed emotion and identity. Godot returns only physical
listener candidates for the occurrence. Nest applies resident and propagation
rules and emits `HeardUtterance` to each final listener. Optional TTS or 3D audio
is presentation for human observers, not evidence of Elfie hearing.

## Godot boundary and project logic

Godot remains the physical authority for scene objects, virtual bodies,
physics/navigation, spatial queries and presentation. Engine primitives such as
SceneTree, CharacterBody3D, collision, NavigationServer3D, animation, Area3D,
ray/space queries, audio players, rendering and WebSocket transport are reused.

ElfieNest-owned Godot code is limited to semantic glue and stateful behavior:

- an Actor controller maps high-level commands to movement/animation and emits
  targeted receipts and body perceptions;
- a World controller publishes semantic scene/object manifests, executes
  environment commands and computes `VisibleSet` and speech reachability;
- a Runtime endpoint validates protocol identity and emits classified typed
  frames over the shared authenticated connection;
- only stateful interactive objects such as doors, lights and movable or special
  facilities receive narrow scripts.

Godot does not store homes, resident ownership, household permissions or speech
content. Python does not copy coordinates, geometry, navigation, collision,
occlusion, acoustic reachability or physical-frame state.

Stable IDs for physical rooms, zones, anchors and objects are authored with the
Godot scene and published in its manifest. Space and Facilities owns the
coordinate-free household catalogue and meaning keyed by those IDs; it neither
creates a competing physical identity nor exposes NodePath as identity.

Godot source paths are classified by purpose, not counted as Nest business
modules:

| Source category | Repository role |
| --- | --- |
| `rooms/`, `characters/` | authored physical scenes, geometry, actor resources and runtime content; these are retained content, not extra business modules |
| `runtime/actor/`, `runtime/world/`, `runtime/endpoint/` | the small authority glue described above; spatial visibility and audibility belong to World rather than Actor |
| `runtime/observer/`, `runtime/lab/`, `ui/` and referenced preview controllers | presentation or development modes; they do not gain physical, household or lifecycle authority |
| `scripts/test/`, `scripts/tools/`, character tools and authoring-source trees | developer-only inputs; they must be excluded from every release export and are not Runtime dependencies |

`main.gd` is assembly and mode dispatch. Directory cleanup does not justify
deleting referenced scenes or assets. Conversely, an all-resources export must
explicitly exclude every developer/authoring tree, and an unreferenced helper or
generated sidecar is retained only with a documented authoring or invocation
purpose.

## Delivery, orchestration and dependencies

Nest and Elfie never import each other or concrete Godot Infrastructure.
Consumer-owned typed Ports are implemented in `infrastructure/godot/` and wired
by Bootstrap. One concrete Gateway may implement several narrow capabilities;
sharing the connection does not merge their semantic lanes.

App Orchestration may correlate real Elfie instances with Nest resident IDs and
deliver a typed, already-authorized perception to the target aggregate. It does
not choose household meaning, invent physical facts or proxy direct body
traffic. Nest Session also owns the current state-store Port and persistence
timing, but can store or restore only snapshots produced or accepted through the
Nest Facade. App Lifecycle alone starts, stops and recovers the Godot authority.

Protocol frames, WebSocket state, process objects and Runtime credentials never
enter Nest. Domain commands, results and events never expose NodePath, raw
coordinates, database records or arbitrary JSON.

## State and recovery

| State | Authority and recovery rule |
| --- | --- |
| residents, homes, facility semantics and household rules | Nest-owned snapshot semantics restored through the App-owned Nest state-store Port and an Infrastructure Adapter |
| Nest time, life phase and desired environment state | durable Nest state resynchronized to a ready new Godot generation |
| actor position, speed, pose, navigation and actual object state | current Godot/body Runtime; old Python projections are invalid after generation change |
| discrete actual environment projection required by rules | source-labelled Space and Facilities projection invalidated and rebuilt after generation/revision change; it is distinct from Time and Environment's desired state |
| utterance, observation and semantic-intent correlation | short-lived Nest interaction state; interrupt or reconcile on generation change, never blindly replay |
| direct body commands and receipts | owning Elfie Body plus Godot; never recovered through Nest |
| Runtime generation and health | App Lifecycle |

Current desired environment state is resynchronized after recovery. Expired
animations, utterances and physical side effects are not replayed.

## Verification and migration discipline

Every migration is one independently reviewable vertical slice. It freezes the
typed boundary, migrates the complete producer-to-consumer call chain, proves
targeted routing and causal identity, deletes the replaced path and closes only
the matching conformance row. No compatibility alias, dual write, second world
projection or empty architecture package is introduced.

Focused evidence must distinguish direct body receipts, body perception,
semantic physical results, visible sets, environment facts, speech reachability,
Nest events and Runtime lifecycle events. A passing transport test alone cannot
prove semantic routing or authority ownership.

Before a conformance row closes, the evidence must trace the exact contract
clause and owner through the real producer, typed boundary, single production
route and final consumer. It must include a positive case, a non-target or
forbidden-route case, retry/deduplication identity and—when physical state is
involved—stale-generation and recovery behavior. Godot behavior and export
claims require real Godot or release-artifact evidence. Folder names, unit tests,
transport round trips and screenshots are individually insufficient.

Structural cleanup additionally inventories tracked, untracked, ignored and
empty paths and classifies every guarded Nest/Godot entry against the approved
source disposition. Unknown entries fail the permanent structural scanner;
temporary paths mapped to an open row cannot gain files. Cleanup is incomplete
while any relevant path or caller remains, regardless of selected test results.

The temporary conformance register cannot be removed in a product migration or
while any row is open. Final deletion is a separate governance-only change
after current implementation, negative-path evidence and recovery evidence all
match this contract.
