import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.orchestration.nest_session import NestSession
from app.orchestration.runtime_adapter import SerializedRuntimeAdapter
from app.orchestration.world_perception import collect_world_sensory_events
from elfie.body import BodySensorEvent
from elfie.profile import AppearanceResolver
from nest import Nest, NestConfig
from nest.godot.api import GodotAPIServer

logger = logging.getLogger("app.orchestration.engine")


class ElfieNestEngine:
    """
    ElfieNest 物理时钟游戏引擎的核心控制箱。
    内置 8000 端口的语音静态分发网关，8765 端口的 WebSocket 控制总线。
    管理多只精灵的具身逻辑、生理衰减以及高逼真度的 edge-tts 语音流水线。
    """

    def __init__(
        self,
        ws_host: str = "127.0.0.1",
        ws_port: int = 8765,
        http_port: int = 8000,
        godot_origin_port: Optional[int] = None,
        tick_interval_sec: float = 1.5,
        tts_enabled: bool = True,
        max_elfies_per_room: Optional[int] = None,
    ):
        """初始化引擎。

        Args:
            ws_host: WebSocket 主机地址
            ws_port: WebSocket 端口
            http_port: HTTP 端口
            tick_interval_sec: 每个 tick 的间隔秒数
            tts_enabled: 是否启用 TTS
            max_elfies_per_room: 房间最大精灵数
        """
        self.tick_interval_sec = tick_interval_sec
        self.tts_enabled = tts_enabled

        # 1. 实例化核心组件
        self.nest = Nest(NestConfig(max_residents=max_elfies_per_room))
        self.api_server = GodotAPIServer(
            host=ws_host,
            port=ws_port,
            http_port=(
                godot_origin_port if godot_origin_port is not None else http_port
            ),
        )
        self.session = NestSession(self.nest, self.api_server)
        self.coordinator = self.session

        # 2. Godot 静态资源端口由网关持有；输出统一走 OutputRouter。
        self.http_port = http_port

        # 3. 注册 Godot 事件回调以驱动 Python 看板
        self.api_server.register_callback(
            "register_scene", self._on_godot_scene_registered
        )
        self.api_server.register_callback("runtime_ready", self._on_godot_runtime_ready)
        self.api_server.register_callback("arrived_at", self._on_godot_elfie_arrived)
        self.api_server.register_callback("user_message", self._on_user_message)

        # 4. 可选的鉴权 WebSocket 管理网关（由 app.py 注入，None 则不启用）
        self.ws_manager: Optional[Any] = None

    def _on_godot_scene_registered(self, payload: Dict[str, Any]):
        """Godot 场景握手回调：动态注册家具"""
        furniture = payload.get("furniture", [])
        self.nest.register_scene_furniture(furniture)

    def _on_godot_runtime_ready(self, _payload: Dict[str, Any]) -> None:
        """向刚连接的 Godot Runtime 同步当前 Python 精灵目录。"""
        self.sync_godot_elfies()

    def sync_godot_elfies(self) -> None:
        """将当前 Python 房间精灵目录同步给 Godot Runtime。"""
        self.api_server.send_action(
            "sync_elfies",
            {
                "elfies": [
                    self._build_godot_elfie_payload(elfie_id, elfie)
                    for elfie_id, elfie in self.session.elfies.items()
                ]
            },
        )

    @staticmethod
    def _build_godot_elfie_payload(elfie_id: str, elfie: Any) -> Dict[str, Any]:
        """从个体配置提取 Godot 渲染所需的最小身份与外观数据。"""
        character_profile = getattr(elfie, "character_profile", None)
        if character_profile is not None:
            resolved = AppearanceResolver().resolve(character_profile)
            appearance = resolved.to_payload()
            return {
                "elfie_id": elfie_id,
                "name": character_profile.identity.display_name,
                "species": character_profile.identity.species_id,
                "height_scale": resolved.height_scale,
                "build_scale": resolved.build_scale,
                "appearance": appearance,
            }

        profile = getattr(getattr(elfie, "brain", None), "profile", None)
        personality = getattr(profile, "personality", {})
        if not isinstance(personality, dict):
            personality = {}
        metadata = personality.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        appearance = metadata.get("appearance", {})
        if not isinstance(appearance, dict):
            appearance = {}

        payload: Dict[str, Any] = {
            "elfie_id": elfie_id,
            "name": metadata.get("name") or getattr(elfie, "name", elfie_id),
        }
        for field in ("species", "height", "build", "height_scale", "build_scale"):
            if field in appearance:
                payload[field] = appearance[field]
        return payload

    def _on_godot_elfie_arrived(self, payload: Dict[str, Any]):
        """Godot 精灵移动到达回调：锁定物理姿态"""
        elfie_id = payload.get("elfie_id", "")
        target = payload.get("target", "")

        # 解析预期的姿势。如果是床则躺下，椅子坐下，传送门消散
        posture = "standing"
        if target and "bed" in target.lower():
            posture = "lying"
        elif target and "chair" in target.lower():
            posture = "sitting"
        elif target and "door" in target.lower():
            posture = "away"

        self.nest.update_resident_posture(elfie_id, posture, target or None)

    def _on_user_message(self, payload: Dict[str, Any]):
        """Parse one owner message into the Communication boundary only."""
        elfie_id = str(payload.get("elfie_id") or "").strip()
        message = str(payload.get("message") or "").strip()
        if elfie_id not in self.session.elfies or not message:
            return
        owner_id = str(payload.get("owner_id") or "owner").strip()
        conversation_id = str(
            payload.get("conversation_id") or f"owner:{owner_id}"
        ).strip()
        external_id = str(
            payload.get("message_id") or ""
        ).strip()
        self.session.send_user_message(
            elfie_id,
            message,
            owner_id=owner_id,
            conversation_id=conversation_id,
            external_message_id=external_id or None,
            account_id=str(payload.get("account_id") or "godot-owner"),
        )

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
        self.session.configure_cognition(SerializedRuntimeAdapter(runtime_agent))
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
