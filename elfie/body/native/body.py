"""Godot 中精灵本体的 BodyPort 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Mapping, Optional, Tuple, overload

from elfie.body.capabilities import BodyCapabilities
from elfie.body.command_execution import (
    WireValue,
    lifecycle_receipts,
    parse_wire_command,
    rejected,
    utc_now,
    validate_command,
)
from elfie.body.contracts import (
    BodyCommand as TypedBodyCommand,
)
from elfie.body.contracts import (
    BodySensorEvent,
    BodySnapshot,
    CommandReceipt,
    ExpressionCommand,
    MotionCommand,
    SpeechCommand,
)
from elfie.body.native.actuators import NativeActuators
from elfie.body.native.godot_transport import GodotTransport
from elfie.body.native.sensors import NativeSensors
from elfie.body.types import (
    BodyCommand as LegacyBodyCommand,
)
from elfie.body.types import (
    BodyDescriptor,
    BodyEvent,
    BodyMode,
    BodyState,
)
from elfie.body.types import (
    CommandResult as LegacyCommandResult,
)


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
        self.actuators = NativeActuators(
            body_id=body_id,
            capabilities=self.capabilities,
            transport=transport,
        )
        self.connected = False
        self._last_typed_receipt: CommandReceipt | None = None

    def connect(self) -> None:
        if self.connected:
            return
        self.transport.connect(self.sensors.receive)
        self.actuators.connected = True
        self.connected = True

    def disconnect(self) -> None:
        if not self.connected:
            return
        self.transport.disconnect(self.sensors.receive)
        self.actuators.connected = False
        self.connected = False

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=self.body_id,
            mode=BodyMode.NATIVE,
            display_name="Native Godot Body",
            capabilities=self.capabilities,
        )

    def read_events(self) -> List[BodyEvent]:
        if not self.connected:
            return []
        return self.sensors.read_events()

    def read_sensor_events(self) -> List[BodySensorEvent]:
        if not self.connected:
            return []
        return self.sensors.read_sensor_events()

    @overload
    def execute(
        self, command: LegacyBodyCommand, *, now: datetime | None = None
    ) -> LegacyCommandResult: ...

    @overload
    def execute(
        self, command: TypedBodyCommand, *, now: datetime | None = None
    ) -> Tuple[CommandReceipt, ...]: ...

    def execute(
        self,
        command: LegacyBodyCommand | TypedBodyCommand,
        *,
        now: datetime | None = None,
    ) -> LegacyCommandResult | Tuple[CommandReceipt, ...]:
        if isinstance(command, LegacyBodyCommand):
            return self.actuators.execute(command)
        return self._execute_typed(command, now=now or utc_now())

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
        return self._execute_typed(parsed, now=current_time)

    def snapshot(self) -> BodyState:
        last_result = self.actuators.last_result
        return BodyState(
            body_id=self.body_id,
            connected=self.connected,
            pending_event_count=self.sensors.pending_count,
            last_action=last_result.action if last_result else "",
            metadata={"godot_runtime_ready": self.transport.runtime_ready},
        )

    def snapshot_body(self, *, now: datetime | None = None) -> BodySnapshot:
        receipt = self._last_typed_receipt
        return BodySnapshot(
            body_id=self.body_id,
            captured_at=now or utc_now(),
            connected=self.connected,
            capability_revision=self.capabilities.revision,
            pending_event_count=self.sensors.pending_count,
            last_command_id=receipt.command_id if receipt else None,
            last_status=receipt.status if receipt else None,
        )

    def emergency_stop(self) -> LegacyCommandResult:
        result = self.execute(LegacyBodyCommand(action="system.emergency_stop"))
        return result

    @property
    def last_result(self) -> Optional[LegacyCommandResult]:
        return self.actuators.last_result

    def _execute_typed(
        self,
        command: TypedBodyCommand,
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
            self._last_typed_receipt = rejection
            return (rejection,)
        if isinstance(command, SpeechCommand):
            self.transport.send_action(
                "speak_event",
                {
                    "elfie_id": self.body_id,
                    "text": command.text,
                    "audio_url": command.audio.uri if command.audio else "",
                },
            )
        elif isinstance(command, MotionCommand):
            if command.target:
                self.transport.send_action(
                    "go_to",
                    {
                        "elfie_id": self.body_id,
                        "target": command.target,
                        "posture": command.posture or "standing",
                        "animation": command.kind,
                    },
                )
            else:
                self.transport.send_action(
                    "emotion_expression",
                    {"elfie_id": self.body_id, "actions": [command.kind]},
                )
        elif isinstance(command, ExpressionCommand):
            self.transport.send_action(
                "emotion_expression",
                {"elfie_id": self.body_id, "expression": command.kind},
            )
        else:
            receipt = rejected(
                command,
                "unsupported_capability",
                "Godot transport cannot acknowledge emergency stop",
                now,
            )
            self._last_typed_receipt = receipt
            return (receipt,)
        receipts = lifecycle_receipts(command, occurred_at=now)
        self._last_typed_receipt = receipts[-1]
        return receipts
