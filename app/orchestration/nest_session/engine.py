from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.orchestration.nest_session.ports import (
    CorticalRuntimeFactory,
    WorldRuntimePort,
)
from app.orchestration.nest_session.session import NestSession
from app.orchestration.nest_session.world_perception import (
    collect_world_sensory_events,
)
from elfie.body import BodySensorEvent
from nest import Nest, NestConfig
from nest.state.repository import NestRepository

logger = logging.getLogger("app.orchestration.engine")


class ElfieNestEngine:
    """
    ElfieNest 物理时钟游戏引擎的核心控制箱。
    通过 WebSocket 控制总线管理多只精灵的具身逻辑、生理衰减与文本发言广播。
    """

    def __init__(
        self,
        world_runtime: WorldRuntimePort,
        *,
        tick_interval_sec: float = 1.5,
        nest_repository: NestRepository | None = None,
    ) -> None:
        """初始化引擎。

        Args:
            world_runtime: Injected semantic world channel.
            tick_interval_sec: 每个 tick 的间隔秒数
        """
        self.tick_interval_sec = tick_interval_sec

        # 1. 实例化核心组件
        self.nest = Nest(NestConfig())
        self.world_runtime = world_runtime
        self.session = NestSession(
            self.nest,
            self.world_runtime,
            repository=nest_repository,
        )
        self.coordinator = self.session
        self._loop_started = False

    def _collect_world_sensory_events(self, elfie_id: str) -> list[BodySensorEvent]:
        """Convert only physical room facts into typed Body sensor events."""
        return collect_world_sensory_events(
            nest=self.nest,
            session=self.session,
            elfie_id=elfie_id,
            captured_at=self._simulation_datetime(),
        )

    def _simulation_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.nest.state.elapsed_seconds, timezone.utc)

    def tick_once(self, seconds: float) -> None:
        """Advance physics and publish inputs without awaiting cognition or output."""
        self.session.poll_runtime_connection()
        for event in self.world_runtime.drain_events():
            self.session.consume_runtime_event(event)
        self.session.flush_runtime_state()
        self.nest.tick(seconds)
        self.session.tick_elfies(seconds)
        for elfie_id, elfie in self.session.elfie_items_snapshot():
            status = self.nest.resident_state(elfie_id)
            if status is None or not status.active or status.posture == "away":
                continue
            elfie.pump_body_events(self._collect_world_sensory_events(elfie_id))

    def start_loop(
        self,
        runtime_factory: CorticalRuntimeFactory,
        ticks_to_run: int = 3,
        interval_sec: Optional[float] = None,
    ) -> None:
        """
        启动世界物理 Tick 仿真循环。
        兼容 main.py，并能够极其自适应地运行。如果检测到 Godot 客户端连入，
        将支持长效通信与 3D 群聊联动；若无连接，则优雅回退至本地终端仿真。

        Args:
            runtime_factory: Injected cognition runtime factory for each Elfie.
            ticks_to_run: 运行周期数
            interval_sec: 间隔秒数，None 则使用 self.tick_interval_sec
        """
        if interval_sec is None:
            interval_sec = self.tick_interval_sec
        if self._loop_started:
            raise RuntimeError("ElfieNestEngine 主循环只能启动一次")
        self._loop_started = True
        # Runtime process/channel lifecycle is owned by orchestration/lifecycle.
        # This loop starts only the resident Elfies it coordinates.
        self.session.configure_cognition_factory(runtime_factory)
        self.session.start_elfies()

        logger.info(
            f"⏳ [时间盒子] 物理仿真启动。总计运行 {ticks_to_run} 个 Tick 周期，每个周期阻尼间歇 {interval_sec} 秒..."
        )

        current_tick = 0
        next_deadline = time.monotonic()
        try:
            while current_tick < ticks_to_run:
                current_tick += 1
                logger.info(
                    f"\n====================== 🌀 PHYSICS TICK {current_tick}/{ticks_to_run} ======================"
                )

                self.tick_once(interval_sec)
                next_deadline += interval_sec
                remaining = next_deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)

        except KeyboardInterrupt:
            logger.info("👋 收到键盘中断，正在强行收束物理世界...")
        finally:
            # Stop only resident workers; lifecycle owns process/channel shutdown.
            self.session.stop_elfies()
            self.session.join_elfies()
            logger.info("🌈 [时间盒子] 仿真主循环已平稳落地退出。")


__all__ = ("ElfieNestEngine",)
