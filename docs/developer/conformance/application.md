# Application conformance

> This page is the executable completion record for the normative
> [Application architecture contract](../contracts/application). The contract
> defines the target; this record states the current App result and the gates
> that prevent the retired structure from returning.

## Current status

The target App folders and the currently implemented deny-all rules are in
place, and the exact App baseline is empty. A manual audit found contract gaps
that are outside the present scanner's coverage, so App migration remains **in
progress**. A zero deny-all result means only that the implemented rules found
no violation; it is not proof that the whole Application contract is closed.

| ID | Severity | Status | Current result |
| --- | --- | --- | --- |
| APP-001 | P0 | open | Most Interfaces use injected public boundaries, but the API factory and legacy WebSocket gateway still import or construct concrete technical implementations. |
| APP-002 | P0 | closed | Features and Orchestration use consumer-owned Ports and have no forbidden framework or Infrastructure dependency. |
| APP-003 | P0 | open | Bootstrap performs most assembly, but the API factory and several CLI commands still resolve paths, initialize stores or construct technical services. |
| APP-004 | P1 | open | Two workflow models still import a Feature-private model or a Gateway-internal model, and several Routes coordinate more than one application boundary. |
| APP-005 | P1 | open | HTTP middleware/dependencies still emit FastAPI `detail` errors, and public WebSocket frames still contain loose dictionaries. |
| APP-006 | P1 | open | Authentication is typed, but logout and security-setting side effects are still coordinated in Routes. |
| APP-007 | P1 | closed | Database, file and external-workflow consistency is expressed by typed Ports and focused atomicity/recovery tests. |
| APP-008 | P1 | open | The legacy WebSocket Interface still owns a thread, event loop, server start and server stop. |
| APP-009 | P1 | closed | Every App Python package and public caller passes the strict App MyPy gate. |
| APP-010 | P1 | closed | Bodies and Embodiment have one product fact model, one lease workflow and root device adapters. |
| APP-011 | P1 | closed | Product APIs and real callers use versioned resource directories; retired routes and aliases are absent. |
| APP-012 | P1 | open | Provider initialization and Accounts cache invalidation still occur outside one explicit product use case. |

## Open cleanup register

The identifiers below are conformance tracking labels, not new contract rules.
Cleanup must preserve the behavior already migrated from `main`; it must not add
capabilities, aliases, fallback routes, dual writes or a second fact source.

| Gap | Contract rows | Current evidence | Completion gate |
| --- | --- | --- | --- |
| APP-G01 Legacy WebSocket lifecycle | APP-001, APP-003, APP-008 | `app/interfaces/api/ws_gateway*` owns the 8766 server thread/event loop and `app/interfaces/api/app.py` starts and stops it. | Preserve accepted user-message delivery, reply persistence and fan-out through the canonical same-origin transport; then remove the legacy server and all production callers without an alias or second transport. |
| APP-G02 API factory composition | APP-001, APP-003 | `app/interfaces/api/app.py` resolves the data path, initializes/seeds persistence, constructs communication infrastructure and inspects the Godot Web bundle. `app/bootstrap/api.py` also initializes the database. | Bootstrap owns one assembly/initialization path; the API factory only wires FastAPI, middleware, Routes and injected public boundaries. Remove unused concrete objects from `app.state`. |
| APP-G03 HTTP/WS boundary strictness | APP-005 | Global exception/CSRF, request-limit, service-access and dependency paths return `detail` errors. `app/interfaces/api/v1/realtime/bodies` and legacy gateway messages expose loose payload dictionaries. | Authentication, CSRF, validation, body-size, unavailable-service and unknown-error paths use the standard `{error:{code,message,details}}` envelope. Every public WebSocket frame has a strict named/discriminated DTO. |
| APP-G04 Route-owned orchestration | APP-004, APP-006, APP-012 | Logout calls Accounts and Observer; security settings update Settings and invalidate Accounts cache; mobile-access Route reads `ServiceAccessPolicy` directly. | Each inbound use case calls one public Facade/workflow or one injected owned Port while preserving revocation, immediate cache effect and mobile URL projection. |
| APP-G05 CLI concrete dependencies | APP-003 | Owner, lifecycle, doctor and uninstall commands import data-home helpers or construct `RuntimeLab` directly. | Bootstrap injects path, diagnostic and uninstall capabilities through public boundaries or narrow Ports; current commands, options, output and exit behavior remain unchanged. |
| APP-G06 Private model imports | APP-004 | Resident Admission imports `app.features.adoption.models.SpeciesId`; Nest Session imports `nest.godot_gateway.observer.ObserverSemanticEntity`. | Use an owning public export or a consumer-owned Port Model, preserving the current semantic fields without copying Godot geometry or runtime facts. |
| APP-G07 Bootstrap product actions | APP-003, APP-012 | Container and CLI composition call `ensure_local_connection`, and database initialization has more than one owner. | Bootstrap only constructs and connects dependencies. Product-state creation is an explicit Feature/Setup use case, and database initialization has one owner. |
| APP-G08 Gate coverage | APP-001, APP-004, APP-005, APP-008 | The scanner recognizes only `app.infrastructure` as Infrastructure, does not cover workflow-private imports or Interface lifecycle ownership, checks HTTP annotations but not WebSocket DTOs, and does not enforce the error envelope. | Strengthen focused rules together with the corresponding fixes; deny-all remains zero with no new baseline exception, and a regression test proves each retired pattern cannot return. |

