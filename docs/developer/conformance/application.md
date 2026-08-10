# Application conformance

> This is the temporary implementation-gap register for the normative
> [Application architecture contract](../contracts/application). It records
> current legacy non-conformance; it does not define architecture or authorize
> another exception. When every item is closed and the exact machine baseline
> is empty, this page and its navigation entry are removed.

## Status and evidence rules

- `open`: current production code still violates the contract.
- `in progress`: one domain is being migrated, but its complete definition of
  done has not passed.
- `closed`: callers, implementation, tests and machine baseline are all clean.
- An item cannot close because a document, interface or replacement class exists;
  the old production call chain must also be removed.
- Every machine exception carries one gap ID. No unregistered exception is
  allowed, and a gap ID never permits a new occurrence.

The executable source is
`test/architecture/baselines/app_layer.py`. Its entries identify exact
imports, functions, constructors or routes. The architecture test requires an
exact match: deleting debt requires deleting its baseline entry in the same
change; adding or restoring debt fails. This page groups those entries by cause
and acceptance gate rather than copying the full generated inventory.

## Current gaps

| ID | Severity | Status | Current gap | Acceptance gate |
| --- | --- | --- | --- | --- |
| APP-001 | P0 | open | Interfaces import concrete persistence/device implementations and therefore know technical storage and gateway details. | Every Interface depends only on injected public Feature/Orchestration services and protocol models; the `interface -> infrastructure` machine set is empty. |
| APP-002 | P0 | open | Features import concrete Infrastructure, some public use-cases receive `db_path`, one Feature imports FastAPI, and embodiment Orchestration imports a persistence implementation. | Consumer-owned Ports replace concrete dependencies, public use-cases receive typed dependencies, and the Feature/Orchestration isolation machine sets are empty. |
| APP-003 | P0 | open | The composition root is incomplete; API/CLI factories, routes and dependency helpers construct repositories, stores or registries. | Bootstrap owns construction and lifetime, entry points receive an application container or explicit services, and the Interface-construction machine set is empty. |
| APP-004 | P1 | open | Interfaces and Features import another Feature's internal modules; Infrastructure also depends on a private Feature module. Stable package facades are inconsistent. | Each migrated domain exports one public facade; cross-domain callers use it or an owned Port; internal-import machine sets are empty and the App import graph is acyclic. |
| APP-005 | P1 | open | Many JSON Routes have no named `response_model`, and loose dictionary/`Any` protocol annotations remain. | Every product Route has strict request/response models and the standard error envelope; non-JSON page/stream responses are explicit; Route model and loose-annotation machine sets are empty. |
| APP-006 | P1 | open | Authentication, role checks and error mapping are spread across Interface and Feature helpers without one Principal/RequestContext and business-error taxonomy. | Strict principals exist for user/setup/admin/observer/device; Interface authenticates, Feature authorizes; business errors have one tested protocol mapping. |
| APP-007 | P1 | open | Transaction ownership, Repository commit behavior, typed-file writers and external-workflow recovery are not uniformly expressed by Ports and tests. | Each migrated command declares its database, file or external-workflow consistency class; no external wait occurs inside a DB transaction; atomicity and recovery tests pass. |
| APP-008 | P1 | open | Some Features own threads/jobs or blocking platform work, while task cancellation, timeout, receipt and restart semantics are inconsistent. | Scheduler/Runner Ports own background work; Bootstrap/lifecycle owns runners; async boundaries and long-task semantics have focused tests. |
| APP-009 | P1 | open | Global MyPy remains non-strict and no migrated-domain strict zone has been established. | Each migrated domain and its public callers pass strict MyPy without `Any` escape hatches; the strict override expands as domains close. |
| APP-010 | P1 | open | External-body persistence and device registration have overlapping registries/repositories; embodiment contracts import persistence records and Orchestration carries `db_path`. | One external-body product model and consumer-owned Ports remain; device transport is an Infrastructure adapter; hosting/homing remains Orchestration; duplicate facts and concrete imports are removed. |
| APP-011 | P1 | open | Versioned and historical product APIs coexist, including duplicated caller projections and untyped legacy resources. | Migrate one API business domain at a time under `app/interfaces/api/AGENTS.md`, move every real caller, then delete the old Route, client, DTO and fixtures without aliases. |
| APP-012 | P1 | open | Configuration, secret access and caches do not yet share one enforced ownership template across App domains. | Every migrated configuration has one typed owner/writer and precedence; secrets use references/Secret Ports; caches declare authority, invalidation, lifetime and rebuild behavior. |

## Machine coverage

