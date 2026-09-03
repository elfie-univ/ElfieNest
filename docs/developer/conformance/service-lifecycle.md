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

> Status: frozen plan with the local implementation slice now landed. Native
> installed-host acceptance remains an explicit external gate.
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
| Non-authoritative CLI state | Optional `<source-root>/.elfienest.local/runtime/cli/` stores protected history and a revalidated catalog but does not affect product completeness or Runtime identity |

### Work packages and gates

Each package starts with a failing contract test. WP1-WP4 may be separate review
commits but form one **non-releasable switchover**: no build may expose the new
resolver while any remembered-root/port-fallback authority remains reachable.

| WP | Implementation | Primary boundary/files | Exit gate |
| --- | --- | --- | --- |
| WP0 — freeze tests and inventory | Baseline and authority inventory completed; remembered-root, caller-environment, port-fallback and port-kill paths were classified before implementation. | Existing CLI/lifecycle/Desktop/process tests and focused target/state tests. | Local baseline is classified; external host evidence remains WP6. |
| WP1 — one typed target resolver | Implemented App-owned `EntrypointMode`, command policy, target request/result, typed selection errors and installed/source canonicalization. | `app/orchestration/lifecycle/target_resolution.py`, target-context resolver and lifecycle exports. | Pure resolver and source-context tests pass; resolver has no UI, subprocess or data-dependent service construction. |
| WP2 — source shell and checkout control state | `elfienest.sh` is a bootstrap; the persistent Python shell owns in-memory context, shared parsing/help, TTY selection and scoped target environment. Protected history/candidates live in optional `.elfienest.local/runtime/cli/`, are lazy and are revalidated. | `elfienest.sh`, `scripts/elfienest.py`, `app/interfaces/cli/target_context.py`, `infrastructure/platform/source_cli_state.py`, `.gitignore`. | Focused shell, parser, source-state and no-fallback tests pass; entering the shell does not create CLI state, and CLI state alone does not initialize product data. |
| WP3 — installed App/global CLI convergence | Installed resolution is fixed to `${ELFIE_HOME:-~/.elfienest}`; Controller IPC protocol 2 carries the expected canonical root and returns the Controller root. Mismatch rejects the operation without attach/stop/switch; Desktop data-root selection and activation paths are removed. | Installed CLI, Controller IPC, Desktop lifecycle client/role and main handlers. | Focused Desktop/CLI tests pass; clean installed-host handoff remains external. |
| WP4 — atomic command cutover | Only the four source lifecycle commands parse `--data-home`; other commands use session/default/candidate resolution. Scoped target environment is restored after dispatch; old active-root receipts and activation aliases are inert. Provider catalog and DB reads are deferred until after target-bound execution. Web/mobile/status consume the selected snapshot endpoint only. | `scripts/elfienest.py`, lifecycle commands/facade, Bootstrap, data-home adapter, parser and lifecycle tests. | Focused resolver/CLI tests pass; no reachable active-root authority or arbitrary-port attachment remains in the implemented paths. |
| WP5 — exact generation shutdown and observation | Implemented process birth-identity capture, snapshot-bound PID/executable/cwd validation, immediate pre-signal rechecks, typed launch/stop failures and per-root service logs. Ports remain published evidence only; no port occupant is signalled. | Lifecycle snapshot/supervisor/service/start-cleanup, process/record/endpoint adapters and CLI rendering. | Focused PID/port reuse, unreadable identity, partial start, log and shutdown tests pass; supported-host race/recovery evidence remains WP6. |
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
| `web` | The exact default has a verified running generation and healthy endpoint | `selection_required`/`task_not_found`; after resolution open only that target |
| `mobile` | The exact snapshot has a verified running generation and healthy endpoint | `no_published_endpoint` or selection |
| Config, Setup, Doctor, Owner, DB | The root is usable or recoverable for that operation | Typed data-root error or selection; Runtime need not be running |
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
| A15 | Old `selected-data-home` exists and `.elfienest.local/runtime/cli` is absent, read-only, a file or a symlink | Old receipt has no effect; explicit/default operation remains safe; control-state failure is visible and cannot affect Runtime or product-data completeness. |
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

