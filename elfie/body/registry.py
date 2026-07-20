"""精灵可用身体实例的注册表。"""

from __future__ import annotations

from threading import RLock
from typing import Dict, List, Optional

from elfie.body.port import BodyPort
from elfie.body.types import BodyDescriptor


class BodyRegistrationError(ValueError):
    """身体注册信息无效或发生冲突。"""


class BodyNotFoundError(KeyError):
    """请求的身体尚未注册。"""


class BodyRegistry:
    """保存一只精灵已经拥有或可以连接的身体实例。"""

    def __init__(self) -> None:
        self._bodies: Dict[str, BodyPort] = {}
        self._lock = RLock()

    def register(self, body: BodyPort, *, replace: bool = False) -> BodyPort:
        if not isinstance(body, BodyPort):
            raise BodyRegistrationError("注册对象没有完整实现 BodyPort")
        body_id = str(getattr(body, "body_id", "")).strip()
        if not body_id:
            raise BodyRegistrationError("body_id 不能为空")

        with self._lock:
            existing = self._bodies.get(body_id)
            if existing is not None and existing is not body and not replace:
                raise BodyRegistrationError(f"身体已经注册: {body_id}")
            self._bodies[body_id] = body
        return body

    def unregister(self, body_id: str) -> BodyPort:
        with self._lock:
            try:
                return self._bodies.pop(body_id)
            except KeyError as exc:
                raise BodyNotFoundError(body_id) from exc

    def get(self, body_id: str) -> Optional[BodyPort]:
        with self._lock:
            return self._bodies.get(body_id)

    def require(self, body_id: str) -> BodyPort:
        body = self.get(body_id)
        if body is None:
            raise BodyNotFoundError(body_id)
        return body

    def list_bodies(self) -> List[BodyPort]:
        with self._lock:
            return list(self._bodies.values())

    def describe_all(self) -> List[BodyDescriptor]:
        return [body.describe() for body in self.list_bodies()]

    def __contains__(self, body_id: object) -> bool:
        if not isinstance(body_id, str):
            return False
        with self._lock:
            return body_id in self._bodies

    def __len__(self) -> int:
        with self._lock:
            return len(self._bodies)
