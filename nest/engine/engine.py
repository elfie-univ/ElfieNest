"""Nest 世界时钟和环境推进。"""

from __future__ import annotations

from dataclasses import dataclass

from nest.state.store import NestState


@dataclass(frozen=True)
class InvalidTickError(Exception):
    """拒绝无效的世界时钟步长。"""

    seconds: float

    def __str__(self) -> str:
        return f"tick 时长不能为负数: {self.seconds}"


class NestEngine:
    """只推进 Nest 环境，不调用精灵认知或 3D 物理。"""

    def __init__(self, state: NestState) -> None:
        self._state = state

    def tick(self, seconds: float) -> None:
        if seconds < 0:
            raise InvalidTickError(seconds)
        if self._state.clock_paused:
            return
        self._state.elapsed_seconds += seconds * self._state.time_scale
