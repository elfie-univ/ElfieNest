# Nest–Godot semantic-world migration specification

**Status:** active temporary conformance specification
**Adopted:** 2026-08-13
**Governing target:** [Nest–Godot semantic-world contract](../contracts/nest-godot-semantic-world)
**Gap register:** [Nest–Godot semantic-world conformance](./nest-godot-semantic-world)

This document is the approved execution order for moving the current Nest and
Godot implementation toward the governing contract. It is normative for the
migration but temporary: after all cards and all `NGW-*` gaps are closed, this
document and its Chinese mirror are deleted in the final governance-only
closure.

It does not claim that the target behavior already exists and does not
authorize a broad rewrite. Each card is a separately reviewable product change.

## 1. Non-negotiable execution rules

1. **One active migration card.** Cards execute in the order below. A later
   card cannot absorb unfinished work from an earlier card merely because the
   same file is convenient to edit.
2. **One complete vertical slice.** A card migrates the real producer, typed
   boundary, consumer, Bootstrap wiring and focused tests together. A new type
   or empty package alone is not progress.
3. **No compatibility architecture.** Do not add protocol dual parsing, dual
   delivery, dual reads/writes, fallback paths, legacy aliases or a second
   world projection. Update the bundled callers and both protocol endpoints in
   the same card, then delete the replaced path.
4. **One fact, one owner, one route.** Distinct facts caused by one occurrence
   have distinct event IDs and types and may share a `cause_id`. The same fact
   must never reach an Elfie through both Body and Nest.
5. **Keep `main` usable.** Every product card must leave the selected Runtime
   generation startable and the migrated path functional. Temporary broken
   intermediate architecture cannot be merged.
6. **Behavior before structure.** A Nest or Godot directory is created only in
   the card that gives it real state or behavior. Final mechanical moves do not
   change behavior.
7. **Test the boundary, not only transport.** Every card proves its positive
   route, forbidden cross-routes, target identity, stale-generation behavior
   where applicable, and removal of the replaced production caller.
8. **Close only proven gaps.** An `NGW-*` row is closed only when all parts of
   its closure gate are true in current code. Partial work remains open.
9. **Stop on a target change.** If implementation reveals that authority,
   dependency direction, lifecycle ownership or a system-level Port meaning
   must change, stop the card and approve a separate bilingual ADR/contract
   governance change first.
10. **Separate governance from product migration.** Product cards may update
    focused tests and current conformance status, but contract/ADR/scanner rule
    changes and final conformance deletion remain separate governance changes.

## 2. Invariants every card must preserve

- One running ElfieNest has one Nest and one authoritative Godot Runtime
  generation.
- Elfie is the only originator of its Actor body intent. Nest may resolve and
  forward a target inside that intent; it cannot create, schedule, resume or
  rewrite Actor behavior.
- Nest may independently command environment objects when enforcing household
  or time/environment rules.
- Godot owns physical IDs, scene geometry, coordinates, movement, pathfinding,
  collision, visibility, audibility and actual execution.
- Nest owns household meaning and stores resident IDs, never real Elfie
  instances. App Orchestration alone maps resident IDs to real Elfies.
- Python commands and events expose stable semantic IDs, not NodePath,
  coordinates, collision shapes or copied navigation state.
- One authenticated Gateway may implement several consumer-owned narrow Ports;
  a shared connection does not merge semantic lanes.
- Runtime lifecycle facts go only to App Lifecycle. Direct body facts go only
  to the owning Body. Nest semantic facts go only to the relevant Nest owner.
- Source Runtime ID, generation and world revision bound every retained
  physical projection; stale input is rejected and never silently relabelled.
- Retries preserve request/event identity. Physical side effects are not
  replayed merely because a new Runtime generation starts.

## 3. Required event classification

The shared Gateway must classify a validated frame before delivery:

| Fact family | Destination | Examples | Forbidden route |
| --- | --- | --- | --- |
| Runtime lifecycle | App Lifecycle | connected, ready, health, generation, disconnected | Nest events or every Body |
| Direct Body | owning Body transport/sensors | command receipt, tactile, proprioceptive or locomotion input | Nest broadcast or an App loop over all Elfies |
| Nest physical input | one typed Nest Port | manifest, `VisibleSet`, speech reach candidates, environment fact/result | raw delivery to an Elfie |
| Nest semantic event | explicit resident IDs through App delivery | `HeardUtterance`, `SemanticVisualScene`, `SemanticActionResult` | default broadcast or direct Body replay |
| Observer projection | authorized App Observer read model | actor pose/zone needed for display | durable Nest resident state |

