# ADR-0021: Authoritative service lifecycle and independent capability health

- **Status:** Accepted
- **Date:** 2026-08-15
- **Scope:** service state, entrypoints, managed-process ownership and readiness

## Context

ElfieNest currently treats Core, Godot and optional model preparation as one
startup result. Desktop and source CLI also reach that result through different
ownership and presentation paths. This makes a usable Core look failed when a
secondary component is slow, and lets PID files, ports or UI state stand in for
authoritative Runtime state.

The product needs one state writer, independently useful readiness tiers and
identical lifecycle semantics across installed App, installed CLI and source
development entrypoints.

## Decision

- Adopt the normative [Service lifecycle contract](../contracts/service-lifecycle)
  and its reviewed [state-machine design](../designs/service-lifecycle-state-machine).
- `app/orchestration/lifecycle` is the sole writer of an atomic,
  generation-scoped snapshot. Backend has exactly `OFFLINE`, `CORE_READY` and
  `WORLD_READY` stable tiers; transition phases and failures are separate.
- Model health is an independent persisted-evidence projection. Common Food,
  Emergency Food and inactive models have different aggregate impact; startup
  never performs blocking inference validation.
- Godot is an exact-generation managed Core child. Ollama is either pre-existing
  `EXTERNAL` or `ELFIENEST_OWNED` and shared through per-user leases.
- The packaged Desktop Controller is globally single-instance and outlives its
  disposable Viewer. Installed `elfienest start` activates that Controller and
  Server without opening Viewer; source `./elfienest.sh` remains the isolated
  development entrypoint.
- Identity, stop authority and recovery derive from product lock, canonical
  data root, generation and validated process identity—not ports, PIDs or names
  alone. Installed startup uses only packaged resources and never builds or
  installs product dependencies.

ADR-0014 remains historical evidence for immediate startup presentation and
bounded cleanup. This decision supersedes its single terminal `ready` model and
any interpretation that quitting a Viewer implicitly stops the Server.

## Consequences

Core configuration becomes available before world/model convergence, partial
failure remains truthful, and every entrypoint attaches to the same authority.
Implementation requires a new snapshot schema, command serialization, process
leases, capability gates, installer integration and phase timing. Current gaps
are tracked only in the temporary
[service lifecycle conformance register](../conformance/service-lifecycle).
