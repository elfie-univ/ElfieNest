# Application conformance

> This page is the executable completion record for the normative
> [Application architecture contract](../contracts/application). The contract
> defines the target; this record states the current App result and the gates
> that prevent the retired structure from returning.

## Current status

The target App folders are in place, the exact App baseline is empty, and the
manual gaps APP-G01 through APP-G08 are closed. The strengthened scanner now
covers root Infrastructure imports, workflow-private imports, Interface-owned
runtime lifecycle, loose WebSocket payloads and non-standard error responses.
Application migration is **closed**; repository-level System debt remains
tracked separately.

| ID | Severity | Status | Current result |
| --- | --- | --- | --- |
| APP-001 | P0 | closed | Interfaces use injected public boundaries; the API factory contains no concrete technical construction and the legacy WebSocket gateway is removed. |
| APP-002 | P0 | closed | Features and Orchestration use consumer-owned Ports and have no forbidden framework or Infrastructure dependency. |
| APP-003 | P0 | closed | Bootstrap is the concrete composition owner; API and CLI consume injected public boundaries or narrow Ports. |
| APP-004 | P1 | closed | Orchestration consumes public Feature boundaries or consumer-owned Port Models, and Routes no longer coordinate the registered multi-boundary cases. |
| APP-005 | P1 | closed | HTTP errors use the standard envelope and public WebSocket frames use strict named DTOs. |
| APP-006 | P1 | closed | Authentication, logout revocation and security-setting invalidation are expressed through typed single-entry workflows/use cases. |
| APP-007 | P1 | closed | Database, file and external-workflow consistency is expressed by typed Ports and focused atomicity/recovery tests. |
| APP-008 | P1 | closed | Interfaces own no runtime thread, event loop or server lifecycle; the retired 8766 transport is absent. |
| APP-009 | P1 | closed | Every App Python package and public caller passes the strict App MyPy gate. |
| APP-010 | P1 | closed | Bodies and Embodiment have one product fact model, one lease workflow and root device adapters. |
| APP-011 | P1 | closed | Product APIs and real callers use versioned resource directories; retired routes and aliases are absent. |
| APP-012 | P1 | closed | Provider initialization, initial Owner seeding and Accounts cache invalidation are explicit Feature use cases. |

## Closed cleanup register

The identifiers below are conformance tracking labels, not new contract rules.
Cleanup must preserve the behavior already migrated from `main`; it must not add
capabilities, aliases, fallback routes, dual writes or a second fact source.

| Gap | Contract rows | Closure evidence | Permanent gate |
| --- | --- | --- | --- |
| APP-G01 Legacy WebSocket lifecycle | APP-001, APP-003, APP-008 | The 8766 server and all `ws_gateway*` modules/callers are removed; same-origin chat preserves accepted delivery, persistence and fan-out. | Storage boundary tests reject restoration of the retired modules. |
| APP-G02 API factory composition | APP-001, APP-003 | Bootstrap owns lifespan, storage/setup recovery, service access and Web/Godot asset discovery; the API factory only wires the injected application. | The construction and forbidden-import scanner stays at zero. |
| APP-G03 HTTP/WS boundary strictness | APP-005 | HTTP failures use `{error:{code,message,details}}`; Body and Chat WebSocket frames have strict DTOs. | Error-envelope and loose-WebSocket scanners stay at zero. |
| APP-G04 Route-owned orchestration | APP-004, APP-006, APP-012 | Logout, security invalidation and mobile access each enter through one workflow/use case or injected projection Port. | Interface construction/private-boundary rules stay at zero. |
| APP-G05 CLI concrete dependencies | APP-003 | Data-home, Doctor, Uninstall and terminal presentation mechanics are injected by Bootstrap; CLI has no root Infrastructure import. | Interface forbidden-import scanning includes CLI and root Infrastructure. |
| APP-G06 Private model imports | APP-004 | Adoption uses the public `SpeciesId`; Nest Session owns its Observer semantic Port Model. | Workflow-private and Gateway-private imports are rejected. |
| APP-G07 Bootstrap product actions | APP-003, APP-012 | Default Provider connection and initial Owner creation are explicit Feature commands; schema initialization has one owner. | Bootstrap construction rules and focused Feature tests prevent direct adapter product actions. |
| APP-G08 Gate coverage | APP-001, APP-004, APP-005, APP-008 | The scanner covers every registered gap and the exact baseline remains empty. | Deny-all and exact-baseline tests must both pass without exceptions. |

## Completed cleanup order

1. APP-G01 and APP-G02 closed atomically around API startup and lifecycle.
2. APP-G05 and APP-G06 removed concrete CLI and private-model dependencies.
3. APP-G03, APP-G04 and APP-G07 closed strict boundaries and single-owner use
   cases after composition was stable.
4. APP-G08 made those retired patterns permanent zero-baseline rules.

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

These active gates keep APP-G01 through APP-G08 closed. Manual descriptions in
this register do not waive a machine-gate failure.

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

`app/infrastructure/` has been removed. Production adapters and their local
governance now live in root `infrastructure/` capability packages and are
created by `app/bootstrap/Container` assembly.

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

Application conformance is closed. Future changes must keep APP-G01 through
APP-G08 at zero and must not restore product capability aliases, fallback
routes, dual writes or a second fact source.
