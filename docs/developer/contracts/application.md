# Application architecture contract

**Contract version:** 1.8
**Adopted:** 2026-08-14
**Scope:** `app/` and App-owned adapters in root `infrastructure/`

> **Normative target.** This document is the long-term architecture authority
> for code under `app/`. It defines ownership, dependency direction and boundary
> semantics. The registered App migration debt is closed; permanent scanners and
> architecture tests enforce this target directly. The English and Chinese files
> are language mirrors and change together.

The authority order is:

1. this versioned contract defines the architecture;
2. `app/AGENTS.md` summarizes the contract for implementation work;
3. child `AGENTS.md` files may refine local rules but may not reverse this contract;
4. architecture tests enforce machine-checkable parts;
5. temporary gaps require a registered conformance entry and never grant a new
   exception.

A deliberate change to ownership or dependency direction requires an explicit
contract-version change before implementation. Ordinary implementation work does
not rewrite the target.

## Goals and deliberate non-goals

The application layer uses a lightweight Ports-and-Adapters structure so that
product rules do not depend on FastAPI, SQLite, files, devices or model-platform
implementations. The intent is clear ownership, replaceable technical edges,
testable use-cases and one composition point—not architectural ceremony.

This contract does **not** introduce microservices, a general event bus, full
CQRS, Event Sourcing, distributed transactions, a generic repository, an
auto-discovered dependency-injection framework or a Port for every helper
function. Those mechanisms require a separate demonstrated need and approval.

The [system architecture contract](system) controls physical top-level
placement. Production Adapters now live under root `infrastructure/`; the
retired `app/infrastructure/` path must not be restored.

## Four App areas and their Infrastructure adapters

| Area | Owns | Must not own |
| --- | --- | --- |
| `app/interfaces/` | HTTP, WebSocket, CLI, Web and Desktop protocol entry; credential parsing; request/response mapping; protocol error mapping | Product rules, SQL, data-root resolution, concrete repositories, Runtime authority |
| `app/features/` | Product use-cases, authorization, commands, queries, results, business errors and the Ports required by those use-cases | FastAPI, SQLite, concrete adapters, process/thread ownership, cross-authority Runtime flows |
| `app/orchestration/` | Workflows crossing two or more authorities, non-atomic external side effects, and Runtime lifecycle coordination | Ordinary CRUD, protocol DTOs, concrete persistence/device adapters |
| `infrastructure/` | Port implementations for persistence, files, network, model platforms, devices and operating-system facilities | Product authorization, page behavior, use-case sequencing |
| `app/bootstrap/` | The composition root: construction, injection, object lifetime, startup and shutdown wiring | Business branches, SQL, protocol mapping, a second configuration source |

The four App-owned areas are Interfaces, Features, Orchestration and Bootstrap.
Root Infrastructure is the separate Adapter layer used by them; it is shown in
the table because the App dependency contract must define that edge explicitly.

## Target App business and workflow map

The following directory map is normative for App code. It freezes ownership;
it does not require empty directories to exist before a real capability needs
them.

```text
app/features/
├── accounts/
├── adoption/
├── communication/
├── elfies/
├── nest_management/
├── configuration/
│   ├── providers/
│   ├── food/
│   ├── capabilities/
│   └── settings/
├── setup/
├── bodies/
└── operations/

app/orchestration/
├── lifecycle/
├── nest_session/
├── resident_admission/
├── setup_installation/
├── message_delivery/
├── embodiment/
└── observer/
```

The Feature owners are:

| Feature | Owns | Explicitly does not own |
| --- | --- | --- |
| `accounts` | accounts, sessions, passwords, roles, member profiles, member administration and preferences | adoption decisions, Runtime lifecycle or protocol authentication DTOs |
| `adoption` | candidates, adoption and ownership relations, per-member quota overrides and final adoption eligibility | Nest bed capacity, Elfie profile facts or live Nest admission |
| `communication` | product conversation relations and user-visible message history already supported by the product | Elfie communication/memory semantics, transport sessions or live delivery coordination |
| `elfies` | authorized Elfie directory, relationship/permission projection and authorized member/admin profile or cognition views | Elfie profile, cognition or memory facts; adoption ownership; Nest resident state |
| `nest_management` | authorized product use-cases over the single public Nest facade | a second Nest repository semantic, geometry, coordinates or live Elfie composition |
| `configuration/providers` | Provider connection administration, credential references and model-resource management projections | technical model discovery, probes, request translation or model calls |
| `configuration/food` | Food package administration, assignments, generation and management reports | one Elfie's semantic model-role choice or physical storage implementation |
| `configuration/capabilities` | existing administrator-facing global tool and capability enablement | tool execution, Elfie Skill policy or speculative new capabilities |
| `configuration/settings` | other existing global product settings with one typed owner and writer | Nest capacity, Provider/Food facts or arbitrary untyped sections |
| `setup` | first-install draft, choices, validation, status and restricted projections | account, Provider, Food or Nest facts and installation task ownership |
| `bodies` | external-body enrollment, pairing, revoke, grants and Elfie/body association | credential material, device transport sessions, body semantics or hosting/homing workflows |
| `operations` | existing authorized system statistics, maintenance, backup/reset use-cases and stable Runtime management projections | Runtime lifecycle decisions, Observer sessions, raw technical objects or duplicate business facts |

