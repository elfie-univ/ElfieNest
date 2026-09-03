# System architecture contract

**Contract version:** 1.10
**Adopted:** 2026-08-12
**Revised:** 2026-09-02
**Scope:** repository-wide target architecture
**Macro architecture baseline:** v1 (frozen)

> **Normative target.** This contract defines the final module ownership,
> dependency direction and system-level Ports/Adapters for ElfieNest. It is the
> authority for root modules. The retired general system baseline remains at
> zero; active child-contract implementation gaps are named in their registered
> conformance files. Permanent scanners and architecture tests enforce all
> currently machine-checkable parts of this target.

The system contract governs root placement and cross-module boundaries. The
Application contract governs behavior inside `app/`. The Model, Food and tool
behavior contract remains only a behavior inventory for the current migration
package; it does not define a target module and cannot reverse this contract.
Where a child contract names an owner or path, this contract controls the
system-level target.

The [Nest–Godot semantic-world contract](./nest-godot-semantic-world) refines
Nest internal ownership, Godot semantic lanes and embodied-world event routing.
It cannot reverse the root dependency direction or physical authority fixed
here.

The [Configuration management contract](./configuration-management) refines
the non-Python bundled-default root, user configuration root, typed loading
boundary and release packaging. It cannot transfer semantic ownership from App,
Elfie, Nest or an Infrastructure capability to the filesystem.

The [Service lifecycle contract](./service-lifecycle) refines authoritative
Runtime tiers, entrypoint semantics, managed-process ownership, model-health
projection and convergence. It cannot move lifecycle authority out of
`app/orchestration/lifecycle` or grant process authority to evidence readers.

## Target system shape

ElfieNest converges on four top-level Python production ownership modules:

```text
app/                 product entry, use-cases, orchestration and composition
elfie/               one complete Elfie domain core
nest/                the Nest world-semantics domain core
infrastructure/      external-system, persistence and platform adapters
```

One running ElfieNest system always has exactly one Nest.

`config/` is a top-level non-Python source-resource root for the bundled
declarative defaults registered by the Configuration Management contract. It is
not a fifth production ownership module or a writable runtime directory.

`elfie/` and `nest/` are the central domain layer. `app/` is above them and
turns user or operator intent into product use-cases. `infrastructure/` is below
them and implements model access, tool execution, Godot integration,
persistence, devices, external communication, filesystem, network, process and
operating-system capabilities required through typed Ports.

`godot_project/` remains a separate Godot source project and runtime authority.
It is not a fifth Python ownership module and is never moved under
`infrastructure/`. Python-side hosting, protocol and Adapter code belongs to
Infrastructure; Godot assets, physics, navigation, collision and rendering stay
in `godot_project/`.

The target Infrastructure is organized by capability, not as an unowned
miscellaneous directory:

```text
infrastructure/
├── models/           Provider discovery, validation and model-call adapters
├── tools/            search, workspace-file and sandbox execution adapters
├── godot/            Gateway, authority host, artifacts and protocol adapters
├── persistence/      database and durable-file adapters
├── devices/          external-body and device transports
├── communication/    external channel adapters
└── platform/         filesystem, clock, process and operating-system adapters
```

Infrastructure Adapters may be internally complex: they may own protocol state,
connection pools, retries, timeouts, process control, sandboxing and technical
validation. They do not own Elfie cognition, Nest rules, product authorization
or administrator workflows.

Infrastructure capability packages do not import or construct another
capability's concrete Adapter. When one capability needs another, it depends on
a narrow Port or shared technical model and Bootstrap supplies the concrete
implementations.

The former `ai_runtime/`, `godot_runtime/` and `app/infrastructure/` roots have
been retired. Their technical responsibilities now live in the existing target
Infrastructure capability packages; no target `infrastructure/ai_runtime/` was
created. Concrete technical I/O must not be restored inside `elfie/` or `nest/`.

## System dependency direction

```text
App Interfaces/Use-cases/Orchestration
          |                         |
          | inbound facade          | App-owned outbound Ports
          v                         v
   Elfie Core + Nest Core -----> Infrastructure Adapters
          |                         |
          | core-owned Ports        v
          +-----------------> databases, models, Godot,
                               devices, channels and OS
```

