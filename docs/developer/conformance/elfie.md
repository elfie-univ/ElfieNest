# Elfie internal architecture conformance

> Open migration register for the normative
> [Elfie internal architecture contract](../contracts/elfie). It records the
> evidence for closed slices and the exact current gaps without weakening the target. Rows
> ELF-001 through ELF-009 record the Ports/Adapters migration; ELF-010 onward
> records the life-system work adopted by the current contract version 2.6.

## Conformance closure

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| ELF-001 | P1 | closed | Production App orchestration and interface callers use the curated `elfie.public`/`nest.public` surfaces; deep domain imports are machine-guarded. | `Elfie`/`ElfieFactory` are the only production aggregate entry points, expose the approved typed capabilities, and deep caller imports are removed and guarded. | target=ELF-001 public Facades; inventory=production Elfie callers; references=deep-import scanner; verification=Factory and architecture tests; residuals=none |
| ELF-002 | P0 | closed | Brain owns the typed Skill boundary in `elfie/brain/reasoning/skill_port.py`; official procedural sources are bundled as `config/brain/skills/<name>/SKILL.md`, and the former pseudo Skill package is deleted. | Metadata is disclosed before a read-only native `load_skill` operation; frontmatter/name/body validation, directory isolation and no-script behavior are covered by focused tests. Skills are not Tool definitions and do not grant Tool permission. | target=ELF-002 Skill ownership; inventory=skill_port.py and config/brain/skills; references=retired package and marker scan; verification=bundled catalog and Reasoning tests; residuals=none |
| ELF-003 | P0 | closed | Brain now exposes separate typed `FoodPort`, `ModelPort` and `ToolPort`; executable Tool definitions are explicit in the Infrastructure registry and model adapters receive a scoped native Tool view through Bootstrap. | `ToolDefinition`/`ToolCall`/`ToolRequest`/`ToolResult` are typed contracts, the Adapter preserves global and per-Elfie safety vetoes, native provider exchanges cover ordinary and structured paths, and the legacy marker loop is absent. | target=ELF-003 cognitive Ports; inventory=Brain Ports, Tool registry and Bootstrap adapters; references=tool boundary scan; verification=tool/model/validation contract tests; residuals=none |
| ELF-004 | P0 | closed | SQLite/schema/record mapping has been removed from `elfie/brain/memory/`; semantic algorithms depend on `MemoryStorePort` and typed Memory records. | Brain memory tests use the typed in-memory SQLite adapter, persistence tests live under Infrastructure, the exact system technical-import baseline is empty, and final-store reopen behavior remains covered. | target=ELF-004 Memory ownership; inventory=elfie/brain/memory and Infrastructure persistence; references=technical-import baseline; verification=typed Memory reopen tests; residuals=none |
| ELF-005 | P0 | closed | Profile loading and path resolution are owned by Infrastructure/Bootstrap; `assemble_profile` and `ElfieFactory` receive only typed profile/dependency inputs. | `ProfileStorePort` remains the domain boundary, bundled defaults are resource-backed, and no Elfie initialization or Factory API accepts a storage path or concrete profile repository. | target=ELF-005 Profile boundary; inventory=Profile Store and Bootstrap; references=path/import scan; verification=profile round-trip tests; residuals=none |
| ELF-006 | P0 | closed | Body semantics, registry and binding remain in Elfie while Godot/device/product-hosting implementations are outside the domain; Elfie retains only the deterministic no-I/O Headless test body. The obsolete anatomy/gait branch and its references are deleted. | Multi-body identity/binding and typed event/receipt tests pass; no Body implementation imports transport, credentials, process ownership or Nest world facts; the retired branch and references scan empty. | target=ELF-006 Body authority; inventory=elfie/body and body adapters; references=body dependency scan; verification=body switching tests and retired-path scan; residuals=none |
| ELF-007 | P0 | closed | `elfie/communication/` owns only canonical envelopes, policy, Hub/router, bounded inbox/outbox and injected channel Ports. WeChat/Telegram and message-delivery transport live in `infrastructure/communication/`; authenticated versioned App conversation and WebSocket routes resolve member/target before delivery Facade. | Keep communication Port/Adapter direction, authenticated ingress, identity/deduplication and delivery-order tests green. | target=ELF-007 Communication authority; inventory=communication and delivery adapters; references=ingress identity scan; verification=dedupe/order tests; residuals=none |
| ELF-008 | P1 | closed | `ElfieFactory` is now a typed domain builder over an immutable `ElfieAssembly`; storage paths, Godot APIs and staged Runtime configuration are resolved before it is called. | Factory assembly/restore tests pass, the returned aggregate is complete but not started, and Bootstrap remains the only production composition root. | target=ELF-008 Factory composition; inventory=elfie/factory and Bootstrap; references=composition-root scan; verification=assembly/restore tests; residuals=none |
| ELF-009 | P1 | closed | Public Profile, Body, Communication, Nest Session, Runtime observation and Infrastructure Port models use named immutable models or bounded JSON values. Permanent Port ratchet rejects `Any`/`object`/concrete peer Adapter signatures; body/channel/Bootstrap evidence is focused and machine-checked. | Keep the strict Port ratchet and evidence green; internal algorithm-local mappings are not public boundary contracts. | target=ELF-009 typed boundaries; inventory=public Port modules; references=Port ratchet; verification=architecture model tests; residuals=none |
| ELF-010 | P0 | closed | `ElfieProfile` is now the external immutable dossier: identity, fixed age/origin anchors and final virtual appearance only. Generator provenance, user answers, Canon/world knowledge, arrival facts, personality, capabilities and runtime state are outside Profile; authorized observers build a read-only dossier from the owning stores. | Keep the contract 2.5 allowlist and the owner-specific projections; any future change to existing workspaces is a separately approved data policy, not a Profile fallback. | target=Elfie 2.5 Profile clauses and ADR-0033; inventory=`elfie/profile/`, profile stores, observer projections and final persistence schema; references=profile field/reference inventory; verification=Profile boundary, final-schema, fresh-create, reopen and owner-projection tests; residuals=real-workspace migration policy remains tracked by SHD-007. |
| ELF-011 | P0 | closed | Brain now owns private cognitive coordination and context assembly; Communication, Embodied and Activity inputs form typed single-domain Turns with host-enforced response scope, and the former root cognitive files are removed. | Focused Brain lifecycle, lane, scope and decision-boundary tests pass; Elfie Lab shows the source domain, Scope, decision and delivery receipt for the communication loop. Keep this boundary ratchet green while later Brain capabilities are added. | target=ELF-011 Brain Turn ownership; inventory=elfie/brain/runtime and Lab; references=root cognition scan; verification=Brain lifecycle/Lab tests; residuals=none |
| ELF-012 | P0 | closed | Body Registry/Binding now assigns an authority generation to the current Body; NervousSystem accepts only that generation, the output executor rejects receipts after a switch, and interruption targets the original Body; failed switches retain the previous Body. | Stage-three Headless and real Godot acceptance passes; body switching, stale-event rejection, stale-receipt rejection, connection-failure rollback and one-current-body authority have focused tests plus real `world_ready`/`intent_terminal` evidence. | target=ELF-012 one-body authority; inventory=body registry/binding and Godot adapter; references=generation guards; verification=body switch and Godot E2E tests; residuals=none |
| ELF-013 | P0 | closed | `elfie/genesis` is the sole semantic compiler and emits one typed bundle for Profile, Selfhood, Memory knowledge, people, relationships, episodes and startup state. Admission owns the durable publication state machine; Infrastructure only stages, validates and saves typed output. Creation inputs are confined to the unpublished transaction and final restore does not load the source package. | Preserve the single candidate→compile→submit path, source-first Memory unit of work, input disposal and Runtime-last publication order. | target=Elfie 2.5 Genesis clauses, Application 1.11 and ADR-0033; inventory=`elfie/genesis/`, adoption/resident admission, workspace adapter and Memory store; references=semantic-decision call-chain inventory; verification=Genesis/compiler, source-first Memory, staging/reopen, admission recovery, idempotency, input-disposal, restore-without-source and architecture tests; residuals=external model/Godot acceptance and real-workspace policy remain outside this structural closure. |
| ELF-014 | P0 | closed | Brain now owns the Persistent Activity semantic Port and output boundary; Lab injects a per-Elfie SQLite Adapter. Validated drafts are committed idempotently, waiting work wakes through typed Activity events, and child Communication/Embodied receipts settle Activity progress without replay after restart. | Focused Activity, persistence and Lab tests cover cross-Turn state, wake-up, Scope validation, receipt-backed terminal state, restart recovery and no duplicate delivery. | target=ELF-014 Activity authority; inventory=Brain Activity and Lab adapter; references=receipt settlement; verification=Activity/persistence/restart tests; residuals=none |
| ELF-015 | P1 | closed | The first bounded Recovery Motivation drive and bounded Cognitive Consolidation slice now have Brain owners and Lab evidence. Consolidation is limited to sleeping-window episodic memory and cannot produce external effects; broader autonomous drives and growth remain separate scope. | Motivation emits cooldown/satisfaction-controlled candidates; Cognitive Consolidation emits a checkpointed Activity candidate with a fixed episode budget and commits Memory only after a completed Activity receipt. Focused Brain/Lab tests and Web build pass; no message, body or Activity output is created by the night-work path. | target=ELF-015 bounded autonomous work; inventory=Motivation and Consolidation; references=Activity-only output guards; verification=Brain/Lab and Web tests; residuals=none |
| ELF-016 | P0 | closed | Brain now owns a bounded `ReasoningRun` inside one Turn: native Model/Skill/Tool calls, real Observations, verification and terminal success/failure all stay inside Brain; only a settled `TurnDecision` can reach the existing external decision boundary. | Focused Brain/Lab tests show native Tool→Observation and procedural Skill load, refuse marker text as an execution protocol, refuse to create an external receipt from tool text, enter explicit `failed/no_op` when the model is unavailable, and start a separate urgent Turn after stale interruption. Plain-text Provider output remains inert/degraded. | target=ELF-016 bounded reasoning; inventory=Brain reasoning and native Model/Skill/Tool Observation loop; references=external-decision guard; verification=Reasoning/Lab/native validation tests; residuals=none |
| ELF-017 | P0 | closed | Orientation and Selfhood are independent authorities. The generic continuity checkpoint contains Energy, Memory, Motivation, Cognitive Consolidation and conversation state, but deliberately excludes Selfhood and Orientation; Selfhood restores from its own sole durable document, Orientation is re-sourced, and short-lived Emotion returns to its personality-derived baseline on sleep or restart. | Focused state, settlement and cross-module recovery tests cover explicit ownership, source/version rules, separate durable-owner restore, process-local Emotion restart, stale checkpoint rejection and single-message resistance for personality and norms. | target=ELF-017 continuous life state and ADR-0030/0031; inventory=Brain state owners, Selfhood store and continuity; references=checkpoint/settlement guards; verification=state and cross-module recovery tests; residuals=none |
| ELF-018 | P0 | open | The three Brain domains and dynamic catalog path are implemented; the real Godot room now proves movement, terminal Body feedback, targeted hearing, semantic vision, touch and proprioceptive position under the stage-one Brain-owned Mock mode. | Keep exactly `Communication`/`Embodied`/`Activity`; keep `ACCEPTED`/`STARTED` in the ledger; publish one terminal embodied outcome plus compatible body facts through EventWorkspace; separately evidence live model-driven control. Hearing/vision/touch/position scenarios are now evidenced. | target=ADR-0033 and Brain/Elfie/System/Nest-Godot contracts v1.7/2.4/1.10/1.2; inventory=Brain workspace/decision types, Body/NervousSystem, Godot Adapter/Transport/Gateway and vertical-slice plan; references=dynamic capability catalog, scoped receipt payloads, Brain-owned Mock controller and real-room E2E harness; verification=relevant Python regression 825/825, architecture suite 229/229, real Godot room E2E `build/e2e/brain-godot-live` with scene manifest, `world_ready`, actual movement, `speech_reach`, `visual_observation`, targeted Body inputs and terminal outcomes, plus compile/lint; residuals=external physical body, v2 async submission/receipt stream and live model-driven embodied control remain open |

