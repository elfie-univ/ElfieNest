# Service lifecycle conformance

> Temporary register for the normative
> [Service lifecycle contract](../contracts/service-lifecycle). `in progress` means
> the implementation slice is verified but the contract still has a residual;
> it is not a release-closure claim.

External acceptance gaps are recorded as **not tested (external)**, not as local
implementation failures. They remain open until the named host or installed-
environment evidence is recorded, and must not be reported as complete merely
because local checks passed.

## Approved implementation plan

> Status: frozen execution plan; it does not claim product implementation.
> Risk: **L**, because installed/source entrypoints, public CLI behavior,
> Desktop handoff and Runtime shutdown converge in one cutover.

Keep the existing authoritative Runtime snapshot/generation, per-data-root
writer lock, user-scoped Controller IPC, atomic endpoint binding and bounded
process-tree primitives. Replace only the non-conforming selection and fallback
paths. The implementation must preserve these boundaries:

| Concern | Frozen result |
| --- | --- |
| Task identity | One canonical data root; code checkout, PID, port, catalog and health are never identity |
| Installed product | Exactly `${ELFIE_HOME:-~/.elfienest}`; configured and default roots are mutually exclusive; one Controller/Runtime per OS user |
| Source CLI | Caller `ELFIE_HOME` is ignored; only `start`, `serve`, `restart` and `stop` accept `--data-home` |
| Interactive context | One in-memory target; no durable active pointer; successful resolution updates context before execution |
| Runtime control | Snapshot `(instance_id, generation)` and exact process identity authorize control; ports are published endpoints only |
| Non-authoritative CLI state | `<source-root>/.elfienest-cli.local/` stores only protected history and a revalidated candidate catalog, outside product roots |

### Work packages and gates

Each package starts with a failing contract test. WP1-WP4 may be separate review
commits but form one **non-releasable switchover**: no build may expose the new
resolver while any remembered-root/port-fallback authority remains reachable.

