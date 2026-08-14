# Elfie internal architecture conformance

> Closure-ready migration register for the normative
> [Elfie internal architecture contract](../contracts/elfie). It records the
> evidence for the completed implementation without weakening the target. Rows
> ELF-001 through ELF-009 record the Ports/Adapters migration; ELF-010 onward
> records the life-system work adopted by contract version 2.0.

## Conformance closure

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| ELF-001 | P1 | closed | Production App orchestration and interface callers use the curated `elfie.public`/`nest.public` surfaces; deep domain imports are machine-guarded. | `Elfie`/`ElfieFactory` are the only production aggregate entry points, expose the approved typed capabilities, and deep caller imports are removed and guarded. | target=ELF-001 public Facades; inventory=production Elfie callers; references=deep-import scanner; verification=Factory and architecture tests; residuals=none |
| ELF-002 | P0 | closed | Skills are now Brain-owned under `elfie/brain/reasoning/skills/`; the former root package and its Runtime proxy are deleted. | Brain-owned declarations, in-memory policy and semantic tool-key authorization are covered by focused tests; no Runtime adapter, store, path or execution implementation remains in the retired Skill package. | target=ELF-002 Skill ownership; inventory=elfie/brain/reasoning/skills; references=retired package scan; verification=Skill policy tests; residuals=none |
| ELF-003 | P0 | closed | Brain now exposes separate typed `FoodPort`, `ModelPort` and `ToolPort`; Runtime model execution receives a scoped Tool Adapter through Bootstrap. | `ToolRequest`/`ToolResult` are closed immutable contracts, the Adapter preserves global and per-Elfie safety vetoes, structured and ordinary paths use the injected Port, and the legacy broad Runtime bridge is absent. | target=ELF-003 cognitive Ports; inventory=Brain Ports and Bootstrap adapters; references=tool boundary scan; verification=tool/model contract tests; residuals=none |
| ELF-004 | P0 | closed | SQLite/schema/record mapping has been removed from `elfie/brain/memory/`; semantic algorithms depend on `MemoryStorePort` and validated `MemoryMetadata`. | Brain memory tests use the in-memory Fake, persistence tests live under Infrastructure, the exact system technical-import baseline is empty, and final-store reopen behavior remains covered. | target=ELF-004 Memory ownership; inventory=elfie/brain/memory and Infrastructure persistence; references=technical-import baseline; verification=memory reopen tests; residuals=none |
| ELF-005 | P0 | closed | Profile loading and path resolution are owned by Infrastructure/Bootstrap; `assemble_profile` and `ElfieFactory` receive only typed profile/dependency inputs. | `ProfileStorePort` remains the domain boundary, bundled defaults are resource-backed, and no Elfie initialization or Factory API accepts a storage path or concrete profile repository. | target=ELF-005 Profile boundary; inventory=Profile Store and Bootstrap; references=path/import scan; verification=profile round-trip tests; residuals=none |
| ELF-006 | P0 | closed | Body semantics, registry and binding remain in Elfie while Godot/device/product-hosting implementations are outside the domain; the remaining Headless/native bodies are deterministic no-I/O references. | Multi-body identity/binding and typed event/receipt tests pass; no Body implementation imports transport, credentials, process ownership or Nest world facts. | target=ELF-006 Body authority; inventory=elfie/body and body adapters; references=body dependency scan; verification=body switching tests; residuals=none |
| ELF-007 | P0 | closed | `elfie/communication/` owns only canonical envelopes, policy, Hub/router, bounded inbox/outbox and injected channel Ports. WeChat/Telegram and message-delivery transport live in `infrastructure/communication/`; authenticated versioned App conversation and WebSocket routes resolve member/target before delivery Facade. | Keep communication Port/Adapter direction, authenticated ingress, identity/deduplication and delivery-order tests green. | target=ELF-007 Communication authority; inventory=communication and delivery adapters; references=ingress identity scan; verification=dedupe/order tests; residuals=none |
| ELF-008 | P1 | closed | `ElfieFactory` is now a typed domain builder over an immutable `ElfieAssembly`; storage paths, Godot APIs and staged Runtime configuration are resolved before it is called. | Factory assembly/restore tests pass, the returned aggregate is complete but not started, and Bootstrap remains the only production composition root. | target=ELF-008 Factory composition; inventory=elfie/factory and Bootstrap; references=composition-root scan; verification=assembly/restore tests; residuals=none |
| ELF-009 | P1 | closed | Public Profile, Body, Communication, Nest Session, Runtime observation and Infrastructure Port models use named immutable models or bounded JSON values. Permanent Port ratchet rejects `Any`/`object`/concrete peer Adapter signatures; body/channel/Bootstrap evidence is focused and machine-checked. | Keep the strict Port ratchet and evidence green; internal algorithm-local mappings are not public boundary contracts. | target=ELF-009 typed boundaries; inventory=public Port modules; references=Port ratchet; verification=architecture model tests; residuals=none |
| ELF-010 | P0 | closed | `ElfieProfile` now contains only immutable identity, origin, appearance and embodiment facts. Selfhood and Energy seeds are Brain-owned under `elfie/brain/`, persisted separately by Infrastructure, and loaded through Bootstrap/Factory; the mixed Profile defaults and broad fields are deleted. | Selfhood/Energy owners receive all mutable values without fallback or dual authority. | target=Elfie Profile/Selfhood/Energy ownership clauses; inventory=elfie/profile, elfie/brain/selfhood, elfie/brain/energy, adoption and restore paths; references=no Profile personality/capability/system-limit fields or legacy defaults; verification=Selfhood, Factory, adoption, Lab and architecture suites pass; residuals=none |
| ELF-011 | P0 | closed | Brain now owns private cognitive coordination and context assembly; Communication, Embodied and Internal inputs form typed single-domain Turns with host-enforced response scope, and the former root cognitive files are removed. | Focused Brain lifecycle, lane, scope and decision-boundary tests pass; Elfie Lab shows the source domain, Scope, decision and delivery receipt for the communication loop. Keep this boundary ratchet green while later Brain capabilities are added. | target=ELF-011 Brain Turn ownership; inventory=elfie/brain/runtime and Lab; references=root cognition scan; verification=Brain lifecycle/Lab tests; residuals=none |
| ELF-012 | P0 | closed | Body Registry/Binding now assigns an authority generation to the current Body; NervousSystem accepts only that generation, the output executor rejects receipts after a switch, and interruption targets the original Body; failed switches retain the previous Body. | Stage-three Headless and real Godot acceptance passes; body switching, stale-event rejection, stale-receipt rejection, connection-failure rollback and one-current-body authority have focused tests plus real `world_ready`/`intent_terminal` evidence. | target=ELF-012 one-body authority; inventory=body registry/binding and Godot adapter; references=generation guards; verification=body switch and Godot E2E tests; residuals=none |
| ELF-013 | P1 | closed | `elfie/genesis/` now owns the validated one-time creation bundle, initialization manifest, bounded biography plan and idempotent memory committer. Adoption writes Profile, Brain Selfhood/Energy seeds and Genesis memory to their final owners exactly once; ordinary `Elfie` runtime receives only typed seed inputs. | Genesis creates the ephemeral bundle and exits after final-owner commits. | target=Genesis one-time creation clauses; inventory=elfie/genesis, initialization, adoption workspace and brain seed adapters; references=typed bundle validation, manifest duplicate guard and final-owner persistence; verification=Genesis, adoption, persistence and Lab suites pass; residuals=none |
| ELF-014 | P0 | closed | Brain now owns the Persistent Activity semantic Port and output boundary; Lab injects a per-Elfie SQLite Adapter. Validated drafts are committed idempotently, waiting work wakes through typed Internal events, and child Communication/Embodied receipts settle Activity progress without replay after restart. | Focused Activity, persistence and Lab tests cover cross-Turn state, wake-up, Scope validation, receipt-backed terminal state, restart recovery and no duplicate delivery. | target=ELF-014 Activity authority; inventory=Brain Activity and Lab adapter; references=receipt settlement; verification=Activity/persistence/restart tests; residuals=none |
| ELF-015 | P1 | closed | The first bounded Recovery Motivation drive and bounded Cognitive Consolidation slice now have Brain owners and Lab evidence. Consolidation is limited to sleeping-window episodic memory and cannot produce external effects; broader autonomous drives and growth remain separate scope. | Motivation emits cooldown/satisfaction-controlled candidates; Cognitive Consolidation emits a checkpointed internal candidate with a fixed episode budget and commits Memory only after a completed Internal receipt. Focused Brain/Lab tests and Web build pass; no message, body or Activity output is created by the night-work path. | target=ELF-015 bounded autonomous work; inventory=Motivation and Consolidation; references=internal-only output guards; verification=Brain/Lab and Web tests; residuals=none |
| ELF-016 | P0 | closed | Brain now owns a bounded `ReasoningRun` inside one Turn: model, cognition Tool, real Observation, verification and terminal success/failure all stay inside Brain; only a settled `TurnDecision` can reach the existing external decision boundary. | 26 focused Brain/Lab tests pass; real Elfie Lab shows Tool→Observation, refuses to create an external receipt from tool text, enters explicit `failed/no_op` when the model is unavailable, and starts a separate urgent Turn after stale interruption. Plain-text Provider `owner_message_fallback` is recorded as degradation rather than a success fact. | target=ELF-016 bounded reasoning; inventory=Brain reasoning and Tool/Observation loop; references=external-decision guard; verification=Reasoning/Lab tests; residuals=none |
| ELF-017 | P0 | closed | Orientation and Selfhood are independent authorities. Emotion, Energy, Memory, Orientation, Selfhood, Motivation and Cognitive Consolidation participate in one continuity checkpoint. Orientation candidates derive from current Body generation, conversation, location and Activity and commit only through Turn Settlement. | Focused state, settlement and cross-module recovery tests cover explicit ownership, source/version rules, cross-Turn restore, stale checkpoint rejection and single-message resistance for personality and norms. | target=ELF-017 continuous life state; inventory=Brain state owners and continuity; references=checkpoint/settlement guards; verification=state and cross-module recovery tests; residuals=none |

**Closure state:** ready

## Machine coverage

The system layer scanner prevents forbidden root imports and ratchets direct
technical imports in Elfie; its exact Elfie technical-import baseline is now
empty. Focused cognitive tests protect the public body/communication contracts,
strict Pydantic boundaries, Facade size, dependency direction and the
Brain-owned ToolPort surface. Memory Fake tests, Infrastructure persistence
tests and the model/tool end-to-end path provide the evidence for the closed
slices.

The Ports/Adapters and life-system rows are closed by migrated production call chains, focused
behavior evidence and permanent machine ratchets. Contract 2.0 reuses those
boundaries and existing baselines; it deliberately creates no second legacy
baseline. The register is closure-ready evidence; it is not a second runtime
authority or permission to add compatibility fields.

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
