# Service lifecycle contract

**Contract version:** 1.3
**Adopted:** 2026-08-15
**Revised:** 2026-08-19
**Scope:** installed and source Runtime lifecycle, readiness and process ownership

> **Normative target.** This contract fixes the service-state authority and the
> invariants shared by Desktop, CLI, Doctor, installers and status surfaces.
> Rationale and explanatory detail belong to
> [ADR-0021](../decisions/0021-authoritative-service-lifecycle) and the reviewed
> [state-machine design](../designs/app/service-lifecycle-state-machine). Current
> gaps belong only in [Conformance](../conformance/service-lifecycle).

## Authority, identity and snapshot

`app/orchestration/lifecycle` is the sole writer of Runtime lifecycle state and
the sole coordinator of Core, Gateway and Godot start, stop, restart, recovery
and convergence. Interfaces, Bootstrap, health probes and Infrastructure
Adapters are clients, constructors or evidence providers; none may derive and
persist a second lifecycle state.

Every canonical data root has at most one writer and one current Runtime
generation. One atomic, schema-versioned snapshot contains at least:

- canonical instance ID and monotonic generation;
- stable Backend tier plus current phase/subphase;
- component PID, process-birth/executable/cwd identity, state and typed failure;
- actual bound endpoints and protocol/resource versions;
- desired target, reached target and remaining convergence;
- correlation ID and monotonic phase timings.

Snapshot writes and lifecycle commands are serialized by the canonical
data-root lock. Installed Desktop first acquires the per-user product lock;
process authority then resolves in this order:

```text
Desktop product lock -> canonical data-root instance -> Runtime generation
-> validated component process identity
```

PID, port, process name, receipt or lock file is evidence only. Process control
also validates generation, executable identity, process birth identity and an
authenticated local control credential. A reconnecting client attaches by
instance, generation and protocol version; an incompatible client reports the
running version and does not start another authority.

Executable, cwd and birth checks validate the process against the selected
snapshot generation, never against the invoking checkout. A later CLI controls
that task only through a compatible protocol and the data root's credential.

## Data-root target resolution

The canonical data root is the task identity. Every command resolves exactly
one target before execution and stays on it; it must never re-resolve, attach by
port, or treat a PID, endpoint or candidate entry as identity.

The packaged App, tray and installed global CLI share one production resolver:

```text
production data root = ${ELFIE_HOME:-~/.elfienest}
```

`ELFIE_HOME` is exclusive: installed reads and writes use it when set, and
otherwise use the default. There is no remembered production selection,
`selected-data-home` pointer or `data-home` command. One OS user has at most
one packaged Controller and Runtime. If the running Controller reports another
root, return a typed mismatch; do not switch, attach elsewhere or start a
second Controller.

Source `./elfienest.sh` uses a separate resolver and ignores caller
`ELFIE_HOME`. Only `start`, `serve`, `restart` and `stop` accept
`--data-home`; the selected root is passed internally to child processes.
All other source commands resolve through context/default/candidates and do
not accept `--data-home`. `uninstall` is installed-only, and there is no public
`data-home` command.

Source target precedence is deterministic:

| Invocation | Resolution order |
| --- | --- |
| Interactive shell | Explicit lifecycle root -> session context -> eligible `<source-root>/.elfienest.local` -> confirmed candidate selection |
| One-shot command | Explicit lifecycle root -> eligible default -> confirmed TTY selection |
| Non-interactive with no unique target | Print validated candidates and fail; never guess or prompt |

TTY selection always requires explicit confirmation; one candidate is not durable
session context.

An explicit root or existing session context is authoritative. Failure there
does not fall through to another task. Each successfully resolved interactive
target becomes the memory-only session context; failure or invalid resolution
does not replace it.

Eligibility is command-specific: `start`/`serve` may create the default root;
`stop` requires a verified generation and an idle default must not hide other
running candidates; `restart` requires a recognized task. `web`, `mobile` and
`desktop` only open an existing healthy target and never start or repair it.
`status`, data and configuration commands only require a usable root. If no
`stop` candidate exists, report that no service is running.

Source-shell history and candidate discovery use only the optional owner-only
`<source-root>/.elfienest.local/runtime/cli/` subtree. Explicit roots need not
contain it. Its absence never invalidates a data root; its presence never grants
authority or selects a task. Candidates are revalidated before display, old
state locations are not read, and selection is separate from execution.

## Stable state and model health

Backend has exactly three stable tiers:

| Tier | Requirement |
| --- | --- |
| `OFFLINE` | No current Core generation satisfies Core readiness |
| `CORE_READY` | The data-root writer, Core control/API/Web surface and published endpoints are ready |
| `WORLD_READY` | `CORE_READY` plus authenticated current-generation Godot, compatible protocol/scene, configured world, navigation and acknowledged actor synchronization |

Transition phases and typed failures are not extra stable tiers. Setup, Normal,
Repair and Viewer are presentation modes, not service states.

Model health is an independent projection owned by the App Food/model-capability
service and derived from persisted technical evidence. Lifecycle consumes the
projection without copying its scoring algorithm or issuing startup inference
requests.

| Group | Aggregate effect |
| --- | --- |
| Common Food | Every currently required route must be executable |
| Emergency Food | The global reserve, preferably local Ollama, must be executable for full resilience |
| Inactive models | Failures are detail warnings and never lower operational health |

The model aggregate is `UNCONFIGURED`, `READY`, `DEGRADED` or `UNAVAILABLE`.
`READY` requires executable Common and Emergency Food. Common Food using a
fallback, or unavailable Emergency Food, is `DEGRADED`; a required capability
with no executable route is `UNAVAILABLE`.

