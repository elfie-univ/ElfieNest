"""Translate physical decision intents into typed Body commands."""

from __future__ import annotations

from datetime import timedelta
from functools import singledispatch
from threading import Lock
from typing import Callable, Dict, Optional, Tuple, TypedDict
from uuid import uuid4

from elfie.body.contracts import (
    BodyCommand,
    BodyId,
    CommandStatus,
    EmergencyStopCommand,
    ExpressionCommand,
    MotionCommand,
    SpeechCommand,
)
from elfie.body.port import BodyPort
from elfie.brain.reasoning.decision_types import (
    DecisionIntent,
    DecisionPlan,
    ExpressionIntent,
    MotionIntent,
    SpeechIntent,
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
        command = _build_command(
            intent,
            plan,
            BodyId(body.body_id),
            body_generation,
            body.capabilities.revision,
            issued_at,
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
def _speech_command(
    intent: SpeechIntent,
    plan: DecisionPlan,
    body_id: BodyId,
    body_generation: int,
    capability_revision: int,
    issued_at: UTCDateTime,
) -> SpeechCommand:
    return SpeechCommand(
        command_type="speech",
        text=intent.text,
        **_identity(
            plan, intent, body_id, body_generation, capability_revision, issued_at
        ),
    )


@_build_command.register
def _motion_command(
    intent: MotionIntent,
    plan: DecisionPlan,
    body_id: BodyId,
    body_generation: int,
    capability_revision: int,
    issued_at: UTCDateTime,
) -> MotionCommand:
    return MotionCommand(
        command_type="motion",
        kind=intent.motion,
        target=intent.target,
        **_identity(
            plan, intent, body_id, body_generation, capability_revision, issued_at
        ),
    )


@_build_command.register
def _expression_command(
    intent: ExpressionIntent,
    plan: DecisionPlan,
    body_id: BodyId,
    body_generation: int,
    capability_revision: int,
    issued_at: UTCDateTime,
) -> ExpressionCommand:
    return ExpressionCommand(
        command_type="expression",
        kind=intent.expression,
        intensity=intent.intensity,
        **_identity(
            plan, intent, body_id, body_generation, capability_revision, issued_at
        ),
    )


__all__ = ("NervousSystemIntentExecutor",)
