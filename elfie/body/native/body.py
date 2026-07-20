"""Godot 中精灵本体的 BodyPort 实现。"""

from __future__ import annotations

from typing import List, Optional

from elfie.body.capabilities import BodyCapabilities
from elfie.body.native.actuators import NativeActuators
from elfie.body.native.godot_transport import GodotTransport
from elfie.body.native.sensors import NativeSensors
from elfie.body.types import (
    BodyCommand,
    BodyDescriptor,
    BodyEvent,
    BodyMode,
    BodyState,
    CommandResult,
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

    def execute(self, command: BodyCommand) -> CommandResult:
        return self.actuators.execute(command)

    def snapshot(self) -> BodyState:
        last_result = self.actuators.last_result
        return BodyState(
            body_id=self.body_id,
            connected=self.connected,
            pending_event_count=self.sensors.pending_count,
            last_action=last_result.action if last_result else "",
            metadata={"godot_runtime_ready": self.transport.runtime_ready},
        )

    def emergency_stop(self) -> CommandResult:
        return self.execute(BodyCommand(action="system.emergency_stop"))

    @property
    def last_result(self) -> Optional[CommandResult]:
        return self.actuators.last_result
