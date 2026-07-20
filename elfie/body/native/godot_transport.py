"""对现有 Godot API 的薄传输适配层。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, List, Protocol


class GodotGateway(Protocol):
    """NativeBody 实际依赖的最小 Godot 网关接口。"""

    def register_callback(
        self, event_name: str, callback: Callable[[Dict[str, Any]], None]
    ) -> None: ...

    def send_action(self, action: str, payload: Dict[str, Any]) -> None: ...


NativeEventHandler = Callable[[str, Dict[str, Any]], None]


class GodotTransport:
    """复用现有 GodotAPIServer，不持有房间或精灵业务逻辑。"""

    _INBOUND_EVENTS = ("runtime_ready", "arrived_at", "user_message")

    def __init__(self, gateway: GodotGateway):
        self.gateway = gateway
        self._handlers: List[NativeEventHandler] = []
        self._callbacks_registered = False

    def connect(self, handler: NativeEventHandler) -> None:
        if handler not in self._handlers:
            self._handlers.append(handler)
        if self._callbacks_registered:
            return

        for event_name in self._INBOUND_EVENTS:
            self.gateway.register_callback(
                event_name,
                self._callback_for(event_name),
            )
        self._callbacks_registered = True

    def disconnect(self, handler: NativeEventHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    def send_action(self, action: str, payload: Dict[str, Any]) -> None:
        self.gateway.send_action(action, payload)

    @property
    def runtime_ready(self) -> bool:
        return bool(getattr(self.gateway, "runtime_ready", False))

    def _callback_for(
        self, event_name: str
    ) -> Callable[[Dict[str, Any]], None]:
        def receive(payload: Dict[str, Any]) -> None:
            for handler in list(self._handlers):
                handler(event_name, dict(payload))

        return receive
