"""Immediate Body reflex execution and normalized perception facts."""

from __future__ import annotations

from datetime import timedelta
from threading import Lock
from typing import Final, Mapping, Optional, Tuple

from elfie.body.contracts import (
    BodySensorEvent,
    CommandReceipt,
    CommandStatus,
    EmergencyStopCommand,
    TactileImpact,
)
from elfie.body.port import BodyPort
from elfie.brain.workspace.contracts import (
    ExecutionStatus,
    PerceptionEvent,
    PerceptionStateUpdate,
    PerceptionWrite,
    PhysicalModality,
    PhysicalPayload,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    CommandId,
    ElfieId,
    EventId,
    IntentId,
    MessageMeta,
    Priority,
    TraceId,
    TurnId,
)

DANGER_FORCE_NEWTONS: Final = 15.0
_STATUS_MAP: Final[Mapping[CommandStatus, ExecutionStatus]] = {
    CommandStatus.ACCEPTED: ExecutionStatus.ACCEPTED,
    CommandStatus.STARTED: ExecutionStatus.STARTED,
    CommandStatus.COMPLETED: ExecutionStatus.COMPLETED,
    CommandStatus.REJECTED: ExecutionStatus.REJECTED,
    CommandStatus.FAILED: ExecutionStatus.FAILED,
    CommandStatus.INTERRUPTED: ExecutionStatus.INTERRUPTED,
    CommandStatus.TIMED_OUT: ExecutionStatus.TIMED_OUT,
}


class BodyReflexController:
    """Own the current reflex target and urgent revision counter."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        body_port: Optional[BodyPort] = None,
        body_generation: int | None = None,
    ) -> None:
        self._elfie_id = elfie_id
        self._body_port = body_port
        self._body_generation: int | None = (
            (body_generation or 1) if body_port is not None else None
        )
        self._urgent_revision = 0
        self._last_command: Optional[EmergencyStopCommand] = None
        self._lock = Lock()

    @property
    def urgent_revision(self) -> int:
        with self._lock:
            return self._urgent_revision

    @property
    def last_command(self) -> Optional[EmergencyStopCommand]:
        with self._lock:
            return self._last_command

    def bind_body_port(
        self,
        body_port: Optional[BodyPort],
        *,
        body_generation: int | None = None,
    ) -> None:
        with self._lock:
            self._body_port = body_port
            self._body_generation = (
                (body_generation or 1) if body_port is not None else None
            )

    def handle(
        self,
        event: BodySensorEvent,
        impact: TactileImpact,
    ) -> Tuple[PerceptionWrite, ...]:
        """Prepare under lock, execute outside it, then describe the result."""
        with self._lock:
            self._urgent_revision += 1
            revision = self._urgent_revision
            body = self._body_port
            command = self._build_command(event, impact, body)
            self._last_command = command
        base_writes = (
            self._reflex_fact(event, impact, revision),
            self._urgent_state(event, revision),
        )
        if body is None or command is None:
            return base_writes
        receipts = body.execute(command, now=event.received_at)
        terminal = next(
            (
                receipt
                for receipt in reversed(receipts)
                if receipt.status not in {CommandStatus.ACCEPTED, CommandStatus.STARTED}
            ),
            None,
        )
        if terminal is None:
            return base_writes
        return base_writes + (self._receipt_event(event, terminal),)

    def _build_command(
        self,
        event: BodySensorEvent,
        impact: TactileImpact,
        body: Optional[BodyPort],
    ) -> Optional[EmergencyStopCommand]:
        if body is None:
            return None
        return EmergencyStopCommand(
            command_type="emergency_stop",
            command_id=CommandId(f"reflex-command:{event.event_id}"),
            turn_id=TurnId(f"reflex-turn:{event.event_id}"),
            intent_id=IntentId(f"reflex-intent:{event.event_id}"),
            body_id=event.body_id,
            issued_at=event.received_at,
            deadline=event.received_at + timedelta(seconds=1),
            capability_revision=body.capabilities.revision,
            body_generation=self._body_generation or event.body_generation,
            reason=f"dangerous tactile impact at {impact.location}",
        )

    def _reflex_fact(
        self,
        event: BodySensorEvent,
        impact: TactileImpact,
        revision: int,
    ) -> PerceptionEvent:
        return PerceptionEvent(
            meta=self._derived_meta(event, "reflex", Priority.CRITICAL),
            payload=PhysicalPayload(
                type="physical",
                body_id=str(event.body_id),
                body_generation=event.body_generation,
                modality=PhysicalModality.TOUCH,
                content=(
                    "reflex emergency_stop; "
                    f"force_newtons={impact.force_newtons:g}; "
                    f"urgent_revision={revision}"
                ),
            ),
            salience=1.0,
        )

    def _urgent_state(
        self,
        event: BodySensorEvent,
        revision: int,
    ) -> PerceptionStateUpdate:
        return PerceptionStateUpdate(
            meta=self._derived_meta(event, "urgent-revision", Priority.CRITICAL),
            body_id=str(event.body_id),
            body_generation=event.body_generation,
            state_key=f"body:{event.body_id}:nervous:urgent_revision",
            revision=revision,
            value=revision,
        )

    def _receipt_event(
        self,
        cause: BodySensorEvent,
        receipt: CommandReceipt,
    ) -> PerceptionEvent:
        return PerceptionEvent(
            meta=MessageMeta(
                event_id=receipt.receipt_id,
                elfie_id=self._elfie_id,
                source=self._source(),
                occurred_at=receipt.occurred_at,
                received_at=receipt.occurred_at,
                trace_id=TraceId(f"body:{cause.event_id}"),
                causation_id=cause.event_id,
                priority=Priority.CRITICAL,
            ),
            payload=PhysicalPayload(
                type="physical",
                body_id=str(cause.body_id),
                body_generation=receipt.body_generation,
                modality=PhysicalModality.PROPRIOCEPTION,
                content=(
                    f"action={receipt.command_id}; intent={receipt.intent_id}; "
                    f"status={_STATUS_MAP[receipt.status].value}"
                    + (
                        f"; reason={receipt.error.message}"
                        if receipt.error is not None
                        else ""
                    )
                ),
            ),
            salience=1.0,
        )

    def _derived_meta(
        self,
        event: BodySensorEvent,
        suffix: str,
        priority: Priority,
    ) -> MessageMeta:
        return MessageMeta(
            event_id=EventId(f"{event.event_id}:{suffix}"),
            elfie_id=self._elfie_id,
            source=self._source(),
            occurred_at=event.received_at,
            received_at=event.received_at,
            trace_id=TraceId(f"body:{event.event_id}"),
            causation_id=event.event_id,
            priority=priority,
        )

    def _source(self) -> ActorRef:
        return ActorRef(
            actor_id=ActorId(f"{self._elfie_id}:nervous-system"),
            source_kind="nervous_system",
        )


__all__ = ("BodyReflexController", "DANGER_FORCE_NEWTONS")
