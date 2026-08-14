# ADR-0016: App Orchestration owns the Nest state-store Port

- **Status:** Accepted
- **Date:** 2026-08-14
- **Scope:** System-level Nest persistence Port semantics

## Context

`NestRepository`, `NestPersistenceSnapshot` and the persistence error are
currently exported from `nest/`. In production, however, Nest never invokes the
repository. `app/orchestration/nest_session` decides when to load, restore,
save, roll back and recover; Bootstrap injects the SQLite Adapter. This conflicts
with the existing System/Nest wording that called the repository Port
Nest-owned and with the Application rule that the direct consumer owns a Port.

Placing the current file at `nest/persistence.py` would make its directory look
intentional without matching its real caller and lifecycle owner. Moving the
domain facts themselves to App would create the opposite error: persistence
coordination does not make App the authority for residents, homes, household
rules or environment intent.

## Decision

The direct consumer owns an outbound storage Port. For Nest state in the current
architecture:

- Nest owns the durable semantic facts, a technology-neutral `NestSnapshot` and
  Facade operations that export and restore valid aggregate state;
- `app/orchestration/nest_session` owns the `NestStateStorePort`, stable
  application-facing storage errors, and load/save/rollback/recovery timing;
- `infrastructure/persistence/` owns SQLite, SQL, schema, transactions,
  serialization, paths and the concrete Adapter;
- Bootstrap constructs the Adapter and injects it into Nest Session.

App Orchestration may coordinate persistence but cannot mutate Nest internals,
redefine household meaning or become a second writer of domain facts. It stores
and restores only snapshots obtained or accepted through the Nest Facade.

A domain-owned storage Port remains valid elsewhere when that domain directly
consumes the capability, as Elfie Brain does for Memory. Port ownership follows
the real capability consumer; semantic fact ownership remains independent.

## Consequences

The target does not contain `nest/persistence.py` or a Nest-exported Repository
Protocol. The current implementation remains tracked by `NGW-R12` until the
snapshot, Facade, App Port, Adapter typing, callers and tests migrate together.
No compatibility alias, fallback read or dual write is introduced.

This decision changes a frozen system-level Port semantic and therefore updates
the bilingual System contract before product migration. Concrete persistence
remains in Infrastructure throughout the migration.
