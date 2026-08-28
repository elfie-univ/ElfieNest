from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Event, Lock
from typing import Optional

from app.orchestration.nest_session.ports import (
    ModelPortFactory,
    NestSessionRuntimePort,
    NestStateStorePort,
)
from app.orchestration.nest_session.session import NestSession
from nest.public import Nest, NestConfig

logger = logging.getLogger("app.orchestration.engine")


@dataclass(frozen=True)
class EngineProgress:
    """Thread-safe progress evidence for Core liveness diagnostics."""

    completed_ticks: int
    loop_started_at: Optional[float]
    last_tick_started_at: Optional[float]
    last_tick_completed_at: Optional[float]
    last_tick_duration_seconds: Optional[float]


class ElfieNestEngine:
    """
    ElfieNest 物理时钟游戏引擎的核心控制箱。
    通过 WebSocket 控制总线管理多只精灵的具身逻辑、生理衰减与文本发言广播。
    """

    def __init__(
        self,
        world_runtime: NestSessionRuntimePort,
        *,
        tick_interval_sec: float = 1.5,
        state_store: NestStateStorePort | None = None,
        nest_config: NestConfig | None = None,
    ) -> None:
        """初始化引擎。

        Args:
            world_runtime: Injected semantic world channel.
            tick_interval_sec: 每个 tick 的间隔秒数
        """
        self.tick_interval_sec = tick_interval_sec

        # 1. 实例化核心组件
        self.nest = Nest(nest_config or NestConfig())
        self.world_runtime = world_runtime
        self.session = NestSession(
            self.nest,
            self.world_runtime,
            state_store=state_store,
        )
        self.coordinator = self.session
        self._loop_started = False
        self._stop_event = Event()
        self._running_event = Event()
        self._progress_lock = Lock()
        self._completed_ticks = 0
        self._loop_started_at: Optional[float] = None
        self._last_tick_started_at: Optional[float] = None
        self._last_tick_completed_at: Optional[float] = None
        self._last_tick_duration_seconds: Optional[float] = None

    @property
    def is_running(self) -> bool:
        """Return whether the physical clock loop is currently alive."""
        return self._running_event.is_set()

    @property
    def stop_requested(self) -> bool:
        """Return whether lifecycle cleanup explicitly requested loop shutdown."""
        return self._stop_event.is_set()

    def progress_snapshot(self) -> EngineProgress:
        """Return monotonic progress evidence without mutating engine state."""
        with self._progress_lock:
            return EngineProgress(
                completed_ticks=self._completed_ticks,
                loop_started_at=self._loop_started_at,
                last_tick_started_at=self._last_tick_started_at,
                last_tick_completed_at=self._last_tick_completed_at,
                last_tick_duration_seconds=self._last_tick_duration_seconds,
            )

    def progress_age_seconds(self, *, now: Optional[float] = None) -> Optional[float]:
        """Return how long the running loop has gone without completing a tick."""
        snapshot = self.progress_snapshot()
        reference = (
            snapshot.last_tick_completed_at
            if snapshot.last_tick_completed_at is not None
            else snapshot.loop_started_at
        )
        if reference is None:
            return None
        observed_at = time.monotonic() if now is None else now
        return max(0.0, observed_at - reference)

    def wait_until_running(self, timeout: float) -> bool:
        """Wait for startup without mistaking engine construction for readiness."""
        if timeout < 0:
            raise ValueError("timeout must be non-negative")
        return self._running_event.wait(timeout)

    def request_stop(self) -> None:
        """Interrupt the production loop's wait so shutdown stays bounded."""
        self._stop_event.set()

    def tick_once(self, seconds: float) -> None:
        """Advance physics and publish inputs without awaiting cognition or output."""
        self.session.poll_runtime_connection()
        for event in self.world_runtime.drain_events():
            self.session.consume_runtime_event(event)
        self.session.flush_runtime_state()
        self.nest.tick(seconds)
        self.session.persist_time_environment()
        self.session.flush_environment_state()
        self.session.tick_elfies(seconds)
        for elfie_id, elfie in self.session.elfie_items_snapshot():
            status = self.nest.resident_state(elfie_id)
            if status is None or not status.active or status.posture == "away":
                continue
            elfie.pump_body_events()

    def start_loop(
        self,
        model_port_factory: ModelPortFactory,
        ticks_to_run: Optional[int] = 3,
        interval_sec: Optional[float] = None,
    ) -> None:
        """
        启动世界物理 Tick 仿真循环。
        兼容 main.py，并能够极其自适应地运行。如果检测到 Godot 客户端连入，
        将支持长效通信与 3D 群聊联动；若无连接，则优雅回退至本地终端仿真。

        Args:
            model_port_factory: Injected model Port factory for each Elfie.
            ticks_to_run: 运行周期数；``None`` 表示持续运行直到明确停止
            interval_sec: 间隔秒数，None 则使用 self.tick_interval_sec
        """
        if interval_sec is None:
            interval_sec = self.tick_interval_sec
        if interval_sec < 0:
            raise ValueError("interval_sec must be non-negative")
        if ticks_to_run is not None and ticks_to_run < 0:
            raise ValueError("ticks_to_run must be non-negative or None")
        if self._loop_started:
            raise RuntimeError("ElfieNestEngine 主循环只能启动一次")
        self._loop_started = True
        # Runtime process/channel lifecycle is owned by orchestration/lifecycle.
        # This loop starts only the resident Elfies it coordinates.
        self.session.configure_cognition_factory(model_port_factory)
        self.session.start_elfies()
        started_at = time.monotonic()
        with self._progress_lock:
            self._loop_started_at = started_at
        self._running_event.set()

        logger.info(
            "ElfieNest engine loop started (ticks=%s interval_sec=%s)",
            "unbounded" if ticks_to_run is None else ticks_to_run,
            interval_sec,
        )

        current_tick = 0
        next_deadline = started_at
        try:
            while not self._stop_event.is_set() and (
                ticks_to_run is None or current_tick < ticks_to_run
            ):
                current_tick += 1
                logger.debug(
                    "ElfieNest engine tick %s/%s",
                    current_tick,
                    "unbounded" if ticks_to_run is None else ticks_to_run,
                )

                tick_started_at = time.monotonic()
                with self._progress_lock:
                    self._last_tick_started_at = tick_started_at
                self.tick_once(interval_sec)
                tick_completed_at = time.monotonic()
                with self._progress_lock:
                    self._completed_ticks = current_tick
                    self._last_tick_completed_at = tick_completed_at
                    self._last_tick_duration_seconds = max(
                        0.0, tick_completed_at - tick_started_at
                    )
                next_deadline += interval_sec
                remaining = next_deadline - time.monotonic()
                if remaining > 0 and self._stop_event.wait(remaining):
                    break

        except KeyboardInterrupt:
            self.request_stop()
            logger.info("ElfieNest engine loop received a keyboard interrupt")
        finally:
            self._running_event.clear()
            # Stop only resident workers; lifecycle owns process/channel shutdown.
            self.session.stop_elfies()
            self.session.join_elfies()
            logger.info("ElfieNest engine loop stopped")


__all__ = ("ElfieNestEngine", "EngineProgress")
