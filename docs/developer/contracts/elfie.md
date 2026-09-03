# Elfie internal architecture contract

**Contract version:** 2.5
**Adopted:** 2026-08-11
**Revised:** 2026-09-03
**Scope:** `elfie/` and Infrastructure Port views scoped to one Elfie

> **Normative target.** This contract defines the life-system ownership,
> dependency direction, public Facades and outbound Ports of one complete Elfie.
> It refines,
> but does not change, the frozen [system architecture contract](./system). The
> the v0.2 structural implementation evidence is recorded in the
> [Elfie conformance register](../conformance/elfie). Supported-model behavior
> and existing-workspace policy remain separately tracked in the open
> [Selfhood conformance register](../conformance/elfie-selfhood). Permanent
> architecture gates remain authoritative after any temporary register is removed.

The system contract remains authoritative for root modules, system authority and
the final location of technical Adapters. This contract is authoritative inside
`elfie/`. The former `ai_runtime/` package has been retired; the model, Food and
tool behavior contract remains authoritative for the accepted behavior now
implemented by the target owners.

## Purpose and non-goals

`elfie/` owns one complete, independently testable creature: immutable external Profile,
continuous Brain, nervous-system processing, body semantics, digital
communication semantics, creation-time Genesis rules and its own internal
lifecycle. Internally it uses a lightweight nested Ports/Adapters shape so that
domain behavior does not depend on SQLite, YAML user storage, Provider SDKs,
Godot frames, device transports or communication-platform protocols.

This contract does not introduce a microservice, event bus, generic dependency
injection framework, universal repository, one Protocol per helper, or a second
App orchestration layer. It does not require a duplicate inbound Protocol for
the stable `Elfie` and `ElfieFactory` Facades.

## Aggregate shape

One Elfie is one aggregate and one internal lifecycle boundary; it is not a
system Runtime authority. Genesis runs before the ordinary aggregate lifecycle,
compiles creation-only inputs and commits sibling outputs to their final owners:

```text
CreatorWorldSkeleton -> ResidentKnowledgeBaseline -> GenesisSourcePackage --+
accepted adoption input -----------------------------------------------------+-> Genesis
                                                                                 |
                  +----------------------+----------------------+----------------+
                  v                      v                      v
               Profile               Selfhood                Memory
          external dossier        Brain identity       knowledge/people/events

--------------------------- successful creation commit ---------------------------

Elfie / ElfieFactory Facades
            |
            v
 Profile + private Brain coordination
              |          |             |
              v          v             v
            Brain   NervousSystem   Communication
              |          |             |
              |       BodyPort    CommunicationChannel
              |
              +--> FoodPort / ModelPort / ToolPort
              +--> MemoryStorePort

Profile ---------------------------> ProfileStorePort
```

The root Facade coordinates the submodules. Brain owns cognition and decisions;
it does not construct or import concrete Body, channel, model, tool or storage
implementations. `ElfieCognitiveRuntime` or its successor is private aggregate
coordination, not an App Runtime, Infrastructure Adapter or public product API.

## Internal module ownership

