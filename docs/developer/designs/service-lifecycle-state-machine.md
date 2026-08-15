# ElfieNest service lifecycle state-machine design

> Status: accepted design
> Confirmed: 2026-08-15
> Scope: service state, Desktop/CLI entrypoints, process ownership, failure convergence and startup observation

## 1. System resources

| Resource | Cardinality and lifetime |
| --- | --- |
| Core Server | At most one Runtime generation per canonical data root |
| Godot authority | At most one per Core generation; converges with that Core |
| Ollama | Optional and shared per normalized service key for one OS user |
| Desktop Controller | At most one packaged-product instance per OS user |
| Desktop Viewer | A disposable and reopenable window managed by the Controller |

Gateway is a logical component managed by Core. PIDs, ports, locks and receipts
are evidence to validate, not service state. `app/orchestration/lifecycle` is
the sole state writer; Desktop, CLI, installers, Doctor and status surfaces are
clients or readers.

## 2. Authoritative stable state

The backend has exactly three stable tiers:

| Tier | Complete requirement |
| --- | --- |
| `OFFLINE` | No current Core generation satisfies readiness |
| `CORE_READY` | The data-root writer, Core control/API/Web surface and actual endpoints are ready |
| `WORLD_READY` | `CORE_READY` plus authenticated current-generation Godot, compatible protocol/scene, configured world, navigation and acknowledged actor-catalog synchronization |

Models form an independent axis, not a fourth Runtime tier. The model-capability
service derives the authoritative projection from persisted evidence, which may
combine explicit validation, real calls and freshness. Lifecycle consumes that
projection and never duplicates its scoring algorithm.

| Model group | Effect on aggregate health |
| --- | --- |
| Common Food | Required routes in effective use; every route must be executable |
| Emergency Food | Global emergency route, preferably local Ollama; determines resilience after failure |
| Inactive models | Unused catalog entries; failures produce detail warnings only |

| Model aggregate | Requirement |
| --- | --- |
| `UNCONFIGURED` | No executable Common Food configuration exists |
| `READY` | All Common Food routes and Emergency Food are executable |
| `DEGRADED` | Common Food executes through fallback, or Emergency Food is unavailable |
| `UNAVAILABLE` | At least one currently required capability has no executable route |

The status surface always shows System health first and Model service second.
The normal product is fully green only when `WORLD_READY` and the model
aggregate is `READY`. Godot or model failure must not hide a still-usable
`CORE_READY` tier.

| Capability | Minimum requirement |
| --- | --- |
| Setup, sign-in, configuration, status and repair | `CORE_READY` |
| 3D world and embodied controls | `WORLD_READY` |
| Model-backed chat | `CORE_READY` plus an executable route for the requested model capability |
| Adoption | `WORLD_READY` plus the strong adoption-model role and client Godot preview capability |

Setup, Normal, Repair and Viewer pages consume state; they are not service
states.

## 3. Lifecycle state machine

Startup:

```text
OFFLINE
  -> PREFLIGHT
  -> CORE_STARTING
  -> CORE_READY
       |-> WORLD_STARTING -> WORLD_READY
       |-> MODEL_PROJECTING / LOCAL_MODEL_STARTING -> stable model aggregate
```

After `CORE_READY`, world and model convergence proceed independently.
`WORLD_STARTING` has fixed subphases:

```text
GATEWAY_BINDING -> AUTHORITY_SPAWNING -> AUTHENTICATING
-> MANIFEST_VALIDATING -> WORLD_CONFIGURING
-> NAVIGATION_WAITING -> ACTOR_SYNCING -> WORLD_READY
```

Runtime disconnection, crash or revision drift enters
`WORLD_RECOVERING / WORLD_RECONCILING`. Success restores `WORLD_READY`; failure
falls back to `CORE_READY`.

`MODEL_PROJECTING` reads authoritative evidence without issuing inference
requests. Local Emergency Food synchronously checks only the Ollama service,
endpoint and required model inventory. Configuration, explicit diagnostics,
background refresh or real calls perform validation and write new evidence;
they never block Core startup.

Shutdown:

```text
any running state -> QUIESCING -> WORLD_STOPPING
-> MODEL_LEASE_RELEASING -> CORE_STOPPING -> OFFLINE
```

`QUIESCING` rejects new mutations immediately. Shutdown is bounded and follows
reverse ownership order; unacquired resources are skipped. `FAILED` is a
command/component result, never a fourth stable state.

