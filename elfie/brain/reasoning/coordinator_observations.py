"""Named frozen payload models for the coordinator-group boundaries.

Each emitting boundary owns one named payload carried inside a
``BrainObservation`` envelope: Emotion appraisal/candidate (§A4),
Energy cognitive-budget settle/release (§A5), Motivation drive
evaluation (§A6), Event-Workspace frame admission (§A1), Orientation
snapshot (§A2) and the unified decision boundary (§A11). Every field is
a raw value the emitting code already holds at the emit point (P1 raw
capture, no inferred data). The Activity Preflight verdict payload
(§A9) lives beside its owner in
``elfie/brain/activity/observation_payloads.py``.

This module stays domain-pure: it imports only ``elfie.message_types``
primitives and never ``infrastructure``, ``app`` or ``devtools``.
"""

from __future__ import annotations

from typing import Literal, Optional, Tuple

from pydantic import Field

from elfie.message_types import FrozenContractModel, UTCDateTime


class EmotionEffectObservation(FrozenContractModel):
    """One calibrated appraisal effect held by the emitting code (§A4)."""

    channel: str
    direction: str
    strength: float
    confidence: float


class EmotionAppraisalObservation(FrozenContractModel):
    """One trusted-scope appraisal with its channel effects (§A4).

    Mirrors the ``TrustedAppraisalScope`` identity and the raw
    ``ChannelEffect`` tuple of one ``AffectiveAppraisal``; the calibrated
    strength the candidate applies later is recomputed by the emotion
    owner and is not duplicated here.
    """

    scope_id: str
    cause_event_id: str
    relevance: str
    related_actor_id: Optional[str] = None
    relationship_weight: float = 1.0
    effects: Tuple[EmotionEffectObservation, ...] = ()
    reason: Optional[str] = None


class EmotionAppraisalInputObservation(FrozenContractModel):
    """One appraised input event plus retained guidance (§A4 sample).

    ``appraisals`` holds the appraiser's trusted-scope output for the
    event; ``guidance_applied``/``guidance_effects``/``guidance_reason``
    record whether a host-retained correction for the same continuing
    cause was merged into the stimulus.
    """

    event_id: str
    stimulus_id: str
    source: str
    dose: float
    appraisals: Tuple[EmotionAppraisalObservation, ...] = ()
    guidance_applied: bool = False
    guidance_effects: Tuple[EmotionEffectObservation, ...] = ()
    guidance_reason: Optional[str] = None


class EmotionDimensionChangeObservation(FrozenContractModel):
    """Per-dimension intermediate value of one candidate (§A4).

    ``before`` is the anchor value and ``after`` the candidate value for
    one emotion channel; both are raw snapshot values held by the
    coordinator, so the accumulation/decay delta is directly readable.
    """

    name: str
    before: float
    after: float


class EmotionCandidateObservation(FrozenContractModel):
    """One purely calculated affect candidate (§A4 output).

    ``stage`` distinguishes the pre-fast frame candidate from the
    model-reviewed replacement computed at worker completion.
    """

    stage: Literal["fast", "slow"]
    revision: int = Field(ge=0)
    dimensions: Tuple[EmotionDimensionChangeObservation, ...] = ()
    changed_dimensions: Tuple[str, ...] = ()
    source_event_ids: Tuple[str, ...] = ()


class EnergyBudgetStateObservation(FrozenContractModel):
    """Homeostasis budget projection read at one settle/release point (§A5)."""

    energy: float
    fatigue: float
    cognitive_mode: str
    long_reasoning_allowed: bool
    available_cognitive_budget: float
    reserved_cognitive_budget: float


class CognitiveBudgetSettledObservation(FrozenContractModel):
    """One cognitive-budget reservation was charged (§A5).

    ``consumed`` is the requested charge and ``charged`` the amount the
    energy owner actually deducted (bounded by the reservation grant).
    """

    stage: str
    consumed: float
    charged: float
    budget: EnergyBudgetStateObservation


class CognitiveBudgetReleasedObservation(FrozenContractModel):
    """One cognitive-budget reservation was released unspent (§A5)."""

    stage: str
    released: bool
    budget: EnergyBudgetStateObservation


