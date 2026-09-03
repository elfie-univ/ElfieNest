# Final Design for the Nest and Godot Virtual Living World

> Status: accepted design
> Confirmed: 2026-08-13
> Nature: functional boundaries, module relationships, information flows and adversarial review; it does not claim that the current code is fully implemented
> Domain baseline: Elfie product, life-form and world materials
> Current system constraint: [System architecture contract](../contracts/system.md)
> Normative boundary: [Nest–Godot semantic-world contract](../contracts/nest-godot-semantic-world.md)

> Design relations: **Owner:** Nest; **Parent:** whole-system design (separate parent; not relocated in this task); **Child designs:** none (current singleton); **Normative contracts:** [System architecture contract](../contracts/system.md), [Nest–Godot semantic-world contract](../contracts/nest-godot-semantic-world.md); **Current architecture:** [Current architecture](../architecture/); **Conformance:** [Nest–Godot semantic-world conformance](../conformance/nest-godot-semantic-world.md); **Domain sources:** Elfie product and world sources.

## 1. Final conclusions

1. A running ElfieNest has one Nest and one current authoritative Godot Runtime.
2. Nest has four first-level functional modules: **space and facilities, in-Nest life rules, time and environment, and Elfie–Nest interaction**. A public event mechanism crosses all four modules. It is not a fifth business module; broadcast is only one possible audience scope.
3. **Elfie is the sole initiator of intent for its own bodily behavior.** Nest may resolve life semantics and forward a resolved body command within the same authorized request, but it may not independently decide, schedule, trigger or rewrite Elfie bodily behavior.
4. The ordinary Nest–Godot relationship is “environment rules and environment facts”: Nest can control lights, door locks and environment phases, while Godot returns facts such as a chair moving, a door opening or the actual light state.
5. Elfie -> Nest -> Godot -> Nest -> Elfie is the unified **semantic–physical loop** for requests that require life semantics and the physical world together, including returning to one's bed, going to the kitchen, finding an available cup, virtual speech and active observation.
6. An immediate bodily action with an already-known physical target and no need for life-semantic resolution flows directly between Elfie and Godot.
7. Virtual vision defaults to structured semantic perception: Godot computes the entities that are actually visible, Nest adds life semantics, and Elfie receives the result. Do not create an independent rendered viewport for every Elfie or use screenshots and an image model by default.
8. One semantic event has one delivery path. The same physical process may produce several different facts, but they must have different event types and unique receivers; a shared cause ID only records that they came from the same cause.
9. Godot's five functional capability areas do not imply five sets of project code. The engine already provides many low-level primitives; the project adds semantic mapping, object state, spatial queries and protocol integration.

This document does not define final class names, database tables, the complete protocol field set, physical thresholds or implementation scheduling.

## 2. Four-part system contract

| Part | Core responsibility | Question it answers | Explicitly does not own |
| --- | --- | --- | --- |
| Elfie | Individual intent, cognition, body-action initiation, bodily perception, emotion, memory and reaction | What do I want to do, what does my body feel, and how do I respond? | Shared household rules, 3D geometry, environment-object authority |
| Nest | Space and facilities, in-Nest life rules, time and environment, and the semantic interaction required for an Elfie to participate in virtual life | What exists in this home, which rules apply, and how are life semantics joined with the physical world into one perception or action? | Elfie bodily intent, physical simulation, real Elfie objects |
| Godot | Scene, virtual bodies, physics, navigation, environment objects, spatial queries and presentation | Can it happen physically, and what actually happened? | Resident ownership, household rules, speech content, Elfie cognition |
| App | Assembly, Runtime lifecycle, fault recovery and product interfaces | How are the first three created, connected and recovered correctly? | Routine bodily control, a second set of world rules, a second physics authority |

Shortest decision rule:

| Question | Sole answerer |
| --- | --- |
| “Do I want to go back to bed?” | Elfie |
| “Which bed is mine?” | Nest |
| “How do I get there, will I hit a wall, and did I really arrive?” | Godot |
| “Which entities can my body physically see right now?” | Godot |
| “What do those entities mean in this home?” | Nest |
| “Should the lights be off at 10 p.m.?” | Nest |
| “Did the lights actually turn off?” | Godot |
| “What was said, and which valid residents should receive it?” | Nest |
| “Which bodies were within hearing range at that moment?” | Godot |
| “Who starts, stops and restores the Runtime?” | App |

## 3. Route by semantic subject first

The system does not broadcast on the basis that “these are all Godot messages”. It first identifies the **subject of the command or fact**.

| Semantic subject | Direction | Examples | Sole receiving boundary |
| --- | --- | --- | --- |
| Elfie body | Elfie -> Godot | Walk, turn, sit, expression, touch a door | Corresponding Godot actor |
| Elfie body | Godot -> Elfie | Action completed, impact, touch, proprioceptive state | Corresponding Elfie Body |
| Nest life semantics | Elfie <-> Nest | Query Home, query facility rules, read time | Requesting Elfie / Nest |
| Semantic body request | Elfie -> Nest -> Godot -> Nest -> Elfie | Go home, go to the kitchen, find an available cup | Nest resolves, Godot executes, original Elfie receives the result |
| Semantic vision | Elfie -> Nest -> Godot -> Nest -> Elfie; important changes may also be Godot -> Nest -> Elfie | Visible entities and their life meaning | Godot computes visibility, Nest adds semantics, target Elfie receives |
| Environment object | Nest -> Godot | Turn off lights on schedule, switch day/night presentation, lock a common door | Corresponding Godot world object |
| Environment object | Godot -> Nest | A chair moved, a door actually opened, a light actually went out | Nest |
| Virtual speech | Elfie -> Nest -> Godot -> Nest -> Elfie | Store content, calculate hearing range, deliver perception | Nest coordinates, listener Elfie receives |
| Nest semantic event | Nest module -> event mechanism -> Elfie | Quiet hours began, facility access rules changed | Life rules resolve the audience; the event router delivers once |
| Runtime | App <-> Godot Bridge | Ready, generation, scene handshake, body binding, disconnect and recovery | App Lifecycle |

The core routing rule is not “who called Godot?” but “whose fact is this?”

For example, Elfie pushing a chair may produce three different facts:

1. BodyActionCompleted: the result of this Elfie's action, delivered only to that Elfie;
2. BodyContact: contact sensed by that body, delivered only to that Elfie;
3. EnvironmentObjectChanged(chair_id): the chair's environment state changed, delivered only to Nest.

