"""毛绒玩具、机器人和母星代理共用的 External BodyPort。"""

from __future__ import annotations

from typing import List, Optional

from elfie.body.capabilities import BodyCapabilities
from elfie.body.external.actuators import ExternalActuators
from elfie.body.external.sensors import ExternalSensors
from elfie.body.external.transport import ExternalTransport
from elfie.body.types import (
    BodyCommand,
    BodyDescriptor,
    BodyEvent,
    BodyMode,
    BodyState,
    CommandResult,
)


class ExternalBody:
    """把外部插件提供的传输实现适配为统一 BodyPort。"""

    def __init__(
        self,
        body_id: str,
        display_name: str,
        capabilities: BodyCapabilities,
        transport: ExternalTransport,
    ) -> None:
        self.body_id = body_id
        self.display_name = display_name
        self.capabilities = capabilities
        self.transport = transport
        self.sensors = ExternalSensors(capabilities)
        self.actuators = ExternalActuators(capabilities, transport)
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
        self.transport.disconnect()
        self.actuators.connected = False
        self.connected = False

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=self.body_id,
            mode=BodyMode.EXTERNAL,
            display_name=self.display_name,
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
            metadata={
                "transport_id": self.transport.transport_id,
                "transport": dict(self.transport.snapshot()),
            },
        )

    def emergency_stop(self) -> CommandResult:
        return self.execute(BodyCommand(action="system.emergency_stop"))

    @property
    def last_result(self) -> Optional[CommandResult]:
        return self.actuators.last_result
