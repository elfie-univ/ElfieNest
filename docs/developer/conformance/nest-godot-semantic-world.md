# Nest–Godot semantic-world conformance

> Temporary migration register for the normative
> [Nest–Godot semantic-world contract](../contracts/nest-godot-semantic-world).
> It records current implementation gaps and the ordered evidence required to
> close them. It does not weaken or redefine the target.

## Why this register was reopened

The original register was removed during the protocol-v3 product migration and
the conformance index was changed to report zero Nest–Godot debt. A later
clause-by-clause and directory-by-directory audit found that transport and
structural work had landed, but several semantic, recovery and cleanup gates
were never proved. Passing tests could not justify deleting the register:

- some tests assert the current dual event/raw-queue behavior rather than the
  contract's single route;
- positive same-zone cases do not prove physical visibility or audibility;
- architecture tests protect imports and typed boundaries, not the complete
  producer-to-consumer behavior;
- the 141-file migration combined work that the approved plan had split into
  independently closable slices.

The zero-debt claim remains guarded by this register. The implementation slices and their
evidence are now complete; every row below is closed and this register remains temporarily
registered until the separate governance-only removal described by NGW-R11.

## Latest closure audit (2026-08-15)

The seven findings from the latest contract audit were closed in the following order. This
short index is intentionally concrete: a directory name or a green unit test alone is not
treated as proof of a route, an owner or a cleanup.

| Finding | Closed implementation | Evidence |
| --- | --- | --- |
| Semantic action identity could be lost between Elfie, Nest and Godot | `intent_id`, `body_generation`, actor identity and `initiator=elfie` are required at the Gateway, Nest session, Actor controller and result payload boundaries. | Protocol, classified-ingress, native-body, Nest and runtime-workflow tests; mypy and architecture scans pass. |
| Snapshot restore could merge stale residents and projections | `Nest.restore_snapshot()` now replaces residents, homes, Runtime mirrors and pending interaction state, preserving AWAY and explicit reconciliation. | `test_restore_snapshot_replaces_residents_and_restores_presence` plus Nest/session persistence tests. |
| Legacy raw vision/audio/environment sensors remained | The old sensor package and tests were deleted; Nervous System and public API now use canonical typed semantic events only. | Repository reference scan returns no retired sensor symbols; Elfie nervous-system/body suites pass. |
| Facility visibility bypassed the Godot spatial query boundary | Godot publishes facility markers and filters them through the same range/FOV/occlusion path as anchors. | Runtime interaction and navigation headless contracts pass; no Camera3D/media path was added. |
| Non-interaction Nest owners had no common typed event producer | Space and Facilities, Living Rules and Time and Environment emit `NestFactNotice` through the shared outbox; audience policy remains in Living Rules. | Nest owner-event and runtime delivery tests cover target filtering, typed payloads and deduplication. |
| Observer camera reset test was environment-sensitive | The frontend test now establishes its secure-context precondition explicitly. | Web frontend: 105 files / 498 tests passed; typecheck and production build passed. |
| Directory/contract closure was asserted without a complete inventory | Structural, effective-dependency, system-layer and App-layer scans were rerun with tracked/generated/support classification; Godot project status is clean after headless checks. | All four scans report zero forbidden targets; no untracked files or retired sensor references remain. |

## Target source disposition

The four Nest owners are business boundaries. Common aggregate plumbing is not
a fifth owner, and technical catch-all packages are not an acceptable substitute
for ownership.

| Current Nest path | Target disposition |
| --- | --- |
| `nest/nest.py` | Keep the stable `Nest` facade and aggregate composition here. Absorb or make private the broad `NestState` compatibility shell. |
| `nest/space/` | Move its real behavior to the descriptive `nest/space_facilities/` owner package. |
| `nest/rules/` | Move its real behavior to the descriptive `nest/living_rules/` owner package. |
| `nest/time_environment/` | Keep clock, life phase, scheduled rules, desired environment and the time/environment driver here. This remains **Time and Environment**, not `engine`. |
| `nest/interaction/` | Move short-lived speech, vision and semantic-action correlation/assembly to `nest/elfie_interaction/`; do not keep a second delivery queue. |
| `nest/events.py` | Keep the cross-owner typed event mechanism here; it is not a business owner. |
| `nest/engine/` | Remove after its negative-tick rule and callers move into Time and Environment. It does not represent an independent Nest responsibility. |
| `nest/state/store.py` | Remove the compatibility shell after callers use the `Nest` facade and real owner state. |
| `nest/state/models.py`, `errors.py` | Move types and errors to the owner that defines their meaning; retain a root type only when it truly crosses owners. |
| `nest/state/config.py` | Move aggregate configuration to `nest/config.py` if it remains necessary. |
| `nest/state/repository.py` | Split it according to ADR-0016: technology-neutral snapshot semantics and Facade export/restore stay with Nest; the store Port and application error move to `app/orchestration/nest_session/`; concrete SQL/SQLite remains under `infrastructure/persistence/`. Do not create `nest/persistence.py`. |