## Genesis v1 gap

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| ELF-019 | P0 | open | The published `config/genesis/` package is now the sole creation source and the old production paths are removed (CFG-006 closed). Remaining gaps are end-to-end life feasibility, accepted-input/version binding, complete personal knowledge/relationship/Episode/Selfhood projection, and Nest-backed admission confirmation. Durable Genesis publication currently precedes runtime registration; runtime recovery is separate. | Close the remaining semantic and admission gates below on the existing single creation path. Preserve source-free restore, the activated package binding, and final-owner authority; do not add a second source path. | target=Elfie 2.6, Application 1.12, Configuration 1.7, ADR-0033/0040; inventory=Bootstrap source, Adoption candidate/session, Genesis compiler/initializer, Memory, Admission, Nest and UI; references=`config/genesis/program.yaml`, ADR-0033/0040, `app_wiring/adoption.py`, `compiler.py`, `initializer.py`, `resident_admission/service.py`; verification=focused characterization, package/feasibility, five-gate semantic, Memory Recall and interrupted-admission checks; residuals=the seven remaining closure slices below. |

**Closure state:** open

## Machine coverage

The system layer scanner prevents forbidden root imports and ratchets direct
technical imports in Elfie; its exact Elfie technical-import baseline is now
empty. Focused cognitive tests protect the public body/communication contracts,
strict Pydantic boundaries, Facade size, dependency direction and the
Brain-owned ToolPort surface. Memory Fake tests, Infrastructure persistence
tests and the model/tool end-to-end path provide the evidence for the closed
slices.

