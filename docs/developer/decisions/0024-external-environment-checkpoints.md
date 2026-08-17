# ADR-0024: Explicit local checkpoints for unavailable platform acceptance

- **Status:** Accepted
- **Date:** 2026-08-16
- **Scope:** task closure and local pre-submit checkpoints

## Context

The closure matrix correctly keeps missing Windows/Linux hosts as `blocked`, but
the strict completion check also prevented a local checkpoint commit even when
all checks executable on the current host passed. Treating unavailable external
evidence as a code failure made the delivery workflow conflate two different
conditions.

## Decision

- A blocked row may declare only the machine-readable `blocker_class` value
  `external_environment` when the missing evidence is caused by an unavailable
  OS or installed host.
- Every `task-closure*.json` file is a governance artifact, so separate task
  matrices do not become false product/implementation changes.
- The local pre-submit gate may receive the explicit
  `--allow-external-environment-blockers` flag. It allows only those classified
  rows for a checkpoint; it never changes their status or clears residuals.
- The default gate, CI, protected-branch checks and final completion remain
  strict. Code failures, missing evidence and unclassified blockers cannot use
  the exception.
- Governance/implementation separation remains unchanged.

## Consequences

Local work can be saved without pretending that cross-platform acceptance is
complete. The missing host and replayable next check remain visible in the
matrix, and a later matching host or CI run is still required before closure.
