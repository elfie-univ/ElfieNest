"""Atomic capability and target validation for complete decision plans."""

from __future__ import annotations

from datetime import timedelta
from functools import singledispatch
from typing import Optional

from elfie.brain.context_types import EffectiveCapabilities
from elfie.brain.decision_types import (
    DecisionIntent,
    DecisionPlan,
    ExpressionIntent,
    InternalIntent,
    MessageIntent,
    MotionIntent,
    NoOpIntent,
    SpeechIntent,
)
from elfie.brain.perception_types import EmbodiedScope
from elfie.message_types import ErrorInfo, UTCDateTime


def validate_plan_for_execution(
    plan: DecisionPlan,
    capabilities: EffectiveCapabilities,
    *,
    now: UTCDateTime,
    max_intents: int,
    max_schedule_horizon: timedelta,
    expected_body_id: str | None = None,
    expected_body_generation: int | None = None,
) -> Optional[ErrorInfo]:
    """Return one rejection only after checking every intent without side effects."""
    if plan.deadline < now:
        return ErrorInfo(code="plan_expired", message="decision plan deadline expired")
    if plan.deadline > now + max_schedule_horizon:
        return ErrorInfo(
            code="schedule_horizon_exceeded",
            message="decision plan exceeds the maximum schedule horizon",
        )
    if plan.capability_revision != capabilities.revision:
        return ErrorInfo(
            code="stale_capability_revision",
            message="decision plan capability revision is stale",
        )
    if expected_body_id is not None:
        body = capabilities.current_body
        if body is None or body.body_id != expected_body_id:
            return ErrorInfo(
                code="stale_body_generation",
                message="decision targets a body that is no longer current",
            )
        if (
            expected_body_generation is not None
            and body.body_generation != expected_body_generation
        ):
            return ErrorInfo(
                code="stale_body_generation",
                message="decision targets an obsolete body generation",
            )
    if len(plan.intents) > max_intents:
        return ErrorInfo(
            code="intent_capacity_exceeded",
            message=f"decision plan exceeds {max_intents} intents",
        )
    sequence_ordinals: set[tuple[str, int]] = set()
    for intent in plan.intents:
        if intent.deadline < now:
            return ErrorInfo(code="intent_expired", message="intent deadline expired")
        target_error = _validate_target(intent, capabilities)
        if target_error is not None:
            return target_error
        if isinstance(intent, MessageIntent) and intent.sequence_id is not None:
            sequence_key = (intent.sequence_id, intent.ordinal or 0)
            if sequence_key in sequence_ordinals:
                return ErrorInfo(
                    code="duplicate_message_ordinal",
                    message="message sequence ordinals must be unique",
                )
            sequence_ordinals.add(sequence_key)
    return None


def _body_action_supported(capabilities: EffectiveCapabilities, action: str) -> bool:
    body = capabilities.current_body
    return body is not None and ("*" in body.actions or action in body.actions)


@singledispatch
def _validate_target(
    intent: DecisionIntent,
    capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    raise TypeError(type(intent).__name__)


@_validate_target.register
def _validate_speech(
    _intent: SpeechIntent,
    capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    if _body_action_supported(capabilities, "speech.say"):
        return None
    return ErrorInfo(code="speech_unavailable", message="current body cannot speak")


@_validate_target.register
def _validate_motion(
    intent: MotionIntent,
    capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    if _body_action_supported(capabilities, intent.motion):
        return None
    return ErrorInfo(code="motion_unavailable", message="current body cannot move")


@_validate_target.register
def _validate_expression(
    intent: ExpressionIntent,
    capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    if _body_action_supported(capabilities, f"expression.{intent.expression}"):
        return None
    return ErrorInfo(code="expression_unavailable", message="expression unavailable")


@_validate_target.register
def _validate_message(
    intent: MessageIntent,
    capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    channel = next(
        (
            candidate
            for candidate in capabilities.connected_channels
            if candidate.channel_id == intent.channel_id
        ),
        None,
    )
    if channel is None:
        return ErrorInfo(code="channel_unavailable", message="channel is not connected")
    if "*" not in channel.content_kinds and "text" not in channel.content_kinds:
        return ErrorInfo(code="text_unavailable", message="channel cannot send text")
    if intent.conversation_id not in channel.authorized_conversation_ids:
        return ErrorInfo(
            code="conversation_unauthorized",
            message="conversation target was not authorized by trusted inbound context",
        )
    return None


@_validate_target.register
def _validate_internal(
    _intent: InternalIntent,
    _capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    return None


@_validate_target.register
def _validate_noop(
    _intent: NoOpIntent,
    _capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    return None


__all__ = ("validate_plan_for_execution",)