They may share a cause ID because they came from one physical process, but they are not one event delivered three times.

## 4. Overall relationship

~~~mermaid
flowchart LR
    E["Elfie<br/>cognition, body control and perception"]
    N["Nest<br/>four first-level modules + public event mechanism"]
    G["Godot<br/>virtual bodies and physical environment"]
    B["shared Godot Bridge<br/>connection, protocol and semantic routing"]
    A["App<br/>assembly and lifecycle"]

    E -->|"explicit-target body action"| B
    B --> G
    G -->|"body receipts and bodily perception"| B
    B --> E

    E -->|"semantic behavior, active observation and speech"| N
    N -->|"resolved, Elfie-authorized request"| B
    G -->|"execution result, visible entities, SpeechReach"| B
    B -->|"semantic physical result, VisibleSet, SpeechReach"| N
    N -->|"semantic result and structured perception"| E

    N -->|"environment-object command"| B
    G -->|"environment-object fact"| B
    B --> N

    A -. "create and inject adapters" .-> E
    A -. "create and inject adapters" .-> N
    A -. "start, stop and recover" .-> B
~~~

Logical channels may share one authenticated connection, but the Gateway must route by semantic subject. It must not send one Godot event to every Elfie and then additionally send it to Nest. App establishes the connection; it is not a relay for routine business messages.

## 5. Seven business paths

### 5.1 Explicit-target body actions: Elfie connects directly to Godot

~~~text
Elfie -> Body Port -> Godot actor
Elfie <- BodyReceipt / BodyPerception <- Godot actor
~~~

All of the following must be true: the target is already known; no ownership, purpose, available-object or household-rule query is needed; and the action changes only the body or physically interacts with one known object. Examples:

- Turn in place, stop, take one step and look toward a known direction;
- ordinary expressions, poses and animations;
- move to an already-resolved anchor ID;
- physically interact with a known object ID;
- impact, touch, blocking, arrival and action failure;
- immediate touch, proprioception and action receipts.

Nest does not participate in, approve or store in-progress state for these direct actions. Path planning still belongs to Godot; **whether pathfinding is needed is not the criterion for passing through Nest. Whether life-semantic resolution is needed is.**

### 5.2 Pure life-semantic queries: Elfie connects directly to Nest

~~~text
Elfie -> NestQuery
Elfie <- NestResult
~~~

Use this when the request only asks for information and does not immediately request physical execution, such as “Which bed is mine?” or “Is it quiet hours now?”

An action must not use the two-turn pattern “return an ID first, then send it to Brain to think again”. The three cases are fixed:

| Request | Path | Reason |
| --- | --- | --- |
| Information is the goal | Elfie -> Nest -> Elfie | The query itself is the purpose |
| Complete a behavior with a semantic target | Elfie -> Nest -> Godot -> Nest -> Elfie | Resolve, execute and associate the result within one intent |
| Target is known and no current rule check is needed | Elfie -> Godot -> Elfie | Do not add a hop for formal uniformity |

Do not send “my bed” directly to Godot: that would put resident ownership inside the physics engine. Do not split it into two Brain turns by default: that adds latency, model calls and intermediate state drift. The reliable default is the one-shot semantic action in the next section.

### 5.3 Semantic bodily behavior: resolve and execute in one request

When the target is described with life semantics such as “mine”, “available”, “the nearest suitable one” or “in the kitchen”, use one loop:

~~~text
Elfie -> Nest: SemanticBodyIntent(go_home)
Nest -> Nest: resolve Home and check rules
Nest -> Godot: ResolvedBodyCommand(actor_id, target_anchor_id, initiator=elfie)
Godot -> Godot: pathfinding and physical execution
Godot -> Nest: PhysicalActionResult
Nest -> Elfie: SemanticActionResult
Godot -> Elfie: immediate bodily perception produced during execution
~~~

This is one request and one execution receipt; Brain does not think again. Nest is the deterministic semantic-resolution and association boundary, not a behavior decision-maker: without the original Elfie intent ID, actor ID and authorization for this request, Nest must not create an Actor command. Nest also cannot change go_home into a different behavior.

| Permission | Sole owner | Meaning |
| --- | --- | --- |
| Behavioral intent | Elfie | Decides whether to go home, take a cup or use a facility |
| Life-semantic resolution | Nest | Resolves “my bed”, “common chair” and “available cup” into rule-constrained candidates |
| Physical candidate and execution | Godot | Determines existence, distance and reachability, then performs pathfinding and physical action |
| Association for this call | Nest | Associates resolution, execution and semantic result through the original intent ID |

Elfie -> Nest -> Godot -> Nest -> Elfie is a logical loop, not a demand that the internals make exactly one round trip. “Take the nearest available cup” may use several deterministic interactions within one intent: Nest filters rule-allowed candidates, Godot filters by current existence, distance and reachability, Nest confirms the target under the original constraint, and Godot executes. It still produces one final result and must not trigger another model cognition.

Examples:

- Return to one's bed, go to the kitchen or go to the activity area;
- find a currently permitted chair and sit down;
- find an available cup and perform the defined take action;
- use a facility whose ownership, reservation or sharing rules must be checked.

Nest chooses the semantic target and applies household rules. Godot handles pathfinding, continuous movement and physical grabbing/sitting. If the request contains an open cognitive choice such as “Whose cup should I take?”, Nest must not decide on its own; it must reject the request or ask Elfie for a clearer intent.

### 5.4 Structured virtual vision: do not render a camera for every Elfie

| Option | Advantage | Fatal problem | Decision |
| --- | --- | --- | --- |
| Render a camera screenshot for every Elfie and run visual understanding | Closest to open-ended image perception | Multiple Viewports, image transport and model inference are expensive and unstable | Not the MVP default |
| Nest stores “what is around every Elfie” | Convenient queries | Loses current orientation, occlusion and physical changes, and duplicates Godot's spatial authority | Reject |
| Godot computes visible entities and Nest adds life semantics | No pixels, still respects sight and occlusion, and keeps household semantics at the right boundary | Requires semantic entity annotations and a narrow assembly flow | **Adopt** |

The MVP does not create an independent Camera3D plus SubViewport for every Elfie, produce screenshots or call a vision model. Each actor needs only a non-rendering semantic “visual probe”: eye/head Transform, orientation, field of view and distance. Godot first narrows candidates by zone or spatial index, then queries occlusion with a view cone and RayCast/PhysicsDirectSpaceState to produce a VisibleSet:

