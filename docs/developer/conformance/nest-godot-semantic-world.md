# Nest–Godot semantic-world conformance

> Temporary migration register for the
> [Nest–Godot semantic-world contract](../contracts/nest-godot-semantic-world).
> It records current implementation gaps without weakening or redefining the
> target. Delete both language mirrors and their registry entry after every row
> is closed. The mandatory execution order and per-card acceptance evidence are
> defined by the [migration specification](./nest-godot-semantic-world-migration).

## Current gaps

| ID | Severity | Status | Current deviation | Closure gate |
| --- | --- | --- | --- | --- |
| NGW-001 | P0 | open | `nest/` is organized around broad state/engine/interaction containers; `InteractionHub` mixes virtual speech, user messages, collision and tactile buffers instead of the four accepted functional owners. | The real Nest facade delegates to implemented Space/Facilities, Living Rules, Time/Environment and Elfie–Nest Interaction ownership without empty packages; user messages remain in Communication and body contact leaves Nest. |
| NGW-002 | P0 | open | `NestRuntimeEventRouter` sends several Runtime events through every Body transport before separately handling speech or tactile input; semantic type and target do not determine the first route. | Every Runtime event is classified before delivery; actor receipts/perception, semantic results, environment facts, Nest events and lifecycle events have one typed route and explicit targets, with focused no-cross-route tests. |
| NGW-003 | P0 | open | Native Godot Body sensors discard Runtime input while tactile contact is reconstructed through Nest; event identity can change and Python fabricates a force estimate from normalized intensity. | Godot-derived body perception reaches only the owning Body with original event/cause identity and physical values; `NativeSensors` queues typed input; Nest tactile compatibility paths and fabricated quantities are deleted. |
| NGW-004 | P0 | open | Speech text crosses the Godot command/event protocol, listener selection is approximated by same-zone membership, and the same occurrence can traverse Body broadcast and Nest delivery paths. | Nest retains utterance content and expressed emotion; Godot receives an opaque occurrence ID and returns spatial reachability based on the accepted physical model; Nest emits one idempotent targeted `HeardUtterance` per final listener. |
| NGW-005 | P1 | open | Virtual vision still depends on camera screenshot/path heuristics and has no actor-scoped, occlusion-aware `VisibleSet` to `SemanticVisualScene` path. | Godot emits bounded typed visible entities for one actor and observation ID; Nest performs one batch semantic join and delivers one targeted visual perception without screenshots, VLM inference or persisted surroundings. |
| NGW-006 | P0 | open | There is no complete `SemanticBodyIntent` → resolved target → physical result → `SemanticActionResult` workflow; Home lookup and Body execution are not one correlated action cycle. | One authorized intent preserves actor/intent identity across Nest rule resolution and Godot execution, produces one semantic terminal result without a second Brain Turn, and cannot be created or rewritten by Nest. |
| NGW-007 | P1 | open | The Nest clock advances elapsed seconds only; Godot lacks a unified environment command/fact surface for lights, doors, movable facilities and life-phase synchronization. | Time/Environment owns phases and desired state; stateful world objects accept typed commands and return actual facts/results; a new Runtime generation receives current desired state without replaying expired side effects. |
| NGW-008 | P1 | open | Godot actor catalogs still carry Home metadata and Nest stores broad posture/actor mirrors beyond the minimum rule projection, blurring household and physical authorities. | Home and ownership remain Nest facts; Godot receives only resolved spawn/action targets; every retained Nest physical projection is source- and generation-bounded, minimal and invalidated on authority change. |
| NGW-009 | P1 | open | Most scene furniture lacks stable object semantics and narrow state behavior; environment-object changes cannot yet be expressed consistently without leaking NodePath or coordinates. | The Godot scene manifest exposes stable IDs for required rooms, zones, anchors and interactive objects; Nest owns the coordinate-free semantic catalogue keyed by them; only stateful objects have narrow scripts; manifests, commands and facts contain no NodePath or unnecessary coordinates. |
| NGW-010 | P0 | open | `WorldRuntimePort` and protocol models combine world configuration, actor synchronization, body events and interaction events without the accepted semantic lane boundaries. | Consumer-owned typed capabilities distinguish direct Body, semantic action, vision, speech, environment and Runtime control while one Gateway may implement them; Bootstrap wiring and focused contract tests prove no second Gateway or authority. |

## Migration order

The binding order is `NG-M01` through `NG-M15` in the
[detailed migration specification](./nest-godot-semantic-world-migration):

1. establish protocol identity, event classification and direct Body input;
2. establish Space/Facilities, Living Rules, persistence and Time/Environment;
3. remove user-message ownership from Nest and establish the Godot semantic scene;
4. migrate speech/events, structured vision and semantic actions as complete slices;
5. add environment object behavior/recovery, close narrow Ports and perform only
   then the final structural cleanup;
6. delete temporary conformance material in a separate governance-only change.

The detailed card is authoritative when this overview is insufficient. No card
may close a row early, pre-create empty packages, retain a replaced route or
introduce compatibility/dual storage.

## Existing machine coverage

The permanent System scanner already forbids Nest imports of Elfie, App and
concrete Infrastructure and forbids technical transport imports in Nest. The
contract registry, bilingual version checks and focused System/Gateway/Observer
architecture tests govern this target. Semantic event ownership and route
uniqueness require focused product tests in the later migration slices; this
governance change does not claim those tests or behaviors already exist.
