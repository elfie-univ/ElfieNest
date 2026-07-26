# Nest module

> 中文版：[`README_zh.md`](README_zh.md)

## Module positioning

`nest/` implements the Python domain model of an Elfie's activity space: it
maintains resident IDs, in-nest semantic state, the environment clock and
interaction propagation, and provides the protocol adapter needed to talk to
the Godot Runtime.

## Responsibilities and non-responsibilities

Responsible for:

- Resident registration, removal, long-term bed allocation, posture and
  activity state;
- Environment time advancement, speech propagation, collision and tactile and
  other in-nest interactions;
- Godot Runtime v2 authentication, single authoritative session, command/event
  queues and rate limiting;
- The scene semantic catalog, the Runtime's temporary mirror, and integrity
  checks on the exported Web Runtime.

Not responsible for:

- Creating, restoring or holding real `Elfie` / `ElfieIndividual` objects;
- Running a single Elfie's cognition, memory, body or communication lifecycle;
- Defining house geometry, world coordinates, collision shapes, navigation
  meshes, furniture assets or rendering;
- Orchestrating the AI Runtime or product account flows.

`NestState` only stores Elfie IDs, long-term homes and in-nest semantic state —
it does not store furniture copies, coordinates or real Elfie objects. The
single source of truth for houses, geometry, coordinates, motion, collision and
rendering is the standalone Godot source project at `godot_project/`; the
Python side only keeps the business-required semantic state and communication
boundary.

## Directory map

```text
nest/
├── nest.py         # public Nest facade
├── state/          # config, residents, homes, world catalog and Runtime mirror
├── engine/         # environment clock advancement
├── interaction/    # speech, user messages, collision and tactile propagation
├── godot/          # v2 messages, authoritative session, WebSocket gateway and Runtime artifact checks
└── events.py       # Nest domain event value objects
```

## Public entry points

- `nest.Nest` — composes state, environment clock and interaction propagation;
- `nest.NestConfig` — configuration such as Nest capacity;
- `nest.NestFullError` — raised when resident capacity is full;
- `nest.NestState` — runtime container holding only in-nest state;
- `nest.godot.GodotAPIServer` — the WebSocket boundary between Python and the
  Godot Runtime.

Real Elfie registration is performed by `app.orchestration.NestSession`; do not
push real objects into `NestState`.

## Dependency direction

```text
app/orchestration ──> nest
nest.nest ──> state + engine + interaction
nest.godot ──> Nest / Godot boundary
godot_project/ ──> single source of truth for scenes and geometry
```

`nest/` does not depend on `app/`, `elfie/` or `ai_runtime/`. When Nest events
must reach a real Elfie, `app/orchestration/` looks the Elfie up by ID and
invokes it.

## Runtime v2 lifecycle

After connecting, the Godot Runtime must first send a `hello` carrying a random
nonce, a `runtime_id` and `protocol: 2`. Only one Runtime holds authority at a
time; a newer connection gets an incremented `generation`, and events from
older generations never enter the Nest.

Startup sync converges in a fixed order:

1. The orchestration layer sends `configure_world` with `nest_id`, the bed
   count and the world revision;
2. The Runtime builds rooms and navigation, and replies with a
   `scene_manifest` that contains no coordinates;
3. The Runtime replies with `world_ready`, after which Python sends the full
   `sync_actors`;
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

## Run & debug

Run Nest domain and Godot protocol checks from the repository root:

```bash
UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q test/nest/

UV_CACHE_DIR=/tmp/elfienest-uv-cache \
  uv run --no-sync pytest -q \
  test/nest/test_nest.py \
  test/nest/godot/test_api_handshake.py
```

Opening, running or screenshotting the Godot project requires following the
repo's Godot operation gate first; the tests here do not need the Godot editor
to be running. For the dev environment and the unified quality gate see
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Corresponding tests

- `test/nest/test_nest.py`: state, environment clock and interaction
  propagation;
- `test/nest/godot/`: v2 handshake, message validation, authoritative session
  and web build artifacts;
- `test/e2e/test_nest_runtime_v2.py`: world and full character catalog
  convergence after reconnection;
- `test/architecture/test_project_structure.py`: Nest directory structure and
  legacy package bans;
- `test/app/orchestration/`: composition behavior of real Elfies and the Nest.
