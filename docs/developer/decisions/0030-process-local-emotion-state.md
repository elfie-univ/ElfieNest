# ADR-0030: Emotion state is process-local and returns to baseline

**Status:** Accepted
**Date:** 2026-08-30

## Context

Emotion is a short-lived physiological-style state. Persisting its live stock,
provisional frame effects, retry ledger, or inhibition guidance across process
restarts preserves stale reactions and duplicates Event Workspace ownership.
Personality, Selfhood and Memory already own the durable facts that determine
how a new emotional state starts.

## Decision

Emotion remains authoritative and continuous across Turns inside one running
Elfie process. Its six channel stocks accumulate, decay and return toward
personality-derived baselines. Sleep and process restart reset those stocks to
their baselines and clear transient guidance.

Emotion state is not stored in Brain Journal or a dedicated database. A
Coordinator-owned, frame-scoped in-memory transaction keeps fast appraisal
idempotent across an in-process frame replay and allows one validated slow
appraisal to replace it atomically. Event Workspace remains the owner of input
deduplication and durable pending-frame recovery.

Memory may retain completed experiences and their historical emotional tone;
that is not a second copy of the live Emotion state.

## Consequences

- Restarted Emotion begins from personality-derived baselines.
- Pending durable events are appraised once again after restart.
- Live emotion checkpoints, event ledgers and persistent inhibition records are
  removed.
- Selfhood, Memory, Activities, receipts and other durable owners keep their
  existing restart semantics.