| WP | Implementation | Primary boundary/files | Exit gate |
| --- | --- | --- | --- |
| WP0 — freeze tests and inventory | Record the current baseline; inventory every `selected-data-home`, `activate`, `use_remembered`, caller-`ELFIE_HOME`, mode/Controller-home override, pre-resolution root read, default-port probe and port-kill path. Identify test/e2e harnesses that currently use caller `ELFIE_HOME` to select a source CLI target; convert those harnesses to explicit/temp target injection during implementation without changing ordinary root-bound product tests. Add failing tests for every acceptance row before behavior changes. Classify unrelated baseline failures instead of repairing them here. | Existing CLI/lifecycle/Desktop/process tests; new `test/app/orchestration/lifecycle/test_target_resolution.py`, `test/app/interfaces/cli/test_interactive_shell.py` and `test/infrastructure/platform/lifecycle/test_source_cli_state.py`. | Every current deviation has a red test or an explicitly external host scenario; no product file changed yet. |
| WP1 — one typed target resolver | Add App-owned `EntrypointMode`, `CommandTargetPolicy`, `TargetResolutionRequest`, `ResolvedTaskTarget` and typed `SelectionRequired`/`TargetIneligible`/`InstalledRootMismatch`. Determine mode from frozen package provenance or the source launcher/tree, never from caller-set runtime/Desktop environment variables. The resolver receives explicit/session/TTY/candidate facts, applies the command matrix, and returns one canonical target plus provenance; it never prompts or executes. Installed relative `ELFIE_HOME` resolves against user home; source relative `--data-home` resolves against the invoking process cwd; source selection never reads caller `ELFIE_HOME`. | Planned `app/orchestration/lifecycle/target_resolution.py`; update lifecycle `types.py`, `ports.py`, `facade.py`, exports and Bootstrap wiring. Infrastructure adapters only canonicalize/inspect paths and read/write candidate state; they own no selection policy. | Pure resolver matrix passes for installed/source, hostile/irrelevant mode env, explicit/session/default/candidate, relative paths, blank env, command eligibility and no-fallthrough. Resolver has no UI, subprocess or data-dependent service construction. |
| WP2 — source shell and checkout control state | Make `elfienest.sh` a bootstrap only: remove caller `ELFIE_HOME` before dependency checks and source dispatch, and ensure bootstrap never initializes a product root. A persistent Python interactive host owns `session_data_home`, secure `shlex` parsing, per-command return codes and TTY prompting; interactive and one-shot modes use the same parser/dispatcher/help instead of a second shell command whitelist. Put bounded, deduplicated `data-homes.json` plus secret-filtered history under Git-ignored `.elfienest-cli.local/`; use owner-only permissions, atomic locked updates and symlink-safe fail-closed persistence. Revalidate the selected candidate after user input. Persistence failure is visible but non-authoritative and does not block an explicit/default command. | `elfienest.sh`, `scripts/elfienest.py`, planned `app/interfaces/cli/interactive_shell.py`, planned source-control-state Port/adapter, `.gitignore`, bootstrap-focused tests. | Opening/exiting the shell does not touch `.elfienest.local`; every supported command has the same options in interactive/one-shot mode; `start --data-home A -> web -> restart --data-home B -> status` keeps exact context and leaves A running; quoted paths work; sensitive input is absent from history; concurrent shells cannot create an active pointer. |
| WP3 — installed App/global CLI convergence | Resolve the installed root through the same Python lifecycle surface before root-bound Desktop composition and freeze it for the Controller lifetime. Bump the versioned Controller IPC atomically: every request carries protocol version plus the caller's expected canonical root, and every response reports protocol plus Controller root. Root/protocol mismatch performs no launch, attach, stop or switch and reports both sides. Controller lock/IPC discovery remains one fixed OS-user scope independent of data root and install path; production environment cannot relocate it (tests inject an isolated adapter path directly). Retire data-root Desktop PID receipts as Controller authority; the user-scoped lock/IPC owns Controller identity while its response binds it to the frozen product root. Remove Desktop “choose data home”, `activateDataHome`, Python `data-home activate` and all installed `--data-home` paths; inspect/recover operate only on the fixed installed root. | `scripts/elfienest.py`, CLI `data_home_commands.py`/`packaged_runtime.py`, lifecycle Desktop facade and Controller IPC, Desktop `lifecycle_client.ts`, `desktop_role_lifecycle.ts`, `main.ts`, recovery window and their tests. | App icon, tray and global CLI agree with env unset/set/blank/relative; changing env while a Controller is live yields typed mismatch; incompatible IPC fails without fallback; default root remains untouched when env selects another root; stale data-root PID receipts or caller env cannot create a second Controller namespace/installed Runtime. |
| WP4 — atomic command cutover | Parse `--data-home` only for the four source lifecycle commands. Split Bootstrap into a root-neutral resolution composition and a target-bound command composition: rootless `help`/`version`/`exit` bypass both, while every root-bearing command resolves once before `create_lifecycle_facade` or any DB/config/account/Provider/Setup/Doctor/operations read. A persistent shell recomposes target-bound services per command and never retains an A-bound object after switching to B. Publish the resolved root through a per-command scoped internal environment/explicit arguments, let launched children inherit it, then restore the host environment; ambient or prior-command values never re-enter selection. Remove `LifecycleDataHomePort.remember`, selected-root reads/writes and activation aliases; old receipt/history metadata are inert and never replayed. `web` may ensure only the resolved target, then `web`/`mobile`/`status` consume only its current snapshot endpoint. Update help and error text. | `scripts/elfienest.py`, `scripts/serve.py`, CLI lifecycle/foreground/mobile/runtime/data-home commands, `app/bootstrap/system_wiring/lifecycle.py`, lifecycle facade/ports, `infrastructure/persistence/layout/data_home.py` and `lifecycle_data_home.py`, other root-bound Bootstrap factories and parser/CLI tests. | No pre-resolution composition calls `get_db_path`, loads Provider/config/account data or creates a product root. Repository search finds no reachable remembered-root/activate authority or arbitrary/default-port attachment. Every root-bearing dispatcher receives one `ResolvedTaskTarget`; old `selected-data-home`/`.cli_history` contents cannot influence any command. WP1-WP4 then land together. |
| WP5 — exact generation shutdown and observation | Capture stable process birth identity at launch and compare birth/executable/cwd/control identity against the selected snapshot. Retire legacy PID receipts as lifecycle authority. Stop through authenticated generation control, then reverse-owned process-tree cleanup; never signal a port occupant. Forced signalling requires a complete identity match; missing/unreadable identity fails safely with a typed result instead of guessing. If a former port is now held externally, leave it untouched and report it without treating that fact as proof the selected task is alive. Restart must reach exact-root `OFFLINE` before creating the next generation and may receive new auto ports. Preserve Controller/Godot ownership and per-user Ollama holder leases. After target resolution, emit the exact canonical target root, instance, generation, component PIDs, endpoints, operation/correlation ID, timings, redacted typed cause and data-root log path when writable; pre-resolution or unwritable-root failures emit the same safe typed diagnostic to stderr/JSON and explicitly mark logging unavailable. Success requires a confirming reread of the same snapshot. | Lifecycle `runtime_snapshot.py`, `runtime_supervisor.py`, `service.py`, `start_cleanup.py`, process/record/endpoint/Controller adapters, CLI result rendering and focused lifecycle/platform tests. | PID/port reuse, unreadable identity, stale snapshots, partial starts, crash recovery and all four command races leave unrelated processes untouched; failed start/restart/stop never prints success or hides its safe cause; stopped exact generation is not kept “alive” by a reused port. |
| WP6 — integration, native acceptance and closure | Run two-root/two-worktree source acceptance, installed App/global-CLI handoff, Desktop/tray shutdown, Godot coexistence, shared Ollama lease and clean-install smoke on every supported OS. Update public help/troubleshooting/tooling after behavior exists, remove temporary-current-behavior wording, and close Conformance rows only with the five evidence classes. | A/B CLI harness, PTY/non-TTY tests, Desktop TypeScript suite, release install smoke, docs/contract gates and LFC-006/007/008/009/010 entries. | All local checks pass; macOS/Windows/Linux external evidence is attached; no affected P0 residual or unclassified path remains. |