`world_ready` must not continue to mean both process readiness and semantic
world configuration. Runtime readiness belongs to Lifecycle; a validated scene
manifest or world-configuration result belongs to the Nest/world session.

## 4. Target ownership layout

The following is the target responsibility layout, not permission to create
empty packages. Each path appears only when its migration card supplies real
behavior.

```text
nest/
  nest.py                     stable aggregate facade
  space/                      semantic catalogue and facility projections
  rules/                      residents, Home, access, sharing and audience policy
  time_environment/           clock, life phases and desired environment state
  interaction/                speech, vision and semantic-action correlation
  events.py                   common typed Nest event envelope/outbox mechanism
```

Owner-specific repository and Godot capability Ports stay with the consumer
owner. The common event mechanism is shared plumbing, not a fifth business
module. Small cohesive code may remain in one file; the names above do not
justify splitting every model into a service/repository package.

The final Godot source layout is:

```text
godot_project/
  main.gd                         assembly only
  characters/shared/elfie_actor.gd
  rooms/                          geometry and authored scene assets
  runtime/
    endpoint/
      websocket_client.gd
      authority_endpoint.gd
      event_envelope.gd
    actor/
      actor_controller.gd
      actor_catalog.gd
      actor_path_planner.gd
      actor_animation_runtime.gd
      actor_appearance.gd
    world/
      world_controller.gd
      semantic_scene_index.gd
      spatial_queries.gd
      environment_controller.gd
      objects/                    only real stateful object scripts
    observer/
      observer_presentation.gd
      nest_camera_controller.gd
    lab/
      lab_runtime.gd
```

This layout is reached incrementally. `main.gd` and room scripts are extracted
as the corresponding behavior migrates; there is no one-shot move followed by
functional changes hidden inside a directory cleanup.

## 5. Data decision gate

`DATA-01` must be resolved before `NG-M04` begins:

- **Development/default:** back up if useful, then rebuild development Nest
  data under the new schema.
- **Explicit real-data preservation:** obtain separate user approval for one
  offline, one-shot conversion with a backup, exact source/target counts and a
  rollback point.

Neither choice permits runtime dual reads, dual writes, fallback repositories
or indefinite `bed_number` compatibility. No product card may delete or rewrite
real `${ELFIE_HOME:-~/.elfienest}` data without that explicit approval.

## 6. Ordered migration cards

| Card | Depends on | Status | Primary gap outcome |
| --- | --- | --- | --- |
| `NG-M01` | governance baseline | open | close `NGW-002`, `NGW-003` |
| `NG-M02` | `NG-M01` | open | establish Space and Facilities; partial `NGW-001/008/009` |
| `NG-M03` | `NG-M02` | open | establish Household Living Rules and Home authority; partial `NGW-001/008` |
| `NG-M04` | `NG-M03`, `DATA-01` | open | cut over Nest persistence; partial `NGW-001/008` |
| `NG-M05` | `NG-M04` | open | establish Time and Environment; partial `NGW-001/007` |
| `NG-M06` | `NG-M01` | open | remove user-message ownership from Nest; partial `NGW-001` |
| `NG-M07` | `NG-M02`, `NG-M03`, `NG-M06` | open | close `NGW-008`, `NGW-009` |
| `NG-M08` | `NG-M01`, `NG-M03`, `NG-M06`, `NG-M07` | open | establish Interaction/events and close `NGW-004` |
| `NG-M09` | `NG-M08` | open | close `NGW-005` |
| `NG-M10` | `NG-M03`, `NG-M07`, `NG-M08` | open | first semantic action; partial `NGW-006` |
| `NG-M11` | `NG-M10` | open | close `NGW-006` |
| `NG-M12` | `NG-M05`, `NG-M07`, `NG-M08` | open | close `NGW-007` |
| `NG-M13` | `NG-M08`–`NG-M12` | open | close `NGW-010` |
| `NG-M14` | `NG-M13` | open | close `NGW-001` and finish structural cleanup |
| `NG-M15` | all `NGW-*` closed | open | governance-only conformance removal |

### NG-M01 — Protocol identity, classified ingress and direct Body input

**Goal:** remove fan-out-first routing and make the existing direct Body path
real before adding new semantic features.

- Replace protocol v2 with one clean protocol v3 cutover across Python and
  Godot. The envelope identifies protocol version, frame/event type, message or
  event ID, optional `cause_id`, semantic lane, actor/target, Runtime
  generation, world revision and occurrence time where applicable.
- The Gateway validates and classifies before delivery. It registers targeted
  Body sinks/transports; App Orchestration must not loop through every Elfie to
  offer each Runtime event to every Body.