class MotivationDriveEvaluatedObservation(FrozenContractModel):
    """One recovery-drive evaluation with its suppression state (§A6).

    ``pressure``/``status`` are read from the motivation owner right
    after ``evaluate``; ``candidate_*`` fields are populated only when a
    drive candidate was produced, ``skip_reason`` only when it was not.
    Cooldown and satisfaction windows are the suppression (inhibition)
    state the current single-drive system holds; the schema draft's
    competition/saturation fields have no code counterpart yet.
    """

    energy: float
    fatigue: float
    sleeping: bool
    blocked: bool
    pressure: float
    status: str
    skip_reason: Optional[str] = None
    candidate_id: Optional[str] = None
    goal: Optional[str] = None
    candidate_pressure: Optional[float] = None
    candidate_reason: Optional[str] = None
    cooldown_until: Optional[UTCDateTime] = None
    satisfaction_until: Optional[UTCDateTime] = None
    last_trigger_id: Optional[str] = None


class EventSalienceObservation(FrozenContractModel):
    """One admitted frame event's identity and raw salience (§A1)."""

    event_id: str
    salience: float = Field(ge=0.0, le=1.0)


class WorkspaceFrameAdmissionObservation(FrozenContractModel):
    """One frame-claim attempt inside the Event Workspace (§A1).

    ``admitted`` is ``False`` only when the claim found no perception
    writes available (``detail="no_perception"``); the trigger decision
    reason and cutoff sequence record why the claim was attempted.
    ``event_saliences`` itemizes the per-event salience of every event
    the claim admitted; ``max_event_salience`` stays as the aggregate
    the depth gate reads.
    """

    source_domain: Optional[str] = None
    trigger_reason: str
    cutoff_seq: int = Field(ge=0)
    event_count: int = Field(default=0, ge=0)
    max_event_salience: float = Field(default=0.0, ge=0.0)
    event_saliences: Tuple[EventSalienceObservation, ...] = ()
    admitted: bool
    detail: Optional[str] = None


class OrientationSnapshotObservation(FrozenContractModel):
    """One proposed orientation snapshot (§A2 output).

    Mirrors the ``OrientationSnapshot`` values the provider holds when
    the candidate is built; nearby actors are reduced to their IDs and
    affordances/unknown fields to counts to keep the record bounded.
    """

    revision: int = Field(ge=0)
    body_id: Optional[str] = None
    body_generation: Optional[int] = None
    location: Optional[str] = None
    location_source: str = "unknown"
    position: Optional[Tuple[float, float, float]] = None
    heading_degrees: Optional[float] = None
    active_channel_id: Optional[str] = None
    active_conversation_id: Optional[str] = None
    nearby_actor_ids: Tuple[str, ...] = ()
    activity_id: Optional[str] = None
    affordance_count: int = Field(default=0, ge=0)
    unknown_field_count: int = Field(default=0, ge=0)
    freshness: str = "unknown"


class DecisionRoutedObservation(FrozenContractModel):
    """One governed decision at the unified execution boundary (§A11).

    Records the host-bound scopes and intent types of the
    ``TurnDecision`` produced by ``govern_decision``; ``routed`` is the
    plan-sink accept result where the caller holds it and ``None``
    where routing happens after the emit point.
    """

    plan_id: str
    intent_types: Tuple[str, ...] = ()
    interaction_scope_kind: str
    source_domain: str
    response_domain: Optional[str] = None
    response_channel_id: Optional[str] = None
    response_conversation_id: Optional[str] = None
    memory_eligible: bool = True
    routed: Optional[bool] = None


__all__ = (
    "CognitiveBudgetReleasedObservation",
    "CognitiveBudgetSettledObservation",
    "DecisionRoutedObservation",
    "EmotionAppraisalInputObservation",
    "EmotionAppraisalObservation",
    "EmotionCandidateObservation",
    "EmotionDimensionChangeObservation",
    "EmotionEffectObservation",
    "EnergyBudgetStateObservation",
    "EventSalienceObservation",
    "MotivationDriveEvaluatedObservation",
    "OrientationSnapshotObservation",
    "WorkspaceFrameAdmissionObservation",
)
