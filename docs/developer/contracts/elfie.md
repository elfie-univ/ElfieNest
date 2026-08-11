# Elfie internal architecture contract

**Contract version:** 1.0
**Adopted:** 2026-08-11
**Scope:** `elfie/` and Infrastructure Port views scoped to one Elfie

> **Normative target.** This contract defines the internal ownership, dependency
> direction, public Facades and outbound Ports of one complete Elfie. It refines,
> but does not change, the frozen [system architecture contract](./system). The
> current implementation is not yet fully conformant; exact migration gaps live
> in the [Elfie conformance register](../conformance/elfie).

The system contract remains authoritative for root modules, system authority and
the final location of technical Adapters. This contract is authoritative inside
`elfie/`. The model, Food and tool behavior contract remains authoritative for
accepted behavior while the historical `ai_runtime/` package is dismantled.

## Purpose and non-goals

`elfie/` owns one complete, independently testable creature: stable Profile,
cognition, emotion, memory semantics, Skills, nervous-system processing, body
semantics, digital communication semantics and its own lifecycle. Internally it
uses a lightweight nested Ports/Adapters shape so that domain behavior does not
depend on SQLite, YAML user storage, Provider SDKs, Godot frames, device
transports or communication-platform protocols.

This contract does not introduce a microservice, event bus, generic dependency
injection framework, universal repository, one Protocol per helper, or a second
App orchestration layer. It does not require a duplicate inbound Protocol for
the stable `Elfie` and `ElfieFactory` Facades.

## Aggregate shape

One Elfie is one aggregate and one internal lifecycle boundary; it is not a
system Runtime authority:

```text
Elfie / ElfieFactory Facades
            |
            v
private Elfie cognitive coordination
   |          |             |
   v          v             v
 Brain   NervousSystem   Communication
   |          |             |
   |       BodyPort    CommunicationChannel
   |
   +--> FoodPort / ModelPort / ToolPort
   +--> MemoryStorePort

Profile --> ProfileStorePort
```

The root Facade coordinates the submodules. Brain owns cognition and decisions;
it does not construct or import concrete Body, channel, model, tool or storage
implementations. `ElfieCognitiveRuntime` or its successor is private aggregate
coordination, not an App Runtime, Infrastructure Adapter or public product API.

## Internal module ownership

| Module | Owns | Must not own |
| --- | --- | --- |
| `elfie/profile/` | Identity, species, appearance, personality, stable capabilities, limits, provenance and immutable bundled defaults | YAML/file persistence, user paths, App adoption or account rules |
| `elfie/brain/` | Perception workspace, context, appraisal, cognition, decision plans, output routing, emotion, energy, memory semantics and Skills | Provider selection/configuration, SDK requests, concrete tool execution or product workflow |
| `elfie/brain/memory/` | Memory nodes, relations, encoding, retrieval, consolidation and the semantic storage Port | SQLite connections, schema, paths or persistence records |
| `elfie/brain/skills/` | Skill declarations, the per-Elfie catalog, policy and authorization of semantic tool requests | Runtime proxies, platform tools, workspace paths or tool execution |
| `elfie/nervous_system/` | Body-event normalization, filtering, reflexes, perception delivery and translation of validated body intents | Device transport, Godot protocol, geometry or body registration policy |
| `elfie/body/` | Body identity, capabilities, anatomy, commands, sensor events, receipts, registry and binding semantics | Godot/WebSocket/device transport, credentials, process ownership or device product authorization |
| `elfie/communication/` | Canonical envelopes, admission and delivery semantics, policy, inbox/outbox, Hub and channel routing | Product conversation authority/history, account membership, platform SDKs, credentials or network transport |

Skills are part of Brain because they influence cognition and authorize which
semantic tool requests one Elfie may make. A Skill names a semantic `tool_key`
or capability; it never wraps a Runtime object or executes the tool itself.
Bundled Skill declarations and per-Elfie in-memory policy require no persistence
Port. Mutable Skill installation, mutation or durable per-Elfie Skill state is
outside this contract; introducing it requires a separate approved contract
decision and cannot begin by writing files from Brain.

## Public inbound surface

Production callers enter the aggregate through `Elfie` and `ElfieFactory`.
`elfie/__init__.py` exposes those Facades and only deliberately stable boundary
types. App production code must not coordinate the aggregate by reaching into
`BrainCoordinator`, `MemorySystem`, `CommunicationHub`, `NervousSystem` or
mutable registries.

The `Elfie` Facade provides these typed capability groups:

- identity and immutable Profile/status projections;
- start, stop, join and explicit advancement of Elfie time;
- typed body-perception and communication ingress;
- registration, binding and unbinding of available bodies, plus registration,
  connection and disconnection of authorized channels;
- typed turn outcomes, decisions and execution receipts needed by authorized
  Orchestration or Observer projections.

The Facade does not expose database paths, workspace paths, Provider objects,
Godot APIs, transport frames, SQLite/YAML stores, mutable dictionaries or its
mutable internal submodules.