### Species availability and adoption

The immutable species registry in `elfie/profile` is the only authority for
which species the product supports. A species is available to Adoption when its
registry definition is enabled and its joined canon, appearance profile and
runtime resources pass registry validation. Adoption reads that registry
directly for options and eligibility, so adding a complete registry entry makes
the species available to existing installations without an administrator write
or a per-Nest approval.

`configuration/settings` owns mutable global rules such as quotas and
personality preset switches. It must not expose, persist or enforce a species
allowlist such as `allowed_species_ids`; settings changes cannot remove or add
species. A staged rollout, if ever required, must be designed as a separate
explicit release contract rather than reusing an administrator settings field.

The acceptance invariant is: with an unchanged existing settings document,
adding a valid enabled species to the registry causes `GET /api/v1/me/adoption`
to list it and candidate creation for it to succeed.

The Orchestration workflows are:

| Workflow | Coordinates |
| --- | --- |
| `lifecycle` | Core, Gateway and Godot-authority start, stop, restart, recovery and readiness |
| `nest_session` | the one Nest, real Elfie instances, world events and the shared Godot world channel |
| `resident_admission` | an accepted adoption, Elfie construction, Nest admission and explicit failure compensation |
| `setup_installation` | Setup state with Accounts, Provider/model, Food, Nest and managed installation runners |
| `message_delivery` | an authorized conversation command, user-visible history, live Elfie delivery and receipts |
| `embodiment` | a real Elfie, Nest and external body for hosting, homing, switching and recovery |
| `observer` | scoped Observer principals/capabilities, authorized projections and allowed high-level intents |

These are not one-to-one layer mirrors. Accounts, configuration, Elfie
projections, Nest administration and operations stay in Features unless a real
flow crosses authorities. Browser HTTP and same-origin WebSocket remain App
Interfaces; `infrastructure/communication/` implements external communication
Ports and does not absorb API protocol ownership.

The target versioned API code is organized under `app/interfaces/api/v1/` by
`auth`, `setup`, `me`, `elfies`, `admin`, `observer` and `realtime` resource
areas. Admin resources are organized by `users`, `elfies`, `nest`,
`model_providers`, `food_packages`, `settings` and `runtime`. Physical Python
directory names use snake_case while public URLs follow the API contract's
kebab-case rules. `/api/health` remains the sole unversioned technical probe.

`app/bootstrap/` remains one composition root and has no business-domain mirror
requirement. Each vertical capability slice adds only the wiring it needs.

There are two application planes. `features/` handles product use-cases that can
be reasoned about inside one business authority. `orchestration/` coordinates a
flow when it crosses authorities such as `elfie/`, `nest/`, Godot, a device or a
managed process. A flow is not orchestration merely because it has several
function calls. Reading Food or invoking a model/tool through one Elfie's
injected Ports is explicitly not an App orchestration flow.

## Allowed dependency direction

```text
interfaces    -> Feature public use-cases / Orchestration public facades
features      -> owned models and Ports + approved domain public APIs
orchestration -> application Ports + elfie / nest public APIs
infrastructure-> implements Feature / Orchestration Ports + technical libraries
bootstrap     -> all areas, for wiring only
```

The detailed matrix is:

| From | May depend on | Forbidden direction |
| --- | --- | --- |
| Interface | public Feature and Orchestration APIs; protocol libraries | Infrastructure implementation, Bootstrap, another Interface's private implementation |
| Feature | its own models and Ports; another Feature's public facade; approved public domain APIs | Interface, Bootstrap, concrete Infrastructure, another Feature's internals |
| Orchestration | public Feature contracts, orchestration-owned Ports, public `elfie`/`nest` APIs | Interface, Bootstrap, concrete Infrastructure |
| Infrastructure | Feature/Orchestration contracts it implements; technical libraries | Interface, Bootstrap, product rules or private Feature internals |
| Bootstrap | all construction targets | Any product decision beyond wiring and lifecycle |

