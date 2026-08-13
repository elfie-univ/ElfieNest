# Nest–Godot semantic-world contract

**Contract version:** 1.0
**Adopted:** 2026-08-13
**Scope:** `nest/`, the Godot semantic boundary, and affected App orchestration

> **Normative target.** This contract defines Nest internal fact ownership,
> semantic interaction with the authoritative Godot world, and unique event
> routing to Elfies. Current gaps are recorded in the
> [Nest–Godot conformance register](../conformance/nest-godot-semantic-world),
> and the approved card order is fixed by the temporary
> [migration specification](../conformance/nest-godot-semantic-world-migration).

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
| `DirectBodyChannel` | Elfie Body ↔ Godot | Known target and no current household-semantic resolution; receipts and body perception return only to the owning Elfie |
| `SemanticAction` | Elfie → Nest → Godot → Nest → Elfie | One authorized intent covers deterministic target resolution, physical execution and one semantic result; it does not require a second Brain Turn |
| `SemanticVision` | Elfie → Nest → Godot → Nest → Elfie, or Godot → Nest → Elfie | An active observation is one correlated request; Godot may also report a bounded significant change. Godot computes the physically visible entity set; Nest adds only household meaning and emits one targeted semantic visual perception |
| `SpeechBridge` | Elfie → Nest → Godot → Nest → target Elfies | Nest retains content and expressed emotion; Godot returns physical listener candidates to Nest; rules filter residents; Nest emits targeted hearing events |
| `EnvironmentChannel` | Nest ↔ Godot world objects | Nest sends desired environment commands; Godot returns actual discrete facts and command results |
| `RuntimeControl` | App Lifecycle ↔ Godot host/Gateway | startup, readiness, generation, health, disconnect and recovery only |

Whether an action needs pathfinding does not decide its route. Godot always owns
pathfinding. The route crosses Nest only when current household meaning—such as
my home, shared, available or allowed—must be resolved.

Nest may forward a resolved Actor target only when the command retains the
original Elfie intent identity, actor identity and authorization. Nest cannot
create, schedule, resume or rewrite Actor behavior independently. Time and
household rules may independently command environment objects such as lights or
doors because those are Nest-owned world intentions, not Elfie body intentions.

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

## Delivery, orchestration and dependencies

Nest and Elfie never import each other or concrete Godot Infrastructure.
Consumer-owned typed Ports are implemented in `infrastructure/godot/` and wired
by Bootstrap. One concrete Gateway may implement several narrow capabilities;
sharing the connection does not merge their semantic lanes.

App Orchestration may correlate real Elfie instances with Nest resident IDs and
deliver a typed, already-authorized perception to the target aggregate. It does
not choose household meaning, invent physical facts or proxy direct body
traffic. App Lifecycle alone starts, stops and recovers the Godot authority.

Protocol frames, WebSocket state, process objects and Runtime credentials never
enter Nest. Domain commands, results and events never expose NodePath, raw
coordinates, database records or arbitrary JSON.

## State and recovery

| State | Authority and recovery rule |
| --- | --- |
| residents, homes, facility semantics and household rules | durable Nest state restored through a Nest-owned repository Port |
| Nest time, life phase and desired environment state | durable Nest state resynchronized to a ready new Godot generation |
| actor position, speed, pose, navigation and actual object state | current Godot/body Runtime; old Python projections are invalid after generation change |
| discrete environment projection required by rules | source-labelled Nest projection invalidated and rebuilt after generation/revision change |
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

The temporary
[Nest–Godot migration specification](../conformance/nest-godot-semantic-world-migration)
defines the mandatory card order, data decision gate, per-card scope and exit
evidence. It may refine execution detail but cannot redefine this target.
