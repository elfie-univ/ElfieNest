# ADR-0003: Contract-driven architecture ratchet

- **Status:** accepted
- **Date:** 2026-08-10
- **Scope:** repository architecture governance

## Context

ElfieNest has been refactored repeatedly. Written target diagrams alone cannot
prevent a later product change or coding agent from restoring a reverse
dependency, weakening the test that judges its own code, or turning a temporary
migration path into permanent ownership. A one-time cleanup also cannot move
every module safely without breaking a runnable product.

## Decision

Architecture is governed by a connected, versioned system:

- contracts define long-term ownership, dependency and authority;
- ADRs explain deliberate changes;
- root and child `AGENTS.md` translate those rules into local coding guidance;
- a machine-readable registry links contracts, mirrors, ADRs, guidance,
  scanners, tests and conformance registers;
- exact baselines admit only already-recorded debt and can only shrink;
- CI uses the immutable base-commit scanner against candidate production code
  for pull requests and protected-branch pushes, and rejects a change that
  modifies governance and production together;
- production-root classification covers every tracked non-documentation file,
  not only a source-code suffix list;
- product migrations may only remove exact baseline entries; governance changes
  cannot edit legacy baselines, and closed conformance rows must be machine-zero;
- migrations proceed as runnable vertical slices and keep one active authority
  per fact;
- after debt reaches zero, the baseline and conformance register are deleted
  while the scanner remains in permanent deny-all mode.

Macro architecture v1 is frozen. A later macro change requires a new standalone
ADR, synchronized contract versions and a governance-only commit before any
product migration.

## Consequences

Architecture changes require explicit governance review before product
migration. Product cleanup remains incremental and can keep existing registered
debt temporarily, but it cannot add new debt or land a broken half-migration.
The additional registry and scanner tests create maintenance work when a real
contract changes; that cost is deliberate because it makes the change visible
and prevents self-approved erosion.

Rejected alternatives are documentation-only architecture, a mutable allowlist
maintained by each feature, letting product changes edit their own scanners,
keeping an empty baseline forever, and requiring a repository-wide big-bang
migration before the application can run.