| Race or failure | Deterministic behavior |
| --- | --- |
| Duplicate start for one data root | Attach to the same generation; only target escalation is allowed |
| Stop during startup | Cancel at a safe checkpoint and clean only resources acquired by that generation |
| Restart | Reach `OFFLINE` before allocating a new generation |
| Start during shutdown | Wait or return `BUSY_STOPPING`; generations never overlap |
| Core crash | Fall to `OFFLINE` and converge its Godot tree |
| Godot crash | Fall to `CORE_READY` and perform bounded recovery |
| Model failure | Update model evidence and aggregate health without changing the Backend tier |
| Health/status | Strictly read-only |

A start request declares both a background `desired_target` and caller
`wait_target`: `CORE`, `WORLD` or `NORMAL`. `NORMAL` means `WORLD_READY` plus a
`READY` model aggregate. First-run Desktop Setup requests only `CORE`; normal
Desktop displays the real UI at `CORE_READY` and converges to `NORMAL` in the
background. Installed `elfienest start` likewise targets `NORMAL` in the
background and returns at `CORE` by default.

## 4. Entrypoint behavior

| Entrypoint | Final semantics |
| --- | --- |
| Desktop | Acquire the per-user product lock first; a second App activates the existing Controller |
| Viewer close | Close presentation only; Server, Godot and model leases remain unchanged |
| Installed `elfienest start` | Start or activate the same Controller and ensure the tray and production Server exist without opening Viewer |
| Tray Stop Server / installed `elfienest stop` | Hide Viewer, then stop the exact production Server and Controller within bounds |
| Source `./elfienest.sh` | Development only: attach for one data root, allow distinct roots concurrently, and let `serve` signals stop only the exact owned generation |
| Install/update | The native installer provides global `elfienest`; with consent, stop production Server and await `OFFLINE`, otherwise refuse replacement |
| Doctor | Invoke restricted repair through the same Lifecycle authority |

The Desktop product lock is independent of App path, version and port. The
installed App and global CLI manage the same production data root; source CLI
manages isolated development roots.

An installed package contains every executable and static resource required at
startup. Startup never installs dependencies, exports Godot or builds product
assets; missing resources fail preflight with a repairable error. An explicit
user-requested Ollama model download is not a product build.

Ports are endpoints only. Automatic mode atomically binds OS-selected ports and
publishes them; an occupied explicit CLI port fails. No entrypoint may infer
identity or termination authority from a port.

## 5. Identity and ownership

Identity resolves in this order:

```text
Desktop product lock
-> canonical data-root instance_id
-> Runtime generation
-> component process identity
```

One data root has one writer. Process control validates generation, PID birth
time, executable identity and authenticated control credentials.

Godot is a managed Core child, but parentage alone is insufficient. Cleanup
combines a liveness pipe/watchdog, POSIX process group or Windows Job Object,
exact identity validation and bounded stop.

Ollama has two origins:

- `EXTERNAL`: healthy before ElfieNest acts; never stopped by ElfieNest;
- `ELFIENEST_OWNED`: directly started with an exact recorded generation.

Runtime instances share one `ELFIENEST_OWNED` Ollama through per-user leases.
Each instance releases only its own lease; the final valid release stops the
service. Setup download work also holds a lease. There is no
`PERSISTENT_MANAGED` or `SESSION_OWNED` third state. If every holder crashes,
the next startup or Doctor precisely reuses or converges that orphan first.

## 6. Failure convergence

| Failure class | Convergence rule |
| --- | --- |
| Same healthy instance already running | Attach; do not start again |
| Stale PID/lock/receipt | Demote evidence after identity validation |
| Exact old-generation orphan | Clean only that process tree |
| Other instance or third-party process | Never terminate it |
| Implicit endpoint conflict | Atomically bind another endpoint |
| Explicit endpoint conflict | Return a typed error |
| Partial Godot/model failure | Preserve usable Core and gate only dependent capabilities |
| Invalid data root or packaged resources | Fail before creating a partial generation |
| Damaged data | Explicit repair only, after stop, confirmation and backup |

`start/restart --force` performs only safe Runtime and endpoint repair; it never
deletes data. When Core is unavailable, a local Desktop recovery shell provides
the repair surface.

## 7. Observation and acceptance

Each entrypoint call has a correlation ID; each Server start has a generation.
Monotonic milestones cover locks, preflight, Core, Viewer, every model/Godot
subphase, requested readiness and shutdown.

Status reports the stable tier, phase/subphase, component state, actual
endpoints, phase duration, typed failure and next safe repair action.

The design guarantees:

- two App copies cannot create two production Servers;
- one data root cannot have two writers, while distinct roots may run together;
- old and new generations never overlap;
- PID, port and process name never grant stop authority;
- Core remains configurable and repairable when Godot or models fail;
- Viewer close does not affect Server;
- no single Runtime prematurely stops shared Ollama;
- every start and stop ends in an explainable state or typed failure.
