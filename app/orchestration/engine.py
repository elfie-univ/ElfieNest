import logging
import os
import time
from typing import Any, Dict, Optional

from elfie.body import BodyCommand, BodyEvent
from elfie.profile import AppearanceResolver
from app.infrastructure.audio.server import AudioServer
from app.infrastructure.audio.tts import async_generate_tts, synthesize_voice
from app.orchestration.nest_session import NestSession
from nest import Nest, NestConfig
from nest.godot.action_mapper import map_action_to_world
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

        # 2. 音频分发参数
        self.http_port = http_port
        self.temp_audio_dir = os.path.abspath(
            os.path.join(os.getcwd(), "data", "temp", "audio")
        )
        os.makedirs(self.temp_audio_dir, exist_ok=True)

        self.audio_server = AudioServer(
            directory=self.temp_audio_dir, port=self.http_port
        )

        # 3. 注册 Godot 事件回调以驱动 Python 看板
        self.api_server.register_callback(
            "register_scene", self._on_godot_scene_registered
        )
        self.api_server.register_callback("runtime_ready", self._on_godot_runtime_ready)
        self.api_server.register_callback("arrived_at", self._on_godot_elfie_arrived)
        self.api_server.register_callback("user_message", self._on_user_message)

        # 4. 可选的鉴权 WebSocket 管理网关（由 app.py 注入，None 则不启用）
        self.ws_manager: Optional[Any] = None

    def _start_http_server(self):
        """在独立线程中拉起极简语音静态分发服务器"""
        self.audio_server.start()

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
        """处理用户通过 WebSocket 发送的消息"""
        elfie_id = payload.get("elfie_id", "")
        message = payload.get("message", "")
        if elfie_id and message:
            self.session.send_user_message(elfie_id, message)

    async def _async_generate_tts(
        self, text: str, output_path: str, voice: str = "zh-CN-XiaoxiaoNeural"
    ):
        """异步调用 edge-tts 生成高品质微软 MP3 语音"""
        await async_generate_tts(text, output_path, voice)

    def _synthesize_voice(self, elfie_id: str, text: str) -> Optional[str]:
        """
        线程安全地同步调用 edge-tts，生成 MP3 文件并返回可供 Godot 拉取的本地静态服务 URL。
        """
        return synthesize_voice(
            elfie_id=elfie_id,
            text=text,
            temp_audio_dir=self.temp_audio_dir,
            http_port=self.http_port,
            tts_enabled=self.tts_enabled,
        )

    def _collect_world_sensory_events(self, elfie_id: str) -> list[BodyEvent]:
        """把房间和管理端输入转换成身体层统一感官事件。"""
        events: list[BodyEvent] = []
        pending_speech = self.nest.consume_sensory_input(elfie_id)
        if pending_speech:
            events.append(
                BodyEvent(
                    sensor="hearing",
                    source="nest:room_speech",
                    payload={"user_message": pending_speech},
                )
            )

        user_message = self.session.consume_user_message(elfie_id)
        if user_message:
            events.append(
                BodyEvent(
                    sensor="hearing",
                    source="nest:owner_message",
                    payload={"user_message": user_message},
                )
            )

        tactile = self.session.consume_tactile(elfie_id)
        if (
            float(tactile.get("impact_force", 0.0)) > 0.0
            or float(tactile.get("gentle_stroke", 0.0)) > 0.0
        ):
            events.append(
                BodyEvent(
                    sensor="touch",
                    source="nest:physical_interaction",
                    payload=tactile,
                )
            )
        return events

    @staticmethod
    def _execute_body_command(
        elfie: Any, command: BodyCommand
    ) -> Optional[Dict[str, Any]]:
        """通过精灵的神经系统控制当前身体；未装配身体时只记录告警。"""
        if getattr(elfie, "current_body", None) is None:
            logger.warning(
                "精灵 %s 尚未绑定身体，跳过动作 %s",
                getattr(getattr(elfie, "identity", None), "elfie_id", "unknown"),
                command.action,
            )
            return None
        return elfie.execute_body_command(command).to_dict()

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
        # 1. 启动 HTTP 语音服务器与 WebSocket 网络总线
        self._start_http_server()
        self.api_server.start()
        if self.ws_manager:
            self.ws_manager.start()

        logger.info(
            f"⏳ [时间盒子] 物理仿真启动。总计运行 {ticks_to_run} 个 Tick 周期，每个周期阻尼间歇 {interval_sec} 秒..."
        )

        current_tick = 0
        try:
            while current_tick < ticks_to_run:
                current_tick += 1
                logger.info(
                    f"\n====================== 🌀 PHYSICS TICK {current_tick}/{ticks_to_run} ======================"
                )

                # A. 物理 Tick 驱动边缘衰减与能耗 (更新下丘脑生理钟和情绪衰减)
                self.nest.tick(interval_sec)
                self.session.tick_elfies(interval_sec)

                # B. 多精灵并发具身认知感知与决策循环
                for elfie_id, elfie in list(self.session.elfies.items()):
                    status = self.nest.resident_state(elfie_id)
                    if status is None or not status.active or status.posture == "away":
                        continue

                    # 1. 当前身体事件与房间补充事件统一进入神经系统。
                    world_events = self._collect_world_sensory_events(elfie_id)
                    logger.info(
                        "👀 [具身感知] 精灵 '%s' 收到 %s 条身体事件",
                        elfie_id,
                        len(world_events),
                    )

                    # 2. 激活大脑神经冲动闭环 (脑干反射弧检测 -> 丘脑组装 Context -> 皮层 LLM 决策)
                    response = elfie.respond_to_body_events(
                        world_events, runtime_agent
                    )

                    # 3. 处理具身决策响应结果
                    if response.get("success", False):
                        speech_text = response.get("speech", "")
                        action = response.get("action", "")
                        mutter = response.get("mutter", "")

                        logger.info(
                            f"💬 [具身响应] 精灵 '{elfie_id}' 发言: \"{speech_text}\" (碎碎念: {mutter})"
                        )
                        logger.info(
                            f"🏃 [具身响应] 精灵 '{elfie_id}' 执行物理意图: {action}"
                        )

                        # 4. 路由群聊广播：听到同伴的声音
                        if speech_text:
                            self.nest.broadcast_speech(elfie_id, speech_text)

                            # 5. 音频合成与播发
                            audio_url = self._synthesize_voice(elfie_id, speech_text)

                            # 发音和头顶文字气泡通过当前身体执行。
                            speech_execution = self._execute_body_command(
                                elfie,
                                BodyCommand(
                                    action="speech.say",
                                    parameters={
                                        "speech": speech_text,
                                        "audio_url": audio_url or "",
                                        "emotion": str(
                                            elfie.amygdala.get_dominant_mood()
                                        ),
                                    },
                                ),
                            )
                            if speech_execution is not None:
                                response.setdefault("body_executions", []).append(
                                    speech_execution
                                )

                            # 通过鉴权 WS 网关只向该精灵的 owner + Owner推送
                            if self.ws_manager:
                                self.ws_manager.broadcast_to_owners(
                                    elfie_id,
                                    {
                                        "action": "speak_event",
                                        "payload": {
                                            "elfie_id": elfie_id,
                                            "text": speech_text,
                                            "audio_url": audio_url or "",
                                            "emotion": str(
                                                elfie.amygdala.get_dominant_mood()
                                            ),
                                        },
                                    },
                                )

                        # 6. 转译并通过当前身体下发物理语义动作。
                        if action:
                            world_action = map_action_to_world(action)

                            if world_action:
                                # 更新房间被动意向状态
                                self.nest.update_resident_posture(
                                    elfie_id,
                                    f"moving_to_{world_action.target_furniture}",
                                    world_action.target_furniture,
                                )

                                command = BodyCommand(
                                    action="movement.go_to",
                                    parameters={
                                        "target": world_action.target_furniture,
                                        "posture": world_action.posture,
                                        "animation": world_action.animation,
                                    },
                                )
                            else:
                                command = BodyCommand(
                                    action=action,
                                    parameters={
                                        "mutter": mutter,
                                        "joint_angles": response.get(
                                            "joint_angles", {}
                                        ),
                                    },
                                )
                            action_execution = self._execute_body_command(
                                elfie, command
                            )
                            if action_execution is not None:
                                response.setdefault("body_executions", []).append(
                                    action_execution
                                )
                    else:
                        logger.warning(
                            f"⚠️ [时钟驱动] 精灵 '{elfie_id}' 心智决策略过: {response.get('reason')}"
                        )

                # 阻尼间歇，维持稳定仿真速率
                time.sleep(interval_sec)

        except KeyboardInterrupt:
            logger.info("👋 收到键盘中断，正在强行收束物理世界...")
        finally:
            # 清理套接字和服务线程，防止端口占用死锁
            self.api_server.stop()
            self.audio_server.stop()
            if self.ws_manager:
                self.ws_manager.stop()
            logger.info("🌈 [时间盒子] 仿真主循环已平稳落地退出。")