| Module | Owns | Must not own |
| --- | --- | --- |
| `elfie/profile/` | Immutable external objective identity, stable age/birth and personal-origin anchors, final virtual appearance and immutable appearance defaults | World knowledge/Canon, generator or model provenance, source-package references, seeds, user answers, arrival/training history, personality, memory, relationships, permissions, runtime limits, current capabilities/state, YAML/file persistence, user paths, App adoption or account rules |
| `elfie/brain/` | Event Workspace, Orientation, Selfhood, Emotion, Energy, Motivation, Memory, Reasoning Core, Persistent Activity, Cognitive Consolidation and trusted Agent Skills | Provider selection/configuration, SDK requests, concrete tool execution, device/channel transport or product workflow |
| `elfie/brain/memory/` | Memory nodes, relations, encoding, retrieval, consolidation and the semantic storage Port | SQLite connections, schema, paths or persistence records |
| `elfie/brain/reasoning/skill_port.py` | Typed Skill metadata/document contracts and the per-Run read-only load boundary | Skill source files, Runtime proxies, platform tools, workspace paths or tool execution |
| `elfie/nervous_system/` | Body-event normalization, filtering, reflexes, perception delivery and translation of validated body intents | Device transport, Godot protocol, geometry or body registration policy |
| `elfie/body/` | Body identity, capabilities, anatomy, commands, sensor events, receipts, candidate registry, switching and the single active binding | Concurrent virtual/physical authority, Godot/WebSocket/device transport, credentials, process ownership or device product authorization |
| `elfie/communication/` | Canonical envelopes, admission and delivery semantics, policy, inbox/outbox, Hub and channel routing | Product conversation authority/history, account membership, platform SDKs, credentials or network transport |
| `elfie/genesis/` | Creation-time semantic compilation, deterministic generation rules, validation and the ephemeral initialization bundle | Daily cognition, permanent duplicate state, technical Adapter construction, persistence implementation or lifecycle authority |

Skills are part of Brain because their procedural instructions influence cognition.
A Skill is a standard directory containing `SKILL.md` with `name` and `description`
frontmatter plus instructions; it is not a Tool definition and does not grant Tool
permission. Bundled sources live under `config/brain/skills/<name>/SKILL.md` and are
advertised as metadata before a native `load_skill` control operation loads one
document for the current Run. Shared executable Tool definitions and authorization
remain separate in the typed `ToolPort`/Infrastructure registry path.
Bundled Skills are read-only and first-party in this phase; user installation,
mutation, scripts and durable per-Elfie Skill state are outside this contract and
require a separate approved decision.

The Brain systems above are conceptual owners rather than a deployment model.
They do not imply ten processes, databases, workers or pre-created packages. A
system receives a directory only when the implementation gives it real state,
contracts or behavior; empty architecture-shaped packages are forbidden.

## Life-system invariants

- Profile answers the external objective question "which Elfie is this?" and is
  immutable after creation. Its semantic allowlist is stable identity, a stable
  age/birth anchor, immutable personal-origin identifiers/labels and final
  virtual appearance. Schema revision is technical metadata. It contains no
  world knowledge or Canon reference, generation source/version/seed, user
  answer, life event, relationship, personality, ability, permission, current
  body or runtime state.
- Genesis co-materializes Profile and Brain Selfhood, Memory and any other
  owner-specific startup seed from one validated bundle. Shared minimum identity
  values are checked as sibling outputs; neither Profile nor Selfhood is derived
  from or synchronized with the other after commit. Ordinary Brain runtime does
  not read or synchronize Profile; Selfhood's frozen `identity_core` supplies
  Brain identity and its `adaptive_self` may change only through a later approved
  Memory-evidenced path.
- A successful Genesis commit severs operational dependency on adoption answers,
  Canon/source packages, `LifeContext`, `PersonalGenesisPlan`, generation seeds
  and full manifests. Ordinary restore uses final-owner state. Source updates
  affect only future creations unless a separate migration or real learning event
  is approved.
- Elfie has two external lines: the embodied line through NervousSystem and Body,
  and the digital-message line through Communication. They may be active in the
  same period but never share an output authority inside one Turn.
- Brain receives `Communication`, `Embodied` and `Activity` events as exactly
  three source domains. Every admitted Turn has exactly one `SourceDomain`; its
  `ResponseScope` cannot be widened by model output.
- A body action outcome remains an external `Embodied` event and a message
  delivery outcome remains a `Communication` event. Activity events represent
  only Brain-owned cross-Turn work. Cross-domain consequences become a validated
  Activity request or a later Activity event and Turn. A chat
  Turn may request future embodied work, but cannot emit a body directive in the
  current Turn.
- Brain's external decision boundary accepts only communication directives,
  nervous-system directives and persistent-activity requests, or no-op. Model,
  Skill and Tool calls are internal cognitive operations.
