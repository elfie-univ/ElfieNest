# System architecture conformance

> Temporary migration register for the normative
> [System architecture contract](../contracts/system). It records current
> deviations and never changes the target. Delete this page when every item and
> its exact machine baseline are closed.

## Current gaps

| ID | Severity | Status | Current deviation | Closure gate |
| --- | --- | --- | --- | --- |
| SYS-001 | P0 | in progress | Root `infrastructure/` owns the target capability areas, Data Home, persistence, model/provider and Runtime technology, tool technology, terminal hosting, Godot Gateway, authority hosting and artifact validation. The former `app/infrastructure/`, `godot_runtime/` and `ai_runtime/` roots are gone. Remaining ownership debt is limited to Observer/Core residuals. | Keep the retired roots absent and close the separately registered Elfie/Nest residuals without compatibility imports. |
| SYS-002 | P0 | open | Elfie memory and profile code constructs SQLite/YAML/path implementations, and Elfie factory/runtime code still knows concrete storage or Godot transport details. This is registered Elfie-internal debt, not part of the current top-level ownership pass. | Elfie owns only semantic models, algorithms, facades and Ports; Infrastructure implements storage/body/channel adapters; Bootstrap injects them; focused Elfie tests use fakes without technical I/O. |
| SYS-003 | P0 | in progress | Raw WebSocket, JSON, bundle, protocol and session implementations now live in `infrastructure/godot/gateway/`, and Nest has no remaining WebSocket import. `nest/godot_gateway/observer.py` remains a registered mixed semantic projection consumed privately by Nest Session. | APP-G06 replaces the remaining private Observer model import with its owning public export or a consumer-owned Port Model; the residual Nest directory is then deleted without changing world semantics, state, events or protocol behavior. |
| SYS-004 | P0 | closed | Production service and interactive entry scripts request Runtime, storage, Nest Session and Elfie restoration from `app/bootstrap/`. Bootstrap constructs the authenticated management WebSocket gateway and injects API startup/shutdown callbacks; Runtime, management Gateway and Godot channels start and stop only through Lifecycle. Interfaces retain protocol mapping only. | Permanent architecture tests keep concrete construction out of Interfaces and assert that API lifespan delegates channel control to Lifecycle. |
| SYS-005 | P1 | open | System facades and outbound Ports are partially present but not exposed through one stable, strict boundary inventory; some paths still use `Any`, concrete paths or protocol details. | Elfie and Nest facades plus Food, model, tool, body, world, communication and persistence Ports use strict models; duplicate or technology-named boundary APIs are removed. |
| SYS-006 | P1 | open | Existing permanent rules cover only part of the target: the exact System scanner focuses on Elfie/Nest technical imports, while Bootstrap completeness, Infrastructure cross-capability composition and packaging ownership are not yet fully ratcheted. | Core tests use fake/in-memory Ports, adapter tests are separate, Bootstrap has wiring tests, migrated paths have end-to-end proof, and the exact system baseline is empty. |
| SYS-007 | P0 | in progress | The former `ai_runtime/` root and imports are absent. Provider/model clients and Runtime technology now live in `infrastructure/models/`, tool technology in `infrastructure/tools/`, Food policy in the App Food Feature, and the read-only Food Port in Elfie. `RuntimeAgent` now receives its technical capabilities through `RuntimeAgentPorts` assembled by Bootstrap. Remaining concrete cross-capability composition is concentrated in the Provider/Food technology Adapters; the isolated Runtime Lab may continue to compose concrete adapters as a developer tool. | Preserve the existing Provider → Food → model → tool → emergency fallback behavior, then replace only the remaining Provider/Food Infrastructure cross-capability construction with narrow injected Ports; keep Runtime Lab isolated; do not redesign Elfie cognition or restore the retired root. |

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
themselves close the remaining target rows. `SYS-001`, `SYS-005`, `SYS-006`
and `SYS-007` still require a complete migrated call chain, focused
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
4. keep the completed `ai_runtime/` decomposition ratcheted: models and Runtime
   technology in `infrastructure/models/`, tools in `infrastructure/tools/`,
   Food policy in the App Feature and the read Port in Elfie;
5. audit remaining Elfie/Nest internal debt separately without reopening the
   retired root;
6. shrink exact baselines only for violations actually removed, then add any
   missing permanent rule in a separate governance change after its live
   violations are zero.

App-domain migration is separately tracked in
[Application conformance](./application). Elfie- and Nest-internal cleanup
remains separate from this top-level pass.