The matrix applies to effective dependencies, not only Python imports. A CLI,
Desktop, API or Web entry cannot bypass its Interface boundary by launching a
forbidden repository module through `python -m`, a script path, subprocess,
Node child process, shell command or dynamic loader. A resolvable process target
is checked as though the caller imported that target directly. Variable launch
plans belong behind an injected Port or in Bootstrap; putting a module name in a
string is not dependency inversion.

No App layer may form an import cycle. A Feature exposes its stable use-cases and
boundary models through its package facade; another Feature or Interface does
not import its internal service, helper or repository module. Bootstrap may
import concrete construction targets but cannot become a callable service
locator used by product code.

## Feature shape and Port ownership

A migrated Feature normally contains:

```text
app/features/<domain>/
├── __init__.py      # stable public facade
├── models.py        # commands, queries, results and value objects
├── ports.py         # Protocols needed by this domain
├── errors.py        # stable business errors
└── service.py       # use-case implementation
```

This is a responsibility map, not a requirement to create empty files. Small
domains may combine files while preserving the same boundaries.

The consumer owns a Port. A Feature defines the persistence, clock, task,
external-service or device capability it needs; Infrastructure implements it;
Bootstrap injects that implementation. Create a Port only for an external fact,
replaceable technical capability or side-effect boundary. Pure calculations and
private helpers stay ordinary typed functions.

An adapter must not broaden the Port into a second business API. Repository
records are adapter-internal. A Repository may express fact storage and queries,
but it may not decide whether an administrator is allowed to adopt an Elfie or
which page should display a field.

### External bodies and devices

The external-body concept, commands and perception contracts belong to
`elfie/body`. Product enrollment, list, revoke, grants and Elfie/body
association belong to an App Feature. Credential material, LAN transport,
device sessions and technical health belong to secret and
`infrastructure/devices` Adapters;
App stores references rather than credential material. Hosting, return-home,
offline and body-switching flows belong to Orchestration when they coordinate
the real Elfie, Nest and device. Persistence implements the owning Feature or
Orchestration Port, and Bootstrap wires the graph. Device transport is not
itself the product workflow or an authorization authority.

## Models at every boundary

Each boundary has an explicit model with one owner:

- Interface DTO: validated HTTP/WS/CLI input and output;
- Feature command/query/result: product intent and projection;
- Principal/RequestContext: authenticated identity and request metadata;
- Port model: the minimal data required across a technical boundary;
- persistence record: database representation, private to its adapter;
- domain public model: a type exported by `elfie` or `nest`.

FastAPI Request objects, SQLite connections/rows, ORM records and unvalidated
dictionaries do not cross these boundaries. Public boundaries do not add
`Any`, `Dict[str, Any]`, role-dependent shapes or unchecked casts. Pydantic is
used where external data or configuration must be validated; internal models
may use dataclasses, Protocols, Enums and value objects. Code models—not a
second handwritten JSON Schema—are the contract source.

New and migrated domains use strict MyPy checking. Existing global type debt is
reduced domain by domain; it is not an excuse to add loose types to a migrated
boundary.

## Identity, authorization and errors

The Interface authenticates credentials and constructs a strict Principal. The
Feature authorizes the requested use-case and resource relationship. UI hiding,
route naming and a client-supplied user or Elfie ID are never authorization.

`user`, `setup`, `admin`, `observer` and `device` principals are separate,
minimal-capability types. Device and Observer credentials never reuse Owner or
Runtime-authority credentials. A RequestContext may additionally carry a
correlation ID, locale and safe client metadata; it does not become an arbitrary
request bag.

Features and Orchestration return typed results or raise stable business
errors such as validation, not-found, conflict, forbidden, unavailable and
retryable-external-failure. Interfaces map them to protocol status and the
versioned error envelope. Infrastructure exceptions are translated at the
adapter/use-case boundary and are not exposed directly to callers.

## Commands, queries and consistency

ElfieNest uses lightweight command/query separation, not full CQRS:

- commands change authoritative facts and use a command service plus write Port;
- queries read authoritative facts or an explicitly derived projection and use
  a query service plus query Port;
- a read operation does not silently repair, migrate or create product state.

Three consistency classes are explicit:

1. **Database transaction.** One use-case owns a Unit of Work. Repositories do
   not hide commits that break a multi-step invariant. SQL remains inside the
   approved persistence boundary.
