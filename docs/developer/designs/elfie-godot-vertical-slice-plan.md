# Elfie Godot Virtual-Body End-to-End Execution Plan

> Status: execution plan based on frozen embodied-control-chain v1
> Scope: one Elfie, one Godot Runtime, and one virtual body; physical devices are out of scope.

## 1. First-version acceptance target

The first version must prove a complete loop, not only that Godot can move:

```text
Brain ControlCall
  → capability-directory dispatch
  → NervousSystem → Body / BodyPort
  → Godot Body Adapter → Transport / Gateway
  → Actor execution and animation
  → terminal embodied outcome + semantic vision/hearing/touch/proprioception
  → Body → NervousSystem → EventWorkspace
  → later Brain Turn
```

The target Runtime may emit `accepted`, `started` and a terminal receipt, but
these are one action lifecycle, not three Brain Turns. The full lifecycle stays
in the action ledger; Brain receives only one external `Embodied` terminal
outcome per command. EventWorkspace coalesces it with body facts from the same
causal window and produces at most one later Brain Turn. `Activity` is reserved
for Brain-owned extra work, not action receipts.

It must prove that:

1. Brain emits one or more precise structured capability calls; prose cannot control the body.
2. A registered movement capability moves the virtual Actor through Godot pathfinding and returns
   `accepted → started → one terminal status`.
3. After an Elfie speaks, Godot computes the audience from range, zone and occlusion; Nest
   delivers the event only to matching Elfies through each target Elfie's Body input boundary,
   never as raw Runtime frames.
4. A visual request returns semantic IDs only; Nest resolves them into a structured scene and
   delivers it through the observer Elfie's Body input boundary, so Brain receives what is around
   it without receiving Godot image frames.
5. Actor collision/touch, action terminal state and current-body state enter the next Brain
   perception cycle.
6. The Brain control Turn completes after producing the structured call. Version one may wait for the target
   terminal result inside an isolated output worker; that wait cannot block transport or sensor ingress. The later
   terminal outcome and perception facts form one later Embodied Turn, while Activity remains separate.

The first-version perception set is semantic hearing, semantic vision, touch/collision,
action receipts, and body state such as zone and posture. Raw microphone audio, raw camera
images, full ambient-sound recognition and open-ended navigation are deferred.

## 2. Current chain and assets to preserve

| Responsibility | Existing owner | Preserve |
| --- | --- | --- |
| Brain decision | `elfie/brain/reasoning/` | `DecisionPlan`, Turns, EventWorkspace and the existing chat path |
| Body binding | `elfie/body/` + `app/orchestration/embodiment/` | `BodyPort`, `BodyBinding`, generations and stale-body rules |
| Body safety/normalization | `elfie/nervous_system/` | limits, reflexes, BodySensorEvent normalization and perception delivery |
| Godot host | `infrastructure/godot/` | Gateway, Session, `GodotTransport`, `NativeBody` and sensor mapping |
| World semantics | `nest/` + `app/orchestration/nest_session/` | home/anchor resolution, speech reach, semantic vision, environment and event routing |
| Godot authority | `godot_project/runtime/` | Actor, NavigationAgent, pathfinding, collision, animation and scene queries |

Do not create a second Brain-to-Godot path or copy geometry, paths, collision or rendering into Python.

## 3. Target-to-existing-owner gaps

