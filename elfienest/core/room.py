import logging
from typing import Any, Dict, List, Optional

from elfie import ElfieIndividual

logger = logging.getLogger("elfienest.core.room")


class RoomFullError(Exception):
    """房间已满异常。"""

    pass


class ElfieNestRoom:
    """
    宿舍空间容器 - 整个 ElfieNest 系统的唯一状态维护与消息路由核心。
    维护所有精灵实例，动态看板，并实现精灵间的群聊广播机制。
    """

    def __init__(
        self,
        max_elfies_per_room: Optional[int] = None,
    ):
        """初始化房间。

        Args:
            max_elfies_per_room: 房间最大精灵数，None 表示无限制
        """
        # 0. 房间容量限制
        self.max_elfies_per_room = max_elfies_per_room

        # 1. 灵魂容器：保存注册进来的小精灵实例 {elfie_id: ElfieIndividual}
        self.elfies: Dict[str, ElfieIndividual] = {}

        # 2. 动态语义状态看板，仅记录"谁在什么家具上做什么"，不涉及任何坐标
        self.room_state: Dict[str, Any] = {
            "furniture": {},  # 由 Godot 动态注册，格式: { "bed_1": {"occupant": "艾菲"} }
            "elfies_status": {},  # 格式: { "elfie_id": { "posture": "standing", "target_furniture": None, "active": True } }
        }

        # 3. 待分发给各精灵的群聊感知消息缓冲 {elfie_id: [messages]}
        self.sensory_buffers: Dict[str, List[str]] = {}

    def register_elfie(self, elfie_id: str, elfie_instance: ElfieIndividual):
        """将精灵实例注入并注册到该宿舍房间中。

        Raises:
            RoomFullError: 房间已满
        """
        if self.max_elfies_per_room is not None:
            if len(self.elfies) >= self.max_elfies_per_room:
                raise RoomFullError(
                    f"房间已满 ({len(self.elfies)}/{self.max_elfies_per_room})"
                )

        elfie_instance.bind_identity(elfie_id)
        self.elfies[elfie_id] = elfie_instance
        self.room_state["elfies_status"][elfie_id] = {
            "posture": "standing",
            "target_furniture": None,
            "active": True,
        }
        self.sensory_buffers[elfie_id] = []
        logger.info(f"✨ [房间容器] 精灵 '{elfie_id}' 已成功注册并入住精灵仓！")

    def register_scene_furniture(self, furniture_list: List[str]):
        """
        根据 Godot 客户端上报的 3D 家具节点，动态更新家具状态看板，实现零硬编码。
        """
        # 保留原有的占用信息（如果有的话），初始化新家具
        current_furniture = self.room_state["furniture"]
        new_furniture = {}
        for f_name in furniture_list:
            if f_name in current_furniture:
                new_furniture[f_name] = current_furniture[f_name]
            else:
                new_furniture[f_name] = {"occupant": None}
        self.room_state["furniture"] = new_furniture
        logger.info(
            f"🧱 [房间容器] 动态加载 Godot 场景成功，已注册语义化家具看板: {list(self.room_state['furniture'].keys())}"
        )

    def broadcast_speech(self, sender_id: str, speech_text: str):
        """
        室内群聊广播：将精灵 A 的发言广播给房间内的所有其他活跃精灵。
        这会暂存到其它精灵的感知缓冲中，在它们下次进行 perceive_and_respond 时被消费。
        """
        if not speech_text:
            return

        broadcast_msg = f'[{sender_id} 说道]: "{speech_text}"'
        for elfie_id in self.elfies:
            if elfie_id != sender_id:
                status = self.room_state["elfies_status"].get(elfie_id, {})
                if status.get("active", True) and status.get("posture") != "away":
                    self.sensory_buffers[elfie_id].append(broadcast_msg)
                    logger.info(
                        f"📣 [群聊广播] 已将 '{sender_id}' 的发言暂存到 '{elfie_id}' 的感知缓冲中"
                    )

    def consume_pending_sensory_input(self, elfie_id: str) -> str:
        """
        消费并清除该精灵累积的所有未读广播消息，将其拼接成一段上下文，作为 perceive 的感知输入。
        """
        buffers = self.sensory_buffers.get(elfie_id, [])
        if not buffers:
            return ""

        # 拼接所有听到的话并清空缓冲
        combined_speech = "；".join(buffers)
        self.sensory_buffers[elfie_id] = []
        return combined_speech

    def update_elfie_posture(
        self, elfie_id: str, posture: str, target_furniture: str = None
    ):
        """
        更新精灵的动作姿态和家具绑定状态
        """
        if elfie_id not in self.room_state["elfies_status"]:
            return

        old_furniture = self.room_state["elfies_status"][elfie_id]["target_furniture"]

        # 1. 释放原家具占用
        if old_furniture and old_furniture in self.room_state["furniture"]:
            if self.room_state["furniture"][old_furniture]["occupant"] == elfie_id:
                self.room_state["furniture"][old_furniture]["occupant"] = None

        # 2. 绑定新家具
        if target_furniture and target_furniture in self.room_state["furniture"]:
            self.room_state["furniture"][target_furniture]["occupant"] = elfie_id

        # 3. 更新精灵状态
        self.room_state["elfies_status"][elfie_id]["posture"] = posture
        self.room_state["elfies_status"][elfie_id]["target_furniture"] = (
            target_furniture
        )
        logger.info(
            f"🔄 [房间状态] 精灵 '{elfie_id}' 状态更新为 姿势={posture}, 绑定家具={target_furniture}"
        )

    def tick(self, dt: float):
        """
        由物理盒子主循环驱动，并发 Tick 房间内的所有活跃小精灵，推进它们的生理和心智周期
        """
        for elfie_id, elfie in self.elfies.items():
            status = self.room_state["elfies_status"].get(elfie_id, {})
            # 只有当精灵活跃且未离开（away）时才进行 Tick
            if status.get("active", True) and status.get("posture") != "away":
                elfie.tick(dt)