2. **Typed file update.** One writer owns a validated document, writes a
   temporary file and atomically replaces the target. There is no dual write or
   fallback fact source.
3. **External workflow.** Network, model, Godot and device operations use
   durable workflow state where required, an idempotency key, timeout, receipt
   and explicit compensation/recovery. They are not presented as a database
   transaction.

A database transaction must not wait for a network, model, Godot or device
response. Persist intent, finish the transaction, perform the external action,
then persist its receipt or failure according to the workflow contract.

## Lifetimes, asynchronous work and reliability

Bootstrap owns production-container object lifetimes and generic cleanup:

| Lifetime | Typical objects |
| --- | --- |
| Process/container | application container, gateways, stateless services, schedulers |
| Request/use-case | Principal, RequestContext, Unit of Work, write/query adapters |
| Connection | WebSocket session and connection-scoped buffers |
| Job/task | cancellation token, progress, receipt and durable task state |

Features do not start threads, processes, infinite loops or unowned
`asyncio.create_task` jobs. A Scheduler/Runner Port owns background work and its
shutdown behavior. Runtime process start, stop and restart decisions and
workflows remain exclusively in `app/orchestration/lifecycle`; Bootstrap only
constructs and invokes that public boundary. Tests may construct fakes without
becoming a second production composition root.

Ports state whether they are synchronous or asynchronous. Async Interfaces do
not perform long blocking work on the event loop. Cross-boundary calls have
explicit timeouts. Retries are limited to classified retryable and idempotent
operations, use bounded backoff, and preserve one correlation/idempotency ID.
Long work returns a stable `task_id` with status-query, failure, cancellation,
timeout and process-restart semantics.

## Configuration, secrets, cache and observability

Every configuration document has one typed owner, one precedence order and one
writer. A Feature requests configuration through a Port; it does not resolve
`ELFIE_HOME` or read YAML/SQLite directly. Secrets travel only as secret
references or through a dedicated Secret Port and never enter normal DTOs,
logs, reports or caches.

A cache declares its authoritative source, key scope, invalidation trigger,
maximum lifetime and rebuild path. A cache cannot become a second fact source.

Requests, jobs and external workflows carry correlation IDs through Port calls
and safe structured logs. Logs identify the use-case and outcome without
recording passwords, tokens, API keys, complete device credentials or private
content. Health reports technical readiness; business backlog belongs in event
or product projections.

## Composition and API mapping

The composition root creates concrete adapters, builds Feature services and
Orchestration facades, and injects those objects into HTTP/WS/CLI/Desktop entry
points. Routes and dependency functions do not instantiate repositories,
registries or stores. Setup and Admin may expose different projections of one
capability, but they reuse the same Feature and Adapter rather than duplicating
facts or algorithms.

The API-specific resource, versioning and DTO rules are refined in
`app/interfaces/api/AGENTS.md`. The App contract remains authoritative for
dependency direction and ownership.

## Machine enforcement and change acceptance

`scripts/architecture/app_layer_scan.py` scans the dependency graph, Feature
isolation, composition boundary, route model requirements and selected public
typing rules. `test/architecture/test_app_layer_boundaries.py` protects that
scanner and the surrounding contract. The scanner runs permanently in deny-all
mode without a legacy App baseline; every detected entry fails.

`scripts/architecture/effective_dependency_scan.py` also scans repository-owned
Python, Node, Godot and shell execution surfaces for resolvable dynamic module
and script targets. It reuses this contract's dependency matrix, has no legacy
baseline and runs permanently in deny-all mode.

The repository-level change process, temporary-debt lifecycle and base-branch
ratchet are defined by the
[repository architecture governance contract](./repository-governance). This
contract defines the App target; it cannot approve its own machine exceptions.

A new or changed business-domain slice is done only when all of the following
are true:

1. routes, callers, services, adapters and fact sources are inventoried;
2. one public Feature facade and strict command/query/result models exist;
3. required Ports are owned by the consumer;
4. Infrastructure adapters implement the Ports and Bootstrap injects them;
5. no forbidden layer or cross-Feature internal import remains;
6. authorization and Principal behavior have focused tests;
7. transaction/file/external-workflow semantics have focused tests;
8. errors, timeouts, retries and idempotency are tested where applicable;
9. all production callers use the authoritative path;
10. replaced routes, DTOs, adapters, compatibility branches and fixtures are removed;
11. at least one real end-to-end use-case proves the final chain.

Any future temporary gap follows the repository governance contract and does
not permit new code to repeat it.