The exact App scanner and `app_layer.py` baseline currently cover
`APP-001`, `APP-002`, `APP-003`, `APP-004`, `APP-005`, `APP-008` and
`APP-011`. The remaining authorization, transaction, strict-typing,
embodiment-fact and configuration-ownership rows require domain-specific
tests and review as each migration is selected. A passing scanner proves only
that no covered violation was added and the baseline is exact; it does not
declare the whole App contract conformant.

## Migration-unit record

Each approved domain migration adds a short record to this section before code
changes begin:

```text
Domain:
Gap IDs:
Current authoritative facts:
Routes and production callers:
Target public facade and models:
Ports and adapters:
Consistency class:
Principal and authorization:
Timeout / retry / idempotency:
Legacy deletion list:
Focused tests and end-to-end gate:
Machine baseline entries to remove:
Status: open | in progress | closed
```

The record is an execution checklist, not a design authority. A migration is
closed only after all twelve completion conditions in the Application
architecture contract pass. API caller migration, persistence changes and UI
changes remain separately reviewable even when they belong to one domain.

### Accounts: authentication and sessions

```text
Domain: accounts / authentication-session
Gap IDs: APP-001, APP-002, APP-003, APP-004, APP-005, APP-006, APP-009, APP-011, APP-012
Current authoritative facts: users credentials and roles in nest.db; hashed browser sessions in nest.db; system.security session TTL and login-rate settings in runtime.yaml
Routes and production callers: POST /api/v1/auth/login and /logout; browser session client; HTTP/page/WS/Setup/Observer authentication dependencies
Target public facade and models: accounts authentication/session facade; strict account principal, login command and authenticated-session result
Ports and adapters: account credential/session persistence Port implemented by root Infrastructure SQLite; typed security-policy Port implemented by root Infrastructure runtime configuration
Consistency class: one database transaction per session issue or revoke; configuration remains a typed-file read
Principal and authorization: Interface parses credentials/cookies and constructs the Feature result as the request principal; Accounts authorizes owner/manager requirements
Timeout / retry / idempotency: local synchronous storage/config access; no retry; session revoke is idempotent
Legacy deletion list: app/features/accounts/auth.py; legacy login/logout routes and paths; direct authentication imports from Feature internals; auth-owned concrete persistence/config construction
Focused tests and end-to-end gate: Accounts service and adapters; shared HTTP dependencies; login/logout cookie and CSRF flow; WebSocket session validation; frontend session client; focused App architecture scan
Machine baseline entries removed: accounts/auth Feature isolation and internal-import entries; replaced Interface construction/internal-import entries; POST /api/auth/login and POST /api/auth/logout
Status: closed
```

### Nest Management

```text
Domain: nest_management
Gap IDs: APP-001, APP-002, APP-003, APP-004, APP-005, APP-006, APP-007, APP-009, APP-011
Current authoritative facts: the one Nest identity and capacity constraints from the public NestConfig; nest.db nest_settings and nullable Elfie bed numbers
Routes and production callers: /api/v1/admin/nest rooms, bed-count and Elfie-bed resources; owner Nest client, monitor projection and storage end-to-end journey
Target public facade and models: authorized Nest Management facade with typed capacity and assignment commands/results
Ports and adapters: NestManagementPort implemented by the root Infrastructure SQLite adapter and injected by Bootstrap
Consistency class: each capacity or assignment command owns one immediate SQLite transaction; reads never create state
Principal and authorization: Interface authenticates an account principal; Nest Management authorizes managers
Timeout / retry / idempotency: local SQLite access; no retry; setting the same capacity or assignment is idempotent
Legacy deletion list: app/features/nest_registration; app/interfaces/api/nest_routes.py; old /api/owner/nest resources and direct Interface repository construction
Focused tests and end-to-end gate: Feature, Adapter and strict Route tests; owner Nest/monitor frontend tests; final-storage product journey; App/System/Storage architecture gates
Machine baseline entries removed: old Nest Interface construction/imports; loose/missing Route models; old GET/PUT /api/owner/nest resources
Status: closed
```

### Configuration: global settings

```text
Domain: configuration/settings
Gap IDs: APP-001, APP-003, APP-004, APP-005, APP-006, APP-007, APP-009, APP-011, APP-012
Current authoritative facts: runtime.yaml system.adoption, system.engine and system.security; defaults remain DEFAULT_SYSTEM_SETTINGS
Routes and production callers: /api/v1/admin/settings/{elfies,runtime,security}; management Settings panel; Adoption and Accounts live configuration readers
Target public facade and models: typed Settings facade with explicit queries, patch commands and results for the three existing resources
Ports and adapters: SettingsStorePort implemented by the root Infrastructure Runtime settings adapter and injected once by Bootstrap
Consistency class: synchronous typed-file read; each patch atomically replaces one owned section while preserving unrelated Runtime fields
Principal and authorization: Interface authenticates a strict account principal; Settings authorizes managers; security changes invalidate the Accounts limiter cache
Timeout / retry / idempotency: local file access; no retry; repeating the same patch is idempotent
Legacy deletion list: app/interfaces/api/system_routes.py; generic /api/owner/system/{section}; old frontend caller and Route fixtures
Focused tests and end-to-end gate: Settings service, Adapter and DTO tests; integrated Adoption/Security live behavior; frontend Settings panel; focused App architecture scan
Machine baseline entries removed: old Settings internal import; loose/missing Route models; GET and PUT /api/owner/system/{section}
Status: closed
```

