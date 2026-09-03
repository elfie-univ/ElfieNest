# Elfie embodied control chain design

> Status: Frozen v1 (responsibility skeleton)
> Scope: the end-to-end path from Brain to a virtual Godot body or a physical
> external body, including the return path of receipts and perception.
> This document freezes the responsibility skeleton; it does not claim that
> every future physical-device protocol already exists.

The repository-wide ownership rules remain in the [System architecture
contract](../contracts/system), the [Elfie contract](../contracts/elfie), the
[Nest–Godot semantic-world contract](../contracts/nest-godot-semantic-world)
and the [Brain contract](../contracts/brain). This design organizes that
existing boundary around one question: how does one body capability invocation
reach two different execution targets — the Godot virtual body and a physical
device — without making Brain or Body depend on either target?

## 1. Design target

The design must provide:

- two explicit Brain output circuits: the conversation circuit returns natural
  language through Communication, while the embodied-control circuit emits
  finite precise MCP-style capability calls (`capability_name(typed_params)`), never
  prose and never raw motor values;
- one Body semantic contract and one selected body execution authority;
- two replaceable execution routes: Godot virtual body and external physical body;
- a per-body/per-device **capability catalog** that can be enumerated, so the
  system and the Brain both know what the current body can and cannot do;
- typed commands, capability registration, receipts and perception feedback;
- exactly three Brain input domains: `Communication`, `Embodied` and
  `Activity`; an external action receipt is an `Embodied` fact, while
  `Activity` is reserved for Brain-owned cross-Turn work;
- no raw protocol frame, motor instruction or engine detail entering Brain;
- no per-frame model control loop; execution runs in the target authority and
  one causal batch of final action outcome plus body perception creates at most
  one later Brain Turn.

It deliberately does not freeze a complete wire schema, a particular hardware
vendor protocol, or every future motion capability. Pairing is defined for
physical devices only; the virtual body has no pairing flow at all.

### Brain input domains and `TurnFrame`

`EventWorkspace` is the only place that accumulates, deduplicates, coalesces
and seals Brain input. It has exactly three domains:

| Domain | Meaning |
| --- | --- |
| `Communication` | user/device conversation content and communication delivery facts |
| `Embodied` | body commands' terminal external outcomes and body/world perception |
| `Activity` | Brain-owned cross-Turn work and its state transitions |

`TurnFrame` is the immutable frame sealed by EventWorkspace for Brain. It is
not a fourth input and is not created by the model. `accepted` and `started`
remain action-ledger states; the final action outcome is an external
`Embodied` fact. When that outcome and position, posture, touch or other body
facts belong to the same causal window, EventWorkspace emits one Embodied
frame. An Activity state update is not a body receipt and does not enter the
Body path.

Godot and a physical device may retain precise coordinates locally, but the
Body exposes only normalized proprioception needed by Brain: body identity and
generation, semantic zone/anchor, posture, heading when needed, active command
and arrival state. It flows `Body → NervousSystem → EventWorkspace`; Brain's
Orientation owns the current self-location projection. Position updates may be
continuous on the device connection, but EventWorkspace coalesces them and
does not create a model Turn per physics frame.

## 2. Dual authority and two semantic lanes

### Dual authority

On the virtual side there are two distinct authorities:

| Authority | Owns |
| --- | --- |
| **Godot Runtime** | virtual-world physical facts: scene, position, physical body, navigation, collision, visibility, audibility, rendering and actual execution; virtual-world pathfinding always belongs to Godot |
| **Nest** | interpretable semantics: household meaning, rules, time/environment intent, semantic interaction, structured vision / virtual hearing / semantic-action correlation |

Whether an action needs pathfinding does not decide its semantic owner. Nest
resolves a world target and its meaning/permission; Godot owns pathfinding and
actual movement only in the virtual world. A physical device is executed by its
Device Agent/controller, or by an explicitly introduced external execution
planner; it is not silently assigned to Godot.

**Environment objects (lights, doors, facilities) are Nest-owned world
intentions, not Elfie body intentions.** Time and household rules command them
automatically (doors open when approached, lights turn on at night). The Elfie
never controls environment objects through its body; its body chain has no such
command.