- Several authorized body candidates may be registered, but virtual and physical
  embodiments are mutually exclusive. Outside an explicit switching transaction,
  exactly one selected body owns sensor and action authority. Headless is only a
  deterministic development/test substitute.

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
| `ToolPort` | Brain | Enforce the technical safety scope and execute one Brain-authorized semantic Tool request, or return a typed denial/bounded result |
| `MemoryStorePort` | Brain/Memory | Store and query typed memory nodes, edges and semantic search results |
| `ProfileStorePort` | Profile | Load and save a validated stable Profile without revealing YAML or paths |
| `BodyPort` | Body (consumed by NervousSystem and aggregate routing) | Expose one replaceable body's capabilities, commands, events, receipts and snapshot |
| `CommunicationChannel` | Communication | Connect one channel and deliver canonical envelopes with typed receipts |

Every injected Port exposes only the authorized scope of one Elfie. A concrete
Adapter may share a container-scoped connection pool, Provider client or Godot
Gateway behind several scoped Port views; shared technical lifetime never
exposes cross-Elfie queries and never transfers cleanup ownership into Elfie.
`ToolPort` therefore receives semantic resource identifiers rather than an
arbitrary filesystem path; a local-file request must carry the owning Elfie
scope and its scoped Adapter resolves the authorized root. Web-search requests
may omit the scope because they do not address Elfie-local resources.
`FoodPort` does not expose a general cross-Elfie query API. Boundary models use
domain language and never leak SDK objects, SQL rows, unvalidated dictionaries
or protocol frames.

## Food, model and tool cognition

Brain chooses a semantic model role and decides whether a proposed tool call is
allowed. `FoodPort` preserves the exact named-role, one optional fallback and
Emergency behavior defined by the model/Food/tool behavior contract; it does
not invent an arbitrary fallback list. `ModelPort` interprets opaque technical
model references and performs generation.

Skill instructions do not authorize Tool execution. Brain supplies an explicit
`allowed_tools` set for a deliberate Run; the `ToolPort` Adapter intersects that
request with global availability and the invocation's technical safety scope, may
return a typed denial, and can never broaden the capability authorized by Brain.
App configures availability but does not proxy the call.

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

## Brain cognitive ownership

The subordinate [Brain internal architecture contract](./brain) is authoritative
for Turn lifecycle, mental-state commits, bounded reasoning and Persistent
Activity semantics. This section fixes only their aggregate-level ownership.

Brain owns ten conceptual systems with distinct authority:

1. Event Workspace admits Communication, Embodied and Activity events into
   bounded, single-domain Turns.
2. Orientation maintains the sourced current snapshot of body, place, time,
   nearby people, conversation and active commitments.
3. Selfhood owns one atomic state with a creation-frozen `identity_core` and a
   slow `adaptive_self`. It supplies Brain's typed self and deterministic model
   projection without reading Profile or Canon during ordinary runtime.
4. Emotion maintains process-local, cross-Turn decaying affective state and
   returns to personality-derived baselines on sleep or process restart.
5. Energy maintains homeostasis, circadian state and cognitive/action budgets,
   including an emergency reserve and deterministic degradation.
6. Motivation turns fixed needs into attention, goal or Activity-trigger
   candidates; it never acts directly.
7. Memory owns subjective experience, knowledge, relationships, retrieval,
   forgetting and semantic consolidation.
8. Reasoning Core assembles Turn context and runs the bounded model/Skill/Tool
   loop, verification, inhibition and completion judgment.
9. Persistent Activity owns validated work that survives the current Turn,
   including waiting, wake-up, retry, cancellation, idempotency and receipts.
10. Cognitive Consolidation performs interruptible, budgeted, no-external-
    side-effect review during sleep or idle periods and emits only validated
    update candidates or a later Activity trigger.

