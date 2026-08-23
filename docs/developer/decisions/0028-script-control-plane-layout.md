# ADR-0028: Separate the script control plane by responsibility

- **Status:** Accepted
- **Date:** 2026-08-23
- **Scope:** Repository script ownership, stable entry points and governance cutover

## Context

`scripts/architecture/` accumulated architecture scanners, database inventory,
change policy, validation routing, evidence caches and Git-hook installation in
one flat directory. Its name no longer described the directory, while stable
commands, individual checks and one product-consumed Godot adapter were mixed at
the `scripts/` root. The resulting layout obscured both responsibility and path
stability.

The repository's immutable-base checker also means that this self-governing
layout cannot move in one unprepared Pull Request: the old classifier would see
deleted governance files and unknown implementation additions, then correctly
reject the mixed candidate.

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
- Perform the cutover through an immutable-base preparation change, separate
  implementation and governance moves, then remove legacy path recognition.
  Do not add compatibility wrappers or retain two physical implementations.
- Maintain `scripts/README.md` and `scripts/README_zh.md` as the concise,
  bilingual directory map and script-placement guide.

## Consequences

The root becomes a small control panel, governance policy is distinguishable
from quality execution, and internal means a compatibility boundary rather
than secrecy or a prohibition on repository-owned calls. The migration needs
multiple independently classified Pull Requests, but ordinary delivery remains
unchanged and no long-lived legacy path survives the cutover.

## Cutover status

The candidate tree now uses the target layout exclusively. Its CI and local
full-gate code may read legacy scanners from the immutable base commit only
while this physical move is being judged; that base-only lookup is removed in
the follow-up cleanup after the new layout reaches protected main.
