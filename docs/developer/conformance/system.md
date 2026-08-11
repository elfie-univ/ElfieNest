# System architecture conformance

> Temporary migration register for the normative
> [System architecture contract](../contracts/system). It records current
> deviations and never changes the target. Delete this page when every item and
> its exact machine baseline are closed.

## Current gaps

| ID | Severity | Status | Current deviation | Closure gate |
| --- | --- | --- | --- | --- |
| SYS-001 | P0 | in progress | Root `infrastructure/` now has the seven target capability areas, but several Adapters still delegate to `ai_runtime/`, `godot_runtime/`, `nest/godot_gateway/` or core-owned technical implementations. | Technical implementations move to owned `models`, `tools`, `persistence`, `godot`, `devices`, `communication` or `platform` subareas; old technical roots and compatibility imports are deleted while root `godot_project/` remains unchanged. |
| SYS-002 | P0 | open | Elfie memory and profile code constructs SQLite/YAML/path implementations, and Elfie factory/runtime code still knows concrete storage or Godot transport details. This is registered Elfie-internal debt, not part of the current top-level ownership pass. | Elfie owns only semantic models, algorithms, facades and Ports; Infrastructure implements storage/body/channel adapters; Bootstrap injects them; focused Elfie tests use fakes without technical I/O. |
| SYS-003 | P0 | in progress | Root `infrastructure/godot/` owns lifecycle, Nest-session and Observer Adapters, while `nest/godot_gateway/` still owns raw WebSocket, JSON, bundle and protocol implementations. | The existing technical transport is moved mechanically into Infrastructure and every caller is switched without changing Nest world semantics, state, events or protocol behavior. |
| SYS-004 | P0 | in progress | The typed `app/bootstrap/` Container constructs many root Adapters, but API, CLI and script entry points still resolve or construct some concrete technical dependencies; lifecycle ownership is not yet fully singular. | Bootstrap constructs every concrete cross-system Adapter and injects all system Ports; Lifecycle alone starts and stops Runtime, Gateway and Godot authority; product/runtime code contains no Service Locator or concrete adapter construction. |
| SYS-005 | P1 | open | System facades and outbound Ports are partially present but not exposed through one stable, strict boundary inventory; some paths still use `Any`, concrete paths or protocol details. | Elfie and Nest facades plus Food, model, tool, body, world, communication and persistence Ports use strict models; duplicate or technology-named boundary APIs are removed. |
| SYS-006 | P1 | open | Existing permanent rules cover only part of the target: the exact System scanner focuses on Elfie/Nest technical imports, while Bootstrap completeness, Infrastructure cross-capability composition and packaging ownership are not yet fully ratcheted. | Core tests use fake/in-memory Ports, adapter tests are separate, Bootstrap has wiring tests, migrated paths have end-to-end proof, and the exact system baseline is empty. |
| SYS-007 | P0 | in progress | Provider, Food and tool-management boundaries now have target Adapters, but `ai_runtime/` still mixes model/tool technology, persistence and inference coordination, and some root Infrastructure Adapters still delegate to it. | Pure technical implementations move to their target capability areas with all callers switched. Any remaining mixed coordinator that cannot move without redesigning Elfie cognition or tool behavior stays registered for the later Elfie-internal work instead of being relabeled as Infrastructure. |

## Current execution boundary

The current priority is **top-level physical ownership and cross-root boundary
stability**. This pass may close Bootstrap, Data Home, packaging and lifecycle
composition gaps; mechanically relocate existing Godot host/Gateway and other
pure technical implementations; migrate their callers; and delete an old path
only after its callers are zero.

Elfie and Nest internal algorithms, state machines, submodule interactions and
user-visible behavior remain unchanged. In particular, this pass does not
redesign cognition, Memory, Skills, the model/tool loop, Nest world semantics,
resident synchronization or event propagation. If an old module cannot move
equivalently under that constraint, it remains an explicit later Elfie- or
Nest-internal item rather than being forced into Infrastructure.

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

For the current pass, use this narrower dependency order:

1. freeze existing behavior, public boundaries and lifecycle owners;
2. close the Bootstrap, Data Home and packaging foundation needed by target
   Infrastructure packages;
3. mechanically move Godot host/artifact and Gateway/protocol technology into
   `infrastructure/godot/`, switch all callers, then delete the old roots;
4. move only the pure technical parts of `ai_runtime/` into their existing
   target capability areas and switch their callers;
5. audit any remaining mixed coordinator and defer it when closing it would
   require Elfie or Nest internal redesign;
6. shrink exact baselines only for violations actually removed, then add any
   missing permanent rule in a separate governance change after its live
   violations are zero.

App-domain migration is separately tracked in
[Application conformance](./application). Elfie- and Nest-internal cleanup
remains separate from this top-level pass.
