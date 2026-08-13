# ADR-0013: Desktop startup progress and bounded shutdown

**Status:** Accepted
**Date:** 2026-08-13

## Context

The Desktop observer previously waited for the complete Runtime readiness
contract before presenting its management page. Godot authority startup is the
slowest part of that contract, so a slow authority made the application appear
not to have launched and made explicit exit wait on a still-running startup.
The lifecycle boundary must remain the only owner of Core and Godot process
state; Desktop cannot solve this by starting a second Runtime or by weakening
the `ready` contract.

## Decision

- `RuntimeSupervisor` writes a transient `startup_owner_id` receipt and emits
  progress phases through the public CLI. The receipt blocks duplicate starts
  and is cleared or promoted to the normal owner lease by the same Supervisor.
- Desktop creates its local window and startup shell immediately. At
  `core_ready` it loads the existing management page, but the Observer keeps
  controls disabled until the full Godot-backed readiness state is available.
- Explicit application exit hides the window and dock/tray affordances first,
  cancels an in-flight startup through the public owner-scoped stop command,
  then performs the normal lifecycle stop for a lease owned by Desktop.
- Closing the observer window remains a presentation-only action and does not
  stop or cancel the Runtime.
- The lifecycle owner gives the hidden authority and managed Core a short
  graceful-stop window. If either exact, re-validated process group remains
  alive, it is force-stopped within the bounded shutdown budget.

The complete Core, Gateway and Godot readiness contract remains unchanged:
`ready` is reported only after all required components are ready. This decision
does not change business APIs, model startup, packaging targets or Runtime
authority ownership.

## Consequences

Users see an immediate, honest startup surface and can use the management page
as soon as the Web/Core layer is available, while Godot-dependent controls are
explicitly limited during the remaining startup window. A quit request no
longer leaves a visible Desktop window while cleanup runs, and a startup can be
cancelled without a private process-control path. The durable receipt gains one
transient field, `startup_owner_id`, which is exposed by `status --json` for
machine clients and is removed when the transaction ends.
A hung child no longer extends explicit shutdown indefinitely, while identity
checks still prevent signals from reaching an unrelated process.
