# Application conformance

> This page is the executable completion record for the normative
> [Application architecture contract](../contracts/application). The contract
> defines the target; this record states the current App result and the gates
> that prevent the retired structure from returning.

## Current status

There are no registered App architecture exceptions. The exact App baseline is
empty and deny-all mode reports zero violations.

| ID | Severity | Status | Closed result |
| --- | --- | --- | --- |
| APP-001 | P0 | closed | Interfaces depend on injected public Feature/Orchestration boundaries, never concrete adapters. |
| APP-002 | P0 | closed | Features and Orchestration use consumer-owned Ports and have no forbidden framework or Infrastructure dependency. |
| APP-003 | P0 | closed | Bootstrap is the sole composition root; API and CLI entry points receive assembled services. |
| APP-004 | P1 | closed | Cross-domain calls use public facades or owned Ports; private cross-feature imports are absent. |
| APP-005 | P1 | closed | Product JSON routes use strict named DTOs, response models and the standard error envelope. |
| APP-006 | P1 | closed | Interfaces authenticate strict principals and application services own authorization and business errors. |
| APP-007 | P1 | closed | Database, file and external-workflow consistency is expressed by typed Ports and focused atomicity/recovery tests. |
| APP-008 | P1 | closed | Background and platform work is owned by injected runners/adapters and lifecycle orchestration. |
| APP-009 | P1 | closed | Every App Python package and public caller passes the strict App MyPy gate. |
| APP-010 | P1 | closed | Bodies and Embodiment have one product fact model, one lease workflow and root device adapters. |
| APP-011 | P1 | closed | Product APIs and real callers use versioned resource directories; retired routes and aliases are absent. |
| APP-012 | P1 | closed | Configuration, secret and cache ownership is typed, single-writer and explicitly injected. |

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

This closure changes structure and ownership only. It adds no product capability,
compatibility alias, fallback route, dual write or second fact source.