~~~text
Godot: VisibleSet(actor_id, observation_id, visible_entities)
  -> Nest: add facility purpose, ownership, sharing rules and life names using stable semantic IDs
  -> Elfie: SemanticVisualScene
~~~

Each visible entity from Godot contains only necessary physical semantics, for example:

- semantic ID and entity kind;
- relative direction such as front/left/right and coarse near/mid/far distance;
- observable physical state such as a door being open, a chair being occupied or another Elfie moving;
- observation ID, occurrence time, world revision and Runtime generation.

Nest adds “this is my bed”, “this is a common chair” and “this is the kitchen entrance”, but **does not save or calculate the actor's surrounding list, sight, coordinates or occlusion**. VisibleSet is short-lived perception input, not Nest's long-lived world state.

This should be one batch association against Nest's in-memory semantic directory by semantic ID, not one database query per object and not a model call. Nest caches stable facility semantics rather than each Elfie's dynamic view, so many Elfies can reuse one directory without copying multiple “nearby world” lists.

Nest adds only semantics it owns. When another Elfie is visible, Nest may confirm that it is a current resident and provide the resident ID. “This is my friend” and “Do I trust it?” belong to the receiving Elfie's relationships and memory; Nest must not add them.

Vision is on-demand and event-driven: update when Elfie actively looks, enters a new area, changes orientation significantly or an important visible object changes. Send only changes or a bounded number of important entities, not every physics frame. This avoids duplicated rendering and image-understanding cost while preserving embodied constraints such as facing direction, occlusion by walls and changes after an object moves.

SemanticVisualScene enters the Nervous System as bodily perception and triggers a normal Embodied Turn. The Godot–Nest assembly does not trigger another cognition turn in either component, and Elfie does not receive a half-finished VisibleSet first.

The trade-off is that texture details, patterns and unexpected visual phenomena not annotated as semantic entities by the scene author will not be understood. If open-ended vision is later necessary, real screenshots/VLM can be an optional high-cost capability rather than the MVP default.

### 5.5 Virtual speech: close the content-and-spatial-propagation loop

~~~text
Speaking Elfie -> Nest -> Godot -> Nest -> listening Elfie
~~~

Speech is exceptional because it needs two authorities at once:

- Nest temporarily stores text, speaker, expressed emotion and event identity;
- Godot determines which bodies can hear from position, distance, walls and doors at the time of occurrence;
- Nest reconnects listener IDs with the original semantic content and delivers it.

Nest sends Godot a narrow SpeechOccurrence, not a reusable general Actor command that could move or manipulate a body. The speaking decision still belongs to the speaking Elfie. Godot may play a speech animation, but the permission Nest gains is limited to this utterance.

### 5.6 Environment rules and facts: a bidirectional Nest–Godot loop

~~~text
Godot -> EnvironmentFact -> Nest
~~~

This covers:

- an environmental object such as a chair or table moving or changing state in a way with life meaning;
- a door actually opening, closing or being blocked;
- the actual state of lights, environmental devices and common facilities;
- a change in facility occupancy.

Godot reports discrete semantic facts only; it does not stream coordinates, physics frames or continuous trajectories into Nest. Nest may store a semantic projection with revision and source, but the object's actual coordinates and physical state remain authoritative in Godot.

~~~text
Nest rule -> EnvironmentCommand -> Godot world object
Nest <- EnvironmentFact / CommandResult <- Godot
~~~

This covers:

- turning lights on or off at a specified life time;
- switching the presentation of day, night and quiet hours;
- locking or unlocking a common door under household rules;
- enabling, disabling or resetting a common facility.

Nest decides how the environment should be; Godot makes it physically so and reports the result. Only an explicit Elfie SemanticBodyIntent may resolve to an Actor command. Nest's own time or environment rules cannot change an Elfie into an Actor target. When Godot is offline, Nest keeps the current expected environment state; when a new generation is ready, it synchronizes the current state instead of replaying every expired animation.

### 5.7 In-Nest events and broadcast: the fact owner produces, the audience is delivered once

~~~text
Nest fact-owning module -> NestEvent -> life rules resolve audience when needed -> event router -> target Elfie
~~~

Rule broadcasts, targeted results and spatial hearing use the same event identity and idempotency mechanism, but their audience sources differ: life rules choose residents for a rule broadcast, a targeted result returns to the original requester, and spatial hearing is determined jointly from Godot physical candidates and life rules. Broadcast does not replace event classification and must not send raw Godot Runtime events directly to every body.

The seven paths above are routine business paths. Startup and recovery have a separate technical path: App starts the Godot authority, binds currently active virtual bodies and reconciles the Godot scene manifest with Nest's semantic projection. It establishes runtime relationships; it does not issue routine body commands on Elfie's behalf.

## 6. Nest's four first-level functional modules

### 6.1 Space and facilities

Answers: **Which places and environment objects exist in the Nest, and what do they mean in life semantics?**

Responsible for:

- Nest ID and current semantic-world revision;
- a coordinate-free semantic directory keyed by stable room, zone, anchor and object IDs published by the Godot scene Manifest;
- facility type, purpose, capability, availability and interaction mode;
- resolving life targets such as Home, activity area and common door into semantic targets Godot can recognize;
- batch-providing facility purpose and life names to Elfie–Nest interaction;
- receiving environment-object facts from Godot and storing the discrete projection actually needed by rules;
- resolving target objects or object groups for environment control.

Not responsible for:

- coordinates, dimensions, collision shapes, navigation paths or physics frames;
- tracking Elfie's step-by-step movement, current speed or bodily action;
- who owns a bed or may use a facility; those belong to in-Nest life rules;
- driving a character toward a facility; that always belongs to Elfie and Godot.

Space and facilities is not a file directory or a Python version of a 3D scene. It is the coordinate-free semantic view Nest uses when referring to environment objects. Physical object IDs are authored with the Godot scene and published through the Manifest; Nest uses those IDs to maintain meaning and does not create a second physical identity system.

### 6.2 In-Nest life rules

Answers: **Who lives here, how are life resources allocated, what behavior is allowed, and which residents should receive an in-Nest event?**

Responsible for:

- currently valid resident IDs and Nest semantic states such as arrival and departure;
- long-term resident-to-Home/bed assignment;
- ownership of private facilities and reservation, occupancy and release rules for shared facilities;
- permission, resource-availability and audience decisions for SemanticBodyIntent, virtual speech and Nest events;
- projecting long-term rules into mechanically enforceable Godot restrictions, such as a currently locked common door;
- producing rules-owned events such as a facility-access change;
- resolving rule-broadcast audiences such as all_residents, specified residents and affected residents;
- defining whether an environment rule allows an Elfie to override direct interaction, so Nest and Elfie do not repeatedly fight over object state.

Not responsible for:

- holding or creating real Elfie objects; Nest uses resident IDs only;
- independently initiating, rewriting, scheduling or recovering an Elfie body action without an explicit Elfie request;
- deciding whether a character hits a wall, how it walks or which coordinates it occupies;
- rebroadcasting ordinary physical changes as a second form of bodily perception;
- storing speech content, assembling vision or associating semantic-action results; these belong to Elfie–Nest interaction;
- owning the event queue, idempotency or actual delivery; these belong to the public event mechanism;
- digital chat, contacts or user-message history.

Life rules decide what is allowed and who is affected, but do not own events produced by other modules or carry low-level messages.

### 6.3 Time and environment

Answers: **Which life time and environment phase is the Nest in, and how should rules change the environment?**

Responsible for:

- continuous Nest time, pause, resume and time scale;
- life phases such as day, night and quiet hours;
- scheduled environment rules such as turning lights off at night and restoring them in the morning;
- Nest-level environment semantics and expected state;
- producing semantic Nest events for time boundaries and environment-phase changes;
- sending environment-object commands to Godot and receiving execution results;
- synchronizing the current environment phase and expected state after Runtime recovery.

Not responsible for:

- Elfie's energy, tiredness, emotion or circadian rhythm;
- ordering Elfie to return to bed, sleep or stop a current action;
- concrete rendering parameters for light brightness, sky materials, particles or sound effects;
- the Godot physics tick.

“Night began” may be an internal semantic trigger for Elfie, but “you must go to sleep now” can only be decided by Elfie's cognition and activity systems. Nest cannot control its body in Elfie's place.

### 6.4 Elfie–Nest interaction

Answers: **How can an Elfie use Nest's life semantics to perceive and participate correctly in the Godot virtual world?**

It owns three complete business loops:

- **Semantic vision:** receive Godot VisibleSet, batch-read facility, life-rule and necessary time/environment semantics, and form a SemanticVisualScene delivered only to the corresponding Elfie;
- **Virtual hearing:** temporarily store text, speaker, expressed emotion and utterance ID, ask Godot to calculate SpeechReach, and combine it with residents and propagation rules to form HeardUtterance;
- **Semantic action:** within the authorization of the original Elfie intent, resolve targets and rules such as “mine”, “common”, “available” and “in the kitchen”, invoke Godot for physical execution and associate one SemanticActionResult;
- store short-term association state for observations, utterances and semantic intents;
- validate Runtime generation, world revision and original request identity to guarantee idempotency, expiry isolation and one final result;
- pass completed structured perception and results to the public event mechanism, which delivers by Elfie ID to the real object.

Not responsible for:

- deciding on Elfie's behalf to look, speak or act;
- autonomously creating, scheduling or rewriting Elfie Actor commands;
- owning rooms, facilities, resident ownership or time/environment source facts; it only reads the other three modules;
- calculating coordinates, navigation, occlusion, distance, sound propagation or action success; those belong to Godot;
- holding real Elfie objects, the Godot connection or protocol frames.

This is a domain function, not a synonym for the current InteractionHub. The current InteractionHub mixes digital user messages, touch and collision with virtual speech. Migration must separate them: digital messages return to Communication, bodily touch goes directly to the corresponding Elfie, and only genuine in-Nest semantic interaction remains here.

The relationship between the four modules and the event mechanism is fixed:

~~~mermaid
flowchart LR
    F["Nest Facade"]
    S["Space and facilities<br/>objects and stable semantics"]
    R["In-Nest life rules<br/>ownership, permissions and audiences"]
    T["Time and environment<br/>phases and expected state"]
    I["Elfie–Nest interaction<br/>vision, hearing and semantic action"]
    EV["Public event mechanism<br/>identity, causality, idempotency and target delivery"]
    GP["Godot semantic Port"]

    F --> S
    F --> R
    F --> T
    F --> I
    I --> S
    I --> R
    I --> T
    S <--> GP
    R --> GP
    T <--> GP
    I <--> GP
    S --> EV
    R --> EV
    T --> EV
    I --> EV
    R -. "resolve event audiences when needed" .-> EV
    EV --> F
~~~

The first three modules own facts and rules. The fourth owns the semantic loop through which Elfie participates in the world. The public event mechanism only transports facts that already exist. They may share a Nest Facade and one injected Godot semantic Port, but no module imports a concrete Gateway.

## 7. In-Nest event and broadcast mechanism

The event mechanism crosses the four modules to express that an in-Nest fact has become true, but it is not a fifth business module. Each module produces only events it owns; the public mechanism standardizes event identity, causality, targets, idempotency and delivery:

~~~text
Fact-owning module produces NestEvent
    -> wrap event_id / cause_id / source / occurred_at / revision / generation
    -> life rules resolve the audience when needed
    -> event router delivers once by target Elfie ID
~~~

| Event source | Examples | How the audience is determined |
| --- | --- | --- |
| Space and facilities | FacilityStateChanged, FacilityUnavailable | Original requester, affected residents or rule-selected residents |
| In-Nest life rules | FacilityAccessChanged, ReservationChanged | Rules directly identify affected residents |
| Time and environment | QuietHoursStarted, EnvironmentPhaseChanged | Rules choose all or affected residents |
| Elfie–Nest interaction | HeardUtterance, SemanticVisualScene, SemanticActionResult | Godot physical candidates plus rule filtering, or the original requester |

Broadcast still exists, but it is only one audience scope of NestEvent: all_residents, a specified resident set or an affected resident set. “Produce the event”, “decide the audience” and “deliver it” must remain separate: the source module produces, life rules resolve rule-based audiences, and the public router delivers once to already-determined targets.

Virtual speech is not unconditional broadcast. Godot first supplies physically hearable candidates, life rules filter valid residents and propagation restrictions, and the interaction module associates the original content before producing targeted HeardUtterance events. SemanticVisualScene is also targeted perception, not broadcast.

The following must not be broadcast through Nest:

- action completion, movement failure or collision receipts;
- one body's touch, proprioception or raw Godot VisibleSet;
- raw physical perception such as a chair moving or lights changing;
- Runtime ready, disconnect or protocol frames.