Godot directories describe source categories, not Nest business modules. The
following disposition prevents both accidental deletion of authored content and
accidental shipping of development material.

| Godot path category | Disposition |
| --- | --- |
| `main.gd`, `main.tscn` | Assembly and mode dispatch only. Remove unused helper APIs after reference proof. |
| `rooms/`, `characters/` | Keep authored physical scenes, geometry, actor resources and runtime assets. These are content, not extra business modules. |
| `runtime/actor/`, `runtime/world/`, `runtime/endpoint/` | Keep the small ElfieNest-owned authority glue. Spatial visibility and audibility belong to `world`, not the Actor controller. |
| `runtime/observer/`, `runtime/lab/`, `ui/`, `lab_preview_controller.gd` | Keep only referenced observer/Lab presentation behavior. They do not own physical or household authority. A rename is not required merely for symmetry. |
| `scripts/test/`, `scripts/tools/`, `characters/tools/`, character `source/` trees | Treat as test, authoring or developer-only inputs. Classify audit/render scripts correctly and exclude all of them from release exports. |
| Unreferenced helpers, reference scenes and ignored-source `.import` sidecars | Review one item at a time; delete only after scene, preload, CLI, documentation and export references are all absent. |

## Closed conformance rows

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| NGW-R01 | P0 | closed | Temporary Nest containers were removed and each fact/model/error now follows its owner. | Nest facade, owner directories and no-legacy-import inventory are enforced by `scripts/governance/boundaries/structural_scope.py` and `test/architecture/test_project_structure.py`; `test/nest` and `mypy` pass. | target=Nest ownership clauses; inventory=nest root and four owner trees; references=no old package or NestState callers; verification=54 focused tests and 49-file mypy pass; residuals=none |
| NGW-R02 | P0 | closed | Typed Nest event delivery is the single production route, including owner-created fact notices. | Interaction correlation and the four owner boundaries emit one typed envelope; the router resolves explicit audiences and retries by the same event identity. | target=common event mechanism; inventory=nest/events.py, nest/elfie_interaction/hub.py, Nest owner emitters and orchestration router; references=event-route and retired-sensor scans; verification=Nest owner-event, speech, visual and workflow duplicate/non-target tests pass; residuals=none |
| NGW-R03 | P0 | closed | Structured hearing, vision and semantic-action payloads retain emotion, cause, target and intent identity through delivery. | The production consumer projects each envelope to the owning Elfie exactly once, including typed `NestFactNotice` payloads. | target=structured semantic perception clauses; inventory=events.py, hub.py, body contracts and world_perception.py; references=typed delivery and protocol identity tests; verification=positive, non-target, retry and dedupe scenarios pass; residuals=none |
| NGW-R04 | P0 | closed | Runtime/generation/revision provenance and one authority-change invalidation path cover resident, environment and pending interaction state. | Stale frames are rejected; snapshot restore replaces rather than merges resident state; only current desired environment is resynchronized. | target=generation and recovery clauses; inventory=runtime_sync, runtime_events, Nest restore and interaction invalidation; references=stale/recovery/restore workflow tests; verification=2350 full Python tests plus 3 skips pass on latest origin/main; residuals=none |
| NGW-R05 | P1 | closed | Household Living Rules now own membership, Home, sharing/access, occupancy, audience filtering and environment override decisions without enterprise roles. | All semantic action and event audience decisions call the same Nest rules. | target=Household Living Rules owner; inventory=living_rules and Nest facade; references=home, audience and override callers; verification=Nest/workflow tests pass; residuals=none |
| NGW-R06 | P0 | closed | Godot World owns bounded visual spatial queries and returns candidates without media or coordinates crossing Nest. | Anchors and facility markers use the same range/FOV/occlusion path; no per-Elfie Camera3D or screenshot/VLM route exists. | target=Godot spatial-query clauses; inventory=rooms/nest.gd, runtime/world and spatial query tests; references=Actor has no world-query owner path and retired-sensor scan; verification=Godot scene, environment, interaction and navigation headless contracts pass; residuals=none |
| NGW-R07 | P0 | closed | Godot World computes speech reach candidates while Nest retains content, emotion and final resident audience policy. | Speech uses the typed Nest bridge, targets only Godot-returned listeners after Living Rules filtering and does not invoke TTS/STT for Elfie hearing. | target=SpeechBridge clauses; inventory=runtime/world, gateway, interaction hub and body contracts; references=protocol identity and speech workflow tests; verification=Godot runtime interaction contract and targeted/retry delivery tests pass; residuals=none |
| NGW-R08 | P1 | closed | Environment actual state is a stable `nest/environment` object projection owned by Space and Facilities with Runtime provenance. | Desired state remains Time and Environment-owned and recovery resends only that desired state. | target=EnvironmentChannel clauses; inventory=space_facilities models/catalog, adapter and Godot environment controller; references=object-id validation; verification=29 environment/persistence tests and Godot runtime validation pass; residuals=none |
| NGW-R09 | P1 | closed | Actor code performs body execution only; World and `spatial_queries.gd` own visual and speech queries, with one Bootstrap-created Gateway. | No Python physical mirror or second Gateway was introduced. | target=Godot authority clauses; inventory=godot_project/runtime and infrastructure/godot; references=world ownership/static scans; verification=runtime observer and scene-path tests pass; residuals=none |
| NGW-R10 | P1 | closed | Web and Linux Dedicated export presets share a complete developer/authoring exclusion boundary and generated manifests record it. | Authoring-only candidates are classified and tracked `.import` sidecars under source trees are gone. | target=export boundary clauses; inventory=export presets, export_boundary.py and source candidates; references=22 export/runtime tests and zero source `.import` files; verification=manifest checks plus candidate/reference scan pass; residuals=none |
| NGW-R11 | P1 | closed | README ownership and route descriptions match the verified four-owner implementation; the register remains registered for separate governance-only removal. | Structural, effective-dependency and layer scans are rerun with a complete target/support/generated inventory rather than inferred from tests. | target=ADR-0015 closure lifecycle; inventory=English/Chinese contracts, READMEs, all Nest/Godot paths, scanner and register; references=bilingual row parity, retired-route scan and current-main audit; verification=governance/architecture suites and four deny-all scans pass; residuals=none |
| NGW-R12 | P0 | closed | Nest exposes only `NestSnapshot` and facade export/restore; App owns `NestStateStorePort` and timing; SQLite remains Infrastructure. | No Nest Repository export, deep `nest.state` mutation or legacy sensor persistence remains. | target=ADR-0016 persistence ownership; inventory=Nest snapshot, App ports/session and SQLite adapter; references=old repository/state and sensor import scans; verification=persistence/workflow tests, mypy and system-port architecture gate pass; residuals=none |