## Current-to-target migration map

The normative owners are defined only by the Application contract. This table
records where current implementation must move and how each migration-state
location can be deleted; it sets no implementation order.

| Current location or grouping | Target owner or workflow | Related gaps | Deletion gate |
| --- | --- | --- | --- |
| `app/features/accounts/` | `app/features/accounts/` | APP-002, APP-004, APP-006, APP-009 | Authentication is removed from FastAPI and concrete persistence/configuration; every caller uses the public accounts facade. |
| `app/features/administration/` | accounts behavior to `accounts`; maintenance projections to `operations`; lifecycle behavior to `orchestration/lifecycle` | APP-002, APP-004, APP-006, APP-007 | Member, Owner, session, maintenance and lifecycle callers use their final owners and the legacy directory is deleted. |
| `app/features/adoption/` | business decisions to `adoption`; live admission and compensation to `orchestration/resident_admission` | APP-002, APP-004, APP-007, APP-009 | Adoption owns one fact/write path, admission uses public facades and Ports, and direct engine/path/persistence coupling is deleted. |
| `app/features/chat/` plus Interface chat persistence/delivery | `communication` and `orchestration/message_delivery` | APP-001, APP-004, APP-005, APP-006, APP-007, APP-011 | HTTP and WS callers share one facade, history has one owner, live delivery has receipts, and legacy Interface persistence helpers are deleted. |
| `app/features/elfie_profile/` plus Interface query assembly | `elfies` authorized query/projection Feature | APP-001, APP-004, APP-005, APP-009, APP-011 | Member/admin callers use one typed facade and no App module becomes a second Elfie profile, cognition or memory writer. |
| `app/features/nest_management/` and `app/features/nest_registration/` | `nest_management`; live composition remains `orchestration/nest_session` | APP-001, APP-002, APP-004, APP-007 | Product commands use the public Nest boundary, duplicate registration ownership is removed and `nest_registration` is deleted. |
| `app/features/configuration/` and App-owned behavior in `ai_runtime/` | `configuration/providers`, `food`, `capabilities`, `settings` | APP-001, APP-002, APP-004, APP-008, APP-009, APP-012 | Each subdomain has one facade, typed owner/writer and Ports; technical model/tool/storage code is moved to its root Infrastructure capability and legacy ownership is deleted. |
| `app/features/setup/` | setup decisions to `setup`; external installation to `orchestration/setup_installation`; account/configuration/Nest facts to their public owners | APP-002, APP-003, APP-004, APP-007, APP-008, APP-009, APP-012 | Feature-owned threads and concrete adapters are gone, the workflow is resumable through injected Ports, and Setup no longer writes another domain's facts directly. |
| `app/features/embodiment/` | enrollment/grants/association to `bodies`; hosting/homing/switching to `orchestration/embodiment` | APP-002, APP-004, APP-007, APP-009, APP-010 | One external-body product model and Port set remain; persistence records, `db_path` and concrete device adapters no longer cross the boundary. |
| flat files in `app/orchestration/` | `nest_session`, `message_delivery` or the implementing root Infrastructure capability according to the contract | APP-002, APP-004, APP-007, APP-009 | Workflow code imports only public facades/owned Ports, technical adapters leave Orchestration and legacy flat ownership is removed. |
| `app/infrastructure/` and technical parts of `ai_runtime/` | root `infrastructure/models`, `tools`, `godot`, `persistence`, `devices`, `communication`, `platform` | APP-001, APP-002, APP-003, APP-004, APP-012 | Every migrated Adapter implements a consumer-owned Port, Bootstrap injects it and the replaced legacy path shrinks without a target `infrastructure/ai_runtime`. |
| historical and mixed API Route groupings | `app/interfaces/api/v1/` resource directories defined by the contract | APP-001, APP-003, APP-004, APP-005, APP-006, APP-011 | Every real caller uses the versioned resource, DTOs are strict, construction is injected and the replaced Route/client/fixture is deleted without an alias. |

Capacity closure, hardware-aware recommendations and any other behavior change
remain separate product work and are not hidden inside architecture migration.