`ElfieFactory` is a domain aggregate builder invoked by Bootstrap, not a second
production composition root. It returns a completely assembled, not-yet-started
Elfie from explicit typed dependencies or a closed immutable assembly record.
It may construct Elfie-owned components, but it does not construct technical
Adapters, parse a product data root, accept `godot_api: Any`, or leave cognition
to be injected into a partially configured running object.

## Outbound Port ownership

Ports are defined beside the consuming semantic owner. A curated `elfie.ports`
surface may re-export them for Bootstrap, but it must not define duplicate
models or become a Service Locator.

| Port | Consumer owner | Semantic contract |
| --- | --- | --- |
| `FoodPort` | Brain | Read the current effective, already-authorized Food projection with named semantic roles, exact opaque model references and the single-fallback/emergency shape defined by the behavior contract |
| `ModelPort` | Brain | Perform Provider-neutral model generation with typed deadlines, cancellation and result metadata |
| `ToolPort` | Brain (Skills authorizes) | Enforce the technical safety scope and execute one Brain-authorized semantic tool request, or return a typed denial/bounded result |
| `MemoryStorePort` | Brain/Memory | Store and query typed memory nodes, edges and semantic search results |
| `ProfileStorePort` | Profile | Load and save a validated stable Profile without revealing YAML or paths |
| `BodyPort` | Body (consumed by NervousSystem and aggregate routing) | Expose one replaceable body's capabilities, commands, events, receipts and snapshot |
| `CommunicationChannel` | Communication | Connect one channel and deliver canonical envelopes with typed receipts |

Every injected Port exposes only the authorized scope of one Elfie. A concrete
Adapter may share a container-scoped connection pool, Provider client or Godot
Gateway behind several scoped Port views; shared technical lifetime never
exposes cross-Elfie queries and never transfers cleanup ownership into Elfie.
`ToolPort` therefore receives semantic resource identifiers rather than an
arbitrary filesystem path, and its scoped Adapter resolves the authorized root.
`FoodPort` does not expose a general cross-Elfie query API. Boundary models use
domain language and never leak SDK objects, SQL rows, unvalidated dictionaries
or protocol frames.

## Food, model and tool cognition

Brain chooses a semantic model role and decides whether a proposed tool call is
allowed. `FoodPort` preserves the exact named-role, one optional fallback and
Emergency behavior defined by the model/Food/tool behavior contract; it does
not invent an arbitrary fallback list. `ModelPort` interprets opaque technical
model references and performs generation.

Brain Skill authorization is necessary but not sufficient for tool execution.
The `ToolPort` Adapter intersects the request with global availability and the
invocation's technical safety scope, may return a typed denial, and can never
broaden the capability authorized by Brain. App configures availability but
does not proxy the call.

The normal path is direct:

```text
Brain -> FoodPort  -> Infrastructure persistence Adapter
Brain -> ModelPort -> Infrastructure model Adapter
Brain -> ToolPort  -> Infrastructure tool Adapter
```

App Configuration manages global availability, assignment and authorization but
does not proxy the runtime path. App Orchestration is not a model or tool
gateway. The historical broad `CorticalRuntimePort` and `RuntimeSkillAdapter`
are migration paths, not the target ownership model.

## Body Ports and multiple bodies

An Elfie can register multiple bodies. Every body instance has a stable
`BodyId`, capability revision and independent lifecycle, and implements the same
`BodyPort`. Examples include a Godot actor body, one or more physical toy bodies,
a device body and a headless/test body.

`BodyRegistry` owns the available body instances and `BodyBinding` owns the
explicit current routing relationship. The initial binding policy may select one
primary command body while retaining multiple registered bodies. Commands and
events always carry `BodyId`, so future role-based or concurrent bindings do not
require a new transport-specific contract. Any simultaneous-body policy must be
explicit; it cannot be inferred from connection state.

The Registry contains only Adapter views already discovered, granted and
associated by App Device use-cases. Connection or health state does not grant,
associate or bind a body. Events from different bodies have stable event IDs and
timestamps; there is no implicit global ordering across bodies.

`BodyPort` is the stable aggregate boundary. Narrow sensor and actuator
Protocols may exist inside a body implementation when they provide real
testability, but callers do not receive a duplicate family of public body APIs.

Body commands, sensor events, capabilities and lifecycle receipts remain in
`elfie/body/`. A deterministic pure-domain reference body or test fake may stay
with domain tests; product Headless hosting and all Godot transport, device
sessions, Bluetooth/LAN, credentials and process control belong to
Infrastructure. App Device features own discovery, enrollment, authorization
and Elfie/body association; cross-authority hosting, switching or return-to-Nest
workflows belong to App Orchestration.

The Body channel carries only actor-scoped commands, perceptions,
proprioception and receipts. Authoritative house geometry, coordinates,
collision/navigation and global interaction facts enter Nest through the world
channel; Orchestration delivers only the resulting authorized semantic
perceptions to affected Elfies. A shared Godot Gateway may back both scoped
views, but `BodyPort` never becomes a bypass around Nest authority.

## Communication Ports and multiple channels