### Body path and World authority

There is one non-bypassable Body path for all body commands and body-owned
perception. The **World authority** is a separate semantic authority, not an
extra hop in that path. Nest may resolve a semantic target or filter a world
event, but it never transports or executes a Body command.

```text
Brain control call
  → NervousSystem (the Elfie's only embodied control gate)
  → Body / BodyPort
  → NativeBody or ExternalBody
  → Transport → Gateway
  → Godot Actor or remote Device Agent / firmware

Godot Actor or remote device
  → Gateway → Transport → Body Adapter
  → Body → NervousSystem
  → EventWorkspace → TurnFrame → Brain

World semantic side:
Godot World or device-world adapter ↔ Nest
  → semantic result targeted to an Elfie
  → that Elfie's Body input boundary
  → NervousSystem → EventWorkspace → Brain
```

The Direct Body return path is:

```text
Godot Actor or physical device
  → Gateway → Transport → Body Adapter → Body
  → NervousSystem → Brain EventWorkspace
```

The World authority is not a shortcut around Body and NervousSystem. Its
semantic result returns to the target Elfie's Body input boundary first:

```text
Godot World authority
  → World Gateway → Nest semantic owner
  → targeted result → Elfie Body input
  → NervousSystem → Brain EventWorkspace
```

`BodyPort` is the stable semantic boundary for the actor body, not an additional
runtime hop. `NativeBody` and `ExternalBody` are Infrastructure implementations
of that contract. Only the selected `BodyBinding` and its current generation may
execute Direct Body commands or update authoritative embodied perception.

Direct actions such as "turn left" or "move forward" stay on the Body path.
Behaviors that need household/world semantics — "what was heard", "what was
seen", "go home" — consult the World authority. If a world decision produces
an actual body movement, the resulting Body command must still pass through
`NervousSystem → Body`; Nest is never a `BodyPort` implementation.

The authority split for important calls is:

| Call | Lane | Semantic owner | Physical executor |
| --- | --- | --- | --- |
| `move_forward(distance)`, `turn(angle)` | Direct Body | current Body capability | Godot Actor or Device Agent |
| `move.to(anchor_id)`, `go_home` | World | Nest resolves target, meaning and permission | Godot pathfinding in the virtual world; physical controller/planner outside it |
| `open_door`, `turn_on_light` | World | Nest-owned environment intention | Godot World or the corresponding environment controller |

### The physical body is a remote runtime

`infrastructure/devices/` code runs on the ElfieNest host and is never installed
inside a physical toy. The physical toy runs a separate firmware or Device Agent
that owns local sensors, actuators, safety policy and a network client.

```text
ElfieNest host                                  external physical device

BodyPort                                        Device Agent / firmware
  → ExternalBody or device BodyPort Driver      ├ camera / mic / touch /
  → ExternalTransport → DeviceGateway           │ collision / IMU / battery
                          ▲                     │ collectors
                          │                     └ motors / servos / speaker /
            Body WebSocket endpoint                    screen actuators
                          ⇄ authenticated Wi-Fi/LAN session
                          ⇄
                    Device Agent / firmware
```

Downstream is `BodyCommand → ExternalTransport → DeviceGateway → Body WebSocket
endpoint → network body message → device dispatcher → local actuator driver`.
Upstream is `sensor/actuator state → device event message → Body WebSocket
endpoint → DeviceGateway → ExternalTransport → Body → BodyPort → NervousSystem`. The
external body is therefore naturally bidirectional: command output plus camera,
mic, collision/touch, proprioception, battery and health input.

Wi-Fi/LAN is a connection medium, not a Body contract. The first-version external
device uses a "pair then authenticated bidirectional IP session". Bluetooth may
later be used for pairing or a device-class connection, but never leaks into
Brain or `BodyPort`.