The left path is a product or cross-authority call into an Elfie/Nest facade.
The right path is an App Feature or Orchestration capability such as account
persistence, a clock, a secret store or a managed external workflow. App does
not route those capabilities through Elfie or Nest merely to preserve a
layered drawing.

Source-code dependencies follow dependency inversion:

```text
app              -> public Elfie/Nest facades and boundary models
infrastructure   -> App/Elfie/Nest Ports it implements
app/bootstrap    -> all concrete construction targets, for wiring only
elfie            -X-> app, nest or concrete infrastructure
nest             -X-> app, elfie or concrete infrastructure
```

These directions govern effective dependencies as well as imports. Launching a
repository module by module name, executable script, subprocess, child process,
shell command or dynamic loader is an edge from the caller's owner to the
target's owner. Moving a forbidden module name from an import into a command
string does not change or hide that edge. Developer Tools may depend on public
product boundaries for isolated experiments; production roots and product
entry scripts never target `devtools/`.

Runtime calls may travel from a core through an injected Port to an Adapter.
That does not authorize the core to import, construct, configure or inspect the
concrete Adapter.

`elfie/` and `nest/` never import one another. `app/orchestration/` owns only
workflows that compose real Elfie instances with Nest state or cross two or
more authorities. An ordinary Food lookup, model call, file read or tool
execution through one Elfie's injected Ports is not Orchestration.

## Inbound facades and explicit Ports

A stable, typed public facade can itself be an inbound Port. `Elfie`,
`ElfieFactory` and `Nest` do not require duplicate `ElfieInboundPort` or
`NestInboundPort` Protocols merely for naming symmetry.

An explicit inbound Protocol is introduced only when at least one real need
exists: multiple implementations, independent versioning, a process boundary,
caller isolation that a facade cannot provide, or reusable test doubles at the
boundary. Importance alone is not a reason to duplicate a facade.

Inbound and outbound Ports are not pairs. A core owns as many of each as its
actual offered use-cases and required external capabilities demand.

## System-level outbound Ports

System-level Ports express semantic capabilities and never expose a technical
product name, transport frame, database row, path or SDK object.

### Elfie

Elfie keeps its profile, cognition, emotion, memory semantics, skills,
communication semantics, body contracts and lifecycle. Its system-level
required capabilities include:

- reading its effective model bundle through a narrow `FoodPort`;
- model generation through a narrow `ModelPort`;
- executing approved tools through a narrow `ToolPort`;
- replaceable body execution and perception through `BodyPort` and a narrow
  actor-body transport contract;
- external communication channels through typed channel contracts;
- semantic storage contracts for private profile and memory facts.

Infrastructure persistence implements `FoodPort`; Infrastructure model
Adapters implement `ModelPort`; Infrastructure tool Adapters implement
`ToolPort`. Bootstrap injects those implementations directly into Elfie. Elfie
does not import App or Infrastructure and does not execute SQL itself. Memory
algorithms, semantic model-role choice, Skill declarations and allow-lists,
body commands and perception models remain in Elfie.

### Nest

Nest has four internal functional owners: Space and Facilities, Household
Living Rules, Time and Environment, and Elfie–Nest Interaction. A common event
mechanism crosses those owners without becoming a fifth business module. These
are conceptual ownership boundaries, not mandatory packages or processes.

Nest keeps resident IDs, homes, coordinate-free world semantics, household
rules, environment time and desired environment state. It also owns the
short-lived semantic correlation required for structured vision, virtual
hearing and semantic action. It does not own an Elfie's independent body intent,
physical calculation, real Elfie objects or concrete Godot transport. Its
required capabilities include:

- a technology-neutral Nest snapshot plus Facade export/restore semantics;
- persistence coordination through the App-owned Nest state-store Port when App
  Orchestration owns load/save/rollback/recovery timing;
- world-authority configuration and synchronization, environment commands and
  facts, and spatial query/action results through narrow semantic world Ports;
- typed Nest-event output with explicit targets after any household-audience
  rule has been applied.

Concrete SQLite, WebSocket, JSON transport, Godot bundle, environment and
process implementations belong to Infrastructure. Nest semantic models and
rules remain in Nest. Exact internal ownership and event semantics are governed
by the [Nest–Godot contract](./nest-godot-semantic-world).

