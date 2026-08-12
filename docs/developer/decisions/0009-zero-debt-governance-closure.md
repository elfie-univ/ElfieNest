# ADR-0009: Atomic zero-debt governance closure

- **Status:** Accepted
- **Date:** 2026-08-12
- **Scope:** Repository governance and completed architecture or behavior migrations

## Context

The architecture ratchet defined how to reduce debt and said that an empty
baseline and completed conformance register must be deleted. It did not make the
last-debt transition an explicit workflow that also updated the registry,
architecture tests, indexes, links and local `AGENTS.md` guidance. As a result,
several registered rule sets reached zero while their temporary governance
artifacts remained, and the App scanner still accepted retired feature
directories.

## Decision

The last product migration and the governance cleanup remain separate changes.
After the migration removes the final production violation and baseline entry,
an immediate governance-only closure must atomically:

- inspect the active checkout and remove every retired physical path, including
  empty, untracked or ignored directories that cannot appear in a Git diff;
- prove zero debt with the permanent scanner in deny-all mode;
- run every architecture test registered to each contract being closed; when
  more than one contract closes together, run the complete `test/architecture/`
  suite rather than a hand-picked subset;
- delete empty baselines and all-closed conformance mirrors;
- remove their registry, test, index and link bindings;
- remove migration-only instructions and retired gap references from local
  `AGENTS.md` files while retaining durable anti-regression boundaries; and
- update bilingual contracts and focused tests together, then rerun the same
  scanners and architecture tests after the temporary artifacts are deleted.

The contract registry may reference a conformance register only while at least
one row is not closed, and may reference a baseline only while that baseline has
at least one exact debt entry. Machine tests enforce both conditions and keep
the complete architecture suite inside CI's full test job, so a selected local
test list cannot serve as closure evidence. Retired App directories are no
longer accepted by the permanent directory scanner.

This closure changes no module ownership, authority or dependency direction. It
records that System, App and Model/Food/Tool debt, plus the completed Elfie
Ports/Adapters slice, reached zero. Later Elfie 2.0 life-system gaps remain in
their active conformance registers and are not hidden by this decision.

## Consequences

Temporary debt machinery cannot silently become permanent documentation or a
regression allowlist. Completing the final migration now creates a small,
mandatory governance follow-up, but the repository finishes with one current
quality system: contracts and local guidance describe the target, scanners and
tests enforce it, and only genuinely open debt has a register or baseline.

Rejected alternatives are keeping empty baselines as harmless placeholders,
keeping all-closed registers as current documentation, relying on manual search,
or allowing tests to require retired debt artifacts.