Environment-object changes enter Nest to update the environmental projection required by rules. Nest must not then broadcast the same change as bodily perception to every Elfie. Touch and proprioception come directly from Godot; virtual vision is made visible by Godot and receives one semantic enrichment pass through Nest. Only when an environment fact creates a new life semantic or rule consequence may the fact-owning module produce a new NestEvent.

## 8. Godot's five functional capability areas

These five areas are a responsibility view of Godot, not a request to create five directories.

### 8.1 Scene and environment objects

- Rooms, walls, floors, doors, beds, chairs, lights and other furniture;
- geometry, coordinates, colliders, physics layers and spatial topology;
- stable Zone, Anchor and Object IDs;
- actual physical and interactable state of environment objects;
- semantic facts to Nest without NodePath and without unnecessary coordinates.

### 8.2 Virtual bodies and actions

- Create, synchronize, sleep and remove Elfie virtual bodies;
- appearance instances, collision shapes, pose, orientation and animation;
- execute explicit-target actions sent directly by Elfie and resolved semantic actions forwarded by Nest on Elfie's behalf;
- output accepted, started, completed, failed and cancelled;
- return meaningful touch and proprioceptive changes only to the corresponding body.

### 8.3 Physics, navigation and movement

- Navigation meshes, path queries, local avoidance and per-physics-frame movement;
- gravity, ground, slopes, collision, anti-penetration and contact data;
- arrival, unreachable, blocked, cancelled and timed-out outcomes;
- receive high-level body intent or semantic targets, never Python per-frame coordinate control.

### 8.4 Spatial queries

- Areas, distance, proximity, line of sight, occlusion and contact;
- speech reachability from a virtual speaker to each body;
- pixel-free VisibleSet from actor orientation, view range, distance and occlusion;
- reduce high-frequency spatial work to typed results;
- do not store speech text, interpret household ownership or decide how Elfie reacts.

### 8.5 Display and observation

- Scene rendering, lights, cameras, character animation, expressions and visible state;
- the read-only image needed by a human Observer;
- optional subtitles, TTS and 3D-audio presentation;
- presentation effects cannot be the sole proof that an action completed or an environment command succeeded.

## 9. What Godot provides and what ElfieNest must write

| Godot engine primitive | Project logic ElfieNest adds |
| --- | --- |
| SceneTree, Node3D, scene resources and Transform | Room composition, stable semantic IDs and scene/environment-object manifests |
| Renderer, Light3D, Camera3D, Viewport, materials and environment | Human Observer views and mapping environment state to lights/sky; virtual vision does not render pixels by default |
| PhysicsBody3D, collision shapes, collision detection and response | Collision-layer configuration, character movement scripts, meaningful-contact filtering and targeted events |
| CharacterBody3D and move_and_slide | Velocity and gravity, action progression, arrival, blocking, cancellation and receipts |
| NavigationServer3D, NavigationRegion and NavigationAgent | Navigation-data configuration, target selection, path-driven movement and failure conditions |
| AnimationPlayer/AnimationTree and the resource system | Mapping high-level actions and expressed emotion to existing animation resources |
| Area3D, RayCast3D and PhysicsDirectSpaceState3D | Composition of SpeechReach, VisibleSet, proximity, line of sight and meaningful object-change queries |
| AudioStreamPlayer3D | Optional human-audible presentation; it does not produce the Elfie listener list |
| WebSocketPeer | Protocol, authentication, generation, message types, routing, idempotency and recovery |