| Target responsibility | Existing path | Smallest in-place change | Acceptance evidence |
| --- | --- | --- | --- |
| Structured control call | `EffectiveCapabilityProjection`, `DecisionPlan`, `NervousSystemIntentExecutor` | Use a generic category plus dynamically registered `capability_id + typed args`; route below Brain | prose and unregistered capabilities cannot form a BodyCommand |
| Direct Body / World split | `BodyPort`, `NestSession`, Godot v3 lanes | Body registers direct capabilities, World owner registers semantic capabilities; composition aggregates discovery only; any resulting body command returns through NervousSystem → Body | `move/turn` and semantic destination calls reach the correct owner without a Body bypass |
| Virtual-body readiness | `build_nest_session_services()`, `restore_registered_elfies()`, `BodyBinding` | Explicitly register/bind `NativeBody`; expose capabilities only after Runtime/Actor readiness | matching `runtime_id/generation/world_revision/body_generation` |
| Virtual movement | `NativeBody` → `GodotTransport` → `actor_controller.gd` → `elfie_actor.gd` | Preserve Godot pathfinding; connect dynamic movement capability, Body execution and terminal outcome | Actor moves, plays walking/idle, and reports obstruction/unreachable reasons |
| Terminal embodied outcome | current `GodotTransport.execute_intent()` waits for terminal state | Keep version-one waiting inside the isolated output worker; normalize the terminal result through Body/NervousSystem, retain the full lifecycle in the action ledger, and publish one coalesced Embodied outcome; defer non-blocking submission to v2 | transport and sensor ingress stay live; Brain sees one terminal outcome, never accepted/started as separate Turns |
| Speak/hear | `prepare_speech()`, `request_speech_reach()`, `NestEventBus` | Preserve Nest content + Godot reachability + Nest hearing event; complete targeted Brain delivery | only spatially matching Elfies receive `HeardUtterance` |
| Semantic vision | `request_visual_observation()`, `resolve_visual_observation()`, `SemanticVisualScene` | Preserve Godot visible IDs → Nest semantic resolution; connect requester to later perception | Brain receives structured entities with label/kind/zone |
| Touch/body state | `NativeSensors` currently maps tactile only; Runtime snapshots mainly update Nest mirrors | Complete touch, posture, zone, position and arrival mapping through Body → NervousSystem; keep world-only facts in Nest | touch and body-state changes trigger later perception without inventing raw coordinates |
| One production loop | `NestSession` Tick, `pump_body_events()`, `NestRuntimeEventRouter` | Unify drain, identity/generation checks, EventWorkspace delivery and later-Turn notification | one command has one traceable causal chain; no duplicate/stale receipt |

## 4. Sequential slices

### P0-A: freeze control and feedback models

- Keep chat and embodied-control outputs as mutually exclusive variants.
- Make each control call a generic category plus dynamically registered `capability_id + typed args`; keep the
  underlying owner/route hidden from Brain.
- Define local submission acknowledgement separately from the Runtime's authoritative `accepted` receipt; neither
  is action success. Define deduplication, stale-generation rejection and typed failure reasons.

Acceptance: every structured call passes catalog validation; prose and unregistered capabilities cannot reach `BodyPort`.

### P0-B: assemble the virtual body

- In existing Bootstrap, construct `NativeBody`, register it in `BodyRegistry`, and bind it through `BodyBinding`.
- Expose the catalog only after Godot Runtime readiness, matching world revision and completed Actor synchronization.
- Preserve one active body authority per Elfie.

Acceptance: a ready state has matching `runtime_id`, Runtime generation, world revision and body generation.

### P0-C: connect movement and terminal action outcomes

- Use the registered movement capability for the first movement acceptance: the World owner resolves a semantic target;
  Godot owns pathfinding, collision, stepping and animation.
- The world resolution is not a second body route: the resulting movement command is validated by NervousSystem and
  executed through Body / BodyPort before it reaches Godot.
- Add direct `body.move_forward/turn` to the same catalog and BodyPort later, without a second motion path.
- Keep the current GodotTransport terminal wait inside the isolated output worker for v1. Preserve
  `intent_accepted`, `intent_started` and `intent_terminal` causal identity while normalizing them into Body
  receipts. Keep all lifecycle transitions in the action ledger, but send one coalesced terminal Embodied outcome
  per command to EventWorkspace; do not create an action-specific Brain trigger. Replace the worker wait with
  local submission plus a fully asynchronous receipt stream in v2.
- Keep `emergency_stop` on a deterministic safety path that can interrupt active motion.