### Native release acceptance queue

These rows are closed independently. Local implementation or unit tests may
move a row to `implemented; not tested (external)`, but only the named native
evidence closes it. The target coverage and closure order are defined by the
[native release validation design](../designs/app/native-release-validation.md).

Before any NAT row becomes `closed`, its row or attached evidence must record
`target`, `inventory`, `references`, `verification` and `residuals`, including
the exact OS image, candidate SHA and package SHA-256. NAT rows supply native
evidence to existing LFC/CFG/PMA contracts; they do not close or duplicate those
contracts by name alone.

| ID | Severity | Status | Immediate implementation | External closure evidence |
| --- | --- | --- | --- | --- |
| NAT-MAC-01 | P0 | implemented; not tested (external) | Release smoke code supports both macOS arm64 and Intel installed Controller/Core/Godot chains. | Both clean native targets pass exact-package smoke and receipt/footprint checks; a real macOS session proves interactive PKG/Launchpad, Viewer/Observer, tray, single-instance, close and uninstall behavior. |
| NAT-WIN-01 | P0 | implemented; not tested (external) | Release smoke starts the installed Windows Controller, runs three cycles, records Controller/Core/Godot PIDs and rejects surviving recorded processes. | The frozen Windows host passes exact-package smoke, receipt/PATH/Start Menu/Apps registration and removal, standard-user launch, tray/single-instance handoff, clean cycles and retained evidence. |
| NAT-LNX-01 | P0 | implemented; not tested (external) | Release smoke runs the installed Linux Controller under Xvfb; CI checks the Dedicated Runtime and freedesktop entry. | Every named supported DEB host passes exact-package smoke, dpkg/desktop-entry/icon/launcher footprint, standard-user launch, graphical and Dedicated authority; a named desktop session proves application-menu and tray behavior. |
| NAT-COMPAT-01 | P0 | implemented; not tested (external) | Exact internal-Beta OS versions, Linux distribution/session and native runner images are frozen in the design and release workflow. | Each declared support cell has an exact CI image or named real-host sample and records architecture, OS build, desktop/session and result; untested cells are excluded from the support claim. |
| NAT-MODEL-01 | P0 | implemented; not tested (external) | Loopback scripted protocol model server, synthetic credential boundary, capability probes, Common/Emergency Food routes, deterministic adoption replies, chat responses and fail-closed request checks are implemented. | One installed reference journey proves model aggregate readiness and complete-response chat through the production HTTP adapter, while adoption uses the deterministic candidate-reply path; the test server and credential leave no residue or secret evidence. |
| NAT-JOURNEY-01 | P0 | implemented; not tested (external) | Installed Setup/provider/Food/adoption/chat/restart Driver is wired into each native smoke cycle and writes redacted evidence without database seeding. | All four package hashes pass from a neutral cwd without checkout fallback; evidence retains Setup, Elfie/history, execution receipt and PID/generation continuity with redacted failures. |
| NAT-UI-01 | P0 | partially implemented | Native smoke now activates the installed Viewer and requires the redacted `management_page_ready` marker; the full rendered Setup-to-chat UI path and event-severity gate remain. | Shared UI path passes; all four targets prove activation, management ready marker, rendered Observer surface and no fatal renderer/console event; OS Shell behavior is attached separately. |
| NAT-RECOVERY-01 | P0 | partially implemented | Native smoke can run a duplicate-start matrix and rejects changed generation or owned PID sets; focused lifecycle tests cover exact identity and bounded cleanup. | Applicable Windows/POSIX/native authority scenarios pass on disposable roots with exact-PID injection, bounded recovery and no unrelated process action; linked LFC residuals remain open until their own evidence closes. |
| NAT-UPGRADE-01 | P0 | not implemented | Replace same-version reinstall with previous-release-to-candidate acceptance, including running-Controller handoff and installed state created only through supported APIs. | All four targets prove safe handoff, version/source change, credential reference usability and Owner/Provider/Food/Nest/Elfie/chat/config continuity with exact old/new hashes. |
| NAT-EVIDENCE-01 | P0 | implemented; not tested (external) | Smoke JSON now carries candidate/package identity and runner fields; an independent four-target aggregator enforces exact hashes, journey presence and redaction sentinels. | Independent aggregation rejects a deliberately mismatched or secret-bearing summary and accepts one exact four-target candidate; normal PRs retain no installer and storage stays within budget. |
| NAT-PROVIDER-01 | P0 | not tested (external) | Keep deterministic package acceptance independent from Provider availability; keep the protected minimal canary only as a separate reachability signal. | The current PMA-002 representative real-provider capability matrix passes for the release without exposing credentials/prompts; adapter gaps are recorded separately from package results. |
| NAT-LONG-01 | P0 | not tested (external) | Freeze target-specific budgets and provide a redacted soak trend classifier; passive read-only observation remains separate from active disposable-host soak. | macOS, Windows and Linux each complete the agreed window with PID/generation, CPU/RSS/handle-or-FD, log/data growth, error/crash and recovery evidence; no unexplained restart or over-budget trend remains. |
| NAT-SIGN-01 | P1 | deferred by internal-test scope | The current internal package contract intentionally has no signing/notarization gate. | Open and close a separate public-distribution task only when public Windows/macOS release is authorized and signing identities are available. |