### App

App Features may define their own outbound Ports for product persistence,
files, clocks, schedulers, secrets, platform probes and external workflows.
Infrastructure implements those Ports. App's internal Ports/Adapters structure
is a nested instance of this system architecture and is governed by the
[Application contract](./application).

## Authoritative facts and writers

Architecture ownership is not only directory placement. Every durable or
runtime fact has one semantic authority, one write path and explicit readers:

| Fact or decision | Semantic authority | Concrete write/execution owner | Allowed readers or coordinators |
| --- | --- | --- | --- |
| Accounts, sessions, roles and member preferences | App account Features | Infrastructure persistence through App-owned Ports | Authenticated App use-cases and authorized projections |
| Adoption, ownership and per-member quota decisions | App adoption Features | Infrastructure persistence through App-owned Ports | Admin/member use-cases; Nest capacity is an input, not a duplicate owner |
| Social relationships, conversation membership and user-visible message history | App communication Features | Infrastructure persistence through App-owned Ports | Authorized App use-cases; Elfie owns communication and memory semantics, not product conversation ownership |
| One Elfie's profile, cognition and memory semantics | `elfie/` | Infrastructure persistence through Elfie-owned Ports | The owning Elfie and explicitly authorized App projections |
| Nest residents, homes, facility semantics, household rules, environment time/intent and semantic interaction results | `nest/` | Nest Facade validates snapshots; App Orchestration coordinates persistence through its `NestStateStorePort`; Infrastructure implements storage | App Orchestration, affected Elfies through typed delivery and authorized Observer projections |
| Food package administration and global tool enablement | App configuration Features | Infrastructure persistence through App-owned Ports | Elfie receives only its effective typed projection through Elfie-owned Ports |
| Provider-connection administration and credential references | App configuration Features | Infrastructure persistence and secret Adapters through App-owned Ports | Authorized App management use-cases; Infrastructure receives only scoped technical inputs |
| Effective Food/model-health aggregate | App configuration Food Feature | App Food policy projects active packages and persisted evidence supplied through Ports | Lifecycle and authorized management/capability projections |
| Endpoint-model observations, technical validation and model calls | Infrastructure model capability | `infrastructure/models/` plus persistence/report Adapters | App management projections and Elfie `ModelPort` calls |
| Tool choice for one cognition step | `elfie/` Skills and cognition policy | `infrastructure/tools/` executes an approved bounded request | Elfie consumes the typed result; App configures global availability |
| House geometry, coordinates, collision, navigation and rendered physical events | `godot_project/` authority | Godot authority through `infrastructure/godot/` protocol Adapters | Nest receives world facts; an actor body receives its own receipts |
| Device enrollment, grants and Elfie/body association | App device Features | Infrastructure persistence through App-owned Ports | Authorized App use-cases and Orchestration |
| Device credential material | Infrastructure secret capability | Secret storage and `infrastructure/devices/` Adapters | App retains references only; the granted device Adapter receives scoped access |
| Device transport sessions and technical health | Infrastructure device capability | `infrastructure/devices/` | App health projections and the owning Elfie body contract within granted scope |
| Body commands and perception semantics | `elfie/body` | The injected body/device Adapter executes transport | The owning Elfie; Orchestration only for cross-authority workflows |
| Process lifecycle and technical readiness | `app/orchestration/lifecycle` | Lifecycle runners and technical probes constructed by Bootstrap | Owner/Observer health projections; business backlog is separate |

Infrastructure can physically store several facts in one database, but storage
co-location does not merge their semantic owners. No second module may infer a
new authoritative fact by copying, caching or projecting the same record.

## Model, Food and tool ownership

There is no target AI Runtime module. The former `ai_runtime/` package was
decomposed into the following owners:

| Responsibility | Target owner |
| --- | --- |
| Provider discovery, model lists, technical probes, request translation, streaming, retries and model calls | `infrastructure/models/` |
| Food administration, automatic package generation, model-management reports and global tool settings | App Features |
| Reading one Elfie's effective Food, selecting a semantic model role, deciding tool use and consuming results | `elfie/` through its Ports |
| Physical storage of Food/configuration and other durable facts | `infrastructure/persistence/` implementing the direct consumer's Port over the semantic owner's typed model; storage is not a second authority |
| Search, bounded workspace files, code sandbox and device-backed tool execution | `infrastructure/tools/` |

