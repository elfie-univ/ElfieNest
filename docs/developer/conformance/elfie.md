# Elfie internal architecture conformance

> Temporary migration register for the normative
> [Elfie internal architecture contract](../contracts/elfie). It records the
> current implementation gaps without weakening the target. Rows ELF-001 through
> ELF-009 record the completed Ports/Adapters migration. Rows ELF-010 onward track
> the life-system target adopted by contract version 2.0.

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
| ELF-010 | P0 | open | `ElfieProfile` still carries `personality`, `capabilities` and `system_limits`; `elfie/profile/defaults/` still mixes selfhood, body capability and energy/runtime defaults with immutable appearance facts. | Establish the receiving Brain/Body/NervousSystem owners, migrate every production caller and persisted field in one approved slice, then remove the three broad Profile mappings and mixed defaults without fallback reads or dual authority. |
| ELF-011 | P0 | closed | Brain now owns private cognitive coordination and context assembly; Communication, Embodied and Internal inputs form typed single-domain Turns with host-enforced response scope, and the former root cognitive files are removed. | Focused Brain lifecycle, lane, scope and decision-boundary tests pass; Elfie Lab shows the source domain, Scope, decision and delivery receipt for the communication loop. Keep this boundary ratchet green while later Brain capabilities are added. |
| ELF-012 | P0 | closed | Body Registry/Binding now assigns an authority generation to the current Body; NervousSystem accepts only that generation, the output executor rejects receipts after a switch, and interruption targets the original Body; failed switches retain the previous Body. | Stage-three Headless and real Godot acceptance passes; body switching, stale-event rejection, stale-receipt rejection, connection-failure rollback and one-current-body authority have focused tests plus real `world_ready`/`intent_terminal` evidence. |
| ELF-013 | P1 | open | `elfie/initialization.py` assembles Profile and anatomy but there is no `genesis/` owner for the validated ephemeral creation bundle, Brain seeds or bounded biography enrichment. | Genesis produces and validates typed creation artifacts, commits each artifact once to its final owner, retains no duplicate life state and leaves ordinary runtime after completion. |
| ELF-014 | P0 | closed | Brain now owns the Persistent Activity semantic Port and output boundary; Lab injects a per-Elfie SQLite Adapter. Validated drafts are committed idempotently, waiting work wakes through typed Internal events, and child Communication/Embodied receipts settle Activity progress without replay after restart. | Focused Activity, persistence and Lab tests cover cross-Turn state, wake-up, Scope validation, receipt-backed terminal state, restart recovery and no duplicate delivery. |
| ELF-015 | P1 | closed | The first bounded Recovery Motivation drive and the first bounded Offline Cognition slice now have Brain owners and Lab evidence. Offline work is limited to sleeping-window episodic consolidation and cannot produce external effects; broader autonomous drives and growth remain separate scope. | Motivation emits cooldown/satisfaction-controlled candidates; Offline Cognition emits a checkpointed internal candidate with a fixed episode budget and commits Memory only after a completed Internal receipt. Focused Brain/Lab tests and Web build pass; no message, body or Activity output is created by the night-work path. |
| ELF-016 | P0 | closed | Brain now owns a bounded `ReasoningRun` inside one Turn: model, cognition Tool, real Observation, verification and terminal success/failure all stay inside Brain; only a settled `TurnDecision` can reach the existing external decision boundary. | 26 focused Brain/Lab tests pass; real Elfie Lab shows Tool→Observation, refuses to create an external receipt from tool text, enters explicit `failed/no_op` when the model is unavailable, and starts a separate urgent Turn after stale interruption. Plain-text Provider `owner_message_fallback` is recorded as degradation rather than a success fact. |
| ELF-017 | P0 | open | Emotion, energy and memory implementations exist, but Orientation and Selfhood are not independent authorities and the complete continuous-life state is not restored consistently across Turns, body switches and process restarts. | Typed Orientation/Selfhood/Emotion/Energy/Memory snapshots have explicit owners, source/version rules and minimal persistence/recovery; Profile remains immutable and transient emotion cannot directly rewrite personality. |

## Machine coverage

The system layer scanner prevents forbidden root imports and ratchets direct
technical imports in Elfie; its exact Elfie technical-import baseline is now
empty. Focused cognitive tests protect the public body/communication contracts,
strict Pydantic boundaries, Facade size, dependency direction and the
Brain-owned ToolPort surface. Memory Fake tests, Infrastructure persistence
tests and the model/tool end-to-end path provide the evidence for the closed
slices.

The Ports/Adapters rows are closed by migrated production call chains, focused
behavior evidence and permanent machine ratchets. Contract 2.0 reuses those
boundaries and existing baselines; it deliberately creates no second legacy
baseline. Open life-system rows are target gaps, not permission to weaken the
contract or pretend design-only capabilities are implemented.

## Completed Ports/Adapters order

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

## Life-system implementation order

1. Brain Kernel and the communication life loop close the single-domain Turn and root cognitive-ownership part of ELF-011;
2. Reasoning Core closes ELF-016 with bounded Model/Skill/Tool observations without adding an external action channel;
3. the virtual embodied loop closes ELF-012's one-active-body authority for the first production body;
4. continuous life state closes ELF-017, establishes Selfhood/Energy/Orientation owners and closes ELF-010 without dual Profile fields;
5. Persistent Activity closes ELF-014 before Motivation can create autonomous work;
6. bounded Motivation and Cognitive Consolidation close ELF-015;
7. Genesis closes ELF-013 only after the final Profile and Brain seed owners exist.

The detailed execution plan is a separate implementation artifact. It may split
these rows into smaller acceptance slices but cannot reorder Motivation ahead of
Activity, remove one-body authority, add compatibility storage or redefine the
owners fixed by the contract.