- Queue typed tactile/proprioceptive/body input in `NativeSensors`. Preserve
  source event/cause identity and real physical values. If Godot cannot provide
  a force, represent it as unknown; never derive fake Newtons from intensity.
- Keep current speech reach input on the Nest semantic route until `NG-M08`, but
  do not send it through Body first.
- Separate Runtime readiness/health/generation from world-configured/manifest
  results.
- Delete Nest collision/tactile compatibility entry points, fake-force logic,
  fan-out routing and all protocol-v2 parsing in this same card.

**Evidence:** focused protocol round trips; one actor receives its receipt and
body input; another actor and Nest receive none; stale generation is rejected;
speech reach goes to only the Nest input; Lifecycle alone receives readiness;
source scans show no v2 parser, all-Body loop or fabricated force.

### NG-M02 — Space and Facilities

**Goal:** make the first Nest owner responsible for household meaning of Godot
physical referents without copying the physical world.

- Extract the coordinate-free semantic catalogue from broad `NestState` and
  expose typed Nest facade use-cases for rooms, zones, anchors, facilities and
  capabilities.
- Accept only Godot-authored stable IDs and a validated manifest revision.
  Store facility purpose/capability and only the discrete environment
  projection required by rules.
- Reject coordinates, NodePath, navigation data, per-frame actor state and
  persisted per-Elfie surroundings.
- Remove broad actor posture/active-command mirrors from Nest consumers. Any
  display-only actor projection is marked for the Observer route completed in
  `NG-M07`.

**Evidence:** catalogue queries contain no geometry; an unknown/revised physical
ID is handled explicitly; generation/revision invalidates the minimum physical
projection; existing callers use the facade rather than mutable state.

### NG-M03 — Household Living Rules and Home authority

**Goal:** put resident and Home decisions behind Nest instead of App SQL or
Godot metadata.

- Establish resident-ID, full `home_anchor_id`, ownership, sharing,
  reservation, occupancy, access and audience-policy behavior behind the Nest
  facade.
- App authenticates/authorizes the household administrator, then calls the
  Nest use-case. App does not calculate bed IDs or decide Home rules.
- Migrate every management and runtime caller away from direct `bed_number`
  SQL assumptions and fabricated values such as `bed-01`.
- A Home is a Nest rule fact. A resolved physical spawn/action target may be
  passed to Godot, but it must not be named or persisted there as Home.

**Evidence:** rule tests cover assignment conflicts and access; API/use-case
tests prove App authorization followed by Nest decision; repository/SQL reads
cannot bypass the Nest use-case; no production caller fabricates Home IDs.

### NG-M04 — Nest persistence cutover

**Goal:** durably restore the state owned by `NG-M02` and `NG-M03` through
owner-defined Ports with exactly one storage path.

- Resolve `DATA-01` first. Define owner-shaped repository operations and a
  schema that stores full stable physical IDs and Nest rule state without
  coordinate arithmetic.
- Update the SQLite adapter and all production composition in one cutover.
  Remove the four-beds-per-dorm calculation, `bed_number` authority and old
  broad state repository path.
- Do not persist short-lived speech/vision/action correlation, direct Body
  state or general Godot actor snapshots.

**Evidence:** restore round trip for catalogue/rules/Home; failure and restart
tests; exact data decision evidence; source scans prove one repository binding
and no old read/write path.

### NG-M05 — Time and Environment domain

**Goal:** turn the current elapsed-seconds engine into Nest-owned time, phase
and desired-environment behavior without yet pretending Godot object control
exists.

- Move clock, pause/scale and life-phase calculation behind Time and
  Environment use-cases.
- Model scheduled household environment rules and the current desired state as
  Nest facts. Individual sleep/energy choices remain Elfie facts.
- Persist only the durable clock/policy/desired state needed across restart.
- Do not create Godot object scripts or an empty environment Gateway here;
  actual command/fact synchronization arrives in `NG-M12`.

**Evidence:** deterministic clock/phase/policy tests, pause/scale behavior and
restart restoration; no physics-tick, Actor-command or rendering dependency in
Nest.

### NG-M06 — User-message ownership cleanup

**Goal:** remove the non-world communication responsibility currently hidden
inside Nest before deleting `InteractionHub`.

- Route user chat through App `message_delivery` and Elfie Communication, with
  existing authorization, history and receipt ownership.
- Remove `Nest.receive_user_message`, user-message queues and related
  `InteractionHub` state after all production callers move.
- Do not turn user messages into Nest broadcasts or Godot events.

