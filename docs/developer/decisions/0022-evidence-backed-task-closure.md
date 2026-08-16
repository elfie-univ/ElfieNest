# ADR-0022: Evidence-backed task closure and immutable two-phase governance

- **Status:** Accepted
- **Date:** 2026-08-16
- **Scope:** implementation completion, conformance closure and repository quality gates

## Context

Tests and a connected main path can pass while crash, installation, platform or
recovery acceptance remains open. A textual completion rule alone did not stop a
partial task from being reported as finished.

## Decision

- Every implementation task uses one compact `task-closure.json` matrix with
  bounded changed-path scope, contract/conformance references, evidence and
  residuals.
- The only completion states are `not_started`, `implementing`, `verifying`,
  `complete` and `blocked`. `complete` requires code, automated tests, a
  replayable runtime scenario, required platform/install evidence and zero
  residuals.
- `scripts/check_task_closure.py` runs before the full pre-submit gate and
  rejects incomplete rows, unclassified changes, broad scopes and listed open
  Conformance rows.
- The root `AGENTS.md` and contributor testing guidance are part of this
  governance surface; changes to their completion rules must ship with this
  bilingual ADR and remain separately reviewable from protected implementation.
- Changes to the closure skill or its guards use two phases: first land the
  governance-only classifier/ADR/test registration; then land the protected
  checker, integration and behavior tests. Immutable-base governance checks are
  never weakened to combine the phases.

## Consequences

Completion claims become evidence-backed and environment limitations remain
explicitly blocked. Governance changes require one extra bootstrap checkpoint,
but a passing subset can no longer masquerade as a converged delivery.
