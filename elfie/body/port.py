"""可由 Headless、Native 和 External 身体共同实现的稳定协议。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Protocol, Tuple, runtime_checkable

from elfie.body.capabilities import BodyCapabilities, BodyCapabilityDescriptor
from elfie.body.contracts import (
    BodyCommand,
    BodySensorEvent,
    BodySnapshot,
    CommandReceipt,
)
from elfie.body.types import BodyDescriptor


@runtime_checkable
class SensorPort(Protocol):
    """身体实现内部使用的传感事件队列。"""

    def read_sensor_events(self) -> List[BodySensorEvent]: ...


@runtime_checkable
class ActuatorPort(Protocol):
    """身体实现内部使用的动作执行器。"""

    def execute(
        self, command: BodyCommand, *, now: datetime | None = None
    ) -> Tuple[CommandReceipt, ...]: ...


@runtime_checkable
class BodyPort(Protocol):
    """一副可替换身体对 Elfie 暴露的最小公共接口。

    调用方只通过 typed sensor event 接收感觉，通过 typed command 控制身体。
    具体身体可以在内部拆分 sensors/actuators，但它们不是公共调用入口。
    """

    body_id: str
    capabilities: BodyCapabilities

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def describe(self) -> BodyDescriptor: ...

    def list_actions(
        self, *, model_visible: bool = False
    ) -> Tuple[BodyCapabilityDescriptor, ...]: ...

    def list_inputs(
        self, *, model_visible: bool = False
    ) -> Tuple[BodyCapabilityDescriptor, ...]: ...

    def register_action(
        self, descriptor: BodyCapabilityDescriptor
    ) -> BodyCapabilities: ...

    def unregister_action(self, capability_id: str) -> BodyCapabilities: ...

    def register_input(
        self, descriptor: BodyCapabilityDescriptor
    ) -> BodyCapabilities: ...

    def unregister_input(self, capability_id: str) -> BodyCapabilities: ...

    def read_sensor_events(self) -> List[BodySensorEvent]: ...

    def execute(
        self, command: BodyCommand, *, now: datetime | None = None
    ) -> Tuple[CommandReceipt, ...]: ...

    def snapshot_body(self, *, now: datetime | None = None) -> BodySnapshot: ...
