"""Translate physical decision intents into typed Body commands."""

from __future__ import annotations

from datetime import timedelta
from functools import singledispatch
from threading import Lock
from typing import Callable, Dict, Mapping, Optional, Tuple, TypedDict
from uuid import uuid4

from elfie.body.contracts import (
    BodyCommand,
    BodyId,
    CapabilityCommand,
    CommandStatus,
    EmergencyStopCommand,
    ExpressionCommand,
    MotionCommand,
    ObservationCommand,
    SpeechCommand,
)
from elfie.body.port import BodyPort
from elfie.brain.reasoning.decision_types import (
    CapabilityIntent,
    DecisionIntent,
    DecisionPlan,
)
from elfie.brain.reasoning.execution_types import IntentExecutionResult
from elfie.message_types import (
    CommandId,
    ErrorInfo,
    IntentId,
    TurnId,
    UTCDateTime,
)
from elfie.nervous_system.nervous_system import NervousSystem


class NervousSystemIntentExecutor:
    """Execute speech, motion, and expression through the active Body port."""

    def __init__(
        self,
        *,
        nervous_system: NervousSystem,
        current_body: Callable[[], Optional[BodyPort]],
        current_body_generation: Callable[[], int | None] | None = None,
        clock: Callable[[], UTCDateTime],
    ) -> None:
        self._nervous_system = nervous_system
        self._current_body = current_body
        self._current_body_generation = current_body_generation or (lambda: 1)
        self._clock = clock
        self._commands: Dict[
            tuple[TurnId, IntentId], Tuple[BodyPort, int, BodyCommand]
        ] = {}
        self._lock = Lock()
        self._interrupt_count = 0

    @property
    def publishes_embodied_outcome(self) -> bool:
        """Expose whether NervousSystem owns the Body feedback publication."""
        return self._nervous_system.perception_configured

    def execute(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> IntentExecutionResult:
        body = self._current_body()
        if body is None:
            return IntentExecutionResult.failed(
                ErrorInfo(code="body_unavailable", message="no current body")
            )
        issued_at = self._clock()
        body_generation = self._current_body_generation() or 1
        try:
            command = _build_command(
                intent,
                plan,
                BodyId(body.body_id),
                body_generation,
                body.capabilities.revision,
                issued_at,
            )
        except (TypeError, ValueError) as error:
            return IntentExecutionResult.failed(
                ErrorInfo(
                    code="invalid_capability_arguments",
                    message=str(error) or "capability arguments are invalid",
                )
            )
        with self._lock:
            self._commands[(plan.turn_id, intent.intent_id)] = (
                body,
                body_generation,
                command,
            )
        receipts = self._nervous_system.execute_body_command(
            body,
            command,
            now=issued_at,
        )
        terminal = receipts[-1]
        if (
            self._current_body() is not body
            or (self._current_body_generation() or 1) != body_generation
            or terminal.body_generation != body_generation
        ):
            return IntentExecutionResult.failed(
                ErrorInfo(
                    code="stale_body_generation",
                    message="body changed before the physical command completed",
                )
            )
        if terminal.status is CommandStatus.COMPLETED:
            return IntentExecutionResult.completed()
        if terminal.status is CommandStatus.INTERRUPTED:
            return IntentExecutionResult.interrupted(
                terminal.error.message if terminal.error is not None else "interrupted"
            )
        if terminal.status is CommandStatus.TIMED_OUT:
            return IntentExecutionResult.timed_out(
                terminal.error.message if terminal.error is not None else "timed out"
            )
        return IntentExecutionResult.failed(
            terminal.error
            or ErrorInfo(code=terminal.status.value, message=terminal.status.value)
        )

    def interrupt(self, turn_id: TurnId, intent_id: IntentId, reason: str) -> None:
        with self._lock:
            original = self._commands.get((turn_id, intent_id))
        if original is None:
            return
        body, body_generation, command = original
        now = self._clock()
        stop = EmergencyStopCommand(
            command_type="emergency_stop",
            command_id=CommandId(f"emergency_{uuid4().hex}"),
            turn_id=turn_id,
            intent_id=intent_id,
            body_id=command.body_id,
            issued_at=now,
            deadline=now + timedelta(seconds=1),
            capability_revision=body.capabilities.revision,
            body_generation=body_generation,
            reason=reason,
        )
        self._nervous_system.execute_body_command(body, stop, now=now)
        with self._lock:
            self._interrupt_count += 1

    @property
    def interrupt_count(self) -> int:
        with self._lock:
            return self._interrupt_count


@singledispatch
def _build_command(
    intent: DecisionIntent,
    _plan: DecisionPlan,
    _body_id: BodyId,
    _body_generation: int,
    _capability_revision: int,
    _issued_at: UTCDateTime,
) -> BodyCommand:
    raise TypeError(type(intent).__name__)


class _CommandIdentity(TypedDict):
    command_id: CommandId
    turn_id: TurnId
    intent_id: IntentId
    body_id: BodyId
    body_generation: int
    issued_at: UTCDateTime
    deadline: UTCDateTime
    capability_revision: int


def _identity(
    plan: DecisionPlan,
    intent: DecisionIntent,
    body_id: BodyId,
    body_generation: int,
    capability_revision: int,
    issued_at: UTCDateTime,
) -> _CommandIdentity:
    return {
        "command_id": CommandId(f"command_{uuid4().hex}"),
        "turn_id": plan.turn_id,
        "intent_id": intent.intent_id,
        "body_id": body_id,
        "body_generation": body_generation,
        "issued_at": issued_at,
        "deadline": intent.deadline,
        "capability_revision": capability_revision,
    }


@_build_command.register
def _capability_command(
    intent: CapabilityIntent,
    plan: DecisionPlan,
    body_id: BodyId,
    body_generation: int,
    capability_revision: int,
    issued_at: UTCDateTime,
) -> BodyCommand:
    """Lower one registered semantic call into the current Body contract."""
    capability_id = intent.capability_id
    arguments = intent.arguments
    if intent.category == "world":
        if capability_id == "move.to":
            return MotionCommand(
                command_type="motion",
                kind="move_to_anchor",
                target=_argument_text(arguments, "anchor_id"),
                **_identity(
                    plan,
                    intent,
                    body_id,
                    body_generation,
                    capability_revision,
                    issued_at,
                ),
            )
        if capability_id == "observe":
            return ObservationCommand(
                command_type="observation",
                observation_id=_argument_text(
                    arguments,
                    "observation_id",
                    f"observation-{intent.intent_id}",
                ),
                max_results=_argument_count(arguments, "max_results", 32),
                **_identity(
                    plan,
                    intent,
                    body_id,
                    body_generation,
                    capability_revision,
                    issued_at,
                ),
            )
        return CapabilityCommand(
            command_type="capability",
            capability_id=capability_id,
            arguments=dict(arguments),
            **_identity(
                plan,
                intent,
                body_id,
                body_generation,
                capability_revision,
                issued_at,
            ),
        )

    if capability_id in {"speak", "body.speak", "speech.say"}:
        return SpeechCommand(
            command_type="speech",
            text=_argument_text(arguments, "text"),
            **_identity(
                plan,
                intent,
                body_id,
                body_generation,
                capability_revision,
                issued_at,
            ),
        )
    if capability_id in {"body.move_to_anchor", "move_to_anchor"}:
        return MotionCommand(
            command_type="motion",
            kind="move_to_anchor",
            target=_argument_text(arguments, "anchor_id"),
            **_identity(
                plan,
                intent,
                body_id,
                body_generation,
                capability_revision,
                issued_at,
            ),
        )
    if capability_id in {
        "emergency_stop",
        "body.emergency_stop",
        "system.emergency_stop",
    }:
        return EmergencyStopCommand(
            command_type="emergency_stop",
            reason=_argument_text(arguments, "reason", "brain_request"),
            **_identity(
                plan,
                intent,
                body_id,
                body_generation,
                capability_revision,
                issued_at,
            ),
        )
    if capability_id == "expression":
        return ExpressionCommand(
            command_type="expression",
            kind=_argument_text(arguments, "kind"),
            intensity=_argument_ratio(arguments, "intensity", 1.0),
            **_identity(
                plan,
                intent,
                body_id,
                body_generation,
                capability_revision,
                issued_at,
            ),
        )
    if capability_id.startswith("expression."):
        return ExpressionCommand(
            command_type="expression",
            kind=capability_id.removeprefix("expression."),
            intensity=_argument_ratio(arguments, "intensity", 1.0),
            **_identity(
                plan,
                intent,
                body_id,
                body_generation,
                capability_revision,
                issued_at,
            ),
        )
    if capability_id.startswith("gesture."):
        return MotionCommand(
            command_type="motion",
            kind=capability_id,
            **_identity(
                plan,
                intent,
                body_id,
                body_generation,
                capability_revision,
                issued_at,
            ),
        )
    return CapabilityCommand(
        command_type="capability",
        capability_id=capability_id,
        arguments=dict(arguments),
        **_identity(
            plan,
            intent,
            body_id,
            body_generation,
            capability_revision,
            issued_at,
        ),
    )


def _argument_text(
    arguments: Mapping[str, object],
    name: str,
    default: str | None = None,
) -> str:
    value = arguments.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"capability argument '{name}' must be non-blank text")
    return value


def _argument_count(arguments: Mapping[str, object], name: str, default: int) -> int:
    value = arguments.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 64:
        raise ValueError(
            f"capability argument '{name}' must be an integer from 1 to 64"
        )
    return value


def _argument_ratio(
    arguments: Mapping[str, object], name: str, default: float
) -> float:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"capability argument '{name}' must be a number from 0 to 1")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise ValueError(f"capability argument '{name}' must be a number from 0 to 1")
    return normalized


__all__ = ("NervousSystemIntentExecutor",)
