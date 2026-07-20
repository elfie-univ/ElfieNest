"""可由 Headless、Native 和 External 身体共同实现的稳定协议。"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from elfie.body.capabilities import BodyCapabilities
from elfie.body.types import (
    BodyCommand,
    BodyDescriptor,
    BodyEvent,
    BodyState,
    CommandResult,
)


@runtime_checkable
class SensorPort(Protocol):
    """身体实现内部使用的传感事件队列。"""

    def read_events(self) -> List[BodyEvent]: ...


@runtime_checkable
class ActuatorPort(Protocol):
    """身体实现内部使用的动作执行器。"""

    def execute(self, command: BodyCommand) -> CommandResult: ...


@runtime_checkable
class BodyPort(Protocol):
    """一副可替换身体对 Elfie 暴露的最小公共接口。

    调用方只通过 ``read_events`` 接收感觉，通过 ``execute`` 控制身体。
    具体身体可以在内部拆分 sensors/actuators，但它们不是公共调用入口。
    """

    body_id: str
    capabilities: BodyCapabilities

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def describe(self) -> BodyDescriptor: ...

    def read_events(self) -> List[BodyEvent]: ...

    def execute(self, command: BodyCommand) -> CommandResult: ...

    def snapshot(self) -> BodyState: ...

    def emergency_stop(self) -> CommandResult: ...
