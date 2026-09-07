"""Named frozen payload models for reasoning-boundary observations.

Each emitting reasoning boundary owns one named payload carried inside a
``BrainObservation`` envelope, replacing the former ad-hoc dict events.
Field shapes follow the brain-observation field-schema draft (§B3 Memory
Bridge, §B4 Context Engine, §C Memory recall) and the sample events
C-1..C-4 / B4: nested sample objects become named sub-models, and every
field is a raw value the emitting code already holds (no inferred data).

This module stays domain-pure: it imports only ``elfie.message_types``
primitives and never ``infrastructure``, ``app`` or ``devtools``.
"""

from __future__ import annotations

from typing import Optional, Tuple

from pydantic import Field

from elfie.message_types import FrozenContractModel


class MemoryStateObservation(FrozenContractModel):
    """Pinned ``MemoryStateSnapshot`` projection (§C sample C-1 ``state``).

    Maps ``MemoryStateSnapshot.revision``/``episodic_count``/
    ``total_count``/``snapshot_freshness`` verbatim; the snapshot's
    ``captured_at`` rides on the envelope and its ``source_event_ids`` are
    outside the sample's ``state`` granularity, so neither is duplicated.
    """

    revision: int = Field(ge=0)
    episodic_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    snapshot_freshness: str


class MemoryTurnOpened(FrozenContractModel):
    """One Run's revision-pinned Memory view was opened (§B3, sample C-1).

    ``query`` is the compiled baseline-recall intent (possibly empty) and
    ``state`` summarizes the pinned ``MemoryStateSnapshot`` that the Run
    will read from.
    """

    frame_id: str
    query: str
    pinned_revision: int = Field(ge=0)
    state: MemoryStateObservation


class MemoryRecallRequestObservation(FrozenContractModel):
    """Bound fields of the ``RecallRequest`` the bridge pinned (sample C-2).

    Mirrors the seven bounds ``ReasoningMemoryBridge._request`` sets on the
    typed ``RecallRequest``; the request's remaining inherited defaults are
    outside the sample's ``request`` granularity and stay unrecorded.
    """

    mode: str
    seed_limit: int = Field(ge=0)
    node_limit: int = Field(ge=0)
    assertion_limit: int = Field(ge=0)
    episode_limit: int = Field(ge=0)
    evidence_limit: int = Field(ge=0)
    character_limit: int = Field(ge=0)


class MemoryRecallStarted(FrozenContractModel):
    """One baseline or on-demand recall intent entered the bridge (§B3/§C)."""

    frame_id: Optional[str] = None
    query: str
    pinned_revision: int = Field(ge=0)
    request: MemoryRecallRequestObservation


class MemoryRecallBundleObservation(FrozenContractModel):
    """ID-level summary of one recalled ``RecallBundle`` (sample C-3).

    Records which records the recall selected (IDs) without copying the
    full material into the observation stream; ``paths`` and ``conflicts``
    carry no single identity, so they are recorded as counts.
    """

    recall_revision: int = Field(ge=0)
    focus_node_ids: Tuple[str, ...] = ()
    assertion_ids: Tuple[str, ...] = ()
    episode_ids: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    path_count: int = Field(default=0, ge=0)
    conflict_count: int = Field(default=0, ge=0)


class MemoryRecallResultObservation(FrozenContractModel):
    """One recall outcome: bounded selection summary or the skip reason (§C).

    ``status`` mirrors ``MemoryRecallStatus``; ``bundle`` is ``None`` only
    when the bridge produced no bundle at all (e.g. an exhausted on-demand
    budget) — a skipped baseline still carries its empty pinned bundle.
    """

    frame_id: Optional[str] = None
    query: str
    status: str
    pinned_revision: int = Field(ge=0)
    reason: Optional[str] = None
    bundle: Optional[MemoryRecallBundleObservation] = None


class CompiledContextObservation(FrozenContractModel):
    """One Context Engine compile for a model request (§B4, sample B4).

    The per-material counts record what the 7-level priority assembly kept
    (events, state updates, media, conversation, summaries, run
    observations), ``memory_chars``/``memory_estimated_tokens`` size the
    compiled memory block, ``memory_recall_revision`` binds the compile to
    the Memory Bridge pin, and ``truncated`` records whether the token
    budget trimmed content. Per-section trim reasons are not yet available
    from the compiler, so only the aggregate flag is recorded.
    """

    turn_id: str
    frame_id: str
    context_revision: int = Field(ge=0)
    capability_revision: int = Field(ge=0)
    memory_recall_revision: int = Field(default=0, ge=0)
    max_tokens: int = Field(ge=0)
    reasoning_mode: str
    response_mode: str
    event_count: int = Field(default=0, ge=0)
    state_update_count: int = Field(default=0, ge=0)
    media_sample_count: int = Field(default=0, ge=0)
    conversation_count: int = Field(default=0, ge=0)
    summary_count: int = Field(default=0, ge=0)
    run_observation_count: int = Field(default=0, ge=0)
    memory_chars: int = Field(default=0, ge=0)
    memory_estimated_tokens: int = Field(default=0, ge=0)
    truncated: bool = False


__all__ = (
    "CompiledContextObservation",
    "MemoryRecallBundleObservation",
    "MemoryRecallRequestObservation",
    "MemoryRecallResultObservation",
    "MemoryRecallStarted",
    "MemoryStateObservation",
    "MemoryTurnOpened",
)
