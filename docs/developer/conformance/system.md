# System architecture conformance

> Temporary migration register for the normative
> [System architecture contract](../contracts/system). It records current
> deviations and never changes the target. Delete this page when every item and
> its exact machine baseline are closed.

## Current gaps

| ID | Severity | Status | Current deviation | Closure gate |
| --- | --- | --- | --- | --- |
| SYS-001 | P0 | open | Technical adapters are split across `app/infrastructure/`, `ai_runtime/`, `godot_runtime/`, `nest/godot_gateway/` and concrete Elfie/Nest storage or transport code; target root `infrastructure/` does not exist. | Technical implementations move to owned `models`, `tools`, `persistence`, `godot`, `devices`, `communication` or `platform` subareas; old technical roots and compatibility imports are deleted while root `godot_project/` remains unchanged. |
| SYS-002 | P0 | open | Elfie memory and profile code constructs SQLite/YAML/path implementations, and Elfie factory/runtime code still knows concrete storage or Godot transport details. | Elfie owns only semantic models, algorithms, facades and Ports; Infrastructure implements storage/body/channel adapters; Bootstrap injects them; focused Elfie tests use fakes without technical I/O. |
| SYS-003 | P0 | open | Nest contains concrete WebSocket, JSON, environment, bundle and Godot transport implementations. | Nest keeps world semantics, rules, facades and Ports; Infrastructure owns protocol/host adapters; global facts pass through Nest while actor receipts use the body channel. |
| SYS-004 | P0 | open | Concrete construction is spread across App routes, Features, factories and Orchestration; `app/bootstrap/` is not yet the complete composition root. | Bootstrap constructs every concrete cross-system Adapter and injects all system Ports; product/runtime code contains no Service Locator or concrete adapter construction. |
| SYS-005 | P1 | open | System facades and outbound Ports are partially present but not exposed through one stable, strict boundary inventory; some paths still use `Any`, concrete paths or protocol details. | Elfie and Nest facades plus Food, model, tool, body, world, communication and persistence Ports use strict models; duplicate or technology-named boundary APIs are removed. |
| SYS-006 | P1 | open | Current tests exercise several real adapters from core tests, and system-level architecture debt is not yet fully covered by an exact ratchet. | Core tests use fake/in-memory Ports, adapter tests are separate, Bootstrap has wiring tests, migrated paths have end-to-end proof, and the exact system baseline is empty. |
| SYS-007 | P0 | open | Current `ai_runtime/` mixes Provider/model adapters, Food administration, reports, persistence, tool execution and inference coordination under one obsolete target owner. | Provider/model access is under `infrastructure/models`; tool execution is under `infrastructure/tools`; persistence implements consumer-owned Ports; App owns Food administration/reports; Elfie uses injected `FoodPort`, `ModelPort` and `ToolPort` directly; all callers migrate and the old root is deleted rather than moved intact. |

## Machine coverage

The exact system scanner and `system_layer.py` baseline currently cover
`SYS-002` and `SYS-003`: forbidden cross-root imports and direct technical
imports in Elfie and Nest. Other architecture tests protect existing Runtime,
Observer, storage, Godot and project-structure safety rules, but they do not by
themselves close the remaining target rows. `SYS-001`, `SYS-004`, `SYS-005`,
`SYS-006` and `SYS-007` still require a complete migrated call chain, focused
behavior evidence and maintainer review; a passing scanner alone cannot close
them.

## Migration order

This register does not authorize a repository-wide move. Migrate one complete
boundary at a time:

1. freeze the facade/Port and fact owner;
2. add the target Adapter and Bootstrap wiring;
3. migrate every production caller and focused test;
4. delete the old implementation and import path;
5. reduce the machine baseline and close only the affected row.

Recommended dependency order is Bootstrap foundation, Elfie Food/model/tool
Ports, model and tool Adapters, Elfie persistence, Nest persistence,
Godot Gateway/host integration, Nest world authority, external devices and
communication, then remaining platform capabilities. App-domain migration is
separately tracked in [Application conformance](./application); current
`ai_runtime/` behavior debt remains inventoried in
[AI Runtime conformance](./ai-runtime) until that migration package is removed.