Context assembly, decision governance, settlement, journal, checkpoint and
receipt reconciliation are required mechanisms inside or underneath these
owners, not additional peer mind systems. Authoritative state changes use a
candidate-validation-commit protocol; model text never directly rewrites
Profile, Selfhood, Memory, Activity or execution facts.

## Genesis

Genesis is a one-time creation flow, not a runtime organ and not a second Brain.
It consumes a published typed `GenesisSourcePackage`, accepted transient
adoption input and controlled randomness. `elfie/genesis/` owns every semantic
decision that turns those inputs into an individual: identity resolution,
life context, personal knowledge eligibility/mastery, people, relationships,
episode skeletons and owner-specific seed policy. Infrastructure may load the
typed package and persist the validated outputs through Ports, but it must not
make any of those decisions.

Genesis co-materializes Profile and Brain Selfhood plus Genesis Memory and any
other explicitly owned startup seed in one ephemeral bundle. Profile and
Selfhood are sibling final-owner outputs rather than a runtime synchronization
pair. Their shared minimum identity facts are validated together; any conflict
or partial commit fails resident admission. Memory receives the Elfie's actual
initial knowledge, people, relationships and episodes. Departure, training,
arrival and adoption are episodes, not Profile fields. A model may render
bounded non-authoritative wording from an already fixed plan; model text cannot
change structured facts or become a second recall source.

`identity_core`, initial `adaptive_self` and the application-wide reasoning
constitution are not freely generated model prose. They use reviewed,
deterministic typed mappings and templates. Genesis cannot bind Selfhood to a
Canon version, remain available to ordinary Brain context, or directly choose
permissions, available channels, device abilities, tool scope, model budget or
real account bindings.

Accepted questionnaire answers, `LifeContext`, `PersonalGenesisPlan`, source
package bindings, generation seeds and model projection inputs are temporary.
They may exist only inside a bounded in-flight admission transaction and are
deleted after successful commit or terminal abort. A minimal technical receipt
outside Profile may preserve output identity/digest, schema/generator revision,
completion time and idempotency result; it contains no answers, world knowledge,
replay seed or complete life plan. A committed Elfie is backed up and restored
from its Profile, Selfhood, Memory and other final-owner state, never regenerated
from that receipt or an old source package.

## Body candidates and one active body

An Elfie may register authorized virtual and physical body candidates. Every
candidate has a stable `BodyId`, capability revision and independent technical
lifecycle, and implements the same `BodyPort`. Registration makes a candidate
available; it never grants concurrent sensor or action authority.

`BodyRegistry` owns the available body instances and `BodyBinding` owns the
explicit selected-body relationship. Virtual-active and physical-active states
are mutually exclusive. A switch is an explicit transaction with generation,
rollback and recovery semantics; stale events or receipts from an earlier body
generation cannot regain authority. Commands and authoritative perceptions are
accepted only for the selected body and always carry `BodyId`.

The Registry contains only Adapter views already discovered, granted and
associated by App Device use-cases. Connection or health state does not grant,
associate or bind a body. Non-selected-body events may be retained as diagnostic
facts but cannot update current Orientation or trigger ordinary embodied action.

`BodyPort` is the stable aggregate boundary. Narrow sensor and actuator
Protocols may exist inside a body implementation when they provide real
testability, but callers do not receive a duplicate family of public body APIs.

Body commands, sensor events, capabilities and lifecycle receipts remain in
`elfie/body/`. A deterministic pure-domain reference body or test fake may stay
with domain tests; Headless is not a third product embodiment. Product hosting
and all Godot transport, device sessions, Bluetooth/LAN, credentials and process
control belong to Infrastructure. App Device features own discovery, enrollment,
authorization and Elfie/body association; cross-authority hosting, switching or
return-to-Nest workflows belong to App Orchestration.

