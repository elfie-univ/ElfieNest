# Elfie internal architecture conformance

> Temporary migration register for the normative
> [Elfie internal architecture contract](../contracts/elfie). It records the
> current implementation gaps without weakening the target. Delete this page
> after every row is closed.

## Current gaps

| ID | Severity | Status | Current deviation | Closure gate |
| --- | --- | --- | --- | --- |
| ELF-001 | P1 | closed | Production App orchestration and interface callers use the curated `elfie.public`/`nest.public` surfaces; deep domain imports are machine-guarded. | `Elfie`/`ElfieFactory` are the only production aggregate entry points, expose the approved typed capabilities, and deep caller imports are removed and guarded. |
| ELF-002 | P0 | closed | Skills are now Brain-owned under `elfie/brain/skills/`; the former root package and its Runtime proxy are deleted. | Brain-owned declarations, in-memory policy and semantic tool-key authorization are covered by focused tests; no Runtime adapter, store, path or execution implementation remains in the retired Skill package. |
| ELF-003 | P0 | closed | Brain now exposes separate typed `FoodPort`, `ModelPort` and `ToolPort`; Runtime model execution receives a scoped Tool Adapter through Bootstrap. | `ToolRequest`/`ToolResult` are closed immutable contracts, the Adapter preserves global and per-Elfie safety vetoes, structured and ordinary paths use the injected Port, and the legacy broad Runtime bridge is absent. |
| ELF-004 | P0 | closed | SQLite/schema/record mapping has been removed from `elfie/brain/memory/`; semantic algorithms depend on `MemoryStorePort` and validated `MemoryMetadata`. | Brain memory tests use the in-memory Fake, persistence tests live under Infrastructure, the exact system technical-import baseline is empty, and final-store reopen behavior remains covered. |
| ELF-005 | P0 | closed | Profile loading and path resolution are owned by Infrastructure/Bootstrap; `assemble_profile` and `ElfieFactory` receive only typed profile/dependency inputs. | `ProfileStorePort` remains the domain boundary, bundled defaults are resource-backed, and no Elfie initialization or Factory API accepts a storage path or concrete profile repository. |
| ELF-006 | P0 | closed | Body semantics, registry and binding remain in Elfie while Godot/device/product-hosting implementations are outside the domain; the remaining Headless/native bodies are deterministic no-I/O references. | Multi-body identity/binding and typed event/receipt tests pass; no Body implementation imports transport, credentials, process ownership or Nest world facts. |
| ELF-007 | P0 | closed | `elfie/communication/` owns only canonical envelopes, policy, Hub/router, bounded inbox/outbox and injected channel Ports. WeChat/Telegram and message-delivery transport live in `infrastructure/communication/`; authenticated versioned App conversation and WebSocket routes resolve member/target before delivery Facade. | Keep communication Port/Adapter direction, authenticated ingress, identity/deduplication and delivery-order tests green. |
| ELF-008 | P1 | closed | `ElfieFactory` is now a typed domain builder over an immutable `ElfieAssembly`; storage paths, Godot APIs and staged Runtime configuration are resolved before it is called. | Factory assembly/restore tests pass, the returned aggregate is complete but not started, and Bootstrap remains the only production composition root. |
| ELF-009 | P1 | closed | Public Profile, Body, Communication, Nest Session, Runtime observation and Infrastructure Port models use named immutable models or bounded JSON values. Permanent Port ratchet rejects `Any`/`object`/concrete peer Adapter signatures; body/channel/Bootstrap evidence is focused and machine-checked. | Keep the strict Port ratchet and evidence green; internal algorithm-local mappings are not public boundary contracts. |

## Machine coverage

The system layer scanner prevents forbidden root imports and ratchets direct
technical imports in Elfie; its exact Elfie technical-import baseline is now
empty. Focused cognitive tests protect the public body/communication contracts,
strict Pydantic boundaries, Facade size, dependency direction and the
Brain-owned ToolPort surface. Memory Fake tests, Infrastructure persistence
tests and the model/tool end-to-end path provide the evidence for the closed
slices.

All rows in this register are now closed by migrated production call chains,
focused behavior evidence and permanent machine ratchets. This contract reuses
the system scanner and existing baseline; it deliberately creates no second
legacy baseline.

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
