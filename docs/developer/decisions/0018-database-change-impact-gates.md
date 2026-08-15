# ADR-0018: Database changes require impact inventory and final-state gates

- **Status:** Accepted
- **Date:** 2026-08-15
- **Scope:** Durable database schema, SQL semantics, and persistence boundaries

## Context

The root Nest database is shared by adoption, ownership, account management,
capacity, food, embodiment, runtime state, management projections and API
fixtures. A change that appears local to one Repository can change counts,
authorization, restart behavior or the meaning of a resident row elsewhere.

The adoption flow also demonstrated a specific failure mode: a process-level
intermediate state was written into the final `elfies` fact table. Filtering
some display queries did not protect quota, capacity, trigger, deletion and
recovery paths.

## Decision

Database changes are protected by three independent layers:

1. `infrastructure/persistence/AGENTS.md` requires a pre-change impact
   inventory, explicit lifecycle and failure analysis, and separation of
   database work from product/UI/runtime changes.
2. `scripts/architecture/database_change_scan.py` provides a read-only
   inventory of schema objects and SQL consumers. It is the required first
   review command; it must be rerun after the change so the complete consumer
   surface is visible.
3. `test/architecture/test_database_change_boundaries.py` and the existing
   architecture suite enforce the persistence boundary and reject transient
   process state embedded in the final Elfie table. CI runs these tests.

Final business tables contain only durable, completed facts. Temporary drafts,
leases, provisioning work and retry state belong in memory or an explicitly
approved temporary store. A new table, column, index, constraint, trigger,
transaction boundary or SQL semantic requires review of every writer, reader,
derived count, capacity rule, authorization path, runtime projection,
fixture, upgrade path and rollback path. `CREATE TABLE IF NOT EXISTS` is not a
database migration.

## Consequences

Database changes become a separately reviewable high-risk slice. The database
consumer inventory is evidence for human review, while the architecture tests
block the known class of final-table contamination. Existing unsafe
intermediate-state implementations remain blocked until they are redesigned;
the guard is not weakened to make them pass.
