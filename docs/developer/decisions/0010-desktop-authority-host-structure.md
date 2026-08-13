# ADR-0010: Desktop authority host structure follows ownership

- **Status:** Accepted
- **Date:** 2026-08-12
- **Scope:** Desktop Interface source structure and Bootstrap authority host

## Context

The System contract already limits `app/interfaces/desktop/` to the visible
Observer and lifecycle client, while `app/bootstrap/` owns production
composition. The permanent project-structure test still required
`app/interfaces/desktop/src/role_dispatch.ts`, an older authority-host dispatch
module. That requirement contradicted the accepted ownership boundary and would
force a retired host implementation to remain in the Interface.

## Decision

The Desktop Interface source contract requires only its observer/lifecycle
modules and no longer requires `role_dispatch.ts`. The Electron authority host
and its packaging configuration belong under `app/bootstrap/desktop_host/`.
This governance step removes the contradictory structural requirement before
the separate product migration deletes the old module. After deletion, a later
governance closure adds the permanent anti-regression assertion. This does not
change module ownership, authority, or dependency direction.

## Consequences

Product migration can remove the obsolete Interface host only after this
governance change lands. The architecture suite continues to protect the
required lifecycle client without forcing the retired host to remain.