The basis for the engine capability boundary is the Godot stable documentation: [CharacterBody3D](https://docs.godotengine.org/en/stable/classes/class_characterbody3d.html), [3D navigation overview](https://docs.godotengine.org/en/stable/tutorials/navigation/navigation_introduction_3d.html), [AudioStreamPlayer3D](https://docs.godotengine.org/en/stable/classes/class_audiostreamplayer3d.html), [Area3D](https://docs.godotengine.org/en/stable/classes/class_area3d.html), [RayCast3D](https://docs.godotengine.org/en/stable/classes/class_raycast3d.html), [PhysicsDirectSpaceState3D](https://docs.godotengine.org/en/stable/classes/class_physicsdirectspacestate3d.html), [Viewport](https://docs.godotengine.org/en/stable/classes/class_viewport.html) and [WebSocketPeer](https://docs.godotengine.org/en/stable/classes/class_websocketpeer.html).

Godot therefore does not need a reimplementation of the physics engine, renderer, navigation algorithm or animation player. But the engine does not automatically understand “return to my bed”, “who heard this utterance”, “whether this collision is worth reporting” or “which household rule applies at 10 p.m.”

In particular:

1. CharacterBody3D is a script-driven character body; the project still writes movement, gravity and completion logic.
2. Navigation supplies pathfinding and avoidance primitives; project scripts still implement movement and business-level arrival conditions.
3. AudioStreamPlayer3D provides positional audio and distance attenuation for human listeners; it does not return the actor IDs the product needs.
4. Viewport is an additional rendering surface. A viewport for every Elfie plus pixel inspection introduces duplicate rendering and later image understanding; the MVP uses spatial queries to produce structured VisibleSet instead.
5. WebSocketPeer provides frame transport only; it does not provide Elfie/Nest/App semantic routing.

## 10. The Godot project needs only a small amount of custom code

Godot's five capability areas can converge on three core runtime code units, plus scene resources and the observation UI:

~~~text
godot_project/
├── rooms/                         scene resources and a few environment-object scripts
├── characters/                    virtual-body resources and shared body scripts
├── runtime/
│   ├── actor_controller.gd        direct body commands and resolved semantic body commands
│   ├── world_controller.gd        environment objects, VisibleSet and SpeechReach
│   └── websocket_client.gd        connection and protocol frames
└── ui/                            Observer and camera presentation
~~~

### 10.1 Actor Controller

Only:

- receive an explicit-target command sent directly by one Elfie, or a resolved command forwarded by Nest with the original Elfie intent;
- invoke body scripts, navigation and animation primitives;
- return a direct command's final receipt to Elfie; return a semantic command's physical result to Nest for association with the original request;
- always return touch and proprioception generated during execution directly to that Elfie;
- play one speech presentation already initiated by the speaking Elfie and associated by Nest.

It does not import Nest rules or broadcast Actor events to other bodies.

### 10.2 World Controller

Only:

- configure and publish scenes, Zones, Anchors and Object manifests;
- receive Nest environment-object commands;
- publish discrete environment-object facts;
- compose engine spatial queries to calculate SpeechReach and each actor's VisibleSet;
- retain Godot's physical authority over actual environment state.

It does not hold resident-to-Home relationships, interpret speech content or control ordinary Elfie actions.

### 10.3 Runtime Bridge

Only:

- WebSocket connection, authentication and protocol version;
- Runtime ID, generation, world revision and message identity;
- route by the six primary subjects actor / semantic_action / visual / environment / speech / runtime;
- timeout, reconnect, cancellation and idempotency.

It is a technical boundary, not a sixth world-function module, and it creates no business facts.

### 10.4 Environment-object scripts

Most static furniture needs no script. Only objects with independent state or interaction need narrow scripts, for example:

- light: receive on/off or an environment preset and report actual state;
- door: opening, closing, locking, blocking and completion state;
- movable chair: report a meaningful position/zone change;
- special common facility: enabled, disabled and occupied state.

Do not create a business class for every static piece of furniture or copy Nest residents and household rules into GDScript.

## 11. Seven semantic interfaces

| Interface | Direction | Content |
| --- | --- | --- |
| NestQuery | Elfie <-> Nest | Home, facility semantics, life rules, time and environment reads |
| DirectBodyChannel | Elfie <-> Godot | Known-target body commands, direct receipts, touch and proprioception |
| SemanticAction | Elfie -> Nest -> Godot -> Nest -> Elfie | Semantic target resolution, authorized physical execution and semantic result; immediate bodily perception still goes directly from Godot to Elfie |
| SemanticVision | Elfie -> Nest -> Godot -> Nest -> Elfie, or Godot -> Nest -> Elfie | Active observation or important change, VisibleSet, household-semantic enrichment and SemanticVisualScene |
| SpeechBridge | Elfie -> Nest -> Godot -> Nest -> target Elfie | Utterance association, SpeechReach and HeardUtterance |
| EnvironmentChannel | Nest <-> Godot | Environment-object commands, object facts and environment synchronization |
| RuntimeControl | App <-> Godot Bridge | Lifecycle, scene handshake, body binding, ready, generation, recovery and health |

Every event must be classified immediately when it enters the Gateway:

| Event type | Sole receiver | Examples |
| --- | --- | --- |
| DirectBodyReceipt | Elfie that initiated the direct command | turn completed, known-target move failed |
| SemanticPhysicalResult | Nest | go_home arrived or failed |
| BodyPerception | Elfie whose body sensed it | tactile contact, proprioceptive change |
| VisibleSet | Nest | entity IDs and physical state visible to one actor at that time |
| SemanticVisualScene | Corresponding Elfie | my bed ahead, common chair on the left |
| EnvironmentFact | Nest | chair moved, door opened, light off |
| SpeechReach | Nest | listener actor IDs for one utterance |
| NestEvent | Specified resident IDs | HeardUtterance, QuietHoursStarted |
| RuntimeEvent | App Lifecycle | ready, disconnect, generation changed |

There must be no default route such as send_to_all_bodies(event). Determine the event type and target ID first.

### 11.1 Rules and physical state of environment objects

Nest and Godot own different facts about an environment object:

- Nest owns rules and expected state, such as “the lights should be off during quiet hours” and “the common door is currently locked”;
- Godot owns actual physical state, such as “the light is off” and “the door is still blocked by an obstacle”.

Every environment command from Nest carries a rule revision; Godot returns the actual result. If Elfie interacts directly with an object:

- Godot mechanically executes or rejects according to the currently synchronized environment restriction;
- a direct action's DirectBodyReceipt returns to that Elfie; a semantic action's SemanticPhysicalResult returns to Nest, which associates the original intent;
- if the object state changes, emit a separate EnvironmentFact to Nest.

To keep rules and direct interaction from fighting forever, every environment rule must state one policy: manual override is forbidden, or manual override is allowed and the new actual state is accepted. Nest must not resend the opposite command indefinitely without an explicit policy.

## 12. Seven key flows

### 12.1 Explicit-target body action

~~~text
Elfie -> Godot: TurnLeft / Stop / MoveToAnchor(known_anchor_id)
Godot -> Elfie: DirectBodyReceipt
Godot -> Elfie: required TactileImpact / Proprioception
~~~

When no ownership, purpose or rule resolution is needed, it does not pass through Nest.

### 12.2 Return to one's bed: one semantic request, not two turns

~~~mermaid
sequenceDiagram
    participant E as Elfie
    participant N as Nest
    participant G as Godot

    E->>N: SemanticBodyIntent(go_home, intent_id)
    N->>N: resolve this resident's Home and current rules
    N->>G: ResolvedBodyCommand(actor_id, home_anchor_id, intent_id)
    G-->>N: accepted / started
    G->>G: pathfinding, movement and collision handling
    G-->>E: immediate bodily perception during execution
    G-->>N: PhysicalActionResult(completed / failed)
    N-->>E: SemanticActionResult(go_home, completed / failed)
~~~

Brain makes one decision: “go home”. Nest resolution, Godot pathfinding and result association are deterministic steps in the same execution cycle; the model is not called again so Elfie can rethink it.

### 12.3 Go to the kitchen or take an available cup

~~~text
Elfie -> Nest: SemanticBodyIntent(go_to="kitchen")
Nest -> Godot: MoveToAnchor(kitchen_entry)

Elfie -> Nest: SemanticBodyIntent(take="available_cup", constraints=...)
Nest: choose a concrete cup_id from facility semantics and life rules; query current physical candidates from Godot when needed
Nest -> Godot: InteractWith(cup_id)
Godot -> Nest: PhysicalActionResult
Nest -> Elfie: SemanticActionResult
~~~

If “nearest” depends on current distance, Godot supplies physical candidates or ordering. Nest decides “available”, “common” and “mine”. Nest does not solve a value choice for Elfie or grow into an open-ended planning system.

### 12.4 Structured virtual vision

~~~mermaid
sequenceDiagram
    participant E as Elfie
    participant N as Nest
    participant G as Godot

    opt Elfie actively looks
        E->>N: ObserveIntent(direction / focus)
        N->>G: SemanticViewQuery(actor_id, observation_id)
    end
    G->>G: query view range, distance, occlusion and physical state
    G-->>N: VisibleSet(actor_id, visible_entities)
    N->>N: add purpose, ownership, life names and availability
    N-->>E: SemanticVisualScene
~~~

Godot may also produce a constrained VisibleSet when an actor crosses a zone, turns significantly or an important visible object changes. In either case Nest does not preserve “what is always around this actor”; it processes this observation only.

### 12.5 Elfie moves a chair or hits a wall

~~~mermaid
sequenceDiagram
    participant E as Elfie
    participant G as Godot
    participant N as Nest

    E->>G: InteractWith(chair_id)
    G->>G: body physically interacts with chair
    G-->>E: DirectBodyReceipt / BodyContact
    G-->>N: EnvironmentObjectChanged(chair_id, semantic_state)
~~~

The body result and chair fact are two events under one cause, not duplicate delivery.

~~~text
Godot -> TactileImpact -> contacted Elfie
Godot -> DirectBodyReceipt(failed: movement_blocked) -> Elfie of the direct command
Godot -> SemanticPhysicalResult(failed: movement_blocked) -> Nest when the original command came from a semantic loop
~~~

An ordinary wall collision does not enter Nest. If the collision also moves an environment object, emit that object's EnvironmentFact separately.

### 12.6 Virtual speech and hearing

~~~mermaid
sequenceDiagram
    participant S as Speaking Elfie
    participant N as Nest
    participant G as Godot
    participant L as Listening Elfie

    S->>N: SpeakRequest(text, expressed_emotion, mode)
    N->>N: create and temporarily store Utterance
    N->>G: SpeechOccurrence(utterance_id, speaker_id, acoustic_profile, cue)
    G->>G: play speech presentation and calculate space at occurrence time
    G-->>N: SpeechReach(utterance_id, listener_actor_ids)
    N->>N: validate residents and generation; associate content idempotently
    N-->>L: HeardUtterance(text, expressed_emotion, speaker_id)
    N-->>S: SpeakResult
~~~

Godot does not need the text. Real TTS/3D audio is for human observation only and does not determine the listener list.

### 12.7 Turn the lights off on schedule

~~~mermaid
sequenceDiagram
    participant N as Nest time and environment
    participant G as Godot
    participant E as Elfie

    N->>N: quiet hours begin; form expected environment state
    N->>G: SetEnvironmentState(light_group, off, rule_revision)
    G->>G: change Light3D/environment presentation
    G-->>N: EnvironmentStateChanged(light_group, off)
    G-->>N: VisibleSet reflects observable light/environment changes
    N-->>E: SemanticVisualScene (only to Elfies actually in that environment)
~~~

The last line is targeted visual perception, not Nest broadcasting “it got dark” to every resident. An Elfie outside the perceptible area receives only a Nest rule event that actually applies to it; it is not told that it saw a light change.

## 13. State ownership and recovery

| State | Sole authority | Recovery rule |
| --- | --- | --- |
| Resident IDs, Home, facility ownership and life rules | Nest | Restore from the Nest Repository |
| Nest time, environment phase and expected environment state | Nest | Synchronize to the new Godot generation after recovery |
| Character coordinates, velocity, pose and body action | Godot / current Body Runtime | Nest does not persist them or treat an old projection as fact |
| Actual physical state of doors, lights and chairs | Godot | Confirm again from a new Runtime snapshot |
| Discrete environment projection needed by Nest | Source-tagged copy in Nest | Invalidate and rebuild after generation/revision changes |
| Utterance waiting for propagation | Nest short-term state | Interrupt on generation change; do not replay automatically |
| SemanticBodyIntent association | Nest short-term state | Keep intent ID; interrupt or reconcile across generations; never blindly replay |
| VisibleSet / SemanticVisualScene | Godot instantaneous fact / Nest instantaneous enrichment | Do not persist long-term; discard when stale and observe again |
| Direct body commands and receipts | Elfie Body + Godot | Do not enter Nest transaction recovery |
| Runtime generation and health | App Lifecycle | App reconciles and rebuilds the connection |

Nest does not store per-frame actor position, current speed or view lists. It stores short-term association only for explicit semantic behavior. Current area and visible entities must come from generation-tagged Godot facts and must not become a second physics authority.

## 14. Adversarial review record

| Scenario | Wrong design | Final treatment |
| --- | --- | --- |
| Elfie turns in place or blinks | Every action first passes through Nest | Explicit-target immediate actions use DirectBodyChannel directly |
| Elfie returns to bed | Ask Nest first, then make Brain think a second time to send a movement command | Resolve, execute and return the semantic result within one SemanticBodyIntent |
| Nest forwards a return-home command | Mistake forwarding for permission to control an actor autonomously | Command carries the original Elfie intent and authorization; Nest cannot create or rewrite one |
| Every pathfinding request goes through Nest | Mistake physical pathfinding for life semantics | Known anchors go directly to Godot; only target selection needs Nest |
| Every Elfie gets a Camera/Viewport | Duplicate screenshots and model cost | Godot spatial queries produce VisibleSet; Nest adds life semantics |
| Nest stores “what is around” directly | Stale second spatial authority cannot handle orientation and occlusion correctly | Nest processes one-shot VisibleSet and does not store dynamic views |
| Godot supplies complete semantic vision | Force Godot to understand “my bed” and “common facility” | Godot supplies physical visibility; Nest adds household semantics and targets the result |
| Elfie sits on a semantically available chair | Send it directly to Godot and force Godot to understand household rules | SemanticBodyIntent lets Nest select chair ID before Godot executes |
| Elfie hits a wall | Send touch into Nest before forwarding it | Send it only to the corresponding Elfie |
| Elfie pushes a chair | Deliver the same event once through Body and once through Nest | DirectBodyReceipt and ChairChanged are different facts with a shared cause ID |
| Virtual speech | Broadcast text through Body or simulate TTS/STT | Nest stores content, Godot computes SpeechReach, Nest targets delivery |
| Nest obtains a semantic-action entry point | Expand it into autonomous Actor control | Resolve only the original Elfie intent; time rules cannot produce Actor commands |
| Scheduled lights | Omit Nest -> Godot because Nest does not control bodies | Nest controls environment objects; Godot returns actual results |
| Light changes | Nest broadcasts “you saw it get darker” to all residents | Godot creates VisibleSet only for actual observers; Nest adds targeted semantics |
| Elfie opens a known door with no pending rule resolution | Route every action around Nest | Go directly to Godot; report the door-state change to Nest separately |
| Environment rules conflict with direct interaction | Nest and Elfie fight repeatedly over light or door state | Rules explicitly forbid override or allow it; no unqualified reverse resend |
| Raw Godot event | Default-send to all Bodies and Nest | Route once by actor/semantic_action/visual/environment/speech/runtime |
| Runtime reconnect | Old speech or environment commands cause side effects again | Isolate generations; resynchronize current environment state and do not replay old effects |
| Vision, hearing and semantic action are scattered | Put them separately into space/facilities and life rules, leaving multiple modules to own one loop's short-term state | Keep an independent Elfie–Nest interaction module for the three semantic–physical loops |
| Events disappear after module reshaping | Treat events as one module's property or broadcast every Runtime event | Each module produces its own facts; the public mechanism routes by type and target |
| Modules keep expanding | Make broadcast, residents, recovery and Gateway separate business modules | Broadcast is audience semantics; recovery and Gateway are technical capabilities, not new business modules |

Review conclusion: vision, hearing and semantic action share a common flow, independent short-term state and common constraints, so they converge into the fourth first-level module, Elfie–Nest interaction. Elfie -> Nest -> Godot -> Nest -> Elfie is not a speech-only path; it is the semantic–physical loop. Returning home, semantic object selection, active observation and speech share the coordination skeleton while keeping narrow request types; the loop must not become a general Nest body remote control. Events do not move into the fourth module; the public event mechanism carries facts produced by all four modules.

## 15. Main gaps against the current code

These are design gaps, not implementation tasks authorized by this document:

1. NestRuntimeEventRouter currently iterates several Runtime event classes to every Body transport and then sends speech and touch into Nest; it does not yet route uniquely by event subject.
2. Touch currently enters InteractionHub, while the target design sends bodily touch only to the corresponding Elfie.
3. InteractionHub currently mixes virtual speech, user messages, collision and touch; digital messages and bodily events must not belong to Nest.
4. Godot actor_controller.gd currently carries text in speech commands and approximates listeners by “same nearest Zone”; the target is utterance ID plus distance/walls/doors through SpeechReach.
5. Speech events currently also broadcast to every Body transport before Nest delivers them, creating duplicate or wrong receivers.
6. The current touch conversion changes event identity, and Python guesses Newton values from normalized intensity, breaking physical authority.
7. NativeSensors does not yet truly receive directed bodily sensation from Godot.
8. Nest currently stores posture and Runtime actor mirrors as body projections; the boundary needs to contract to the smallest read-only, generation-tagged projection actually required by rules.
9. WorldRuntimePort currently carries world configuration, actor synchronization and event draining together; Body, SemanticAction, Visual, Environment, Speech and Runtime routes are not explicit.
10. Godot does not yet have a unified semantic command and EnvironmentFact path for lights, doors, chairs and other environment objects.
11. Most furniture is static scene content; doors, lights and movable facilities still lack narrow state scripts and stable object IDs.
12. Nest time currently advances only elapsed seconds; it has no life phases, scheduled environment rules or environment-state synchronization.
13. The actor catalog carries a Home anchor and Godot actors store Home metadata; the target puts Home in Nest, leaving Godot to execute a resolved semantic target or initial spawn configuration.
14. The message model does not route primarily by actor / semantic_action / visual / environment / speech / runtime, and lacks environment commands, environment facts and stable correlation for multiple facts from one cause.
15. The semantic boundary between movement_blocked and a terminal action is unclear; touch and command failure may share a cause ID, but the same failure result must not be delivered as two event types.
16. VisionSensor still uses a Godot Camera3D screenshot path and filename guesses for objects; this is neither real vision nor the target structured vision. Replace it with VisibleSet -> SemanticVisualScene.
17. Godot cannot yet generate VisibleSet from actor orientation, distance and occlusion, and Nest lacks a vision boundary that performs only instantaneous semantic enrichment.
18. The one-shot deterministic loop SemanticBodyIntent -> ResolvedBodyCommand -> SemanticActionResult is missing; Home semantics and physical action are not yet connected by this rule.
19. nest/events.py currently has only a few domain value objects; it lacks a unified event identity, cause ID, audience scope, generation, idempotency and targeted-delivery contract for the public mechanism.
20. nest/state + engine + interaction is a historical implementation structure, not the ownership model of this design's four modules. Migration must first define narrow contracts and acceptance scenarios, then shrink old responsibilities through complete feature slices; do not create empty directories or mechanically rename code merely to match the diagram.

## 16. Final invariants

1. Nest always has exactly four first-level functional modules: space and facilities, in-Nest life rules, time and environment, and Elfie–Nest interaction. The public event mechanism crosses them but is not a fifth business module.
2. Elfie is the sole initiator of intent for its own bodily behavior. Nest may resolve and forward only within that intent's authorization and cannot control the body autonomously.
3. Pure physical behavior with an explicit target goes directly to Godot. Behavior requiring ownership, purpose, an available object or household-rule resolution uses the semantic–physical loop.
4. Nest resolution and Godot execution are one action cycle; Brain must not be forced to think again.
5. Pathfinding always belongs to Godot. The need for pathfinding does not decide whether Nest is involved; the need for life-semantic resolution does.
6. Virtual vision defaults to Godot VisibleSet -> Nest semantic enrichment -> Elfie; do not default to a per-actor camera, screenshot or VLM.
7. Nest does not store dynamic views or surrounding lists; Godot does not interpret household semantics such as “my bed”.
8. Nest may autonomously control environment objects and environment phases, but environment rules must not autonomously create Elfie Actor commands.
9. Godot owns actual physical state of bodies and environment; Nest owns life rules and expected environment state.
10. Each module produces only events it owns. Life rules resolve audiences when needed, and the event router delivers once, directly and idempotently; broadcast is only one audience scope of NestEvent.
11. One semantic event has one delivery path. Different facts from one physical cause are correlated by cause ID.
12. Touch and proprioception go directly to the corresponding Elfie. VisibleSet and SpeechReach go to Nest for targeted association. Environment facts go to Nest; Runtime events go to App.
13. An environment fact entering Nest does not mean Nest rebroadcasts it as bodily perception.
14. Nest does not duplicate coordinates, navigation, collision or physics frames; Godot does not store resident ownership, household rules or speech content.
15. Godot capability areas do not equal project module count. Prefer engine primitives and write only the semantic glue and state scripts required.
16. App only assembles and manages lifecycle; it is not the business bus for routine actions, environment facts, vision or speech delivery.
17. Current implementation gaps must be resolved as independent feature slices; this design is not permission for a one-shot rewrite of the entire Runtime.