An Elfie can connect multiple communication channels concurrently. Web chat,
the dedicated ElfieNest App, WeChat, DingTalk, Feishu, Telegram and future
platforms all implement one `CommunicationChannel` Port per channel instance.
`CommunicationRouter` routes by stable `channel_id` while `CommunicationHub`
owns validation, deduplication, policy, inbox/outbox and canonical delivery
semantics.

For external inbound traffic, the platform Adapter authenticates and translates
the native payload; an App Communication Feature resolves the account,
conversation membership, target Elfie and authorization; only then does it call
the `Elfie` Facade with a canonical `CommunicationEnvelope`. A trusted local
channel already scoped by App may use the same Facade directly. Infrastructure
never chooses an Elfie or bypasses product authorization. The Facade itself is
the inbound domain boundary, so no symmetrical `InboundCommunicationPort` is
required without a separate process or multi-implementation need. Outbound
envelopes use the registered channel Port and return a typed `DeliveryReceipt`.

Each envelope and receipt carries stable message/correlation identity and a
`channel_id`. Deduplication is idempotent, replies default to the originating
channel unless a decision explicitly selects another authorized channel, and
there is no implicit total ordering across concurrent channels. A native
platform sender identifier is never treated as an authenticated ElfieNest
principal.

Product accounts, relationships, conversation membership and user-visible
history belong to an App Communication Feature. Infrastructure owns platform
SDKs, credentials, Webhooks, network sessions, retry transport and external
protocol mapping. Elfie owns only communication and cognition semantics.
Communication inbox/outbox state is bounded processing and delivery state, not
a second durable conversation history or transport-retry authority. Elfie
Memory may encode its own semantic memory of an interaction, but it does not
copy or become authority for the App conversation record.

## Nervous system and internal adapters

NervousSystem translates Body events into Brain perception, applies physical
limits and reflexes, and translates validated body intents toward the current
Body Port. Communication converts canonical envelopes and delivery receipts
into a separate digital-perception stream. Body and digital communication are
not collapsed into one generic input channel.

Internal bridges such as a perception adapter or intent executor may remain in
Elfie when both sides are Elfie-owned semantic contracts. They are internal
coordination, not permission to embed an external technical Adapter in the
domain package.

## Boundary models, errors and lifecycle

Public Facades and Ports use named immutable models. Profile fields, memory
metadata, tool arguments/results, body commands/events and communication
envelopes must converge away from `Any`, unconstrained dictionaries and dynamic
role-dependent shapes. Pydantic models remain the machine-readable contract;
the repository does not maintain duplicate JSON Schema files.

Technical failures are translated into stable Elfie errors or typed receipts at
the Adapter boundary. External calls state timeout, cancellation, retry,
idempotency and terminal-receipt semantics. Bootstrap constructs scoped views,
owns container object lifetimes and registers cleanup; only
`app/orchestration/lifecycle` decides and coordinates system Runtime component
start, stop or restart. Elfie owns only its internal aggregate start/stop/join
order and may close a Port only when the injected lifecycle contract explicitly
gives that Elfie exclusive ownership. It never starts or stops Core, Gateway,
Godot authority or a shared Adapter resource.

## Dependency rules

```text
Elfie Facade -> Profile + private coordination
private coordination -> Brain + NervousSystem + Body + Communication
Brain -> its own Food/Model/Tool/Memory Ports
NervousSystem -> Body semantic contracts and Brain perception Port
Communication -> its own channel Port and Brain perception Port
Profile -> its own persistence Port
Infrastructure -> only the Elfie Port it implements
```

`elfie/` never imports `app`, `nest`, `ai_runtime`, `godot_runtime`, concrete
`infrastructure`, platform SDKs or product data-root resolvers. Technical Adapter
packages may import the Elfie Port and model they implement; this is dependency
inversion. Elfie submodules must not form import cycles.

## Testing and migration ratchet

Brain, Memory, NervousSystem, Body and Communication tests use typed fakes or
in-memory Ports. They do not require SQLite, mutable YAML user storage, network,
Godot or physical devices. Infrastructure Adapters receive focused integration
tests; Bootstrap receives assembly tests; every completed production body or
channel Adapter family has at least one real end-to-end path.

Migration is incremental and follows the repository governance contract. Each
slice fixes one complete boundary: freeze the owner and models, define the
consumer Port, implement and inject the Adapter, migrate every production
caller, remove the old implementation and compatibility path, then close the
matching conformance gap. Existing system baselines only shrink; this contract
does not create a second legacy baseline.

Recommended order is: public Facade and boundary inventory, Brain Skills,
Food/Model/Tool Ports, Memory persistence, Profile persistence, Body technical
Adapters, Communication platform Adapters, then final Factory and public-export
cleanup. A slice must remain runnable and keep one active authority for every
fact.

## Explicitly rejected designs

This contract rejects a flat package where every submodule imports every other,
one universal `ElfiePort`, one Protocol per helper, a generic Runtime proxy,
technical Body or channel SDKs inside Elfie, App Orchestration proxying ordinary
cognition, multiple active persistence writers, compatibility aliases, fallback
reads and a Service Locator hidden in `ElfieFactory`.
