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

The six version-1 stocks are happiness, sadness, anger, fear, surprise and
disgust. Sparse appraisals provide signed semantic strength for only the
affected channels; the deterministic owner calculates saturation, direct stock
consumption and exponential return. Observed actor affect is evidence rather
than Elfie's state, and relationship-weighted empathy remains a separate
appraisal from direct self-relevance.

Emotion state is not stored in Brain Journal or a dedicated database. A
Coordinator-owned, frame-scoped in-memory transaction keeps fast appraisal
idempotent across an in-process frame replay and allows one validated slow
appraisal to replace it atomically. Event Workspace remains the owner of input
deduplication and durable pending-frame recovery.

The model receives the stable pre-fast Emotion projection and host-trusted
candidate scopes, not the provisional fast stock. Structured slow appraisal is
recomputed from the same pre-fast anchor. Exact dynamics and the current
quality gaps are specified by the
[Emotion design](../designs/elfie-emotion-system) and
[conformance register](../conformance/elfie-emotion).

Audio/image affect detection is deferred. Existing typed media transport is
preserved, but no unused detector placeholder is retained; future detectors
must produce observation evidence through the same appraisal boundary.

Memory may retain completed experiences and their historical emotional tone;
that is not a second copy of the live Emotion state.

## Consequences

- Restarted Emotion begins from personality-derived baselines.
- Pending durable events are appraised once again after restart.
- Live emotion checkpoints, event ledgers and persistent inhibition records are
  removed.
- The old fixed stock-to-stock interaction matrix and parallel VAD/Episode
  state are not version-1 authorities.
- Semantic effect quality remains independently evaluated and does not become
  proven merely because the deterministic state transition tests pass.
- Selfhood, Memory, Activities, receipts and other durable owners keep their
  existing restart semantics.
