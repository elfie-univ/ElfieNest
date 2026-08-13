"""一只精灵当前使用身体的绑定和切换生命周期。"""

from __future__ import annotations

from threading import RLock
from typing import List, Optional

from elfie.body.port import BodyPort
from elfie.body.registry import BodyRegistry
from elfie.body.types import BodyDescriptor


class BodySwitchError(RuntimeError):
    """身体切换失败，并且无法恢复先前身体。"""


class BodyBinding:
    """管理当前身体，切换失败时恢复先前身体。"""

    def __init__(self, registry: Optional[BodyRegistry] = None) -> None:
        self.registry = registry if registry is not None else BodyRegistry()
        self._current: Optional[BodyPort] = None
        self._generation = 0
        self._current_generation: Optional[int] = None
        self._lock = RLock()

    @property
    def current(self) -> Optional[BodyPort]:
        with self._lock:
            return self._current

    @property
    def current_body_id(self) -> Optional[str]:
        current = self.current
        return current.body_id if current is not None else None

    @property
    def current_generation(self) -> Optional[int]:
        """The authority generation of the currently selected body."""
        with self._lock:
            return self._current_generation

    def register(self, body: BodyPort, *, replace: bool = False) -> BodyPort:
        return self.registry.register(body, replace=replace)

    def register_and_bind(self, body: BodyPort) -> BodyPort:
        self.register(body)
        return self.bind(body.body_id)

    def bind(self, body_id: str) -> BodyPort:
        """连接指定身体并断开旧身体；连接失败时尝试恢复旧身体。"""
        candidate = self.registry.require(body_id)
        with self._lock:
            previous = self._current
            if candidate is previous:
                if not candidate.snapshot_body().connected:
                    candidate.connect()
                return candidate

            if previous is not None:
                previous.disconnect()
            try:
                candidate.connect()
            except Exception as connect_error:
                try:
                    candidate.disconnect()
                except Exception:
                    pass
                if previous is not None:
                    try:
                        previous.connect()
                    except Exception as rollback_error:
                        self._current = None
                        raise BodySwitchError(
                            f"无法连接身体 {body_id}，并且旧身体 "
                            f"{previous.body_id} 恢复失败: {rollback_error}"
                        ) from connect_error
                raise
            self._current = candidate
            self._generation += 1
            self._current_generation = self._generation
            return candidate

    def unbind(self) -> Optional[BodyPort]:
        with self._lock:
            previous = self._current
            if previous is None:
                return None
            previous.disconnect()
            self._current = None
            self._generation += 1
            self._current_generation = None
            return previous

    def unregister(self, body_id: str) -> BodyPort:
        with self._lock:
            if self._current is not None and self._current.body_id == body_id:
                self.unbind()
            return self.registry.unregister(body_id)

    def attach(self, body: Optional[BodyPort]) -> None:
        """装配初始当前身体，不隐式改变传入身体的连接状态。"""
        with self._lock:
            if body is None:
                self._current = None
                self._generation += 1
                self._current_generation = None
                return
            self.registry.register(body, replace=True)
            self._current = body
            self._generation = max(self._generation, 1)
            self._current_generation = self._generation

    def available(self) -> List[BodyDescriptor]:
        return self.registry.describe_all()