### Resolver command matrix

The resolver evaluates default-root eligibility only when no explicit or session
target exists. An explicit/session target is final even when the command cannot
run there. A TTY selector appears only after the default is ineligible; a non-
TTY prints the same revalidated candidates and exits with a typed non-zero
result. A confirmed interactive candidate becomes session context. Selection
confirmation and any later destructive-operation confirmation are separate.

| Command group | Source default is eligible when | If no eligible target/candidate |
| --- | --- | --- |
| `start`, `serve` | Always; it may initialize `.elfienest.local` | Not applicable unless the path itself is invalid |
| `restart` | A recognizable lifecycle task exists | `selection_required`, or `task_not_found` when the candidate set is empty |
| `stop` | A verified active/converging generation exists | `no_running_service`; an idle default cannot suppress running A/B candidates |
| `status` | A recognizable task/snapshot exists, including `OFFLINE` | `task_not_found` |
| `web` | The exact default is recognizable/startable | `selection_required`/`task_not_found`; after resolution ensure only that target |
| `mobile` | The exact snapshot publishes the required endpoint | `no_published_endpoint` or selection |
| Config, Setup, Doctor, Owner, DB, uninstall, `data-home inspect/recover` | The root is usable or recoverable for that operation | Typed data-root error or selection; Runtime need not be running |
| `help`, `version`, shell `exit` | No target required | Execute without touching either data-root or catalog state |

### Acceptance matrix

