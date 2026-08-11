# Elfie internal architecture conformance

> Temporary migration register for the normative
> [Elfie internal architecture contract](../contracts/elfie). It records the
> current implementation gaps without weakening the target. Delete this page
> after every row is closed.

## Current gaps

| ID | Severity | Status | Current deviation | Closure gate |
| --- | --- | --- | --- | --- |
| ELF-001 | P1 | open | The root Facade is small, but production callers can still reach deep Elfie coordinators and mutable submodules; the complete typed inbound inventory is not frozen. | `Elfie`/`ElfieFactory` are the only production aggregate entry points, expose the approved typed capabilities, and deep caller imports are removed and guarded. |
| ELF-002 | P0 | open | Skills live at root `elfie/skills/` and runtime-facing skill adapters couple authorization to the historical execution Runtime. | Skills move to `elfie/brain/skills/`, refer only to semantic tool keys/capabilities, and authorize requests that an injected `ToolPort` executes. Bundled declarations/in-memory policy use no store; mutation and durable Skill state remain disabled. The old package and Runtime adapters are deleted. |
| ELF-003 | P0 | open | Brain uses the broad historical `CorticalRuntimePort`; Food selection, model access and tool behavior are not yet represented by the final narrow Ports. | Brain owns separate typed `FoodPort`, `ModelPort` and `ToolPort`; Food preserves named-role/single-fallback/Emergency behavior; the scoped Tool Adapter retains technical safety veto; Bootstrap injects the Infrastructure views; all callers migrate and the broad Runtime bridge is removed. |
| ELF-004 | P0 | open | Brain Memory contains SQLite connections, schemas and concrete graph stores, and some memory boundaries still expose loose dictionaries. | `elfie/brain/memory/` keeps semantic algorithms and `MemoryStorePort`; concrete SQLite/schema/record mapping moves to Infrastructure; models are strict and domain tests use fakes. |
| ELF-005 | P0 | open | Profile repository/resolver code knows YAML and paths, while Factory accepts concrete configuration paths. | Profile owns `ProfileStorePort`; user-writable persistence and path resolution move to Infrastructure/Bootstrap; bundled immutable defaults remain resources; Factory receives typed dependencies. |
| ELF-006 | P0 | open | `BodyPort`, typed events, receipts, registry and binding exist, but Godot transport and external/native implementations remain under `elfie/body/`; the Headless implementation has not been classified as pure reference/test support versus product hosting. | Elfie retains body identity, capabilities, commands, events, receipts and binding semantics; Godot/device/product-hosting implementations move to Infrastructure; only a deterministic no-I/O reference body or test fake may remain; BodyPort cannot carry Nest world facts; multi-body identity/routing has focused tests. |
| ELF-007 | P0 | open | The communication domain has canonical envelopes and a channel Protocol, but WeChat/Telegram implementations and some delivery execution remain inside `elfie/communication/`; the final authenticated App ingress path is not frozen. | Platform SDK, credentials, Webhooks and transport/retry implementations move to Infrastructure; App resolves principal, membership, target and authorization before Facade ingress and owns product conversation facts; Elfie keeps semantic Hub/router/policy, bounded transient inbox/outbox and injected channel Ports with concurrent-channel, identity and deduplication tests. |
| ELF-008 | P1 | open | `ElfieFactory` still knows `config_dir`, `memory_db_path`, a loosely typed Godot API and staged cognitive configuration. | Factory is only a domain builder and creates one complete, not-started aggregate from an immutable typed assembly record; Bootstrap constructs scoped concrete Adapter views, lifecycle Orchestration owns system start/stop/restart, and no partially configured production Elfie exists. |
| ELF-009 | P1 | open | Several public boundaries still use `Any`, raw dictionaries or implementation-shaped models, and assembly/fake coverage does not yet prove every final Port. | Public Facades and Ports use named immutable domain models, focused core tests use fakes, Adapter tests cover translation, and Bootstrap wiring plus one real path per completed body/channel proves the final boundary. |

## Machine coverage

The system layer scanner already prevents forbidden root imports and ratchets
direct technical imports in Elfie. The focused Elfie cognitive tests protect
the current public body/communication contracts, strict Pydantic boundaries,
Facade size and dependency direction. They also protect the newly documented
Port ownership and public aggregate surface where the implementation is already
conformant.

The remaining rows require migrated production call chains and focused behavior
evidence; a passing static test cannot close them. This contract reuses the
system scanner and existing baseline. It deliberately creates no second legacy
baseline.

## Migration order

1. inventory and freeze the `Elfie`/`ElfieFactory` public surface;
2. move Skills under Brain and separate authorization from execution;
3. replace the broad Runtime bridge with Food, model and tool Ports;
4. extract Memory and Profile persistence Adapters;
5. extract Body technical Adapters while preserving the stable Body Port;
6. extract communication platform Adapters while preserving canonical
   envelopes and channel routing;
7. finish Factory/Bootstrap assembly and remove deep production imports;
8. close strict-model, fake, Adapter and end-to-end evidence gaps.

Each step is an independently approved vertical slice: define or freeze the
consumer Port, implement and inject one Adapter, migrate every caller, delete
the old path, then close only the matching row.