The earlier Ports/Adapters and life-system rows retain their evidence. The v0.2
Profile and Genesis ownership gaps in ELF-010 and ELF-013 are closed for the
current implementation; the full Genesis v1 behavior remains open in ELF-019.
Embodied-control gaps in ELF-018, real-workspace migration and external
model/embodiment acceptance remain separate gates. Contract 2.6 reuses these boundaries and
existing baselines; it does not create a second legacy baseline. This register is not a second runtime
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
4. continuous life state closed ELF-017 and established Selfhood/Energy/Orientation owners; strict Profile cleanup is closed structurally in ELF-010;
5. Persistent Activity closes ELF-014 before Motivation can create autonomous work;
6. bounded Motivation and Cognitive Consolidation close ELF-015;
7. Genesis now closes ELF-013 for the v0.2 structural slice: semantic compilation is in `elfie/genesis`, creation inputs are transaction-only, and final-owner/source-isolation evidence exists.

## Genesis v1 closure order

The Genesis v1 closure order is recorded below. CFG-006 is now closed; the
remaining items describe separate open implementation gates:

1. **Typed source and product cutover (`CFG-006`; closed).** The published
   `config/genesis/program.yaml` manifest and its 18 members feed the typed
   creation and availability views. Adoption and Genesis use this single source;
   old production config files are removed, and Myelle remains excluded as
   draft. Check: package integrity, closed inventory, release-manifest coverage
   and persisted Adoption/Memory E2E.