| ID | Replayable scenario | Required result |
| --- | --- | --- |
| A1 | Installed App/global CLI, `ELFIE_HOME` unset or blank | Only `~/.elfienest` is resolved; no selector or remembered root exists. |
| A2 | Installed App/global CLI, absolute or relative `ELFIE_HOME=X` | Only canonical X is read/written; relative X is stable against user home; default root remains untouched. |
| A3 | Controller runs on A, a new installed process resolves B | Typed mismatch names A/B; no second Controller/Server, cross-root stop or port attachment occurs. Existing tray can stop A. |
| A4 | Source wrapper starts with caller `ELFIE_HOME=X` | X is not read/written by bootstrap or selection; merely entering the shell creates no product data root. |
| A5 | Parser/help inspection in source and installed modes, including caller-set mode/Desktop variables | Provenance still selects the correct mode; source supports `--data-home` on exactly four lifecycle commands; installed mode and all other commands reject it. |
| A6 | Interactive `start --data-home A`, `web`, `restart --data-home B`, `status` | First two target A; restart/status target B; A remains running; results identify roots/generations/endpoints. |
| A7 | Explicit/session target is offline, corrupt or ineligible while another task runs | Report only that exact target; never silently switch, probe another port or overwrite session on failed resolution. |
| A8 | One-shot `stop` with idle/missing default and running A/B | TTY lists revalidated A/B and requires confirmation even for one; non-TTY prints candidates and exits non-zero; no candidate reports no running service. |
| A9 | Candidate file has duplicates, stale roots, replaced instance IDs, malformed JSON or concurrent writers | Display only deduplicated currently eligible roots; revalidate after choice; warn/disable convenience safely; never infer authority. |
| A10 | `web`/`mobile`/`status` with an unrelated healthy process on 8000 and a selected task on another endpoint | Consume only selected snapshot endpoint; `web` may start only that target; unrelated process is untouched. |
| A11 | Snapshot PID is gone/reused, command/cwd/birth differs or is unreadable, or published port is reused | Never signal the replacement or unverifiable process; safely reconcile stale evidence or return typed identity-unverifiable; port occupancy alone cannot block a confirmed stop or prove a start. |
| A12 | Duplicate start, stop-during-start, restart, and start-during-stop | One generation per root; attach/escalate, cancel safely, reach `OFFLINE`, or return `BUSY_STOPPING` exactly as contracted. |
| A13 | Two worktrees run roots A/B with separate Godot processes and shared Ollama | Both Runtime/Godot generations coexist; stopping A leaves B; each releases only its Ollama holder lease. |
| A14 | Selection or start/restart/stop fails before launch, during partial launch or during bounded shutdown | Non-zero typed result preserves a redacted cause and correlation ID. Once resolved it includes exact target/phase and log path when writable; otherwise it explicitly says no data-root log was available. No false success or silent exception loss. |
| A15 | Old `selected-data-home` exists and `.elfienest-cli.local` is deleted, read-only or symlinked | Old receipt has no effect; explicit/default operation remains safe; control-state failure is visible and cannot affect Runtime or product data. |
| A16 | Recovery/uninstall is selected through TTY | Canonical target/state is shown, target is revalidated, then a separate destructive confirmation is required; only that root can change. |

### Cutover, rollback and completion

- This change has no product database migration, dual read/write, compatibility
  alias or feature flag. Old `selected-data-home` files remain inert and may be
  reported as obsolete; old CLI history is not replayed; neither is consulted
  or copied into the new control state.
- The cutover precondition is that old managed Controllers/Runtimes are stopped
  with the old version (native update uses its existing bounded stop). A new
  client that encounters an old/incompatible live protocol reports it and does
  not guess, attach by port or force-kill it.
- Governance/spec changes, implementation, and final Conformance closure stay
  reviewable separately, but WP1-WP4 ship atomically. A pre-release rollback is
  the whole implementation revision with managed services stopped, never a
  runtime fallback to the old authority.
- A new ADR is unnecessary while ownership remains in
  `app/orchestration/lifecycle`. If implementation discovers a real authority,
  top-level ownership or protocol change, stop and obtain approval before an
  ADR/contract version change.
- Completion requires LFC-010 plus affected LFC-006/007/008/009 to close with
  `target`, `inventory`, `references`, `verification` and `residuals` evidence.
  Local green tests do not close supported-host installed acceptance.

### Three-pass adversarial review

