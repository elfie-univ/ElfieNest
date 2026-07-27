"""Connection-level rate limiting for Godot protocol v2."""

from __future__ import annotations

import time
from typing import Final

MAX_EVENTS_PER_SECOND: Final = 60
RATE_LIMIT_WINDOW_SECONDS: Final = 1.0


class MessageRateLimiter:
    """限制单个 Godot 连接的事件速率，避免回调被消息洪泛拖垮。"""

    def __init__(
        self,
        limit: int = MAX_EVENTS_PER_SECOND,
        window_seconds: float = RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._window_started_at = time.monotonic()
        self._count = 0

    def allow(self) -> bool:
        """记录一条事件并返回当前窗口是否仍允许继续处理。"""
        now = time.monotonic()
        if now - self._window_started_at >= self._window_seconds:
            self._window_started_at = now
            self._count = 0
        self._count += 1
        return self._count <= self._limit
