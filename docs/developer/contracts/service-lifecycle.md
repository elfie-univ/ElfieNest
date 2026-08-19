# Service lifecycle contract

**Contract version:** 1.3
**Adopted:** 2026-08-15
**Revised:** 2026-08-19
**Scope:** installed and source Runtime lifecycle, readiness and process ownership

> **Normative target.** This contract fixes the service-state authority and the
> invariants shared by Desktop, CLI, Doctor, installers and status surfaces.
> Rationale and explanatory detail belong to
> [ADR-0021](../decisions/0021-authoritative-service-lifecycle) and the reviewed
> [state-machine design](../designs/service-lifecycle-state-machine). Current
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

Executable and cwd checks validate the process against the selected snapshot's
recorded generation; they do not compare it to the invoking checkout and do not
turn code location into task identity. A later local CLI process may control an
explicitly selected task only through compatible protocol and that data root's
validated control credential.

## Data-root target resolution

The canonical data root is the task identity. Every command resolves exactly
one target before execution; execution, observation and cleanup then remain on
that target. A command must never re-resolve to another root, attach by a
healthy port, or treat a PID, endpoint or candidate-catalog entry as identity.

The packaged App, tray and installed global CLI share one production resolver:

```text
production data root = ${ELFIE_HOME:-~/.elfienest}
```

If `ELFIE_HOME` is set, every installed-product read and write uses that root
and the default root is untouched. Relative values remain supported but must be
resolved by the shared installed resolver against one stable per-user base,
never against an entrypoint's working directory. There is no remembered
production selection, no `selected-data-home` active pointer and no
`data-home` command. One OS user still has at most one packaged
Controller and production Runtime. If the running
Controller reports a different data root from the current installed resolver,
the caller returns a typed configuration mismatch; it does not switch the
Controller, attach to an unrelated Runtime or start a second one. The error
identifies both roots and instructs the user to stop through the existing tray
or restore the prior global setting before issuing installed CLI stop.

Source `./elfienest.sh` uses a separate resolver and must ignore caller
`ELFIE_HOME` during target selection. Only `start`, `serve`, `restart` and
`stop` accept `--data-home`. After selection, the launcher publishes the
canonical result to child processes as their internal `ELFIE_HOME`; this does
not make the caller's environment a source-selection input. All other source
commands, including `status`, `web`, `mobile`, configuration, Setup, Doctor,
Owner and database commands, resolve through context and do not accept
`--data-home`. `uninstall` is available only in the installed CLI; there is no
`data-home` command.

Source target precedence is deterministic:

| Invocation | Resolution order |
| --- | --- |
| Interactive shell | Explicit `--data-home` on one of the four lifecycle commands; in-memory session context; command-eligible `<source-root>/.elfienest.local`; validated interactive candidate selection |
| One-shot command | Explicit `--data-home` on one of the four lifecycle commands; command-eligible `<source-root>/.elfienest.local`; validated candidate selection when attached to a TTY |
| Non-interactive one-shot with no unique target | Print validated candidates and fail with a typed selection-required result; never guess or prompt |

TTY candidate selection requires explicit confirmation even when revalidation
leaves one candidate; uniqueness is not durable session context.

An explicit root or existing session context is authoritative. If the command
cannot run there, it reports that exact target's state and never falls through
to another task. Every successfully resolved interactive target—an explicit
lifecycle root, an eligible default or an explicitly confirmed catalog
candidate—becomes the session context before command execution. A later command
failure does not trigger fallback; an invalid or ineligible resolution does not
replace the prior context. The context is memory-only and disappears when the
shell exits.

Default-root eligibility is command-specific and is evaluated before command
execution. `start` and `serve` may create/use the default root. `stop` requires
a verified current generation; therefore an idle default must not prevent the
selector from listing other running roots. `restart` requires a recognized
lifecycle task. `web`, `mobile`, and the CLI `desktop` command only open an
already running target and never start or repair a Runtime; they must fail when
the target has no current healthy endpoint or Viewer. `status` may inspect a
recognized offline task.
Data/configuration commands require a root usable for their declared operation,
not a running Runtime. If no eligible `stop` candidate exists, report that no
service is running.

Source-shell history and the checkout-scoped candidate catalog live only in the
optional owner-only subtree `<source-root>/.elfienest.local/runtime/cli/` of
that checkout's default source root. Explicitly selected roots need not contain
this subtree. Product-data inspection and Runtime freshness ignore this
subtree: its absence cannot make a root incomplete, and its presence cannot
make a root recognized or eligible. The catalog may retain canonical source
roots and last-observed metadata solely for candidate discovery. It is not a
current-selection record, cannot grant process authority, and must be
deduplicated and revalidated before every display. Control-state loss or write
failure may remove history/convenience but cannot create, select, change or
stop a Runtime. No former CLI-state location is read or migrated. The default
root is an eligible candidate, not a terminal failure; target selection and
command execution are separate phases.

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

The product lock is independent of App path, version, data root and port. A second App copy
activates the existing Controller and never starts another production Server.
The installed App and global CLI use the same binary production-root resolver;
source development roots and command context remain isolated.

Every native installer provides the global `elfienest` launcher. There is no
source-install path. Installed startup uses only packaged executables and
static resources: it never installs Python/Node dependencies, exports Godot or
builds product assets. Missing or incompatible resources fail preflight with a
typed repair/reinstall action. An explicit user-requested Ollama model download
is not a product build.

Ports are published endpoints, never instance identity or cleanup targets.
Automatic mode binds OS-selected available ports atomically and records the
result. Restart allocates a new generation and may publish different automatic
ports; previous ports never select the task. An occupied explicit development
port returns a typed conflict. No entrypoint kills or attaches to a process
merely because it occupies a port.

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

`QUIESCING` rejects new mutations. Cleanup follows reverse ownership order and
skips resources not acquired by the generation. Stale evidence is demoted only
after identity checks; only an exact old-generation process tree may be
reconciled. A dead/reused PID or a recorded port now owned by another process is
reported and left untouched. Ports are never killed; sockets are released only
when the validated owning process exits. Third-party and other-instance
processes are never terminated.

Every entrypoint emits one correlation ID and every Server start one generation.
Monotonic timings cover product/data-root locks, preflight, Core, Viewer, model,
Godot, requested target and each shutdown phase. Status exposes the stable tier,
phase, component facts, model aggregate, endpoints, durations, typed failure and
one safe next action. Lifecycle logs live under the resolved data root and tag
the instance ID, generation and correlation ID.

Start, restart and stop report success only after the selected snapshot confirms
their promised state. A caught failure keeps its typed cause in the snapshot and
data-root log and is returned to the CLI with the target and correlation ID;
entrypoints must not replace it with generic success or silently attach elsewhere.

Permanent tests must protect the authority paths and document invariants here;
behavior tests must cover duplicate App/CLI starts, command races, stale
receipts, endpoint conflicts, partial failures, reattachment, orphan cleanup,
install/update handoff, installed-resource preflight and bounded shutdown before
Conformance can close.
