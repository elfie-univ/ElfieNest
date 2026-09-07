"""Named frozen payload models for Memory-boundary observations.

Each emitting Memory boundary owns one named payload carried inside a
``BrainObservation`` envelope. Field shapes follow the brain-observation
field-schema draft (§A7 Memory encode direction, §C Memory recall) and the
sample event C-5: nested sample objects become named sub-models, and every
field is a raw value the emitting code already holds (no inferred data).

Payloads speak domain language only — candidate IDs, scores, kept/excluded
reasons, revision transitions and character budgets. No storage detail
(SQL, rows, paths) may appear here; the infrastructure adapter translates.

This module stays domain-pure: it imports only ``elfie.message_types``
primitives and never ``infrastructure``, ``app`` or ``devtools``.
"""

from __future__ import annotations

from typing import Optional, Tuple

from pydantic import Field

from elfie.message_types import FrozenContractModel


class RecallCandidateScored(FrozenContractModel):
    """One recall candidate received a lexical score and a selection outcome
    (§C, sample C-5 ``scored``/``dropped`` entries).

    ``score`` is the raw lexical relevance the scorer computed before any
    truncation. ``kept`` is the selection decision at the emitting stage and
    ``exclusion_reason`` is ``None`` exactly when ``kept`` is true. The
    character budget is reported once per recall on
    :class:`RecallSelectionSummary`, not per candidate.
    """

    query_terms: Tuple[str, ...] = ()
    candidate_id: str
    candidate_kind: str
    score: float = Field(ge=0.0, le=1.0)
    matched_terms: Tuple[str, ...] = ()
    kept: bool
    exclusion_reason: Optional[str] = None
    source: str = "lexical"


class RecallSelectionSummary(FrozenContractModel):
    """End-of-recall selection and truncation summary (§C, sample C-5
    ``filters``).

    ``candidates_seen`` counts the candidates that entered the selection
    stage: the lexical survivors returned by the search pass plus the
    request's explicit seed IDs. Candidates dropped inside the lexical pass
    before carrying a score (no search-term hit at all) are not part of this
    count. ``character_budget_used`` sums the final bounded episode excerpt
    lengths and ``character_budget_limit`` is the request's budget.
    """

    candidates_seen: int = Field(ge=0)
    kept: int = Field(ge=0)
    truncated: bool = False
    character_budget_used: int = Field(default=0, ge=0)
    character_budget_limit: int = Field(ge=0)


class MemoryEncodeCandidate(FrozenContractModel):
    """One episodic encode candidate entered validation (§A7 input).

    ``content_chars`` records the candidate content length only; the full
    content text is deliberately not duplicated into the observation stream.
    ``source_event_ids`` are the candidate's provenance anchors.
    """

    candidate_id: str
    base_revision: int = Field(ge=0)
    source_event_ids: Tuple[str, ...] = ()
    emotion: str
    intensity: float = Field(ge=0.0, le=100.0)
    content_chars: int = Field(ge=0)


class MemoryEncodeCommit(FrozenContractModel):
    """One encode candidate settled into a commit receipt (§A7 output).

    ``status``/``reason`` mirror ``StateCommitReceipt`` verbatim; a
    ``duplicate`` or ``stale`` rejection carries no ``episode_id`` because no
    episode was written. ``revision_before``/``revision_after`` bracket the
    semantic revision transition observed by this commit.
    """

    candidate_id: str
    episode_id: Optional[str] = None
    status: str
    reason: Optional[str] = None
    revision_before: int = Field(ge=0)
    revision_after: int = Field(ge=0)


class MemoryUseProposalRecorded(FrozenContractModel):
    """One bounded use proposal passed or failed its allow-list validation.

    ``accepted`` is the boolean the facade returned; a ``ValueError``
    rejection records its message in ``reason`` with ``accepted=false``.
    """

    proposal_id: str
    target_kind: str
    target_ids: Tuple[str, ...] = ()
    recall_revision: int = Field(ge=0)
    accepted: bool
    reason: Optional[str] = None


class MemoryReinforcementApplied(FrozenContractModel):
    """One authoritative outcome was settled into the storage-owned policy.

    ``accepted`` mirrors the storage consumer result and the revision
    transition only advances when the receipt was applied. A validation
    rejection records its message in ``reason`` with ``accepted=false``.
    """

    event_id: str
    proposal_id: Optional[str] = None
    target_kind: str
    target_id: str
    outcome_kind: str
    recall_revision: Optional[int] = Field(default=None, ge=0)
    accepted: bool
    reason: Optional[str] = None
    revision_before: int = Field(ge=0)
    revision_after: int = Field(ge=0)


__all__ = (
    "MemoryEncodeCandidate",
    "MemoryEncodeCommit",
    "MemoryReinforcementApplied",
    "MemoryUseProposalRecorded",
    "RecallCandidateScored",
    "RecallSelectionSummary",
)
