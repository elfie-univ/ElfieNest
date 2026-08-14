# Nest–Godot semantic-world conformance

> Temporary migration register for the normative
> [Nest–Godot semantic-world contract](../contracts/nest-godot-semantic-world).
> It records current implementation gaps and the ordered evidence required to
> close them. It does not weaken or redefine the target.

## Why this register is open again

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

The zero-debt claim is therefore revoked. Every row below is open until its
current-code closure gate is met.

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

## Current gaps

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| NGW-R01 | P0 | open | `nest/engine/` duplicates `TimeEnvironmentState.advance()`; broad `nest/state/` mixes aggregate composition, configuration, all owner models/errors and a persistence Port; `NestState` remains public compatibility surface. | The target disposition above is reached without compatibility imports; `Nest` is the stable facade; each fact/type has one owner; focused Nest tests and import scans pass. | pending |
| NGW-R02 | P0 | open | The typed `NestEventEnvelope` is produced only by interaction paths while speech and vision also enter raw per-resident sensory queues. Production consumes the raw queues; compatibility speech methods bypass the envelope. | Every owner can emit through one common mechanism; one production consumer delivers typed targeted events exactly once; raw/compatibility delivery paths are deleted; duplicate and forbidden-route tests pass. | pending |
| NGW-R03 | P0 | open | `SemanticActionResult` can remain only in the outbox with no production delivery to its Elfie; speech and vision are converted to flattened Body payloads, and expressed speech emotion is dropped. | `HeardUtterance`, `SemanticVisualScene` and `SemanticActionResult` retain their structured payloads to the target Elfie; emotion and causal identity survive; each has positive, non-target and duplicate tests. | pending |
| NGW-R04 | P0 | open | Generation checks reject some incoming events and desired environment is resynchronized, but resident/environment projections are not uniformly source-labelled, pending speech/vision/action correlations are not collectively invalidated, and stale actual state can survive an authority change. | Every retained physical projection carries Runtime/generation/revision provenance; a generation change invalidates old projections, interrupts pending correlations once and resynchronizes only current desired state; stale/recovery tests pass. | pending |
| NGW-R05 | P1 | open | Living Rules implements membership, Home assignment and bed conflict, but not the accepted sharing, reservation, occupancy, access, audience-policy or environment-override decisions. | The smallest household rule set needed by current product flows is implemented behind `Nest`, with one administrator and no enterprise role/approval system; speech/event audiences and semantic actions consume the same rules. | pending |
| NGW-R06 | P0 | open | Godot visual observation uses same-zone membership plus a fixed distance and lives in the Actor controller; it does not test field of view, occlusion or current physical visibility. | World-owned spatial queries use actor transform, bounded range, FOV, ray/space occlusion and current state; target, behind-observer, occluded, out-of-range, bounded and stale-generation cases pass in real Godot tests. | pending |
| NGW-R07 | P0 | open | Godot speech reach selects every other actor in the same zone; the acoustic profile is validated but does not affect range or propagation, and doors/occlusion are ignored. | World-owned audibility applies the agreed range/profile and obstruction model, returns candidates only, and passes same-zone-but-unheard, out-of-range, blocked, profile and retry cases; Nest remains owner of content and final resident audience. | pending |
| NGW-R08 | P1 | open | Environment support is a coarse light/quiet snapshot. Actual state is placed with desired time/environment state and is not a stable, provenance-bound per-object projection. | Each supported stateful object/group has a stable ID, typed desired command and actual fact/result; actual projection belongs to Space and Facilities, carries provenance, and recovery resends only current desired state. Objects without approved behavior need no script. | pending |
| NGW-R09 | P1 | open | Speech reach and visual observation are implemented in `runtime/actor/actor_controller.gd` even though World and `spatial_queries.gd` exist, so Actor owns actor-relative world queries as well as body execution. | Actor owns body execution only; World owns speech/vision spatial queries; existing narrow Python capabilities and the single Bootstrap-created shared Gateway remain intact. | pending |
| NGW-R10 | P1 | open | Godot exports use `all_resources` while excluding only two source globs, so test/tool/authoring resources can enter release packages. Ignored authoring source still contains tracked import sidecars, and several no-reference candidates remain unclassified. | Runtime export inputs are allowlisted or comprehensively exclude developer/authoring trees; release manifests prove the boundary; every candidate is classified as referenced, authoring-retained or deleted with no broken scene/resource/test reference. | pending |
| NGW-R11 | P1 | open | The register was deleted early and indexes reported zero debt; ADR-0015 now machine-guards that failure mode, but some current README descriptions still contradict the contract's fact ownership and event routes, and final closure evidence does not yet exist. | Current architecture/README text matches verified implementation; the base-aware deletion and evidence gates remain green; every other row is closed with complete evidence before a separate governance-only change removes both mirrors and registrations. | pending |
| NGW-R12 | P0 | open | ADR-0016 now fixes the target, but `NestRepository`, its error and `NestPersistenceSnapshot` remain exported by Nest; App Orchestration owns all production calls and directly mutates broad `nest.state` during restore. | Nest exposes a technology-neutral `NestSnapshot` and Facade export/restore operations; App Nest Session owns `NestStateStorePort`, persistence timing and application errors; Infrastructure implements it; all callers and strict-boundary tests migrate together with no Nest Repository export or deep state mutation. | pending |

## Binding migration order

Implementation work must use independently approved, reviewable slices. A phase
migrates its real producer, typed boundary, consumer and focused evidence before
the next phase starts.

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
8. **NG-R8 — Current documentation and closure (`NGW-R11`).** Run the complete
   direct-body, semantic-action, vision, speech, environment and lifecycle
   scenarios; update current-state docs; close and delete this register in a
   separate governance-only change only when all rows are genuinely closed.

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
alone is insufficient. The register and its bilingual registry entries cannot
be removed while any row remains open.
