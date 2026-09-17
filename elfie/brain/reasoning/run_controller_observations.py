"""Named frozen payloads for the Run Controller and Context Engine group.

Each emitting boundary owns one named payload carried inside a
``BrainObservation`` envelope: the ReasoningRunController mode decision and
reasoning-budget freeze (§B1), the deferred Energy cognitive-budget reserve
emit at the ``reserve_cognitive_budget`` call site (§A5), the frozen Selfhood
projection snapshot read during context assembly (§A3), the immutable owner
snapshots sealed after ``BrainContext`` assembly, the Context Engine budget
trim decision recorded beside ``compiled_context`` (§B4), and the
ReasoningContextWorkspace append observation taken at the controller's
``observe_conversation`` point (§B2). Every field is a raw value the
emitting code already holds at the emit point (P1 raw capture, no inferred
data).

This module stays domain-pure: it imports typed owner contracts plus
``elfie.message_types`` primitives and never ``infrastructure``, ``app`` or
``devtools``.
"""

from __future__ import annotations

from typing import Literal, Optional, Tuple

from pydantic import Field

from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.energy.contracts import EnergySnapshot
from elfie.brain.motivation.contracts import MotivationSnapshot
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.reasoning.coordinator_observations import (
    EnergyBudgetStateObservation,
)
from elfie.brain.selfhood.contracts import SelfhoodPromptProjection
from elfie.message_types import FrozenContractModel, UTCDateTime


class ReasoningModeSelectedObservation(FrozenContractModel):
    """One DIRECT/DELIBERATE admission decision with its basis (§B1).

    ``depth_basis`` records which host signal the depth gate used, exactly
    as computed by ``ReasoningRunController._reasoning_depth``; the code
    does not compute any further complexity metrics, so none are invented
    here.
    """

    depth: Literal["direct", "deliberate"]
    depth_basis: str
    reasoning_mode: Literal["fast", "long"]
    response_mode: str
    requires_model: bool
    structured_owner_reply: bool
    fast_owner_reply: bool
    effective_tools: Tuple[str, ...] = ()
    skill_count: int = Field(default=0, ge=0)


class ReasoningBudgetFrozenObservation(FrozenContractModel):
    """One frozen per-Run admission envelope (§B1 output).

    ``deadline_seconds`` is the Run-relative budget deadline and
    ``hard_deadline_seconds`` the Turn-level timeout both live on the
    controller; ``absolute_deadline`` is the Turn deadline sealed into the
    decode seed.
    """

    max_steps: Optional[int] = Field(default=None, ge=1)
    max_model_calls: int = Field(ge=1)
    max_planned_model_calls: Optional[int] = Field(default=None, ge=1)
    max_tool_calls: int = Field(ge=0)
    deadline_seconds: Optional[float] = Field(default=None, ge=0.0)
    hard_deadline_seconds: float = Field(ge=0.0)
    absolute_deadline: UTCDateTime
    max_context_tokens: int = Field(ge=16)
    cognitive_mode: str
    long_reasoning_allowed: bool


class CognitiveBudgetReservedObservation(FrozenContractModel):
    """One cognitive-budget reservation granted before a Run (§A5).

    Emitted at the ``reserve_cognitive_budget`` boundary inside
    ``ReasoningRunController.build_task``; ``budget`` is the Energy
    snapshot sealed immediately after the reservation.
    """

    mode: str
    source: str
    granted: float = Field(ge=0.0)
    owner_revision: int = Field(ge=0)
    responsive: bool
    budget: EnergyBudgetStateObservation


class SelfhoodProjectionObservation(FrozenContractModel):
    """One frozen two-layer Selfhood projection actually read (§A3).

    Read-only: the projection text is the deterministic prompt material
    the Context Engine consumes this Turn; no write path exists.  The
    identity/trait mapping happens inside Selfhood before this point, so
    the raw Big-Five values never appear here.
    """

    revision: int = Field(ge=0)
    projected_at: UTCDateTime
    identity_core_text: str
    adaptive_self_text: str


class ReasoningContextFrozenObservation(FrozenContractModel):
    """The owner snapshots sealed when the immutable BrainContext was built.

    This is the read point for Setup's frozen state.  It deliberately carries
    the five owner contracts that the model sees at reasoning entry, rather
    than re-reading mutable state later or projecting the Lab's ``state_before``
    fixture.  Conversation, memory and capabilities remain in their own
    stage projections so this record does not duplicate those authorities.
    """

    context_revision: int = Field(ge=0)
    constitution_version: int = Field(ge=0)
    context_captured_at: UTCDateTime
    emotion: EmotionSnapshot
    homeostasis: EnergySnapshot
    motivation: MotivationSnapshot
    orientation: OrientationSnapshot
    selfhood: SelfhoodPromptProjection


class ContextTrimObservation(FrozenContractModel):
    """One Context Engine budget split with its cut counters (§B4).

    Recorded beside ``compiled_context`` for the same compile pass.  The
    ``*_truncated_count`` fields are how many rows the matching budget
    cursor clipped or dropped entirely; per-row reasons do not exist in
    the code (a row is cut purely by word count), so none are invented.
    ``history_truncated_count`` covers state updates, summaries and
    conversation rows, which share one cursor by construction.
    """

    max_tokens: int = Field(ge=16)
    reserved: int = Field(ge=0)
    memory_budget: int = Field(ge=0)
    content_budget: int = Field(ge=1)
    event_budget: int = Field(ge=0)
    observation_budget: int = Field(ge=0)
    truncated: bool
    memory_truncated: bool
    event_truncated_count: int = Field(default=0, ge=0)
    history_truncated_count: int = Field(default=0, ge=0)
    run_observation_truncated_count: int = Field(default=0, ge=0)


class ConversationSummaryCoverageObservation(FrozenContractModel):
    """One workspace summary's provenance coverage (§B2)."""

    summary_id: str
    version: int = Field(ge=1)
    source_event_ids: Tuple[str, ...] = ()
    unresolved_count: int = Field(default=0, ge=0)


class ConversationAppendedObservation(FrozenContractModel):
    """One controller-side conversation workspace observation (§B2).

    Recorded at ``ReasoningRunController.observe_conversation`` after the
    workspace ingested the admitted input.  ``channel_id``/``conversation_id``
    form the partition key of the last social event in the frame (the
    workspace's active partition); ``input_event_ids`` are the social event
    identities offered for append.  Per-event dedup happens inside the
    workspace and is not visible at this boundary, so this record makes no
    per-event appended claim.
    """

    channel_id: Optional[str] = None
    conversation_id: Optional[str] = None
    input_event_ids: Tuple[str, ...] = ()
    message_count: int = Field(default=0, ge=0)
    active_topic_message_count: int = Field(default=0, ge=0)
    summaries: Tuple[ConversationSummaryCoverageObservation, ...] = ()


__all__ = (
    "CognitiveBudgetReservedObservation",
    "ContextTrimObservation",
    "ConversationAppendedObservation",
    "ConversationSummaryCoverageObservation",
    "ReasoningBudgetFrozenObservation",
    "ReasoningModeSelectedObservation",
    "ReasoningContextFrozenObservation",
    "SelfhoodProjectionObservation",
)
