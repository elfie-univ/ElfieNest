"""外部身体插件必须实现的传输契约。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping, Protocol, Union, runtime_checkable

from elfie.body.contracts import (
    BodyCommand,
    BodySensorEvent,
    CommandReceipt,
)
from elfie.body.types import (
    BodyCommand as LegacyBodyCommand,
)
from elfie.body.types import (
    BodyEvent,
)
from elfie.body.types import (
    CommandResult as LegacyCommandResult,
)

ExternalEventHandler = Callable[[Union[BodyEvent, BodySensorEvent]], None]


@runtime_checkable
class ExternalTransport(Protocol):
    """由毛绒玩具、机器人或母星代理插件实现的同步边界。"""

    transport_id: str

    def connect(self, event_handler: ExternalEventHandler) -> None: ...

    def disconnect(self) -> None: ...

    def send_command(
        self, command: LegacyBodyCommand | BodyCommand
    ) -> LegacyCommandResult | CommandReceipt: ...

    def snapshot(self) -> Mapping[str, Any]: ...
