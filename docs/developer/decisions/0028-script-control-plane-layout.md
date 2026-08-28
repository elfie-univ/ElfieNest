# ADR-0028: Separate the script control plane by responsibility

- **Status:** Accepted
- **Date:** 2026-08-23
- **Revised:** 2026-08-23 by ADR-0029
- **Scope:** Repository script ownership, stable entry points and governance cutover

## Context

`scripts/architecture/` accumulated architecture scanners, database inventory,
change policy, validation routing, evidence caches and Git-hook installation in
one flat directory. Its name no longer described the directory, while stable
commands, individual checks and one product-consumed Godot adapter were mixed at
the `scripts/` root. The resulting layout obscured both responsibility and path
stability.

At the time of the cutover, the old classifier rejected every candidate that
contained both governance and implementation paths. The migration was therefore
split into multiple Pull Requests. ADR-0029 later identified that PR-level split
as an over-broad control: immutable-base rules prevent self-approval without
turning every local review boundary into a main-delivery boundary.

## Decision

- Keep only deliberate high-level command or import contracts directly under
  `scripts/`.
- Put contract registration, change policy, code/dependency boundaries and
  persistence guards under `scripts/governance/`.
- Put individual quality checks, validation planning/execution/cache and the
  managed Git hook under `scripts/quality/`. Changes in this tree remain
  governance changes because they alter the mechanism that judges candidates.
- Keep replaceable Bootstrap, build, release and manual-diagnostic helpers under
  `scripts/internal/`. Internal callers may use them directly, but their paths
  are not external compatibility contracts.
- Move the concrete Godot species-validation runner to its existing
  Infrastructure artifact owner instead of retaining a product dependency on a
  convenience module under `scripts/`.
- Perform the cutover with immutable-base protection, logically separate local
  commits and a final removal of legacy path recognition. Do not add
  compatibility wrappers or retain two physical implementations. The historical
  multi-PR execution is not a reusable delivery requirement.
- Maintain `scripts/README.md` and `scripts/README_zh.md` as the concise,
  bilingual directory map and script-placement guide.

## Consequences

The root becomes a small control panel, governance policy is distinguishable
from quality execution, and internal means a compatibility boundary rather
than secrecy or a prohibition on repository-owned calls. No long-lived legacy
path survives the cutover. Future work may keep governance and implementation
in separate local commits on one long-lived branch and use one final Pull
Request when the immutable base rules still accept the implementation.

## Cutover status

Completed. Protected `main`, ordinary callers, CI and local gates now use only
the target layout. The temporary immutable-base lookup and caller fallbacks
were removed in separate governance and product changes. Retired paths remain
only as historical context and explicit fail-closed rejection targets; they are
not executable fallbacks or valid ownership locations.