Startup may confirm a configured local Ollama service, endpoint and required
model inventory, but real inference validation runs only through configuration,
explicit diagnostics, bounded background refresh or actual model use. Those
results update the model evidence authority and never block Core readiness.

## Commands, convergence and capability gates

A start command declares independent `desired_target` and `wait_target` values:
`CORE`, `WORLD` or `NORMAL`. `NORMAL` is the derived condition `WORLD_READY`
plus model aggregate `READY`.

```text
OFFLINE -> PREFLIGHT -> CORE_STARTING -> CORE_READY
  |-> WORLD_STARTING -> WORLD_READY
  |-> MODEL_PROJECTING / LOCAL_MODEL_STARTING -> stable model aggregate
```

World and model convergence proceed independently after `CORE_READY`. A Godot
failure falls back to `CORE_READY`; a model failure changes only model health.
Core failure yields `OFFLINE`.

| Command race | Required result |
| --- | --- |
| Duplicate start for one data root | Attach to the same generation; only target escalation is allowed |
| Stop during startup | Cancel at a safe checkpoint and clean only resources acquired by that generation |
| Restart | Reach `OFFLINE` before allocating the next generation |
| Start during shutdown | Wait or return typed `BUSY_STOPPING`; generations never overlap |
| Status/health | Read-only; never starts, repairs or kills a component |

One typed capability-requirement registry maps each product operation to its
minimum Backend tier and model requirement. One server-side evaluator enforces
that registry and returns a generation-scoped permit or typed rejection; UI
disabling is only a projection. Capability checks do not auto-start components,
and committing workflows revalidate before their irreversible boundary.

## Entrypoints and installed resources

| Entrypoint | Required behavior |
| --- | --- |
| Packaged Desktop | Acquire the global product lock, start/attach the production Server, create the tray and open Viewer |
| Viewer close or presentation quit | Close presentation only; Server, Godot and model leases remain unchanged |
| Installed `elfienest start` | Start/activate the same Controller, tray and production Server without opening Viewer; default to `desired=NORMAL`, `wait=CORE` |
| Installed `elfienest restart` | Stop the exact production Server through the Controller lifecycle, then start/activate that same Controller and Server without opening Viewer; publish the new generation's actual endpoints |
| Installed `elfienest web` / `mobile` / `desktop` | Open only an already running target; never start or repair Server, Controller or Runtime, and fail when the target cannot be found or has no healthy endpoint |
| Tray Stop Server / installed `elfienest stop` | Hide Viewer, then stop the exact production Server and Controller within bounds |
| Source `./elfienest.sh` | Development only; attach for the same data root, allow distinct explicit roots concurrently, and keep `serve` foreground-owned |
| Install or update | Detect the validated running Controller, ask the user to stop it, and wait boundedly for `OFFLINE`; refuse overwrite if it cannot converge |

The product lock is independent of App path, version, data root and port. A
second App copy activates the existing Controller; installed and source
resolvers remain isolated.

Every native installer provides the global `elfienest` launcher. There is no
source-install path. Installed startup uses only packaged executables and
static resources: it never installs Python/Node dependencies, exports Godot or
builds product assets. Missing or incompatible resources fail preflight with a
typed repair/reinstall action. An explicit user-requested Ollama model download
is not a product build.

Ports are endpoints, never identity or cleanup targets. Automatic restart may
publish different ports; old ports never select a task. An occupied explicit
port returns a typed conflict. No entrypoint kills or attaches by port.

## Managed-process ownership

Godot is an exact-generation Core child managed through Lifecycle-owned Ports.
Infrastructure supplies platform mechanics: authenticated liveness watchdog,
POSIX process group or Windows Job Object, exact identity validation and
bounded graceful/forced stop. Parentage alone is not a cleanup guarantee.

Ollama has exactly two origins:

- `EXTERNAL`: healthy before ElfieNest acts; ElfieNest never stops it;
- `ELFIENEST_OWNED`: started by ElfieNest with exact process identity.

Runtime instances share one `ELFIENEST_OWNED` service under per-user leases.
Each instance releases only its lease; the final valid release stops the
service. Setup downloads also hold a lease. After all holders crash, the next
startup or Doctor must validate and either reuse or converge the orphan. No
third ownership mode or broad name-based kill is allowed.

## Shutdown, recovery and observation

Shutdown is serialized and bounded:

```text
any running state -> QUIESCING -> WORLD_STOPPING
-> MODEL_LEASE_RELEASING -> CORE_STOPPING -> OFFLINE
```

`QUIESCING` rejects new mutations. Cleanup is reverse-order and generation
scoped. A dead/reused PID or a port owned by another process is reported and
left untouched; ports are never killed, and third-party processes are never
terminated.

Every entrypoint emits a correlation ID and every Server start a generation.
Status and lifecycle logs use the resolved data root and include identity,
endpoints, timings, typed failure and one safe next action.

Start, restart and stop report success only after the selected snapshot confirms
the promised state. Failures retain their typed cause in the snapshot/log and
return to the CLI with the target and correlation ID; no generic success or
silent reattachment is allowed.

Permanent tests must protect the authority paths and document invariants here;
behavior tests must cover duplicate App/CLI starts, command races, stale
receipts, endpoint conflicts, partial failures, reattachment, orphan cleanup,
install/update handoff, installed-resource preflight and bounded shutdown before
Conformance can close.