2. **Geography and life-feasibility primitives (`elfie/genesis`).** Use the 100
   cells, 83 birth-eligible cells, allowed species regions, 16 ordered land chains,
   local same-subregion adjacency and the four registered ferry ports from that
   view. Expose legal paths and travel
   days (two per land edge, three per water edge), not invented straight lines.
   Check: known routes, ordinary ferry access to the lake island, blocked
   land crossing, inaccessible Cloudcrown and unregistered dungeon access, plus
   feasible birth/guardian/learning/arrival witnesses for eligible stages.
3. **Candidate gate (`Adoption`, `GenesisEngine`).** Validate hard choices and
   supported age/appearance; generate five distinct candidates where feasible
   within 12 complete-candidate attempts per batch (the existing 96 internal
   appearance proposals are not extra attempts), each with a life witness before
   display. The five questionnaire answers affect personality only.
   Preserve the existing 1–3 invitations and deterministic reply semantics.
   Check: five-way diversity, age ≥2, impossible-choice explanation, no
   unproven candidate display and no Myelle option while draft.
4. **Acceptance freeze (`Adoption`, Admission reservation).** Atomically bind
   the accepted candidate/name, package/policy/compiler revisions, seed, time
   anchor and idempotency key in a private durable envelope. Validate the name
   as data, including Unicode/control/reserved-character rules. Published replies
   never change, and restart or candidate TTL cannot regenerate an accepted
   identity. Check: duplicate/changed clicks, expiry, package revocation and
   restart all preserve or reject the *same* reservation.
