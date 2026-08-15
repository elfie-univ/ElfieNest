# Service lifecycle conformance

> Temporary register for the normative
> [Service lifecycle contract](../contracts/service-lifecycle). It records only
> verified implementation gaps and their closure gates; the detailed execution
> plan is a separate, non-normative artifact.

| ID | Severity | Status | Current deviation | Closure gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| LFC-001 | P0 | open | `RuntimeHealth` and `runtime.json` combine aggregate state, component probes and owner receipt without canonical instance identity, snapshot schema version, target or phase timing. | One atomic generation snapshot and data-root command lock implement the contract fields; stale/corrupt records cannot grant authority. | pending |
| LFC-002 | P0 | open | Start waits for one full `ready/degraded` result; desired/wait targets and deterministic start/stop/restart races are not represented. | Typed commands implement `CORE/WORLD/NORMAL`, idempotent attach, target escalation, cancellation, `BUSY_STOPPING` and no generation overlap. | pending |
| LFC-003 | P0 | open | Godot starts from a Core-health callback; authority failure stops Core instead of preserving `CORE_READY`, and crash re-convergence is not an independent workflow. | World convergence and recovery are generation-scoped, independently cancellable and fall back truthfully to `CORE_READY`; platform child cleanup is proved. | pending |
| LFC-004 | P0 | open | Ollama is a boolean optional Runtime component and provider/monitor code recomputes health independently; no central capability gate consumes Common/Emergency Food evidence. | The model-capability service projects the four aggregate states from persisted evidence, Lifecycle only consumes them, and one server-side capability registry enforces requirements. | pending |
| LFC-005 | P0 | open | Ollama startup has no `EXTERNAL`/`ELFIENEST_OWNED` identity, per-user lease, final-release stop or orphan reconciliation. | Multi-instance lease tests prove exact ownership, reuse, final release, crash reconciliation and protection of pre-existing services. | pending |
| LFC-006 | P0 | open | Packaged Desktop always opens Viewer; packaged CLI starts the Server directly, and no installed global launcher activates a shared Controller in headless-Viewer mode. | App copies and installed CLI share one authenticated Controller; Viewer-only exit is independent, and explicit tray/CLI stop closes the exact production Server and Controller. | pending |
| LFC-007 | P1 | open | Default ports are fixed and instance discovery still depends partly on PID/port evidence; native packages do not install a global `elfienest` command on every supported platform. | Automatic endpoints are atomically selected/published, explicit conflicts are typed, and clean-machine install/update/uninstall tests prove bounded running-Server handoff plus a global launcher without source files. | pending |
| LFC-008 | P0 | open | Shutdown and Doctor contain several receipt/process repair paths, but no single quiesce-to-offline workflow proves reverse ownership, bounded escalation and exact residual reporting. | Stop/restart/Doctor share one command executor; race, timeout, orphan and third-party negative tests prove exact bounded cleanup. | pending |
| LFC-009 | P1 | open | Progress phases are coarse and the status UI independently combines `/api/health`, provider and Ollama data without one atomic lifecycle/model projection or stage timings. | CLI/API/Desktop/status UI consume one versioned projection, show system then model health, and release acceptance records startup/shutdown phase budgets and typed repair actions. | pending |

Implementation closes rows in dependency order: `LFC-001` and `LFC-002` first;
`LFC-003`–`LFC-005` next; entrypoints, packaging and shutdown after that; final
observation and release evidence closes `LFC-009`. No row closes from tests alone:
its evidence must include target, inventory, references, verification and residuals.
