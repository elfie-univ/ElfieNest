"""Atomic capability and target validation for complete decision plans."""

from __future__ import annotations

from datetime import timedelta
from functools import singledispatch
from typing import Optional

from elfie.brain.activity.system import ActivityStepKind
from elfie.brain.reasoning.context_types import EffectiveCapabilities
from elfie.brain.reasoning.decision_types import (
    CapabilityIntent,
    DecisionIntent,
    DecisionPlan,
    ExpressionIntent,
    MessageIntent,
    MotionIntent,
    NoOpIntent,
    PersistentActivityRequest,
    SpeechIntent,
)
from elfie.brain.workspace.contracts import ExternalExecutionDomain
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
    if body is None or ("*" not in body.actions and action not in body.actions):
        return False
    return True


def _registered_body_capability(
    capabilities: EffectiveCapabilities,
    capability_id: str,
) -> bool:
    """Accept the semantic aliases while preserving the existing Body vocabulary."""
    if _body_action_supported(capabilities, capability_id):
        return True
    aliases = {
        "body.speak": "speech.say",
        "body.move_to_anchor": "move_to_anchor",
        "body.emergency_stop": "system.emergency_stop",
    }
    alias = aliases.get(capability_id)
    if alias is not None and _body_action_supported(capabilities, alias):
        return True
    if capability_id == "body.expression":
        body = capabilities.current_body
        return body is not None and (
            "*" in body.actions
            or any(action.startswith("expression.") for action in body.actions)
        )
    return False


@singledispatch
def _validate_target(
    intent: DecisionIntent,
    capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    raise TypeError(type(intent).__name__)


@_validate_target.register
def _validate_capability(
    intent: CapabilityIntent,
    capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    if intent.category == "world":
        if intent.capability_id not in capabilities.world_capabilities:
            return ErrorInfo(
                code="world_capability_unavailable",
                message=f"world capability is not registered: {intent.capability_id}",
            )
        if intent.capability_id == "world.go_to":
            anchor_id = intent.arguments.get("anchor_id")
            if not isinstance(anchor_id, str) or not anchor_id.strip():
                return ErrorInfo(
                    code="invalid_capability_arguments",
                    message="world.go_to requires a non-blank anchor_id",
                )
            if not _body_action_supported(capabilities, "move_to_anchor"):
                return ErrorInfo(
                    code="motion_unavailable",
                    message="current body cannot execute semantic movement",
                )
        elif intent.capability_id == "world.observe":
            max_results = intent.arguments.get("max_results", 32)
            if (
                not isinstance(max_results, int)
                or isinstance(max_results, bool)
                or not 1 <= max_results <= 64
            ):
                return ErrorInfo(
                    code="invalid_capability_arguments",
                    message="world.observe max_results must be an integer from 1 to 64",
                )
            if not _body_action_supported(capabilities, "world.observe"):
                return ErrorInfo(
                    code="vision_unavailable",
                    message="current body cannot request semantic vision",
                )
        return None

    if not _registered_body_capability(capabilities, intent.capability_id):
        return ErrorInfo(
            code="body_capability_unavailable",
            message=f"body capability is not registered: {intent.capability_id}",
        )
    if intent.capability_id in {"body.speak", "speech.say"}:
        text = intent.arguments.get("text")
        if not isinstance(text, str) or not text.strip():
            return ErrorInfo(
                code="invalid_capability_arguments",
                message="body.speak requires a non-blank text",
            )
    elif intent.capability_id == "body.move_to_anchor":
        anchor_id = intent.arguments.get("anchor_id")
        if not isinstance(anchor_id, str) or not anchor_id.strip():
            return ErrorInfo(
                code="invalid_capability_arguments",
                message="body.move_to_anchor requires a non-blank anchor_id",
            )
    elif intent.capability_id == "body.expression":
        kind = intent.arguments.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            return ErrorInfo(
                code="invalid_capability_arguments",
                message="body.expression requires a non-blank kind",
            )
        if not _registered_body_capability(capabilities, f"expression.{kind}"):
            body = capabilities.current_body
            if body is None or "body.expression" not in body.actions:
                return ErrorInfo(
                    code="expression_unavailable",
                    message=f"expression is not registered: {kind}",
                )
    return None


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
    action = "move_to_anchor" if intent.target else intent.motion
    if _body_action_supported(capabilities, action):
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
def _validate_noop(
    _intent: NoOpIntent,
    _capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    return None


@_validate_target.register
def _validate_activity(
    intent: PersistentActivityRequest,
    capabilities: EffectiveCapabilities,
) -> Optional[ErrorInfo]:
    """Check every persisted external step against current capabilities."""
    for step in intent.draft.steps:
        scope = step.scope
        if step.kind is ActivityStepKind.INTERNAL:
            continue
        if scope is None:
            return ErrorInfo(
                code="activity_scope_missing",
                message="external Activity step has no execution scope",
            )
        if scope.external_domain is ExternalExecutionDomain.COMMUNICATION:
            channel = next(
                (
                    candidate
                    for candidate in capabilities.connected_channels
                    if candidate.channel_id == scope.channel_id
                ),
                None,
            )
            if channel is None:
                return ErrorInfo(
                    code="activity_channel_unavailable",
                    message="Activity communication channel is not connected",
                )
            if scope.conversation_id not in channel.authorized_conversation_ids:
                return ErrorInfo(
                    code="activity_conversation_unauthorized",
                    message="Activity conversation target is not authorized",
                )
        elif scope.external_domain is ExternalExecutionDomain.NERVOUS_SYSTEM:
            body = capabilities.current_body
            if body is None or (
                body.body_id != scope.body_id
                or body.body_generation != scope.body_generation
            ):
                return ErrorInfo(
                    code="activity_body_unavailable",
                    message="Activity body target is no longer current",
                )
            if "*" not in body.actions and step.operation not in body.actions:
                return ErrorInfo(
                    code="activity_operation_unavailable",
                    message="Activity body operation is not currently supported",
                )
    return None


__all__ = ("validate_plan_for_execution",)