The Body channel carries actor-scoped commands, perceptions, proprioception and
receipts. Direct body traffic returns through the owning Body and NervousSystem
and does not pass through Nest. Authoritative house geometry, coordinates,
collision/navigation and global interaction meaning enter Nest through the World
channel; when Nest produces a targeted semantic result, Orchestration injects it
at the target Elfie's Body input boundary, after which it follows NervousSystem
to Event Workspace. A shared Godot Gateway may back both scoped views, but it
does not merge their authorities and `BodyPort` does not bypass Nest's world
semantic authority.

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
not collapsed into one generic input channel. NervousSystem accepts ordinary
commands and perceptions only for the selected body generation; deterministic
low-latency safety reflexes remain here rather than entering an open model Turn.

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
idempotency and terminal-receipt semantics. `ACCEPTED` and `STARTED` are ledger
states; the Brain-facing body result is one of `COMPLETED`, `REJECTED`, `FAILED`,
`INTERRUPTED` or `TIMED_OUT`. Bootstrap constructs scoped views,
owns container object lifetimes and registers cleanup; only
`app/orchestration/lifecycle` decides and coordinates system Runtime component
start, stop or restart. Elfie owns only its internal aggregate start/stop/join
order and may close a Port only when the injected lifecycle contract explicitly
gives that Elfie exclusive ownership. It never starts or stops Core, Gateway,
Godot authority or a shared Adapter resource.

## Dependency rules

```text
Creator/Resident sources -> published GenesisSourcePackage -> Genesis
transient adoption input -------------------------------> Genesis
Genesis -> Profile + Selfhood + other owner seeds + Genesis Memory
successful commit -X-> questionnaire / LifeContext / plan / source package
Elfie Facade -> Profile + private Brain coordination
private Brain coordination -> Brain + NervousSystem + Body + Communication
Brain -> its own Food/Model/Tool/Memory Ports
ordinary Brain -X-> Profile / Canon
NervousSystem -> Body semantic contracts and Brain perception Port
Communication -> its own channel Port and Brain perception Port
Profile -> its own persistence Port
Infrastructure -> only the typed loader or Elfie Port it implements
Infrastructure -X-> semantic life compilation
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

The current Genesis/Profile migration removes generation provenance, choices,
capability/arrival facts and Canon projections from Profile; moves every
personal knowledge, relationship and episode decision out of Infrastructure;
and deletes creation-only inputs after commit. The Selfhood migration also
removes every Profile/Canon projection owned by Selfhood, ordinary
Profile/Canon Brain input, Profile-derived fallback, Memory-owned authoritative
self narrative and generic-checkpoint Selfhood copy. Contract text tests protect
the targets during migration; permanent runtime scanners and behavior/restart
tests replace them as implementation rows close.

The Ports/Adapters migration accepted by ADR-0005 is complete and remains a
permanent boundary. Life-system implementation now proceeds as independently
accepted vertical slices: Brain Kernel and communication loop, Reasoning Core,
virtual embodied loop, continuous life state and Profile transfer, Persistent
Activity, Motivation, then Cognitive Consolidation and Genesis completion. A
slice must remain runnable, keep one active authority for every fact, delete the
path it replaces and provide one visible result, one boundary attack, one
failure/restart check and an explicit non-goal.

## Explicitly rejected designs

This contract rejects a flat package where every submodule imports every other,
one universal `ElfiePort`, one Protocol per helper, a generic Runtime proxy,
technical Body or channel SDKs inside Elfie, App Orchestration proxying ordinary
cognition, multiple active persistence writers, compatibility aliases, fallback
reads, simultaneously active virtual and physical bodies, an empty package per
conceptual Brain system, Genesis as a daily runtime, and a Service Locator hidden
in `ElfieFactory`. It also rejects ordinary Brain reads of Profile/Canon, a
Canon-version-bound Selfhood, Memory as a second identity/personality owner,
Profile as a creation ledger or world encyclopedia, persisted adoption
questionnaires/replay seeds, silent regeneration of committed Elfies, and
semantic life compilation inside an Infrastructure Adapter.