**Evidence:** a real chat use-case reaches only the selected Elfie and records
its normal receipt/history; Nest has no user-message API, queue or persisted
copy.

### NG-M07 — Godot semantic scene and physical projections

**Goal:** give later speech, vision, action and environment cards one stable
physical vocabulary while removing household meaning from Godot.

- Author stable room/zone/anchor/object IDs in scenes/builders and index them in
  `semantic_scene_index.gd`. Publish a revisioned, geometry-free semantic
  manifest.
- Remove `home_anchor_id` from the Godot actor catalogue. New actor creation may
  receive a resolved `spawn_anchor_id`; Godot never retains why that anchor is
  the resident's Home.
- Move display-only actor pose/zone/current-command projections to the
  Observer route. Nest retains only explicitly listed discrete physical state
  needed by rules.
- Begin extracting endpoint, actor, world and observer responsibilities from
  `main.gd` and room scripts as those behaviors move. Reuse Godot physics,
  navigation, animation and query APIs rather than wrapping each engine class.
- Add narrow scripts only for objects with real state or interaction. Static
  furniture needs semantic metadata, not a script per object.

**Evidence:** manifest IDs are stable across reload; no NodePath/coordinate
leak; no Godot Home field; Observer and Nest projections are distinct; existing
movement/navigation behavior remains functional.

### NG-M08 — Virtual speech/hearing and common Nest events

**Goal:** implement the first complete Elfie–Nest–Godot semantic interaction
and introduce event plumbing only because a real `HeardUtterance` uses it.

- Add an Elfie-owned virtual-world participation Port. App Orchestration
  implements the cross-authority coordinator; Elfie does not import Nest.
  Physical embodiments may retain a distinct direct `SpeechCommand` capability
  and are not a compatibility fallback for virtual speech.
- A virtual speech intent carries utterance identity, text and explicit
  expressed emotion. Nest retains content; Godot receives only occurrence ID,
  speaker ID and bounded acoustic/propagation parameters.
- Godot computes physically reachable listener candidates. Nest rules resolve
  the final resident audience, then the common event mechanism emits one
  idempotent targeted `HeardUtterance` per listener. App maps IDs to real
  Elfies.
- Introduce the typed Nest event envelope/outbox with event owner, event ID,
  cause/origin ID, target IDs, occurrence time and Runtime provenance.
- Delete the old same-zone/text-through-Godot speech path. Delete
  `InteractionHub` only now, after tactile (`NG-M01`), user messages (`NG-M06`)
  and speech have all moved.

**Evidence:** occluded/out-of-range/resident-policy cases; text and expressed
emotion never enter Godot frames; speaker and non-listener do not receive a
duplicate; retry preserves identity; one listener gets one semantic event;
`InteractionHub` no longer exists.

### NG-M09 — Structured semantic vision

**Goal:** provide efficient actor-relative vision without per-Elfie rendered
cameras or screenshot inference.

- Add an observation intent/ID through the Elfie participation Port. Nest
  creates short-lived correlation and asks a narrow vision Port.
- Godot computes a bounded `VisibleSet` using actor transform, field of view,
  range, occlusion and current physical state, returning stable IDs only.
- Nest batch-joins facility/rule meaning and emits one targeted
  `SemanticVisualScene`. It does not persist a surrounding-object list.
- A bounded significant-change report may use the same typed path, but it is
  not a default per-frame stream.

**Evidence:** target, occlusion, bounds, stale observation and generation tests;
no Viewport-per-Elfie, screenshot/VLM input, coordinate leakage or unbounded
per-frame event production.

### NG-M10 — First semantic action: go Home

**Goal:** prove the one-intent cycle with the smallest household-semantic action.

- Add a typed semantic-action intent distinct from free-string direct motion.
  It preserves intent, actor and authorization identity through Elfie → App
  coordinator → Nest.
- Nest resolves `my Home` and rule permission once, then sends a resolved stable
  target under the same intent to Godot. Godot performs pathfinding/execution
  and returns a typed physical terminal result.
- Nest correlates that result and emits one `SemanticActionResult`; no second
  Brain Turn is required merely to look up and then execute the target.
- Nest cannot initiate this Actor action itself. Direct known-target motion
  remains on the direct Body channel.

**Evidence:** success, no Home, forbidden, unreachable, interrupted and stale
generation scenarios; one intent/one terminal result; no duplicate Body/Nest
result and no Nest-created Actor command.

### NG-M11 — General semantic actions

**Goal:** generalize the proven cycle without building a universal string
command interpreter.

- Add typed resolvers/executors only for approved meanings such as a named
  facility, shared/available object or allowed destination.