A normal inference path is direct:

```text
Elfie -> FoodPort -> Infrastructure persistence Adapter -> database
Elfie -> ModelPort -> Infrastructure model Adapter       -> Provider
Elfie -> ToolPort  -> Infrastructure tool Adapter        -> external capability
```

App manages configuration through Feature use-cases, but it is not a runtime
hop between Elfie and these Adapters. Orchestration enters only when a workflow
actually crosses Elfie, Nest, Godot, a device or another authority.

App configuration Features write Food visibility, grants, assignments and
package selection. The persistence Adapter resolves the effective projection
for the requested Elfie scope from those stored facts; it does not make a new
authorization decision. Elfie selects the semantic role and invokes
`ModelPort` separately.

### Body, Adapter, Transport and Gateway boundary

`BodyPort` is the Elfie-owned semantic contract for one selected actor body. It
describes registered capabilities, typed body commands, body-scoped sensor
events, proprioception, lifecycle binding and receipts; it contains no socket,
wire frame or vendor protocol. `NativeBody` (Godot) and `ExternalBody` (a
host-side remote-device proxy) are Infrastructure implementations of this same
Port, not additional domain bodies.

A Body Adapter maps the Port's semantic call to one target body's command
vocabulary. Transport is the Infrastructure connection/message-delivery
component used by that Adapter; it encodes, sends, receives and correlates
messages but does not choose capabilities or own physical truth. A Gateway is
needed when a real endpoint/session/authentication/routing boundary exists. It
owns that boundary and queues/routes messages; it is not a second BodyPort or a
decision layer. A device-specific driver is optional and may live beside the
Adapter; vendor translation should remain in the remote Device Agent/firmware
when the device owns it.

The remote physical path is therefore:

```text
Elfie BodyPort -> ExternalBody -> ExternalTransport -> DeviceGateway
  -> authenticated Wi-Fi/LAN -> Device Agent/firmware -> sensors/actuators
```

The return path reverses through the same boundaries. The remote Device Agent
is separate code running on the physical device; host-side Infrastructure code
is never assumed to be installed on the toy. The Godot path uses the same
semantic Port boundary with a Godot Adapter/Transport/Gateway and the
`godot_project/` authority.

## Godot authority semantic lanes

The Godot authority is reached through one shared, versioned and authenticated
Gateway connection, not one raw connection per Elfie. Sharing transport does
not merge semantic ownership. The boundary has three lane families:

1. **Actor body channel.** Brain emits one or more catalog-checked capability
   calls within a finite plan; NervousSystem validates them and submits them
   through the selected BodyPort.
   The Godot Adapter returns body-scoped perceptions and an action receipt to
   the originating Body. `ACCEPTED` and `STARTED` remain ledger states; the
   Brain-facing terminal set is `COMPLETED`, `REJECTED`, `FAILED`,
   `INTERRUPTED` or `TIMED_OUT` (`cancelled` is represented as `INTERRUPTED`
   with a reason). Known-target body traffic does not pass through Nest.
2. **Nest semantic-world lanes.** Semantic action, structured vision, virtual
   speech/hearing and environment commands/facts cross narrow Nest-owned
   capabilities. Godot supplies physical candidates or actual results; Nest
   supplies household meaning, rules, correlation and targeted semantic output.
3. **Runtime control channel.** Readiness, generation, connection, health and
   recovery belong to App Lifecycle and never become Nest or Body perception.

One physical cause may produce a body receipt, body perception and environment
fact, but these are distinct typed events with distinct recipients and a shared
cause identity. Body receipts and body perceptions return through Body and
NervousSystem; a targeted Nest semantic result enters the target Body input
boundary before NervousSystem. Runtime events are classified before delivery;
broadcasting a raw event to all Bodies or sending one semantic event through
both Body and Nest paths is forbidden. The semantic lanes may be implemented by
one shared Godot Gateway Adapter.

