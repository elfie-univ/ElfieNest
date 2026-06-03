import asyncio
import http.server
import logging
import os
import socketserver
import threading
import time
from typing import Any, Dict, Optional

from elfie import ElfieIndividual

from .godot_api import GodotAPIServer
from .room import ElfieNestRoom

logger = logging.getLogger("elfienest.engine")


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """压制大量 HTTP 静态请求日志的极简 RequestHandler"""

    def log_message(self, format, *args):
        # 保持控制台日志干练清爽，仅在 Debug 时记录 HTTP 请求
        logger.debug(f"[语音服务器] 请求: {format % args}")


class ElfieNestCoordinator:
    """
    生态协调器兼物理触觉反射分配中心。
    兼容 main.py 现有接口，并在 Tick 发生时，将外界干预、碰撞等物理刺激转换为具身感官数据流，
    进而激活脑干自律物理反射弧或注入大脑丘脑。
    """

    def __init__(self, room: ElfieNestRoom, api_server: GodotAPIServer):
        self.room = room
        self.api_server = api_server

        # 缓存每个精灵积压的物理触觉感官包
        self.pending_tactile: Dict[str, Dict[str, Any]] = {}

    def register_elfie(self, elfie_id: str, elfie: ElfieIndividual):
        """兼容 main.py 接口：在房间中注册精灵"""
        self.room.register_elfie(elfie_id, elfie)

    def trigger_elfie_interaction(
        self, sender_id: str, receiver_id: str, event_type: str
    ):
        """
        兼容 main.py 接口：模拟一个物理碰撞/揉尾巴事件，
        将该刺激投递到对应精灵的具身触觉缓冲区中，以在下一个 Tick 激活脑干反射！
        """
        logger.info(
            f"💥 [物理刺激] 触发来自 '{sender_id}' 针对 '{receiver_id}' 的 {event_type} 交互"
        )

        if event_type == "collision":
            # 揉揉尾巴/拍一拍，完美对接 elfie_individual.py 的 Somatic Reflex
            self.pending_tactile[receiver_id] = {
                "impact_force": 1.5,
                "impact_direction": "back",
                "gentle_stroke": 1.0,
            }

            # 如果有 Godot 在线，将碰撞状态发送给 Godot 端同步播动作
            self.api_server.send_action(
                "physical_impact_event",
                {"elfie_id": receiver_id, "impact_type": "gentle_stroke"},
            )

    def consume_tactile(self, elfie_id: str) -> Dict[str, Any]:
        """消费并返回针对该精灵的物理触觉，消费后清空"""
        default_tactile = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 0.0,
        }
        return self.pending_tactile.pop(elfie_id, default_tactile)


