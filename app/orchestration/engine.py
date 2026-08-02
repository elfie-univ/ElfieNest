from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ai_runtime.food.resolver import MainFoodSelection
from ai_runtime.storage.data_home import get_elfie_workspace_dir
from app.orchestration.nest_session import NestSession
from app.orchestration.runtime_adapter import SerializedRuntimeAdapter
from app.orchestration.runtime_gateway import RuntimeGateway
from app.orchestration.world_perception import collect_world_sensory_events
from elfie.body import BodySensorEvent
from nest import Nest, NestConfig
from nest.godot_gateway.api import GodotAPIServer
from nest.state.repository import NestRepository

logger = logging.getLogger("app.orchestration.engine")


class ElfieNestEngine:
    """
    ElfieNest 物理时钟游戏引擎的核心控制箱。
    通过 WebSocket 控制总线管理多只精灵的具身逻辑、生理衰减与文本发言广播。
    """

    def __init__(
        self,
        ws_host: str = "127.0.0.1",
        ws_port: int = 8765,
        godot_origin_port: Optional[int] = None,
        tick_interval_sec: float = 1.5,
        max_elfies_per_room: Optional[int] = None,
        api_server: RuntimeGateway | None = None,
        nest_repository: NestRepository | None = None,
        food_key_resolver: Callable[[str], MainFoodSelection | None] | None = None,
        elfie_workspace_resolver: Callable[[str], str | None] | None = None,
    ):
        """初始化引擎。

        Args:
            ws_host: WebSocket 主机地址
            ws_port: WebSocket 端口
            godot_origin_port: 允许连接 Godot WebSocket 的页面来源端口
            tick_interval_sec: 每个 tick 的间隔秒数
            max_elfies_per_room: 房间最大精灵数
        """
        self.tick_interval_sec = tick_interval_sec
        self._food_key_resolver = food_key_resolver or (lambda _elfie_id: None)
        self._elfie_workspace_resolver = elfie_workspace_resolver or (
            lambda elfie_id: str(get_elfie_workspace_dir(elfie_id))
        )

        # 1. 实例化核心组件
        self.nest = Nest(NestConfig(max_residents=max_elfies_per_room))
        self.api_server = api_server or GodotAPIServer(
            host=ws_host,
            port=ws_port,
            http_port=godot_origin_port if godot_origin_port is not None else 8000,
        )
        self.session = NestSession(
            self.nest,
            self.api_server,
            repository=nest_repository,
        )
        self.coordinator = self.session

        # 2. 可选的鉴权 WebSocket 管理网关（由 app.py 注入，None 则不启用）
        self.ws_manager: Optional[Any] = None

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
        for event in self.api_server.drain_runtime_events():
            self.session.consume_runtime_event(event)
        self.session.flush_runtime_state()
        self.nest.tick(seconds)
        self.session.tick_elfies(seconds)
        for elfie_id, elfie in tuple(self.session.elfies.items()):
            status = self.nest.resident_state(elfie_id)
            if status is None or not status.active or status.posture == "away":
                continue
            elfie.pump_body_events(self._collect_world_sensory_events(elfie_id))

    def start_loop(
        self,
        runtime_agent: Any,
        ticks_to_run: int = 3,
        interval_sec: Optional[float] = None,
    ):
        """
        启动世界物理 Tick 仿真循环。
        兼容 main.py，并能够极其自适应地运行。如果检测到 Godot 客户端连入，
        将支持长效通信与 3D 群聊联动；若无连接，则优雅回退至本地终端仿真。

        Args:
            runtime_agent: 运行时 LLM 代理
            ticks_to_run: 运行周期数
            interval_sec: 间隔秒数，None 则使用 self.tick_interval_sec
        """
        if interval_sec is None:
            interval_sec = self.tick_interval_sec
        # 1. 先装配并启动每只精灵的独立认知生命周期，再启动传输。
        self.session.configure_cognition_factory(
            lambda elfie_id: SerializedRuntimeAdapter(
                runtime_agent,
                food_key_resolver=lambda: self._food_key_resolver(elfie_id),
                elfie_workspace_resolver=lambda: self._elfie_workspace_resolver(
                    elfie_id
                ),
            )
        )
        self.session.start_elfies()
        self.api_server.start()
        if self.ws_manager:
            self.ws_manager.start()

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
            # 先停止输入和精灵工作线程，再清理套接字服务。
            self.session.stop_elfies()
            self.session.join_elfies()
            self.api_server.stop()
            if self.ws_manager:
                self.ws_manager.stop()
            logger.info("🌈 [时间盒子] 仿真主循环已平稳落地退出。")