5. **LifeContext (`elfie/genesis/compiler.py`).** Choose an allowed region
   uniformly, then a birth cell uniformly within it; build private home,
   age-valid care, one real apprenticeship when applicable, work and actual
   journeys in chronological order. Actual visit is distinct from reachability;
   arrival needs consent, age ≥2 and the simple three-local-day preparation.
   Check: boundary cells, missing guardian/teacher/route and youth cases fail
   cleanly; every selected route and event slot is time/space-valid.
6. **Personal plan (`elfie/genesis`, Selfhood).** Evaluate the four declared
   knowledge condition leaves against evidence at the time of acquisition;
   draw difficulty once and keep the entire resident paragraph or none. Build
   actual people/relationships, necessary complete Episodes (normally at least
   five, with the youth exception and no padding), personal life facts and
   closed Selfhood mapping without quotas or generic personality fallback.
   Model wording may only project fixed facts. Check: no self-supporting
   knowledge/event, no invented stranger,
   youth episode exception, no discarded life fact or unknown mapping.
7. **Bundle, Memory and determinism (`elfie/genesis/initializer.py`).** Jointly
   validate identity/age, timeline, routes, relationships, knowledge, Selfhood
   and final-owner references; use versioned canonical SHA-256 domains and
   bounded dependency-aware backtracking. Submit only knowledge, relationships
   and episodes through Memory's existing atomic source-first entry; index
   objects to their actual evidence, not the first Episode by default. Check:
   fixed vectors, retry equivalence, failure atomicity, source-free reopen and
   Recall with no unearned facts or technical markers.
8. **Admission transaction (`resident_admission`, Adoption, Nest).** Extend the
   current durable state machine with a real Nest bed reservation/confirmation,
   execution fencing, package-revocation ordering, compensation and status/
   cancellation. `committed` is the activation fence only after all three owner
   results; Runtime connection follows it. Check: concurrency, duplicate calls,
   each crash window, cancellation before/after publication and no partially
   visible resident.
Each slice first characterizes the existing path and then changes only its
owner. No fallback, dual-read period, new life generator or Profile/Canon runtime
dependency is permitted. The closed ELF-013 structural slice stays closed;
ELF-019 remains open until its remaining generation and admission evidence exists.
CFG-006 is closed in the [configuration-management register](configuration-management).
Migration of existing real workspaces and Myelle role-asset completion are
separate scopes; neither is hidden inside Genesis v1 cutover.