| Pass | Attacks applied | Plan hardening |
| --- | --- | --- |
| 1 — identity/authority | Treat catalog, remembered root, PID, cwd, healthy port or invoking checkout as identity; change installed env while Controller lives; reuse a deleted root path. | One canonical root resolves first; catalog is discovery only; Controller root mismatch is fatal; `(instance_id, generation, birth identity, credential)` controls processes; cwd verifies the observed recorded generation only. |
| 2 — context/command flow | Let an idle default suppress A/B, let failed explicit targets fall through, lose context after candidate choice, prompt a pipeline, construct DB/config services before selection, or reuse an A-bound facade after switching to B. | Command-specific eligibility, no-fallthrough, pre-execution session update, TTY-only prompting, typed non-TTY failure, root-neutral resolution and per-command target-bound composition are explicit gates. Source env is removed before bootstrap. |
| 3 — failure/security/cutover | Pollute `.elfienest.local` with history, race two shells, follow symlinks, kill reused PID/port, swallow launch errors, or release half of the new authority. | Separate owner-only control state, atomic locked writes and revalidation; exact-generation shutdown with fail-safe identity checks; identity-rich typed logs; WP1-WP4 atomic release and whole-revision rollback. |

The review found no remaining decision that needs a new product rule. The open
items are implementation and external supported-host evidence, not unresolved
authority semantics.

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| LFC-001 | P0 | in progress | Snapshot schema, generation, phase, targets, endpoints, failures, timings, Controller token authentication and generation-scoped writer handoff are implemented; stale writer credentials are rejected. | Prove the same authority/identity chain on installed supported hosts, including process birth identity and recovery. | target=authoritative snapshot; inventory=`runtime_snapshot.py`, `runtime_record.py`, `runtime_supervisor.py`, `controller_ipc.py`; references=contract §Authority; verification=architecture gate plus runtime-record/supervisor/IPC tests; residuals=installed cross-platform identity and recovery acceptance remain. |
| LFC-002 | P0 | in progress | Core-first start, same-generation attach, typed `operation_id`/generation results, cancellation, target escalation and `NORMAL` waiting are implemented; an attached command waits for an explicitly requested World/Normal target without starting a second generation. | Prove the same protocol and race behavior through every installed entrypoint. | target=command/convergence; inventory=`runtime_supervisor.py`, CLI lifecycle commands, Desktop lifecycle client; references=contract §Commands; verification=supervisor, CLI and desktop tests; residuals=installed entrypoint interoperability and full race matrix remain. |
| LFC-003 | P0 | in progress | Core-resident World worker starts and observes the exact generation; POSIX process groups and Windows Job Objects cover launch/stop/attach-failure cleanup; World failure leaves Core usable. | Prove authenticated watchdog and bounded recovery on supported Windows/POSIX hosts. | target=Godot ownership; inventory=`world_worker.py`, Godot authority adapters, process/job mechanics; references=contract §Managed-process ownership; verification=world-worker/supervisor/process/Godot tests and CLI smoke; residuals=host-level kill-tree/watchdog acceptance remains. |
| LFC-004 | P0 | closed | Food evidence is read through one persistence projection; required capability evidence, Common/Emergency aggregation, capability permits and status API use the same model state without startup inference. The complete Core/World/Chat/Adoption matrix is server-gated; the configured remote Provider evidence recorded by PMA-002 is consumed through the same projection. | The registry, persisted projection, chat route and adoption route tests cover the required backend/model combinations and rejection boundaries. | target=model axis and server gates; inventory=Food projection adapter, `capability_gate.py`, API routes; references=contract §Stable state and §Commands; verification=`test/app/orchestration/lifecycle/test_capability_gate.py`, `test/infrastructure/persistence/test_model_health_projection.py`, chat/adoption API tests, and PMA-002 live Provider evidence; residuals=none |
| LFC-005 | P0 | in progress | Ollama has only `EXTERNAL` and `ELFIENEST_OWNED`, exact process identity and shared per-user holder leases; Doctor/start do not broadly kill. | Add real crash/orphan/process-reuse acceptance across multiple data roots and Setup/runtime races. | target=shared Ollama ownership; inventory=`lifecycle_ollama.py`, setup lease, Ollama tests; references=contract §Managed-process ownership; verification=shared-lease and provider tests; residuals=multi-process crash and platform acceptance remain. |
| LFC-006 | P0 | in progress | Desktop Viewer close is presentation-only; an authenticated user-scoped Controller IPC serves `ACTIVATE_VIEWER`/`ENSURE_SERVER`/`STOP_SERVER`/`STATUS` (UDS on POSIX, loopback token endpoint on Windows); Electron single-instance remains a second guard. | Prove installed CLI/App handoff on supported platforms and replace the Windows TCP fallback with a named pipe if the product contract requires it. | target=Desktop/CLI entrypoints; inventory=`main.ts`, `controller_ipc.ts`, `desktop_role_lifecycle.ts`, `desktop.py`; references=contract §Entrypoints; verification=44 desktop tests (including authorized IPC run) plus Python IPC/CLI tests; residuals=installed clean-machine handoff and Windows named-pipe acceptance remain. |
| LFC-007 | P1 | in progress | Core reserves the HTTP/Godot pair atomically, publishes actual endpoints and never terminates port occupants, but some CLI readers still retain command/default-port fallback after snapshot lookup; native PKG/NSIS/DEB hooks create the global `elfienest` launcher. | Remove post-selection endpoint fallback, prove snapshot-only Web/mobile/status behavior, and execute native install/update/uninstall smoke on each clean supported host. | target=endpoints and packaging; inventory=Core endpoint binder, lifecycle snapshot, CLI handoff, release pipeline and native launcher hooks; references=contract §Entrypoints; verification=loopback/Gateway tests, port-conflict tests, release-resource tests and launcher-hook tests; residuals=strict snapshot-only consumers and clean-host package evidence remain. |
| LFC-008 | P0 | in progress | Stop publishes `QUIESCING`/reverse phases and Doctor is diagnostic-only; exact current-root stop is verified, but target selection still depends on the remembered-root path and the full stale PID/port reuse matrix is absent. | Share one bounded stop executor with upgrade/Doctor, resolve the target once, add authenticated force escalation, and prove reused PIDs/ports are never signalled. | target=shutdown/recovery; inventory=`runtime_supervisor.py`, CLI target resolver, Doctor commands, process adapters; references=contract §Shutdown; verification=supervisor/Doctor tests and stop smoke; residuals=target-resolution, full orphan/process-tree, PID/port reuse and timeout matrix remain. |
| LFC-009 | P1 | in progress | A versioned lifecycle/model projection is exposed through API and status UI; system health precedes model health and phase timings are visible. The release coordinator runs lifecycle smoke and writes typed phase budgets when enabled, but CLI output does not consistently identify the resolved root/generation/endpoints. | Add identity-rich lifecycle output, complete the native runner matrix and retain its JSON timing evidence with release artifacts. | target=observation/release gate; inventory=runtime projection DTO, frontend schema/panel, CLI JSON, `release_install_smoke.py` and workflow; references=contract §Observation; verification=API/frontend/desktop tests, lifecycle pressure test, smoke-runner tests and workflow wiring; residuals=target identity output and macOS/Windows/Linux installed timing evidence remain. |
| LFC-010 | P0 | open | Installed selection still supports a durable `selected-data-home`/`data-home activate`; source selection and shell history still consume caller `ELFIE_HOME`; entering the shell can write history inside a product/default root; only `start`/`serve` accept `--data-home`; no memory-only session context, command-eligible default fallback or validated candidate selector exists. | One resolver passes the installed binary-root, source four-command, A/B session switch, idle-default `stop`, TTY/non-TTY, no-fallthrough and catalog-revalidation matrices; history/catalog are isolated under `.elfienest-cli.local`; old selected-root artifacts are ignored and no replacement active pointer exists. | target=data-root task context; inventory=`scripts/elfienest.py`, `elfienest.sh`, CLI lifecycle/data-home commands, lifecycle data-home adapter; references=contract §Data-root target resolution and design §4; verification=pending focused resolver/parser/shell/CLI tests plus A/B smoke; residuals=all target-context behavior remains to implement. |

No row is closed by tests alone. Each row records target, inventory, references,
verification and residuals. External residuals are final-release acceptance gaps,
not local checkpoint blockers; strict release closure still requires them.
