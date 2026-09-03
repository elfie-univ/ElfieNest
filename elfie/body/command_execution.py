"""Shared typed command validation and lifecycle receipt creation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, List, Mapping, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from typing_extensions import TypeAlias

from elfie.body.capabilities import BodyCapabilities
from elfie.body.contracts import (
    BodyCommand,
    BodyId,
    CapabilityCommand,
    CommandReceipt,
    CommandStatus,
    ExpressionCommand,
    MotionCommand,
    ObservationCommand,
    SpeechCommand,
)
from elfie.message_types import (
    CommandId,
    ErrorInfo,
    EventId,
    IntentId,
    TurnId,
    UTCDateTime,
)

WireScalar: TypeAlias = Union[str, int, float, bool, datetime, None]
WireValue: TypeAlias = Union[WireScalar, List["WireValue"], dict[str, "WireValue"]]

_COMMAND_ADAPTER: TypeAdapter[BodyCommand] = TypeAdapter(BodyCommand)


class _CommandIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    command_id: CommandId
    turn_id: TurnId
    intent_id: IntentId
    body_id: BodyId
    capability_revision: int
    body_generation: Annotated[int, Field(strict=True, ge=1)] = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def command_capability(command: BodyCommand) -> str:
    if isinstance(command, SpeechCommand):
        return "speech.say"
    if isinstance(command, MotionCommand):
        return "move_to_anchor" if command.target else command.kind
    if isinstance(command, ObservationCommand):
        return "world.observe"
    if isinstance(command, CapabilityCommand):
        return command.capability_id
    if isinstance(command, ExpressionCommand):
        return f"expression.{command.kind}"
    return "system.emergency_stop"


def validate_command(
    command: BodyCommand,
    *,
    expected_body_id: str,
    capabilities: BodyCapabilities,
    connected: bool,
    now: UTCDateTime,
) -> CommandReceipt | None:
    if str(command.body_id) != expected_body_id:
        return rejected(
            command, "body_mismatch", "command targets a different body", now
        )
    if not connected:
        return rejected(command, "body_disconnected", "body is not connected", now)
    if command.deadline < now:
        return rejected(
            command, "deadline_expired", "command deadline has expired", now
        )
    if command.capability_revision != capabilities.revision:
        return rejected(
            command,
            "stale_capability_revision",
            "command capability revision is stale",
            now,
        )
    if not capabilities.supports_action(command_capability(command)):
        return rejected(
            command,
            "unsupported_capability",
            f"body does not support {command_capability(command)}",
            now,
        )
    return None


def lifecycle_receipts(
    command: BodyCommand,
    *,
    occurred_at: UTCDateTime,
    terminal: CommandReceipt | None = None,
) -> tuple[CommandReceipt, ...]:
    accepted = CommandReceipt.for_status(
        command,
        CommandStatus.ACCEPTED,
        occurred_at=occurred_at,
    )
    started = CommandReceipt.for_status(
        command,
        CommandStatus.STARTED,
        occurred_at=occurred_at,
    )
    completed = terminal or CommandReceipt.completed(command, occurred_at=occurred_at)
    return accepted, started, completed


def rejected(
    command: BodyCommand,
    code: str,
    message: str,
    occurred_at: UTCDateTime,
) -> CommandReceipt:
    return CommandReceipt.for_status(
        command,
        CommandStatus.REJECTED,
        occurred_at=occurred_at,
        error=ErrorInfo(code=code, message=message),
    )


def parse_wire_command(
    payload: Mapping[str, WireValue],
    *,
    occurred_at: UTCDateTime,
) -> BodyCommand | CommandReceipt:
    try:
        return _COMMAND_ADAPTER.validate_python(dict(payload))
    except ValidationError as validation_error:
        try:
            identity = _CommandIdentity.model_validate(dict(payload))
        except ValidationError:
            revision = payload.get("capability_revision")
            body_generation_value = payload.get("body_generation")
            body_generation = (
                body_generation_value
                if isinstance(body_generation_value, int)
                and not isinstance(body_generation_value, bool)
                and body_generation_value >= 1
                else 1
            )
            identity = _CommandIdentity(
                command_id=CommandId(
                    _fallback_identifier(payload.get("command_id"), "invalid-command")
                ),
                turn_id=TurnId(
                    _fallback_identifier(payload.get("turn_id"), "invalid-turn")
                ),
                intent_id=IntentId(
                    _fallback_identifier(payload.get("intent_id"), "invalid-intent")
                ),
                body_id=BodyId(
                    _fallback_identifier(payload.get("body_id"), "invalid-body")
                ),
                capability_revision=(
                    revision
                    if isinstance(revision, int)
                    and not isinstance(revision, bool)
                    and revision >= 1
                    else 1
                ),
                body_generation=body_generation,
            )
        return CommandReceipt(
            receipt_id=EventId(f"receipt_{uuid4().hex}"),
            command_id=identity.command_id,
            turn_id=identity.turn_id,
            intent_id=identity.intent_id,
            body_id=identity.body_id,
            status=CommandStatus.REJECTED,
            occurred_at=occurred_at,
            capability_revision=identity.capability_revision,
            body_generation=identity.body_generation,
            error=ErrorInfo(
                code="bad_payload",
                message="command payload failed strict validation",
                retryable=False,
                causes=(
                    ErrorInfo(
                        code="pydantic_validation_error",
                        message=str(validation_error),
                    ),
                ),
            ),
        )


def _fallback_identifier(value: WireValue, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return fallback
