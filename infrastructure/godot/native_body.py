"""Godot 中精灵本体的 BodyPort 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Mapping, Optional, Tuple

from elfie.body.capabilities import BodyCapabilities
from elfie.body.command_execution import (
    WireValue,
    parse_wire_command,
    rejected,
    utc_now,
    validate_command,
)
from elfie.body.contracts import (
    BodyCommand,
    BodyId,
    BodySensorEvent,
    BodySnapshot,
    CommandReceipt,
    CommandStatus,
    EmergencyStopCommand,
    ExpressionCommand,
    MotionCommand,
    SpeechCommand,
)
from elfie.body.types import (
    BodyDescriptor,
    BodyMode,
)
from elfie.message_types import ErrorInfo, EventId
from infrastructure.godot.body_sensors import NativeSensors
from infrastructure.godot.body_transport import GodotTransport, RuntimeIntentPayload


class NativeBody:
    """连接精灵本体与现有 Godot API，不实现大脑或运动算法。"""

    def __init__(
        self,
        body_id: str,
        transport: GodotTransport,
        capabilities: Optional[BodyCapabilities] = None,
    ):
        self.body_id = body_id
        self.transport = transport
        self.capabilities = capabilities or BodyCapabilities(
            sensors=frozenset({"hearing", "proprioception"}),
            actions=frozenset({"*"}),
        )
        self.sensors = NativeSensors(body_id)
        self.connected = False
        self._last_receipt: CommandReceipt | None = None

    def connect(self) -> None:
        if self.connected:
            return
        self.transport.connect(self.sensors.receive)
        self.connected = True

    def disconnect(self) -> None:
        if not self.connected:
            return
        self.transport.disconnect(self.sensors.receive)
        self.connected = False

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=BodyId(self.body_id),
            mode=BodyMode.NATIVE,
            display_name="Native Godot Body",
            capabilities=self.capabilities,
        )

    def read_sensor_events(self) -> List[BodySensorEvent]:
        if not self.connected:
            return []
        return self.sensors.read_sensor_events()

    def execute(
        self,
        command: BodyCommand,
        *,
        now: datetime | None = None,
    ) -> Tuple[CommandReceipt, ...]:
        return self._execute(command, now=now or utc_now())

    def execute_wire(
        self,
        payload: Mapping[str, WireValue],
        *,
        now: datetime | None = None,
    ) -> Tuple[CommandReceipt, ...]:
        current_time = now or utc_now()
        parsed = parse_wire_command(payload, occurred_at=current_time)
        if isinstance(parsed, CommandReceipt):
            return (parsed,)
        return self._execute(parsed, now=current_time)

    def snapshot_body(self, *, now: datetime | None = None) -> BodySnapshot:
        receipt = self._last_receipt
        return BodySnapshot(
            body_id=BodyId(self.body_id),
            captured_at=now or utc_now(),
            connected=self.connected,
            capability_revision=self.capabilities.revision,
            pending_event_count=self.sensors.pending_count,
            last_command_id=receipt.command_id if receipt else None,
            last_status=receipt.status if receipt else None,
        )

    def _execute(
        self,
        command: BodyCommand,
        *,
        now: datetime,
    ) -> Tuple[CommandReceipt, ...]:
        rejection = validate_command(
            command,
            expected_body_id=self.body_id,
            capabilities=self.capabilities,
            connected=self.connected,
            now=now,
        )
        if rejection is not None:
            self._last_receipt = rejection
            return (rejection,)
        payload: RuntimeIntentPayload
        if isinstance(command, SpeechCommand):
            payload = {
                "command_id": str(command.command_id),
                "actor_id": self.body_id,
                "intent": "speak",
                "text": command.text,
            }
        elif isinstance(command, MotionCommand):
            if command.target:
                payload = {
                    "command_id": str(command.command_id),
                    "actor_id": self.body_id,
                    "intent": "move_to_anchor",
                    "anchor_id": command.target,
                }
            else:
                payload = {
                    "command_id": str(command.command_id),
                    "actor_id": self.body_id,
                    "intent": "emotion_expression",
                    "expression": command.kind,
                }
        elif isinstance(command, ExpressionCommand):
            payload = {
                "command_id": str(command.command_id),
                "actor_id": self.body_id,
                "intent": "emotion_expression",
                "expression": command.kind,
            }
        elif isinstance(command, EmergencyStopCommand):
            self.transport.cancel_all(actor_id=self.body_id)
            receipts = (
                CommandReceipt.for_status(
                    command,
                    CommandStatus.ACCEPTED,
                    occurred_at=now,
                ),
                CommandReceipt.completed(command, occurred_at=now),
            )
            self._last_receipt = receipts[-1]
            return receipts
        else:  # pragma: no cover - discriminated BodyCommand is exhaustive.
            receipt = rejected(
                command,
                "unsupported_capability",
                "Godot transport cannot execute this command",
                now,
            )
            self._last_receipt = receipt
            return (receipt,)
        timeout_seconds = max((command.deadline - now).total_seconds(), 0.0)
        payload["deadline_seconds"] = timeout_seconds
        result = self.transport.execute_intent(
            payload,
            timeout_seconds=timeout_seconds,
        )
        receipts_list: list[CommandReceipt] = []
        for event in result.events:
            status_value = {
                "intent_accepted": CommandStatus.ACCEPTED,
                "intent_started": CommandStatus.STARTED,
            }.get(event.name.value)
            if status_value is None:
                continue
            receipts_list.append(
                CommandReceipt(
                    receipt_id=EventId(event.message_id),
                    cause_id=(
                        EventId(event.cause_id) if event.cause_id is not None else None
                    ),
                    command_id=command.command_id,
                    turn_id=command.turn_id,
                    intent_id=command.intent_id,
                    body_id=command.body_id,
                    status=status_value,
                    occurred_at=event.occurred_at,
                    capability_revision=command.capability_revision,
                    body_generation=command.body_generation,
                )
            )
        terminal_status = {
            "completed": CommandStatus.COMPLETED,
            "cancelled": CommandStatus.INTERRUPTED,
            "interrupted": CommandStatus.INTERRUPTED,
            "timed_out": CommandStatus.TIMED_OUT,
        }.get(result.terminal_status, CommandStatus.FAILED)
        terminal_error = None
        if terminal_status is not CommandStatus.COMPLETED:
            terminal_error = ErrorInfo(
                code=result.terminal_status,
                message=result.reason or result.terminal_status,
            )
        terminal_event = next(
            (
                event
                for event in reversed(result.events)
                if event.name.value == "intent_terminal"
            ),
            None,
        )
        if terminal_event is None:
            receipts_list.append(
                CommandReceipt.for_status(
                    command,
                    terminal_status,
                    occurred_at=utc_now(),
                    error=terminal_error,
                )
            )
        else:
            receipts_list.append(
                CommandReceipt(
                    receipt_id=EventId(terminal_event.message_id),
                    cause_id=(
                        EventId(terminal_event.cause_id)
                        if terminal_event.cause_id is not None
                        else None
                    ),
                    command_id=command.command_id,
                    turn_id=command.turn_id,
                    intent_id=command.intent_id,
                    body_id=command.body_id,
                    status=terminal_status,
                    occurred_at=terminal_event.occurred_at,
                    capability_revision=command.capability_revision,
                    body_generation=command.body_generation,
                    error=terminal_error,
                )
            )
        final_receipts: tuple[CommandReceipt, ...] = tuple(receipts_list)
        self._last_receipt = final_receipts[-1]
        return final_receipts
