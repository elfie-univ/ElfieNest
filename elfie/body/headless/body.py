"""不渲染、不驱动硬件，只接收刺激并记录动作的身体实现。"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional

from elfie.body.capabilities import BodyCapabilities
from elfie.body.headless.actuators import HeadlessActuators
from elfie.body.headless.sensors import HeadlessSensors
from elfie.body.types import (
    BodyCommand,
    BodyDescriptor,
    BodyEvent,
    BodyMode,
    BodyState,
    CommandResult,
    CommandStatus,
)


class HeadlessBody:
    """用于调试平台、单元测试和无渲染运行。"""

    def __init__(
        self,
        body_id: str = "headless_default",
        capabilities: Optional[BodyCapabilities] = None,
    ):
        self.body_id = body_id
        self.capabilities = capabilities or BodyCapabilities(
            sensors=frozenset({"*"}),
            actions=frozenset({"*"}),
        )
        self.sensors = HeadlessSensors(source=body_id)
        self.actuators = HeadlessActuators(self.capabilities)
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=self.body_id,
            mode=BodyMode.HEADLESS,
            display_name="Headless Body",
            capabilities=self.capabilities,
        )

    def inject_sensor_data(
        self,
        sensor_data: Mapping[str, Any],
        *,
        event_id: Optional[str] = None,
    ) -> BodyEvent:
        return self.sensors.inject_sensor_data(sensor_data, event_id=event_id)

    def read_events(self) -> List[BodyEvent]:
        return self.sensors.read_events()

    def execute(self, command: BodyCommand) -> CommandResult:
        if not self.connected:
            return CommandResult(
                command_id=command.command_id,
                action=command.action,
                status=CommandStatus.REJECTED,
                error="HeadlessBody 尚未连接",
            )
        return self.actuators.execute(command)

    def snapshot(self) -> BodyState:
        last_result = self.actuators.last_result
        return BodyState(
            body_id=self.body_id,
            connected=self.connected,
            pending_event_count=self.sensors.pending_count,
            last_action=last_result.action if last_result else "",
        )

    def emergency_stop(self) -> CommandResult:
        return self.execute(BodyCommand(action="system.emergency_stop"))

    @property
    def last_result(self) -> Optional[CommandResult]:
        return self.actuators.last_result