**Closure state:** ready

## Completed migration order

Implementation used independently approved, reviewable slices. Each phase
migrated its real producer, typed boundary, consumer and focused evidence before
the next phase started.

1. **NG-R1 — Unique event delivery (`NGW-R02`, `NGW-R03`).** Establish the one
   production Nest event consumer, preserve structured semantic payloads, then
   delete raw sensory queues and compatibility speech delivery.
2. **NG-R2 — Generation and recovery (`NGW-R04`).** Add provenance to every
   retained physical projection and implement one authority-change invalidation
   path for projections and pending semantic correlations.
3. **NG-R3 — Household decisions (`NGW-R05`).** Implement the minimal sharing,
   access/occupancy, audience and environment-override behavior actually used by
   product scenarios; do not add enterprise governance.
4. **NG-R4 — Physical perception (`NGW-R06`, `NGW-R07`, `NGW-R09`).** Move
   spatial operations to World and prove real Godot FOV/occlusion/range and
   audibility behavior, including negative cases.
5. **NG-R5 — Environment objects (`NGW-R08`).** Complete one real stateful
   environment capability end to end, then add only product-required objects.
6. **NG-R6 — Nest structural cleanup (`NGW-R01`, `NGW-R12`).** Implement the
   ADR-0016 snapshot/Port split and, only after behavior has one owner and route,
   remove `engine/` and dissolve `state/` according to the accepted disposition.
   This phase must be behavior-preserving.
7. **NG-R7 — Godot source/export cleanup (`NGW-R10`).** Separate runtime export
   inputs from tests/authoring, then remove only proven dead artifacts and
   helpers. Do not delete scene/character content because it is not a business
   module.
8. **NG-R8 — Current documentation and closure (`NGW-R11`).** Completed:
   direct-body, semantic-action, vision, speech, environment and lifecycle
   scenarios were run; current-state docs and evidence are aligned. A separate
   governance-only change may now remove this register and both registry entries.

## Evidence required before closing any row

For each affected semantic fact, the review must show one traceability row with:

1. the exact contract clause and semantic owner;
2. the real producer and typed boundary;
3. the single production route and final consumer;
4. a positive scenario and an explicit non-target/forbidden-route scenario;
5. retry/deduplication identity and, when physical state is involved,
   stale-generation and recovery behavior;
6. source/reference evidence that the replaced route or artifact is gone;
7. real Godot or release-export evidence when engine behavior or packaging is
   claimed.

When a row closes, its `Evidence` cell replaces `pending` with compact
`target=`, `inventory=`, `references=`, `verification=` and `residuals=`
references covering the material above.

A unit test, a passing transport round trip, a directory name, or a screenshot
alone is insufficient. All rows are now closed with the required five evidence
fields; the register and its bilingual registry entries remain until the
separate governance-only removal.