The current `ExternalBody` and `DeviceGateway` are host-side artifacts. The
repository already has an authenticated, versioned external-body WebSocket
endpoint and a `BodyDeviceChannel` that forwards heartbeat, sensor, terminal-receipt and
command-poll frames. But `DeviceGateway` itself is still an in-process registry
and queue; the Device Agent/firmware and the physical sensor loop are outside the
repository. Production Bootstrap does not yet assemble `ExternalBody` into an
active `BodyBinding` of an Elfie, so the complete BodyPort-to-network-runtime
chain is an implementation gap. In particular the current `ExternalTransport`
connection only carries sensor callbacks; terminal receipts are not yet wired
back into `ExternalBody`; commands today can at most prove "enqueued", not that
the physical device completed them.

The WebSocket endpoint and `DeviceGateway` are two code parts of one external
device Gateway subsystem, not two new domain layers: the endpoint owns network
frame boundaries, `BodyDeviceChannel` owns host-side identity validation, and
`DeviceGateway` owns host-side session/queue routing.

## 3. Brain output circuits and capability invocation

Brain has two different output circuits:

| Circuit | Turn/output scope | Output | Execution rule |
| --- | --- | --- | --- |
| Conversation | Communication | natural-language response through `Communication` | text is never parsed as a body command |
| Embodied control | Embodied | precise capability invocation through `NervousSystem` | only typed, catalog-checked calls may reach `BodyPort` |

One Turn does not mix these external domains. A control result cannot contain
free prose that the runtime might guess how to execute; a chat result cannot
silently control a body. If a user request needs both, the system creates
separate scoped Turns rather than interpreting one output string twice.

### Capability invocation form: MCP-style precise method calls

The embodied-control circuit's output to the body is a precise method call, not
a semantic description:

- Every body/device exposes a **capability catalog**. Each entry is
  `name + typed parameter schema + return type`, shaped like an MCP tool
  definition. The system and the Brain can enumerate the catalog ("pull all
  capabilities") and therefore know what the current body can and cannot do.
- Each catalog entry declares a broad `category` (`body`, `world`,
  `communication` or `activity`) and a registration source. `BodyPort` registers
  capabilities directly executable by the current body; Nest or another owner
  registers capabilities requiring world semantics. The composition root may
  aggregate them into one read-only catalog for Brain discovery, but it never
  merges their execution paths.
- The Brain produces a finite set of generic, exact invocations through
  structured output. Each call contains `call_id + category + capability_id +
  typed arguments + subject=self`; calls may be ordered or run concurrently
  within the one settled DecisionPlan.
  `DecisionIntent` does not enumerate verbs such as `move.to`, `turn` or `speak`.
  Those are catalog entries that can vary by body. Brain does not provide a
  Godot/device/Transport/Body route; the lower layer selects it from the
  catalog and active `BodyBinding`.
- The split happens at **capability registration and dispatch**, not by
  splitting `Body` into two bodies. A body capability goes through
  `NervousSystem → BodyPort → current Body Adapter`. A world capability is
  resolved by its world owner; if it produces a body action, that action returns
  to `NervousSystem → BodyPort` before execution. Brain chooses the registered
  capability, never the underlying circuit.
- NervousSystem validates body calls (capability present, typed parameters,
  body generation, physical limits and reflexes) and delivers them through
  `BodyPort`. A world call cannot be disguised as a body action and must pass
  its owner's semantic and permission checks. The body returns a typed result
  plus a lifecycle receipt. Receipt states are `accepted`, `started`,
  `completed`, `rejected`, `failed`, `interrupted` and `timed_out`; movement
  blocked is a typed failure reason, not a second status vocabulary.

Example catalog entries, not a fixed `DecisionIntent` union, are
`move.forward(distance)`, `move.turn(angle_degrees)`, `speak(text)`,
`expression(kind)`, `emergency_stop(reason)`, `move.to(anchor_id)` and
`observe()`.

> This call shape does **not** make body capabilities ToolPort. `ToolPort` is
> the cognitive-tool line (web search, bounded workspace file). Body and device
> capabilities are the embodied line (NervousSystem/Body). The **call form** is
> identical — precise, enumerable, schema-typed — but the **line** is different.

### Receipt and terminal-state contract

The first version may let `BodyPort.execute()` wait for the target to finish
inside an isolated output worker. It must not block the transport receiver or
the sensor-ingress path. A local transport send is not proof that a remote
Runtime or device accepted or completed the action. Version two may replace
that worker wait with local submission plus a fully asynchronous receipt stream;
this is an evolution of execution, not a new Body contract.

Both versions use the same typed receipt identity:
`call_id/command_id`, `body_id`, `generation`, `capability_revision`, `status`
and `timestamp`, with a typed `error_code` on failure. The current Body and
NervousSystem normalize the target's lifecycle into the common receipt model.

The minimum state machine is:

```text
submit ├→ rejected
       └→ accepted → started → completed
                              ├→ failed
                              ├→ interrupted
                              └→ timed_out
```

NervousSystem validates receipt identity, generation, and capability revision.
The Body/output action ledger may retain every lifecycle transition for audit
and recovery, but `accepted` and `started` never enter Brain as separate
events. Brain receives only one external, embodied terminal outcome per
command. It is coalesced with body perception from the same causal window, so
the action outcome does not create an action-specific Brain Turn. A
safety-critical failure uses the existing generic critical-event path.
Receipts from an old generation and duplicates must be idempotently discarded or
recorded; enqueuing a command must never be treated as terminal success.

The same rule applies to sensor events: device-side or Godot-side callbacks are
normalized by the owning Body, then delivered to NervousSystem. Events first
accumulate, deduplicate and coalesce in EventWorkspace; one incoming event does
not imply one Brain Turn. Body input is always `Body → NervousSystem →
EventWorkspace`; Nest is not inserted into this path. A later action outcome or
sensor fact may trigger one later Turn or an `Activity` state update.

## 4. Two execution routes

| Concern | Godot virtual body | External physical body |
| --- | --- | --- |
| Body implementation | `NativeBody` | host-side `ExternalBody` proxy or device-specific `BodyPort` driver |
| Host transport | `GodotTransport` | `ExternalTransport` / `DeviceGatewayTransport` to the host Gateway |
| Network protocol endpoint | `infrastructure/godot/gateway/` | `app/interfaces/api/v1/realtime/bodies/` |
| Host Gateway registry | Godot Gateway/session code | `infrastructure/devices/gateway.py` |
| Remote execution authority | Godot Runtime | independent Device Agent/firmware and local actuator drivers |
| Capability catalog | what the Godot avatar supports | capabilities the device registers at pairing time |
| Navigation | Godot owns pathfinding, stepping, collision and animation | only if the device/controller advertises and implements it |
| Command rule | invoke capabilities from the registered catalog | invoke only capabilities the physical body actually registered; never expose raw motor control to Brain |
| Return facts | Runtime lifecycle receipts and body/world perception from Godot; Brain normally receives one coalesced action outcome per command | Runtime/device lifecycle receipts plus sensor/proprioception/battery/health facts; Brain normally receives one coalesced action outcome per command |

The two Direct Body routes share `BodyCommand`, `BodySensorEvent`,
`CommandReceipt`, body identity, generation and capability revision. They differ
only after the `BodyPort` boundary. The World lane is independent: its facts are
owned and semantically filtered by Nest and are not forced into `BodyPort`.

For both Godot and the physical toy, classify facts by meaning rather than by
sensor type. Local microphone/camera/touch/proprioception describing body-own
state travel on the Body path. Facts describing the external environment and
needing semantics such as "there is another audible object over there" use the
virtual World lane on the Godot side; on the physical-device side there is no
forced parallel semantic authority. If the physical environment is represented
in Nest, an external world adapter sends the observation to Nest for semantic
resolution; if that scope is not enabled, the fact remains a body-local device
input. Device telemetry is never directly treated as a Nest fact.

For a semantic target such as "go home", target resolution may use Nest/Godot
world semantics before execution. That does not make Nest the Body executor. For
a direct action such as turn or move forward, the command stays on the Body
route and does not pass through Nest.

## 5. Device pairing: physical devices only

The **virtual body has no pairing.** It is the Elfie's own body: it connects
through the Godot Runtime authority (Gateway handshake plus generation) and
belongs to the Elfie by construction. There is nothing to recognize or register.

A physical device follows an explicit pairing flow before it can be hosted:

```text
discovery → pairing → authentication → session → capability registration → ready
```

1. **Discovery** — the device powers on and connects to the server (or is found
   by LAN discovery).
2. **Pairing** — the device and the server exchange a pairing credential or code
   and bind the device identity to the user/nest.
3. **Authentication** — the device receives an independent least-privilege
   identity (device principal), never reusing an administrator or Observer
   credential.
4. **Session** — an authenticated bidirectional network channel is established
   (server sends commands; device returns events, receipts and perception).
5. **Capability registration** — the device reports its capability catalog
   (sensors + actions, MCP-shaped); the server records it, so the system now
   knows exactly what the device can do.
6. **Ready** — the device is healthy and its catalog is queryable, so it becomes
   available for hosting.

The virtual body skips physical pairing, but it still goes through runtime
assembly, registration, explicit `BodyBinding` and generation checks. “No pairing”
means no user/device trust exchange, not “no binding”.

## 6. Hosting and return-to-nest: Brain decision plus ready gate

Going out is a brain-controlled switch plus an external ready gate:

- The Brain decides "I want to go out" and emits an outgoing intent.
- The system checks whether the physical body is **ready** (paired, capability
  catalog registered, connection healthy).
- If ready, the switch proceeds: the virtual body sleeps and the physical body
  gains sensor and action authority (HOSTED).
- The Brain decides "I want to come back": the physical body releases authority
  and the virtual body wakes (return-to-nest).

There is no separate cognitive context-copy mechanism, but the switch itself is
an explicit `BodyBinding` transaction owned by App Orchestration. It acquires
the ready body's authority, advances generation, releases the previous body,
and supports rollback/recovery. Orientation then rebuilds from the selected
body's facts on the next event frame.

## 7. Module responsibilities

| Module | Owns | Does not own |
| --- | --- | --- |
| `elfie/brain/` | selfhood, cognition, reasoning, Skills and the decision of what to do; emitting precise capability invocations | Godot frames, sockets, motor values, navigation execution or device protocols |
| `elfie/nervous_system/` | Direct Body event normalization, physical limits, deterministic reflexes, command preflight and conversion of capability invocations to `BodyCommand` | open-ended decisions, sockets, protocol sessions, geometry, pathfinding or Nest world semantics |
| `elfie/body/` | body IDs, capability catalog, commands, sensor events, receipts, registry, selected binding and body generation | concrete Godot/device adapters, credentials, WebSocket/Bluetooth/LAN and process control |
| `BodyPort` | the Body domain's typed interface for describe/connect, sensors, commands and snapshots | wire encoding or target-specific behavior |
| `nest/` | household/world semantics, target meaning, vision/hearing/action correlation and targeted semantic results | the Elfie's Direct BodyPort, physical execution, device transport or actor ownership |
| `infrastructure/godot/native_body.py` | `BodyPort` implementation for one Godot body; maps capability invocations to Godot Actor semantics | Brain decisions, world meaning, Godot scene authority or product authorization |
| `infrastructure/devices/external_body.py` | host-side remote-body proxy implementing `BodyPort`; shared capability validation, sensor buffering and receipt normalization | running on the toy, collecting physical sensors, driving motors, or necessarily owning all vendor translation |
| external-device driver (optional, in `infrastructure/devices/`) | translating between generic device messages and vendor protocols by family/model; when the device can run it, prefer the remote Device Agent/firmware | Brain decisions, household semantics or exposing raw protocols to Brain |
| `infrastructure/*/body_transport.py` | host-side Adapter-to-Gateway delivery, cancellation, pending state and delivery failures | deciding goals, defining Body semantics or owning physical truth |
| `app/interfaces/api/v1/realtime/bodies/` | network-facing versioned WebSocket frame parsing, authentication and ingress/egress for the remote Device Agent | Brain logic, Body binding, Nest semantics, navigation or device physics |
| `app/orchestration/embodiment/BodyDeviceChannel` | checks device principal/body identity and forwards validated heartbeat, sensor, receipt and command-poll operations | wire framing, motor drivers, Brain decisions or routine motion |
| `infrastructure/devices/gateway.py` | host-side in-process device registry, command queue and sensor/receipt callback routing; the technical half of the external gateway | WebSocket framing/authentication, Brain logic, Body binding, Nest semantics or device physics |
| Device Agent / firmware (separate device code, outside this repository) | device identity/pairing client, sensor collectors, local safety, actuator dispatch and network session | Elfie identity, Nest household semantics, Brain reasoning or host-side Body binding |
| `godot_project/` / physical-device actuator controller | actual movement, navigation, collision, animation and hardware behavior; reports what happened | Elfie identity, memory, household rules or a second Brain |
| `app/orchestration/nest_session/` | composing real Elfie/Nest instances and routing the Nest World Channel | deciding world semantics, owning Godot physics or proxying each Direct Body command |
| `app/orchestration/embodiment/` | enrollment, pairing, association, hosting, switching and recovery across authorities | routine movement commands and per-frame body control |
| `app/orchestration/lifecycle/` | starting, stopping and recovering Core, Gateway and the selected world authority | Brain decisions, Nest rules or ordinary body control |

The distinction between the last Infrastructure terms is:

```text
BodyPort       = the common Actor-Body semantic contract
Body Adapter   = one BodyPort implementation plus target-body translation
Transport      = host-side connection and message delivery used by an Adapter
Gateway        = host-side protocol endpoint plus session/routing boundary
Device Agent   = remote device code that collects sensors and drives actuators
```

A Body Adapter may be the only target-specific implementation. `ExternalBody`
does not automatically add a second translation layer: it is used only when
shared host-side body validation, sensor buffering or receipt normalization is
needed. If a device-specific driver can implement `BodyPort` directly, it does
so; if the target protocol already accepts the generic typed commands, no extra
host-side translator is needed.

For devices that run our Device Agent, the necessary translation is not empty:
the generic `BodyCommand` first becomes a device-independent network message,
which the Device Agent/firmware maps to vendor motor, servo, speaker or screen
drivers. Vendor mapping should not be duplicated in each host-side
`ExternalBody`. Devices that cannot run our Agent use explicitly supported
host-side vendor drivers.

Transport is not a new top-level module; it is a component inside the target
Infrastructure package, beside or inside the Adapter. A Gateway is needed only
when a real protocol endpoint, session or router exists.

## 8. Command and feedback cycle

1. The current body exposes a typed capability catalog through `BodyPort`.
2. Brain reads the capability projection and produces a **precise capability
   invocation** within the registered catalog; it does not choose a wire frame or
   a motor value.
3. If it is a Direct Body invocation, NervousSystem checks scope, body
   generation, capability revision, deadline, physical limits and deterministic
   reflex rules; the BodyPort/body implementation performs the final capability
   and connected-state validation.
4. If household/world semantics are needed, the World owner resolves the
   semantics and correlates the result with its authority. This does not turn
   Nest into a Body executor. If the result requires physical movement, the
   resulting Body command must re-enter NervousSystem and Body before delivery.
5. On the Direct Body path, the host-side body implementation/driver maps the
   typed invocation to the target semantic API; Transport and Gateway deliver it
   and correlate the response by command/intent/body/generation identity. An
   external body also crosses the authenticated Wi-Fi/LAN session to the
   independent Device Agent, which dispatches to local actuators.
6. The target authority executes the action and reports actual facts: Godot
   reports Actor/World facts; the Device Agent reports physical sensor,
   actuator, battery and health facts.
7. Direct Body receipts and body sensors return along
   `Body Adapter → Body → NervousSystem → Brain`. A world semantic result is
   targeted to the Elfie, enters its Body input boundary, and then follows the
   same `Body → NervousSystem → Brain` path. Stale generations and revisions
   are rejected.
8. Brain consumes the result in a later event frame and decides the next step;
   it does not run the target's frame loop.

One Brain Turn settles one bounded decision. Its `DecisionPlan` may contain a
finite set of validated dependent or concurrent invocations, but the embodied
route remains finite and receipt-driven; continuous adjustment belongs to later
Turns or Persistent Activities, not to a hidden model loop inside Transport or
Gateway. Each invocation keeps its own action ledger and terminal result; the
resulting Embodied events may still be coalesced into one later frame.

## 9. Boundary rules to preserve

- Brain emits precise capability invocations; it never imports a concrete Body
  Adapter, Transport or Gateway, and never emits semantic prose as a call.
- NervousSystem is the deterministic embodied processing layer and the only
  Elfie-side gate for Body input/output; it may reject, filter, limit or
  emergency-stop, but it does not perform pathfinding, Nest world resolution
  or network I/O.
- Body owns the semantic body contract and the single active binding; it does
  not encode target protocols.
- `NativeBody` and `ExternalBody` implement the same `BodyPort`; neither creates
  a second body authority.
- `infrastructure/devices/` is host-side integration code. Physical device
  firmware/Device Agent is an independent runtime and cannot be imported by host
  code the way `elfie/body` is.
- Transport and Gateway carry commands and facts; they do not decide what the
  Elfie wants to do.
- External-device communication is bidirectional: one authenticated session
  carries downstream commands and upstream receipts/sensor events.
- Godot Body and Godot World are two independent authority channels even when
  they share one Gateway. A world result targeted to an Elfie is normalized at
  that Elfie's Body input boundary before NervousSystem sees it; it never
  bypasses Body or becomes a raw protocol frame.
- Godot and the physical controller own their actual physical facts. Python
  stores only the typed semantic projection and receipt needed by the domain.
- App Orchestration manages lifecycle and cross-authority workflows, but normal
  body control does not detour through a product use-case.

## 10. Deferred detail

The following can be designed later without changing this skeleton:

- the exact external-device wire protocol, pairing handshake and reconnection
  strategy;
- the Device Agent/firmware boundary and concrete sensor/actuator message shapes;
- whether a physical device has local navigation or needs a separately owned
  Infrastructure execution planner;
- retry and queue policy for each device class;
- how the capability catalog vocabulary grows for future devices.

The capability-invocation **form** is fixed now (precise, enumerable, typed);
the exact catalog **contents** grow per device. The terminal receipt semantics
and identity are fixed now; fully asynchronous host-side execution is deferred
to version two. The version-one worker may wait for a terminal result without
blocking sensor ingress or the transport receiver.
If a generic physical navigation planner is later needed, it must be introduced
as an explicit execution-side Infrastructure capability. It must not silently be
placed in NervousSystem, Gateway or Brain.

## 11. Design self-review

### Target architecture

| Requirement | Result |
| --- | --- |
| Brain to Godot and physical body are shown end to end | Pass |
| Body, BodyPort, Adapter, Transport and Gateway are separated | Pass |
| The two routes share one semantic contract | Pass |
| Direct Body and World semantic lanes are separated | Pass |
| Conversation and embodied-control Brain circuits are separated | Pass |
| Capability invocation is a precise, MCP-style method call | Pass |
| Per-body/per-device capability catalog is enumerable | Pass |
| Physical pairing is separated from virtual binding | Pass |
| `move.to`/`go_home` world ownership is separated from body-relative motion | Pass |
| Hosting/return is a Brain decision plus an external ready gate | Pass |
| No fabricated real-world semantic authority parallel to Nest | Pass |
| The Elfie does not control environment objects | Pass |
| Terminal receipts, one causal Brain Turn and Activity separation are defined | Pass |
| Low-level control is kept out of Brain | Pass |
| Future details can evolve without moving module ownership | Pass |
| Exact wire schema and every hardware capability are already settled | Intentionally deferred |

### Current implementation readiness

| Evidence | Result |
| --- | --- |
| Authenticated external-body WebSocket endpoint and frame types | Present |
| Host-side `DeviceGateway` queue/routing | Present, in-process |
| `ExternalBody` assembled into an active Elfie `BodyBinding` | Not complete |
| Terminal receipt delivered back into `ExternalBody` | Not complete |
| Device Agent/firmware and physical sensor/actuator loop | Outside this repository |
| Brain-to-physical-device end-to-end execution | Not complete |

Conclusion: the responsibility skeleton is now clear enough to freeze as a
design candidate, but it is not a completed implementation. The first-version
plan deliberately freezes the Body/NervousSystem path, external embodied
terminal outcomes, Activity-only events, dynamic capability
registration and one-causal-window Brain triggering. Fully asynchronous
execution remains a version-two optimization. Any changed ownership or
`BodyPort` semantic requires the corresponding ADR and contract update.