Godot protocol transport, authority-host selection, artifacts and process
launch belong to `infrastructure/godot/`. Godot source assets and physical
authority remain in root `godot_project/`. Nest and Elfie never import
Godot-specific transport or process implementations. The detailed path and
event rules are normative in the
[Nest–Godot semantic-world contract](./nest-godot-semantic-world).

## Bootstrap and Orchestration

`app/bootstrap/` is the only production composition root. It creates concrete
Adapters, constructs cores and services, injects Ports, owns container object
lifetimes and registers cleanup. Runtime component start, stop and restart
decisions and workflows belong exclusively to `app/orchestration/lifecycle`;
Bootstrap only constructs and invokes that public lifecycle boundary. Tests and
isolated development tools may construct fakes or sandbox containers without
becoming a second production composition root. Bootstrap contains no product
branch, world rule, protocol mapping or persistence logic.

`app/orchestration/` executes runtime workflows that cross authorities. It may
coordinate Elfie, Nest and injected capability contracts, but it does not
construct concrete Infrastructure, act as a Service Locator, or proxy ordinary
Food/model/tool calls. Bootstrap wires; Orchestration conducts.

## Persistence, tools and static resources

The component that directly consumes an external storage capability owns its
outbound Port; the semantic authority still owns its domain facts and models.
A domain therefore owns the Port when it directly loads or saves through that
capability. When App Orchestration owns load/save, transaction, rollback or
recovery timing, App owns the Port and may persist only snapshots accepted or
produced by the domain Facade. Infrastructure owns connections, SQL, schemas,
transactions, paths, serialization, atomic writes and technical records. No
database row, connection, raw dictionary or user path crosses a domain boundary.

Elfie Skills describe what a particular Elfie may request and remain in Elfie.
App Features own administrator-facing global enablement and configuration.
Search, file, code or device execution implementations belong to
`infrastructure/tools/` and remain subject to tool safety and bounded-result
contracts.

Registered application-level declarative defaults, including the current Brain,
species and Nest documents, live under root `config/` and are staged once as
`resources/config/`. Their semantic models remain with their App, Elfie, Nest,
Models or Tools owner. Product and domain code receive typed values and do not
resolve paths or parse those files directly. Algorithm invariants and narrow
startup-safety constants may remain in code but cannot duplicate registered
product defaults. User data, mutable configuration, Runtime state and generated
files use Infrastructure Adapters.

## Boundary models and errors

Every public facade and Port uses named, strict models owned by the boundary's
consumer or provider. HTTP DTOs, domain models, Port models, protocol frames and
persistence records are distinct. Mapping occurs in Adapters or
Orchestration, never through unvalidated `Any` or unconstrained dictionaries.

Infrastructure failures are translated into stable domain/application errors
before they reach a facade. Timeouts, cancellation, retry, idempotency and
receipt semantics are explicit for every external operation.

## Testing and change containment

Elfie and Nest unit tests use in-memory or fake Port implementations and do not
require SQLite, files, networks, devices or Godot. Infrastructure adapters have
focused integration tests. Bootstrap has wiring tests, and one real end-to-end
path proves each migrated cross-system capability.

An internal implementation change that preserves its facade and Ports remains
inside the owning module. Replacing a technology changes its Adapter. A system
Port change necessarily migrates the facade/consumer, Adapter and affected
callers together; architecture isolation reduces accidental cross-module
changes but does not hide a deliberate contract change.

## Change and enforcement

Governance-only changes remain separate from production implementation changes.
For each complete boundary change:

1. identify the current fact owner and complete call chain;
2. define or confirm the facade, Port and strict models;
3. implement the Infrastructure Adapter and Bootstrap wiring;
4. update every production caller;
5. delete the replaced technical implementation and compatibility path; and
6. prove the complete call chain with focused and end-to-end evidence.

All code follows this contract. The permanent system scanner runs in deny-all
mode without a legacy baseline. Any future temporary gap must follow the
repository governance contract and cannot weaken this contract implicitly.

## Deliberate non-goals

This contract does not require a Protocol for every facade or helper, one
Adapter per Port, one Port per method, a global generic repository, a Service
Locator, automatic dependency injection, microservices, full CQRS, Event
Sourcing or distributed transactions.
