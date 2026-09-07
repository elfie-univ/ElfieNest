"""Named frozen payload models for reasoning-boundary observations.

Each emitting reasoning boundary owns one named payload carried inside a
``BrainObservation`` envelope, replacing the former ad-hoc dict events.
Field shapes follow the brain-observation field-schema draft (§B3 Memory
Bridge, §B4 Context Engine, §C Memory recall) at core-field granularity;
later observation todos refine them toward the full schema.

This module stays domain-pure: it imports only ``elfie.message_types``
primitives and never ``infrastructure``, ``app`` or ``devtools``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from elfie.message_types import FrozenContractModel


class MemoryTurnOpened(FrozenContractModel):
    """One Run's revision-pinned Memory view was opened (§B3).

    ``query`` is the compiled baseline-recall intent (possibly empty) and
    the ``memory_*`` fields summarize the pinned ``MemoryStateSnapshot``
    that the Run will read from.
    """

    frame_id: str
    query: str
    pinned_revision: int = Field(ge=0)
    memory_revision: int = Field(ge=0)
    memory_episodic_count: int = Field(ge=0)
    memory_total_count: int = Field(ge=0)
    state_freshness: str


class MemoryRecallStarted(FrozenContractModel):
    """One baseline or on-demand recall intent entered the bridge (§B3/§C)."""

    frame_id: Optional[str] = None
    query: str
    pinned_revision: int = Field(ge=0)
    mode: str


class MemoryRecallResultObservation(FrozenContractModel):
    """One recall outcome: bounded evidence summary or the skip reason (§C).

    ``status`` mirrors ``MemoryRecallStatus``; the ``*_count`` fields
    summarize the recalled ``RecallBundle`` evidence without copying the
    full material into the observation stream.
    """

    frame_id: Optional[str] = None
    query: str
    status: str
    pinned_revision: int = Field(ge=0)
    reason: Optional[str] = None
    recall_revision: Optional[int] = Field(default=None, ge=0)
    focus_node_count: int = Field(default=0, ge=0)
    assertion_count: int = Field(default=0, ge=0)
    episode_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    conflict_count: int = Field(default=0, ge=0)


class CompiledContextObservation(FrozenContractModel):
    """One Context Engine compile for a model request (§B4).

    The material counts and ``truncated`` record what the 7-level
    priority assembly kept and whether the token budget trimmed content;
    ``max_tokens`` is the provider-neutral budget the compile ran under.
    """

    turn_id: str
    frame_id: str
    context_revision: int = Field(ge=0)
    capability_revision: int = Field(ge=0)
    max_tokens: int = Field(ge=0)
    reasoning_mode: str
    response_mode: str
    event_count: int = Field(default=0, ge=0)
    conversation_count: int = Field(default=0, ge=0)
    summary_count: int = Field(default=0, ge=0)
    run_observation_count: int = Field(default=0, ge=0)
    memory_chars: int = Field(default=0, ge=0)
    truncated: bool = False


__all__ = (
    "CompiledContextObservation",
    "MemoryRecallResultObservation",
    "MemoryRecallStarted",
    "MemoryTurnOpened",
)