- Separate semantic target resolution (Nest) from physical path/action
  execution (Godot). Capability and policy failures are domain results, not
  arbitrary transport errors.
- Define cancellation, timeout, idempotency and terminal-result rules for every
  added action kind.

**Evidence:** a second non-Home action proves reuse; malformed/unapproved action
kinds are rejected; direct Body motion still bypasses Nest; `NGW-006` closes
only after the generic contract has no special Home-only shortcut.

### NG-M12 — Environment objects, schedules and recovery

**Goal:** complete Nest-controlled environment behavior without granting Nest
Actor control.

- Add a Time/Environment-owned narrow Port for desired object state. Godot
  `environment_controller.gd` maps commands to real stateful objects and
  returns actual discrete facts/results.
- Implement only required object scripts, beginning with one real end-to-end
  capability such as a light group. Add doors or movable facilities only when
  their product behavior is approved.
- Convert actual environment changes into Space/Facilities projections and
  owner-created Nest events where needed. Audience policy is applied only when
  a resident event is required.
- On a new Runtime generation, resynchronize current desired state. Do not
  replay expired speech, animation or physical side effects.
- Keep environment commands separate from Actor commands; a schedule may turn
  off a light but cannot decide that an Elfie should walk or sleep.

**Evidence:** desired-versus-actual result, manual override/policy, failure,
restart and stale-fact tests; one stateful object works end to end; no Actor
command is emitted by Nest time rules.

### NG-M13 — Narrow capability and Bootstrap closure

**Goal:** delete the remaining broad `WorldRuntimePort`/generic protocol surface
after real narrow capabilities exist.

- Each consumer owns only the capability it needs: direct Body transport,
  semantic action, vision, speech reachability, environment and Runtime
  lifecycle/control.
- One concrete Godot Gateway may implement all those Ports, and Bootstrap may
  instantiate it once and inject typed views. Concrete Godot adapters do not
  construct one another.
- Delete broad world/session methods, arbitrary-dictionary payloads and old
  Bootstrap aliases after every production caller migrates.

**Evidence:** dependency/Bootstrap tests prove one Gateway and no second
authority; each consumer can be tested with its narrow fake; source scans find
no broad Port or legacy binding; `NGW-010` closes.

### NG-M14 — Final Nest/Godot structural cleanup

**Goal:** make physical structure match the now-real ownership without changing
observable behavior.

- Finish moving remaining broad `NestState`, engine and interaction code into
  the four implemented owners and keep `Nest` as the stable facade.
- Finish the Godot layout shown above. `main.gd` is assembly/dispatch only;
  endpoint, Actor, world, observer and lab code no longer share broad scripts.
- Delete dead models, imports, adapters and tests from replaced paths. Do not
  add wrappers solely to preserve old imports.
- Verify public developer architecture pages describe current implementation
  only after the structure is real.

**Evidence:** all four Nest owners contain real behavior, the common event
mechanism is not a business owner, no forbidden responsibility remains in
Nest, focused architecture tests pass and `NGW-001` closes.

### NG-M15 — Governance-only closure

**Goal:** remove temporary migration machinery after, never before, the product
matches the permanent contract.

- Confirm every `NGW-*` row is closed with current evidence and no temporary
  baseline remains.
- In one governance-only change, delete both conformance documents and Chinese
  mirrors, their registry entries, index links, temporary Agent migration
  references and conformance-specific test assertions.
- Keep the permanent contract, ADR, deny-all scanner and permanent authority
  tests.

**Evidence:** registry/governance/system architecture tests pass with no
Nest–Godot conformance registration; the change contains no product source.

## 7. Per-card review and completion template

Every product migration review must answer all of the following:

1. Which card and exact `NGW-*` gate is in scope? Which adjacent work is
   explicitly out of scope?
2. Who owns every changed fact before and after the card?
3. What is the single production route, and which old route is deleted?
4. How are actor/target, request/event/cause identity, generation and revision
   preserved?
5. What happens on retry, timeout, cancellation, disconnect and stale input?
6. Does any Python state duplicate Godot geometry or dynamic physical state?
7. Does Nest gain any ability to originate Actor behavior?
8. Are real Elfie objects kept out of Nest and resolved only by App?
9. Are positive behavior, negative cross-route and recovery cases tested?
10. Is the changed data path covered by `DATA-01`, with no dual storage?
11. Are all production callers migrated and the replaced code physically
    deleted?
12. Is the current conformance row updated honestly without changing the target
    contract to match unfinished code?

A card is complete only when these answers are evidenced by the current diff
and focused tests. A written type, folder diagram or passing WebSocket test by
itself is insufficient.