Acceptance: one Brain control decision makes the Actor move; the Brain control path and sensor receiver remain available while
the isolated worker waits, and Brain later receives one structured terminal action outcome; obstruction, timeout,
interruption and stale generations are distinguishable.

### P0-D: connect speak-to-hear

- Brain emits `speak(text)`; the current Body produces action submission and terminal receipts.
- Nest stores speech content; Godot computes only spatial reachability, same-zone and occlusion conditions.
- After `speech_reach`, Nest creates targeted `HeardUtterance` events for matching Elfies and
  injects each one through that Elfie's Body input boundary.

Acceptance: the speaker receives the action result; listeners receive structured hearing in a later Turn; no audience
does not create a false hearing event.

### P0-E: connect semantic vision

- Brain requests observation without receiving an image.
- Nest/Godot World returns semantic IDs bounded by Actor position, visual cone and occlusion.
- Nest validates IDs, zone and world revision, resolves `SemanticVisualScene`, and injects the
  result through the observer Elfie's Body input boundary.

Acceptance: Brain distinguishes visible actors, anchors and facilities with labels/capabilities; invisible or stale
objects never enter perception.

### P0-F: connect body feedback and the later Turn

- Godot collision emits `tactile_contact`, which maps to `TactileImpact` and passes NervousSystem reflex/filtering.
- Map action results and zone/posture body state into the correct semantic lane; world and environment facts remain Nest-owned.
- Make `pump_body_events()`, the Nest event outbox and Brain `EventWorkspace` enforce identity, generation,
  deduplication, lifecycle coalescing and backpressure consistently. All action outcomes use the same Workspace
  trigger policy as other embodied facts; critical safety failures use the existing generic critical path.

Acceptance: movement, collision, hearing, vision and one coalesced action outcome per command produce later Brain
inputs; every body input/output passes through Body and NervousSystem, targeted world results re-enter through the
Elfie's Body input boundary, and one lifecycle does not create multiple receipt-driven Turns.

## 5. First-version capability catalog

The following are first-version catalog entries, not a hard-coded `DecisionIntent`
union. The Brain can call only entries currently registered by the active Body or
World owner.

| Capability | Owner | First-version use |
| --- | --- | --- |
| `world.go_to(anchor_id)` | Nest World | semantic destinations such as bed, chair and activity point; Godot pathfinds |
| `body.emergency_stop(reason)` | Direct Body | immediately stop the current action |
| `body.speak(text)` | Direct Body + Nest interaction | play speech action and compute who hears it |
| `body.expression(kind)` | Direct Body | play a registered expression/action and return terminal state |
| `world.observe()` | Nest World | return semantic objects in the current view |
| Body tactile/proprioception | Direct Body | collision, touch, posture and action-state feedback |

`move_forward(distance)` and `turn(angle)` remain frozen Direct Body capabilities. If `go_to` is used first to prove
path movement, they still reuse the same catalog, BodyPort, receipts and EventWorkspace rather than creating a new path.

## 6. Explicitly deferred

- Physical devices, pairing, Wi-Fi/MQTT/WebSocket Device Agents.
- Raw image, raw audio and multimodal media upload.
- A general external planner for physical bodies without navigation.
- Multi-step autonomous navigation Activity; the first version advances by one call and later receipts.
- Fully non-blocking BodyPort submission and receipt streaming; this is version two.
- Broadcasting all Godot Runtime frames to all Elfies.

## 7. Completion gate

Call the Godot virtual-body chain complete only when all are true:

- one real Brain Control Turn emits one or more registered structured capability calls;
- the virtual Actor moves, animates and returns a real terminal embodied outcome;
- speech, hearing, semantic vision, touch and body state enter the next Brain Turn through their proper authorities;
- Body, Runtime generation, world revision and command identity remain consistent end to end;
- Godot headless scene tests, Python boundary tests and at least one replayable host-to-Runtime integration scenario pass;
- there is no second control path, body input/output bypass of Body or NervousSystem, raw-media bypass of Nest, or
  Runtime fact incorrectly persisted as Nest fact.