Closure crosswalk: NAT-MODEL and NAT-PROVIDER preserve LFC-004 and PMA-002;
NAT-JOURNEY preserves CFG-003 and supplies LFC-001/002/009/010 evidence;
NAT-RECOVERY supplies LFC-001/002/003/005/006/008 evidence; platform rows and
NAT-UPGRADE supply LFC-006/007/009 evidence. Closing a NAT row with an affected
LFC/PMA residual still open is not a release-closure claim.

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| LFC-001 | P0 | in progress | Snapshot schema, generation, phase, targets, endpoints, failures, timings, Controller token authentication and generation-scoped writer handoff are implemented; stale writer credentials are rejected. | Prove the same authority/identity chain on installed supported hosts, including process birth identity and recovery. | target=authoritative snapshot; inventory=`runtime_snapshot.py`, `runtime_record.py`, `runtime_supervisor.py`, `controller_ipc.py`; references=contract §Authority; verification=architecture gate plus runtime-record/supervisor/IPC tests; residuals=installed cross-platform identity and recovery acceptance remain. |
| LFC-002 | P0 | in progress | Core-first start, same-generation attach, typed `operation_id`/generation results, cancellation, target escalation and `NORMAL` waiting are implemented; an attached command waits for an explicitly requested World/Normal target without starting a second generation. | Prove the same protocol and race behavior through every installed entrypoint. | target=command/convergence; inventory=`runtime_supervisor.py`, CLI lifecycle commands, Desktop lifecycle client; references=contract §Commands; verification=supervisor, CLI and desktop tests; residuals=installed entrypoint interoperability and full race matrix remain. |
| LFC-003 | P0 | in progress | Core-resident World worker starts and observes the exact generation; POSIX process groups and Windows Job Objects cover launch/stop/attach-failure cleanup; World failure leaves Core usable. | Prove authenticated watchdog and bounded recovery on supported Windows/POSIX hosts. | target=Godot ownership; inventory=`world_worker.py`, Godot authority adapters, process/job mechanics; references=contract §Managed-process ownership; verification=world-worker/supervisor/process/Godot tests and CLI smoke; residuals=host-level kill-tree/watchdog acceptance remains. |
| LFC-004 | P0 | closed | Food evidence is read through one persistence projection; required capability evidence, Common/Emergency aggregation, capability permits and status API use the same model state without startup inference. The complete Core/World/Chat/Adoption matrix is server-gated; the configured remote Provider evidence recorded by PMA-002 is consumed through the same projection. | The registry, persisted projection, chat route and adoption route tests cover the required backend/model combinations and rejection boundaries. | target=model axis and server gates; inventory=Food projection adapter, `capability_gate.py`, API routes; references=contract §Stable state and §Commands; verification=`test/app/orchestration/lifecycle/test_capability_gate.py`, `test/infrastructure/persistence/test_model_health_projection.py`, chat/adoption API tests, and PMA-002 live Provider evidence; residuals=none |
| LFC-005 | P0 | in progress | Ollama has only `EXTERNAL` and `ELFIENEST_OWNED`, exact process identity and shared per-user holder leases; Doctor/start do not broadly kill. | Add real crash/orphan/process-reuse acceptance across multiple data roots and Setup/runtime races. | target=shared Ollama ownership; inventory=`lifecycle_ollama.py`, setup lease, Ollama tests; references=contract §Managed-process ownership; verification=shared-lease and provider tests; residuals=multi-process crash and platform acceptance remain. |
| LFC-006 | P0 | in progress | Desktop Viewer close is presentation-only; an authenticated user-scoped Controller IPC serves `ACTIVATE_VIEWER`/`ENSURE_SERVER`/`STOP_SERVER`/`STATUS` (UDS on POSIX, loopback token endpoint on Windows); Electron single-instance remains a second guard. | Prove installed CLI/App handoff on supported platforms and replace the Windows TCP fallback with a named pipe if the product contract requires it. | target=Desktop/CLI entrypoints; inventory=`main.ts`, `controller_ipc.ts`, `desktop_role_lifecycle.ts`, `desktop.py`; references=contract §Entrypoints; verification=44 desktop tests (including authorized IPC run) plus Python IPC/CLI tests; residuals=installed clean-machine handoff and Windows named-pipe acceptance remain. |
| LFC-007 | P1 | in progress | Core reserves and publishes the actual HTTP/Godot pair and never terminates port occupants. CLI start output now prints the selected HTTP and Godot WebSocket ports; web/mobile/status consume the selected snapshot endpoint. | Execute native install/update/uninstall smoke on each clean supported host. | target=endpoints and packaging; inventory=Core endpoint binder, lifecycle snapshot, CLI handoff, release pipeline and native launcher hooks; references=contract §Entrypoints; verification=loopback/Gateway, port-conflict, lifecycle-command and launcher-hook tests; residuals=clean-host package evidence remains. |
| LFC-008 | P0 | in progress | Stop resolves the selected data root, validates snapshot PID/birth identity/executable/cwd and rechecks identity immediately before each signal; PID/port occupants are never used as authority. | Complete the full orphan/process-tree, PID reuse, port reuse and timeout matrix on supported hosts. | target=shutdown/recovery; inventory=`runtime_supervisor.py`, `service.py`, CLI target resolver and process adapters; references=contract §Shutdown; verification=supervisor/service/process/target-resolution tests; residuals=host-level and full race matrix remain. |
| LFC-009 | P1 | in progress | Versioned lifecycle/model projection and phase timings are exposed; start output includes exact runtime ports and failure output carries typed causes/log paths. | Complete native runner matrix and retain installed timing evidence with release artifacts. | target=observation/release gate; inventory=Runtime projection DTO, frontend schema/panel, CLI JSON and release smoke; references=contract §Observation; verification=API/frontend/Desktop, lifecycle pressure, CLI and smoke-runner tests; residuals=installed cross-platform timing evidence remains. |
| LFC-010 | P0 | in progress | The installed root is the exclusive `${ELFIE_HOME:-~/.elfienest}` choice; source context is memory-only, source `ELFIE_HOME` is ignored, only the four lifecycle commands accept `--data-home`, and candidates are isolated in optional `.elfienest.local/runtime/cli/` state that cannot qualify a task. Legacy selected-root/activation files are inert. | Complete the supported-host App/global-CLI handoff and final A/B PTY/non-TTY smoke. | target=data-root task context; inventory=`scripts/elfienest.py`, `elfienest.sh`, target resolver/context, source state, lifecycle data-home adapter and Controller IPC; references=contract §Data-root target resolution and design §4; verification=target-resolution/source-state/CLI/desktop tests; residuals=installed host and PTY smoke evidence remain. |

No row is closed by tests alone. Each row records target, inventory, references,
verification and residuals. External residuals are final-release acceptance gaps,
not local checkpoint blockers; strict release closure still requires them.
