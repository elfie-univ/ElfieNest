"""Atomic capability and target validation for complete decision plans."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from functools import singledispatch
from typing import Any, Optional

from elfie.brain.activity.system import ActivityStepKind
from elfie.brain.reasoning.context_types import (
    CapabilityDescriptor,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.decision_types import (
    CapabilityIntent,
    DecisionIntent,
    DecisionPlan,
    MessageIntent,
    NoOpIntent,
    PersistentActivityRequest,
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
    if body is None:
        return False
    registered = (
        frozenset(item.capability_id for item in body.action_catalog)
        if body.action_catalog
        else frozenset(body.actions)
    )
    if "*" in registered or action in registered:
        return True
    return False


def _body_input_supported(capabilities: EffectiveCapabilities, sensor: str) -> bool:
    """Check a Body input against its registered catalog before legacy sets."""
    body = capabilities.current_body
    if body is None:
        return False
    registered = (
        frozenset(item.capability_id for item in body.input_catalog)
        if body.input_catalog
        else frozenset(body.sensors)
    )
    return "*" in registered or sensor in registered


def _find_capability(
    capabilities: EffectiveCapabilities,
    capability_id: str,
    category: str,
) -> CapabilityDescriptor | None:
    descriptor = next(
        (
            item
            for item in capabilities.capability_catalog
            if item.capability_id == capability_id and item.category == category
        ),
        None,
    )
    if descriptor is not None:
        return descriptor
    body = capabilities.current_body
    if category == "body" and body is not None and not body.action_catalog:
        if "*" in body.actions or capability_id in body.actions:
            return CapabilityDescriptor(
                capability_id=capability_id,
                category="body",
            )
    if (
        category == "world"
        and not any(
            item.category == "world" for item in capabilities.capability_catalog
        )
        and capability_id in capabilities.world_capabilities
    ):
        return CapabilityDescriptor(
            capability_id=capability_id,
            category="world",
        )
    return None


def _validate_arguments(
    arguments: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> Optional[ErrorInfo]:
    """Validate the small JSON-Schema subset used by capability catalogs."""
    required = schema.get("required", ())
    if isinstance(required, (list, tuple)):
        for name in required:
            if isinstance(name, str) and name not in arguments:
                return ErrorInfo(
                    code="invalid_capability_arguments",
                    message=f"capability requires argument '{name}'",
                )
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        properties = {}
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            return ErrorInfo(
                code="invalid_capability_arguments",
                message=f"unknown capability argument: {unknown[0]}",
            )
    for name, value in arguments.items():
        definition = properties.get(name)
        if not isinstance(definition, Mapping):
            continue
        expected_type = definition.get("type")
        if expected_type == "string":
            if not isinstance(value, str):
                return ErrorInfo(
                    code="invalid_capability_arguments",
                    message=f"capability argument '{name}' must be a string",
                )
            min_length = definition.get("minLength")
            if isinstance(min_length, int) and len(value) < min_length:
                return ErrorInfo(
                    code="invalid_capability_arguments",
                    message=f"capability argument '{name}' is too short",
                )
        elif expected_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                return ErrorInfo(
                    code="invalid_capability_arguments",
                    message=f"capability argument '{name}' must be an integer",
                )
        elif expected_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return ErrorInfo(
                    code="invalid_capability_arguments",
                    message=f"capability argument '{name}' must be a number",
                )
        elif expected_type == "boolean" and not isinstance(value, bool):
            return ErrorInfo(
                code="invalid_capability_arguments",
                message=f"capability argument '{name}' must be a boolean",
            )
        enum = definition.get("enum")
        if isinstance(enum, (list, tuple)) and value not in enum:
            return ErrorInfo(
                code="invalid_capability_arguments",
                message=f"capability argument '{name}' is not registered",
            )
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = definition.get("minimum")
            maximum = definition.get("maximum")
            if isinstance(minimum, (int, float)) and value < minimum:
                return ErrorInfo(
                    code="invalid_capability_arguments",
                    message=f"capability argument '{name}' is below minimum",
                )
            if isinstance(maximum, (int, float)) and value > maximum:
                return ErrorInfo(
                    code="invalid_capability_arguments",
                    message=f"capability argument '{name}' is above maximum",
                )
    return None


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
    descriptor = _find_capability(capabilities, intent.capability_id, intent.category)
    if descriptor is None:
        unavailable_code = (
            "world_capability_unavailable"
            if intent.category == "world"
            else "body_capability_unavailable"
        )
        return ErrorInfo(
            code=unavailable_code,
            message=f"{intent.category} capability is not registered: {intent.capability_id}",
        )
    argument_error = _validate_arguments(intent.arguments, descriptor.argument_schema)
    if argument_error is not None:
        return argument_error
    if intent.category == "world" and intent.capability_id == "move.to":
        if not (
            _body_action_supported(capabilities, "move.forward")
            or _body_action_supported(capabilities, "move_to_anchor")
        ):
            return ErrorInfo(
                code="motion_unavailable",
                message="current body cannot execute semantic movement",
            )
    if intent.category == "world" and intent.capability_id == "observe":
        if not _body_input_supported(capabilities, "vision"):
            return ErrorInfo(
                code="vision_unavailable",
                message="current body has no vision input",
            )
    return None


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
            if not _body_action_supported(capabilities, step.operation):
                return ErrorInfo(
                    code="activity_operation_unavailable",
                    message="Activity body operation is not currently supported",
                )
    return None


__all__ = ("validate_plan_for_execution",)
