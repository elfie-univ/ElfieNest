# System architecture conformance

> Temporary migration register for the normative
> [System architecture contract](../contracts/system). It records current
> deviations and never changes the target. Delete this page when every item and
> its exact machine baseline are closed.

## Current gaps

| ID | Severity | Status | Current deviation | Closure gate |
| --- | --- | --- | --- | --- |
| SYS-001 | P0 | closed | Root `infrastructure/` owns the target capability areas, Data Home, persistence, model/provider and Runtime technology, tool technology, terminal hosting, Godot Gateway, authority hosting and artifact validation. The former `app/infrastructure/`, `godot_runtime/` and `ai_runtime/` roots are absent, and the exact Elfie/Nest and cross-capability ownership gates are clear. | Retired roots remain absent; the deny-all system scanner and Port/Adapter ratchets stay green. |
| SYS-002 | P0 | closed | The Elfie memory/profile and Factory slices no longer construct SQLite/YAML/path implementations or know concrete Godot transport. Storage, profile and tool adapters live in Infrastructure and are injected by Bootstrap. | The exact Elfie/Nest technical-import baseline is empty; Brain Memory tests use Fakes, Infrastructure owns persistence integration tests, and typed Factory/ToolPort assembly tests pass. |
| SYS-003 | P0 | closed | Raw WebSocket, JSON, bundle, protocol and session implementations live in `infrastructure/godot/gateway/`; Nest has no Gateway transport or Observer implementation directory. Nest Session consumes the App-owned semantic Observer Port Model, while `infrastructure/godot/observer_world.py` only translates typed world facts and high-level intents. | Keep the retired `nest/godot_gateway/` path absent and preserve world semantics, state, events and protocol behavior with the existing Gateway and Observer boundary tests. |
| SYS-004 | P0 | closed | Production service and interactive entry scripts request Runtime, storage, Nest Session and Elfie restoration from `app/bootstrap/`. Bootstrap constructs the authenticated management WebSocket gateway and injects API startup/shutdown callbacks; Runtime, management Gateway and Godot channels start and stop only through Lifecycle. Interfaces retain protocol mapping only. | Permanent architecture tests keep concrete construction out of Interfaces and assert that API lifespan delegates channel control to Lifecycle. |
| SYS-005 | P1 | closed | System facades and outbound Ports have one strict machine-checked inventory. Port methods use named models or bounded JSON values; concrete peer Adapters and unvalidated boundary objects are rejected. | Keep `test_system_ports_contract.py`, the App/Elfie/Nest boundary tests and strict focused type checks green. |
| SYS-006 | P1 | closed | Bootstrap wiring, Infrastructure peer-composition rules, communication ingress and packaging ownership are now permanently ratcheted alongside the exact system scanner. Core/Adapter separation and migrated end-to-end evidence are covered by focused and full architecture tests. | Keep the Bootstrap, cross-capability, packaging and deny-all gates green; the exact system baseline remains empty. |
| SYS-007 | P0 | closed | The former `ai_runtime/` root and imports are absent. Provider/model clients and Runtime technology live in `infrastructure/models/`, tool technology in `infrastructure/tools/`, Food policy in the App Food Feature, and the read-only Food Port in Elfie. Runtime execution and model validation now receive the Brain-owned ToolPort instead of constructing concrete tool plugins in the call path. | Provider → Food → model → tool → emergency fallback behavior, scoped tool execution and the focused Runtime/Tool end-to-end path remain green; no `infrastructure/ai_runtime/` or broad Runtime tool bridge is restored. |

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

The exact system scanner and `system_layer.py` baseline cover `SYS-002` and
`SYS-003`: forbidden cross-root imports and direct technical imports in Elfie
and Nest. `test_system_ports_contract.py` ratchets strict Port annotations,
peer-capability imports, authenticated communication ingress and Bootstrap
composition. Bootstrap, Runtime, Observer, storage, Godot, packaging and
project-structure tests provide the remaining wiring and behavior evidence.
The exact system baseline and deny-all scan are both empty.

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
