import logging
from typing import Any, Dict

from elfie import ElfieIndividual

from .room import ElfieNestRoom
from .transport.godot_api import GodotAPIServer

logger = logging.getLogger("elfienest.coordinator")


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

        # 用户消息缓冲（WebSocket 入站）
        self.pending_messages: Dict[str, str] = {}

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

    def send_user_message(self, elfie_id: str, message: str):
        """接收来自 WebSocket 客户端的用户消息，缓存到下一个 tick"""
        self.pending_messages[elfie_id] = message
        logger.info(f"💬 [用户消息] 收到给 '{elfie_id}' 的消息: {message}")

    def consume_user_message(self, elfie_id: str) -> str:
        """消费并返回该精灵的用户消息，消费后清空"""
        return self.pending_messages.pop(elfie_id, "")

    def consume_tactile(self, elfie_id: str) -> Dict[str, Any]:
        """消费并返回针对该精灵的物理触觉，消费后清空"""
        default_tactile = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 0.0,
        }
        return self.pending_tactile.pop(elfie_id, default_tactile)