class ElfieNestEngine:
    """
    ElfieNest 物理时钟游戏引擎的核心控制箱。
    内置 8000 端口的语音静态分发网关，8765 端口的 WebSocket 控制总线。
    管理多只精灵的具身逻辑、生理衰减以及高逼真度的 edge-tts 语音流水线。
    """

    def __init__(
        self, ws_host: str = "127.0.0.1", ws_port: int = 8765, http_port: int = 8000
    ):
        # 1. 实例化核心组件
        self.room = ElfieNestRoom()
        self.api_server = GodotAPIServer(host=ws_host, port=ws_port)
        self.coordinator = ElfieNestCoordinator(self.room, self.api_server)

        # 2. 音频分发参数
        self.http_port = http_port
        self.temp_audio_dir = os.path.abspath(
            os.path.join(os.getcwd(), "assets", "temp")
        )
        os.makedirs(self.temp_audio_dir, exist_ok=True)

        self.httpd: Optional[socketserver.TCPServer] = None
        self._http_thread: Optional[threading.Thread] = None

        # 3. 注册 Godot 事件回调以驱动 Python 看板
        self.api_server.register_callback(
            "register_scene", self._on_godot_scene_registered
        )
        self.api_server.register_callback("arrived_at", self._on_godot_elfie_arrived)

    def _start_http_server(self):
        """在独立线程中拉起极简语音静态分发服务器"""
        try:

            def handler(*args, **kwargs):
                return QuietHTTPRequestHandler(
                    *args, directory=self.temp_audio_dir, **kwargs
                )

            # 允许端口快速重用，避开 TIME_WAIT
            socketserver.TCPServer.allow_reuse_address = True
            self.httpd = socketserver.TCPServer(("127.0.0.1", self.http_port), handler)

            self._http_thread = threading.Thread(
                target=self.httpd.serve_forever,
                daemon=True,
                name="ElfieNest_HTTP_Thread",
            )
            self._http_thread.start()
            logger.info(
                f"🎵 [语音服务] 静态音频分发服务器已在 http://127.0.0.1:{self.http_port} 成功挂载！映射目录: {self.temp_audio_dir}"
            )
        except Exception as e:
            logger.error(f"❌ [语音服务] 启动 HTTP 服务失败，无法播放高品质语音: {e}")

    def _on_godot_scene_registered(self, payload: Dict[str, Any]):
        """Godot 场景握手回调：动态注册家具"""
        furniture = payload.get("furniture", [])
        self.room.register_scene_furniture(furniture)

    def _on_godot_elfie_arrived(self, payload: Dict[str, Any]):
        """Godot 精灵移动到达回调：锁定物理姿态"""
        elfie_id = payload.get("elfie_id")
        target = payload.get("target")

        # 解析预期的姿势。如果是床则躺下，椅子坐下，传送门消散
        posture = "standing"
        if "bed" in target.lower():
            posture = "lying"
        elif "chair" in target.lower():
            posture = "sitting"
        elif "door" in target.lower():
            posture = "away"

        self.room.update_elfie_posture(elfie_id, posture, target)

    async def _async_generate_tts(
        self, text: str, output_path: str, voice: str = "zh-CN-XiaoxiaoNeural"
    ):
        """异步调用 edge-tts 生成高品质微软 MP3 语音"""
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)

    def _synthesize_voice(self, elfie_id: str, text: str) -> Optional[str]:
        """
        线程安全地同步调用 edge-tts，生成 MP3 文件并返回可供 Godot 拉取的本地静态服务 URL。
        """
        if not text:
            return None

        filename = f"voice_{elfie_id}_{int(time.time() * 1000)}.mp3"
        output_path = os.path.join(self.temp_audio_dir, filename)

        try:
            # 优雅地在新事件循环中驱动异步 edge-tts 保存
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._async_generate_tts(text, output_path))
            loop.close()

            # 返回 HTTP 静态文件服务的下载链接
            audio_url = f"http://127.0.0.1:{self.http_port}/{filename}"
            logger.info(
                f"🎤 [语音服务] 精灵 '{elfie_id}' 发言音频合成成功 -> {audio_url}"
            )
            return audio_url
        except Exception as e:
            logger.warning(
                f"⚠️ [语音服务] edge-tts 合成失败 (可能是网络超时或包未完全安装)，优雅降级为空音频: {e}"
            )
            return None

    def start_loop(
        self, runtime_agent: Any, ticks_to_run: int = 3, interval_sec: float = 1.5
    ):
        """
        启动世界物理 Tick 仿真循环。
        兼容 main.py，并能够极其自适应地运行。如果检测到 Godot 客户端连入，
        将支持长效通信与 3D 群聊联动；若无连接，则优雅回退至本地终端仿真。
        """
        # 1. 启动 HTTP 语音服务器与 WebSocket 网络总线
        self._start_http_server()
        self.api_server.start()

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
                self.room.tick(interval_sec)

                # B. 多精灵并发具身认知感知与决策循环
                for elfie_id, elfie in list(self.room.elfies.items()):
                    status = self.room.room_state["elfies_status"].get(elfie_id, {})
                    if (
                        not status.get("active", True)
                        or status.get("posture") == "away"
                    ):
                        continue

                    # 1. 组装感官输入：包含群聊听到的话 + Coordinator 注入的物理碰撞触觉
                    pending_speech = self.room.consume_pending_sensory_input(elfie_id)
                    tactile_sensory = self.coordinator.consume_tactile(elfie_id)

                    raw_sensor_data = {
                        "has_new_message": bool(pending_speech),
                        "user_message": pending_speech if pending_speech else "",
                        **tactile_sensory,
                    }

                    logger.info(
                        f"👀 [具身感知] 精灵 '{elfie_id}' 正在感知环境: {raw_sensor_data}"
                    )

                    # 2. 激活大脑神经冲动闭环 (脑干反射弧检测 -> 丘脑组装 Context -> 皮层 LLM 决策)
                    response = elfie.perceive_and_respond(
                        raw_sensor_data, runtime_agent
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
                            self.room.broadcast_speech(elfie_id, speech_text)

                            # 5. 音频合成与播发
                            audio_url = self._synthesize_voice(elfie_id, speech_text)

                            # 发送发音和头顶文字气泡事件给 Godot
                            self.api_server.send_action(
                                "speak_event",
                                {
                                    "elfie_id": elfie_id,
                                    "text": speech_text,
                                    "audio_url": audio_url or "",
                                    "emotion": str(elfie.amygdala.get_dominant_mood()),
                                },
                            )

                        # 6. 转译并下发物理语义动作
                        if (
                            action
                            and action != "reflex_avoidance"
                            and action != "reflex_soothing"
                        ):
                            # 将大模型动作映射到语义家具目标
                            target_furniture = None
                            animation = "idle_loop"
                            posture = "standing"

                            # 动作词模糊匹配语义化家具
                            action_lower = action.lower()
                            if "sleep" in action_lower or "bed" in action_lower:
                                target_furniture = (
                                    "bed_1"  # 默认床 1，后续可实现动态选空闲床
                                )
                                posture = "lying"
                                animation = "sleep_loop"
                            elif (
                                "sit" in action_lower
                                or "chair" in action_lower
                                or "chat" in action_lower
                            ):
                                target_furniture = (
                                    "chair_1"  # 默认椅子 1，后续可实现动态选空闲椅
                                )
                                posture = "sitting"
                                animation = "chat_look"
                            elif (
                                "door" in action_lower
                                or "away" in action_lower
                                or "leave" in action_lower
                            ):
                                target_furniture = "wormhole_door"
                                posture = "away"
                                animation = "walk_loop"

                            if target_furniture:
                                # 更新房间被动意向状态
                                self.room.update_elfie_posture(
                                    elfie_id,
                                    f"moving_to_{target_furniture}",
                                    target_furniture,
                                )

                                # 下发给 Godot 去进行 3D 寻路与寻路到达 Area 的碰撞反馈
                                self.api_server.send_action(
                                    "go_to",
                                    {
                                        "elfie_id": elfie_id,
                                        "target": target_furniture,
                                        "posture": posture,
                                        "animation": animation,
                                    },
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
            if self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
            logger.info("🌈 [时间盒子] 仿真主循环已平稳落地退出。")