## Required cleanup order

1. APP-G01 and APP-G02 must close atomically because both touch API startup and
   lifecycle ownership.
2. APP-G05 and APP-G06 are independent of that startup cut and may be cleaned in
   parallel in isolated worktrees.
3. APP-G03, APP-G04 and APP-G07 follow the composition cut so their single owner
   is unambiguous.
4. APP-G08 is added with the fixes it detects, then a final deny-all and focused
   behavior regression pass closes the reopened contract rows.

## Machine gates

- `test/architecture/baselines/app_layer.py` contains only empty sets.
- `scripts/architecture/app_layer_scan.py --mode deny-all` must report zero.
- `test/architecture/test_app_layer_boundaries.py` enforces dependency,
  construction, DTO and route rules against that exact baseline.
- Strict MyPy is run over `app/features`, `app/orchestration`, `app/bootstrap`,
  `app/interfaces/api` and `app/interfaces/cli`; imported legacy implementation
  bodies are not used to weaken the App result.
- Domain tests mirror the final source directories and cover authorization,
  transaction/recovery behavior, adapters and versioned HTTP/WS contracts.

These are the active gates, not a waiver for APP-G01 through APP-G08. Until
APP-G08 closes, manual evidence in this register is part of the acceptance gate.

The repository-level System scanner may still report separately registered
non-App migration debt. It cannot be added to this App baseline.

## Final dependency matrix

| Caller | May depend on | Must not depend on |
| --- | --- | --- |
| `app/interfaces/` | public Feature/Orchestration facades, Interface DTOs, injected request dependencies | concrete Infrastructure, private Feature/Orchestration modules, composition logic |
| `app/features/` | its own models/Ports, stable core facades, another domain's public facade only when it is the real inbound boundary | FastAPI, concrete Infrastructure, task/process ownership, another Feature's internals |
| `app/orchestration/` | public Feature/core facades and workflow-owned Ports | concrete Infrastructure, HTTP DTOs, physical Godot or process mechanisms |
| `app/bootstrap/` | public App boundaries and concrete root Infrastructure adapters | product rules, transport DTO mapping, alternate facts or defaults |
| `infrastructure/` | the consumer-owned Port it implements and lower technical libraries | another concrete adapter, Interface DTOs, product authorization or workflow policy |
| `elfie/` and `nest/` | their own domain code and owned Ports | App, concrete Infrastructure, or each other |

Inbound HTTP/WS/CLI boundaries call one public facade. Commands, queries and
results are App-owned; outbound Port models are owned by their consumer; HTTP
DTOs remain Interface-owned and never become persistence or domain models.

## Final folder map

The map is intentionally folder-level. It does not prescribe individual file
names.

```text
app/
├── features/
│   ├── accounts/
│   ├── adoption/
│   ├── bodies/
│   ├── communication/
│   ├── configuration/
│   │   ├── capabilities/
│   │   ├── food/
│   │   ├── providers/
│   │   └── settings/
│   ├── elfies/
│   ├── nest_management/
│   ├── operations/
│   └── setup/
├── orchestration/
│   ├── embodiment/
│   ├── lifecycle/
│   ├── message_delivery/
│   ├── nest_session/
│   ├── observer/
│   ├── resident_admission/
│   └── setup_installation/
├── interfaces/
│   └── api/
│       └── v1/
│           ├── auth/
│           ├── setup/
│           ├── me/
│           ├── elfies/
│           ├── admin/
│           ├── observer/
│           └── realtime/
└── bootstrap/
```

`/api/v1` is organized by resource and principal, not by page. `admin/`, `me/`,
`elfies/`, `observer/` and `realtime/` may contain resource subdirectories. The
only unversioned JSON exception is the lightweight `/api/health` process probe;
HTML/page and static-asset routes are not product JSON resources.

`app/infrastructure/` contains local governance instructions only. Production
adapters live in the root `infrastructure/` capability packages and are created
by `app/bootstrap/Container` assembly.

## Retired-to-final mapping

| Retired ownership | Final ownership |
| --- | --- |
| `administration` | `accounts`, `operations`, `orchestration/lifecycle` |
| `chat` and Interface-owned delivery/persistence | `communication`, `orchestration/message_delivery`, root communication/persistence adapters |
| `elfie_profile` and mixed Elfie projections | `elfies`; Food, Nest and Embodiment remain separate resources |
| `nest_registration` and flat Nest workflow files | `nest_management`, `orchestration/nest_session` |
| Feature-owned setup installers and platform work | `setup`, `orchestration/setup_installation`, root platform/model adapters |
| Feature-owned embodiment persistence/devices | `bodies`, `orchestration/embodiment`, root device/persistence adapters |
| `app/infrastructure` product implementations | matching root `infrastructure/` capability packages |
| unversioned or page-grouped product routes | resource-owned `app/interfaces/api/v1/` directories |

The target directory migration is present, but Application conformance remains
open until APP-G01 through APP-G08 are cleared. Closing them changes structure
and ownership only; it must not remove existing behavior or add product
capability, compatibility aliases, fallback routes, dual writes or a second fact
source.
