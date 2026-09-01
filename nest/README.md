# Nest module

> 中文版：[`README_zh.md`](README_zh.md)

## Module positioning

`nest/` implements the Python domain model of an Elfie's activity space: it
maintains resident IDs, in-nest semantic state, the environment clock and
interaction propagation. Godot transport and protocol adapters live outside
the domain in `infrastructure/godot/`.

## Responsibilities and non-responsibilities

Responsible for:

- Resident registration, removal, long-term bed allocation, posture and
  activity state;
- Environment time advancement and desired environment rules;
- Semantic speech, vision and intent correlation plus one typed Nest event
  outbox;
- The scene semantic catalog and the Runtime's temporary semantic mirror;
- World rules applied after typed facts arrive through the NestSession boundary.

Not responsible for:

- Creating, restoring or holding real `Elfie` / `ElfieIndividual` objects;
- Running a single Elfie's cognition, memory, body or communication lifecycle;
- Defining house geometry, world coordinates, collision shapes, navigation
  meshes, furniture assets or rendering;
- Orchestrating cross-authority runtime flows or product account flows.

The `Nest` facade composes the four owner states and exposes typed use-cases. It
does not store furniture copies, coordinates or real Elfie objects. The single
source of truth for houses, geometry, coordinates, motion, collision and
rendering is the standalone Godot source project at `godot_project/`; Python
keeps only business-required semantic state and the typed communication
boundary.

## Directory map

```text
nest/
├── nest.py             # stable Nest facade and aggregate composition
├── config.py           # aggregate configuration
├── snapshot.py         # technology-neutral durable semantic snapshot
├── space_facilities/   # coordinate-free catalog and environment facts
├── living_rules/       # residents, homes, access and audience policy
├── time_environment/   # clock, phases, schedules and desired state
├── elfie_interaction/  # speech, vision and semantic-action correlation
└── events.py           # cross-owner typed event value objects
```

## Public entry points

- `nest.Nest` — the only Nest aggregate facade;
- `nest.NestConfig` — configuration such as Nest capacity;
- `nest.NestSnapshot` — the durable semantic shape accepted by App state storage;
- `app.orchestration.nest_session` — composes the Nest, real Elfies and typed world channel;
- `infrastructure.godot.gateway` — owns the concrete WebSocket protocol implementation.

Real Elfie registration is performed by `app.orchestration.NestSession`; do not
push real objects into the Nest aggregate.

## Dependency direction

```text
app/orchestration ──> nest
nest.nest ──> the four owner packages + events
app/orchestration/nest_session ──> typed Nest world boundary
infrastructure/godot ──> protocol, host and artifact adapters
godot_project/ ──> single source of truth for scenes and geometry
```

`nest/` does not depend on `app/`, `elfie/` or model, Food or tool adapters. When Nest events
must reach a real Elfie, `app/orchestration/` looks the Elfie up by ID and
invokes it.

## Runtime authority and Observer lifecycle

After connecting, the Godot authority completes the authenticated Gateway
handshake owned by `infrastructure/godot/gateway`. Only one Runtime holds
authority at a time; a newer connection gets an incremented `generation`, and
events from older generations never enter the Nest. Runtime lifecycle selects
the exported host; `nest/` never launches Godot or owns a host process.

Startup sync converges in a fixed order:

1. The orchestration layer sends `configure_world` with `nest_id`, the bed
   count and the world revision;
2. The Runtime builds rooms and navigation, and replies with a
   `scene_manifest` that contains no coordinates;
3. The Runtime replies with `world_configured`; Python sends the full
   `sync_actors` only after both world configuration and navigation are ready;
4. The Runtime replies with `world_snapshot`, and the Nest stores only a
   temporary semantic mirror.

Body actions use lifecycle-bearing semantic commands rather than the brain
issuing "step forward" each frame. For example
`execute_intent(intent="move_to_anchor")` is executed by Godot frame by frame
along the navigation mesh; only key facts such as accepted, started, completed,
blocked, cancelled, timed out, tactile contact and speech listeners are
reported back to Python. When the Runtime disconnects or the generation
changes, any in-flight body command uniformly enters an interrupted state and
is handled by the Elfie's next decision.

Authenticated product clients use the separate Observer surface. A capability
is bound to the product session and narrows to a room or owned Elfie; it exposes
generation/sequence semantic frames only. Observer navigation is limited to
resync and focus intents, and its separately authorized high-level interaction
request is rate-limited. It has no geometry, camera/video frame or authority
credential access.

## Run & debug

Run Nest domain and Godot protocol checks from the repository root:

```bash
uv run --no-sync pytest -q test/nest/

uv run --no-sync pytest -q \
  test/nest/test_nest.py \
  test/infrastructure/godot/gateway/test_api_handshake.py
```

Opening, running or screenshotting the Godot project requires following the
repo's Godot operation gate first; the tests here do not need the Godot editor
to be running. For the dev environment and the unified quality gate see
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Corresponding tests

- `test/nest/test_nest.py`: state, environment clock and interaction
  propagation;
- `test/infrastructure/godot/gateway/`: authority handshake, message validation
  and authoritative session;
- `test/app/orchestration/observer/`: capability-scoped Observer projection and
  generation/sequence behavior;
- `test/infrastructure/godot/`: host selection, launcher, artifact metadata and
  protocol transport;
- `test/e2e/test_nest_runtime_v3.py`: world and full character catalog
  convergence after reconnection;
- `test/architecture/test_project_structure.py`: Nest directory structure and
  legacy package bans;
- `test/app/orchestration/`: composition behavior of real Elfies and the Nest.
