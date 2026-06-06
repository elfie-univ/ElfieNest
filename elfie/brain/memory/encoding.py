"""编码引擎：将感知事件编码为记忆节点和边。

MemoryEncoder 负责将 SensoryBuffer 中的感知事件（如"看到一只鸟"、情绪波动等）
编码为图记忆中的 episodic 节点及与之关联的边（involves、temporal、emotional）。

编码流程：
1. 事件先进 SensoryBuffer（短期缓冲）
2. 高情绪强度（>30）或有刺激源的事件 → 创建 episodic 节点 + 关系边
3. 低情绪强度且无刺激源的事件 → 只停留在缓冲，不生成长期记忆
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .graph_storage import GraphStorage
from .node_types import EdgeTypes, MemoryNode, NodeTypes
from .sensory_buffer import SensoryBuffer

logger = logging.getLogger("elfie.brain.memory.encoding")


class MemoryEncoder:
    """编码引擎：将感知事件编码为记忆节点和边"""

    def __init__(self, storage: GraphStorage, sensory_buffer: SensoryBuffer):
        self.storage = storage
        self.sensory_buffer = sensory_buffer

    def encode(
        self,
        event_content: str,
        emotion: str,
        intensity: float,
        stimulus: str = None,
        sensory: dict = None,
        runtime_agent=None,
    ) -> str:
        """编码流程：
        1. 写入SensoryBuffer（事件先进缓冲）
        2. 如果intensity > 30.0 或有stimulus：创建episodic节点 + 边
        3. 如果intensity <= 30.0 且无stimulus：只写缓冲，不创建长期节点，返回空字符串
        4. 返回创建的episodic节点ID（或空字符串）
        """
        # 1. 事件始终先写入感知缓冲
        self.sensory_buffer.add(
            event_content=event_content,
            emotion=emotion,
            intensity=intensity,
            stimulus=stimulus,
            sensory=sensory,
        )

        # 2. 高情绪强度或有刺激源 → 创建长期记忆
        if intensity > 30.0 or stimulus:
            # 在创建当前节点前，先获取前一 episodic（避免取到自身）
            prev_node_id = self.get_previous_episodic()

            # 创建 episodic 节点
            node_id = self.create_episodic_node(
                content=event_content,
                emotion=emotion,
                intensity=intensity,
                stimulus=stimulus,
                sensory=sensory,
            )

            # 提取实体（Task 8 实现，当前返回空列表）
            entities = self.extract_entities(event_content, runtime_agent)

            # 建立编码边
            self.build_encoding_edges(node_id, entities, prev_node_id, emotion)

            logger.info(
                f"感知事件已编码: [{emotion}] {event_content[:40]}... → {node_id}"
            )
            return node_id

        # 3. 低强度且无刺激源 → 不进长期存储
        logger.debug(
            f"低强度事件仅写入缓冲区: [{emotion}] {event_content[:40]}..."
        )
        return ""

    def create_episodic_node(
        self,
        content: str,
        emotion: str,
        intensity: float,
        stimulus: str = None,
        sensory: dict = None,
    ) -> str:
        """创建episodic节点

        metadata包含: emotion, emotion_intensity, stimulus, importance=intensity/100,
                       recall_count=0, consolidated=False, timestamp=now
        """
        timestamp = datetime.now().isoformat()
        node_id = f"episodic_{datetime.now().timestamp()}"

        # 构建 metadata
        metadata: Dict[str, Any] = {
            "emotion": emotion,
            "emotion_intensity": intensity,
            "stimulus": stimulus,
            "importance": intensity / 100.0,
            "recall_count": 0,
            "consolidated": False,
            "timestamp": timestamp,
        }

        node = MemoryNode(
            id=node_id,
            type=NodeTypes.EPISODIC.value,
            content=content,
            metadata=metadata,
            created_at=timestamp,
            updated_at=timestamp,
        )

        self.storage.add_node(node)
        return node_id

    def build_encoding_edges(
        self,
        node_id: str,
        entities: List[str] = None,
        prev_node_id: str = None,
        emotion: str = None,
    ) -> None:
        """建立编码时3种边：
        - involves: episodic→entity, weight=0.9
        - temporal: 与前一个episodic, weight按时间间隔（<5min=0.9, <30min=0.7, <2h=0.5, >2h=0.3）
        - emotional: 与最近同情绪episodic, weight=0.6
        """
        entities = entities or []

        # involves 边：episodic → entity
        for entity_id in entities:
            self.storage.add_edge(
                source_id=node_id,
                target_id=entity_id,
                rel=EdgeTypes.INVOLVES.value,
                weight=0.9,
            )

        # temporal 边：前一个 episodic → 当前 episodic，按时间间隔计算权重
        if prev_node_id:
            prev_node = self.storage.get_node(prev_node_id)
            if prev_node:
                prev_ts_str = prev_node.metadata.get("timestamp")
                if prev_ts_str:
                    try:
                        prev_ts = datetime.fromisoformat(prev_ts_str)
                        now = datetime.now()
                        diff_minutes = (now - prev_ts).total_seconds() / 60.0

                        if diff_minutes < 5:
                            weight = 0.9
                        elif diff_minutes < 30:
                            weight = 0.7
                        elif diff_minutes < 120:  # 2小时
                            weight = 0.5
                        else:
                            weight = 0.3

                        self.storage.add_edge(
                            source_id=prev_node_id,
                            target_id=node_id,
                            rel=EdgeTypes.TEMPORAL.value,
                            weight=weight,
                        )
                    except (ValueError, TypeError):
                        logger.warning(
                            f"解析前驱节点时间戳失败: {prev_node_id}"
                        )

        # emotional 边：最近同情绪 episodic → 当前 episodic
        if emotion:
            similar_id = self.get_similar_emotion_episodic(
                emotion, exclude_id=node_id
            )
            if similar_id:
                self.storage.add_edge(
                    source_id=similar_id,
                    target_id=node_id,
                    rel=EdgeTypes.EMOTIONAL.value,
                    weight=0.6,
                )

    def get_previous_episodic(self, timestamp: str = None) -> Optional[str]:
        """获取时间最近的episodic节点ID

        按 created_at 降序排列，返回最近的一个 episodic 节点。
        如果数据库为空返回 None。
        """
        episodic_nodes = self.storage.get_nodes_by_type(
            NodeTypes.EPISODIC.value, limit=100
        )
        if not episodic_nodes:
            return None

        # 按创建时间降序，取最近的一个
        episodic_nodes.sort(key=lambda n: n.created_at or "", reverse=True)
        return episodic_nodes[0].id

    def get_similar_emotion_episodic(
        self, emotion: str, exclude_id: str = None
    ) -> Optional[str]:
        """获取最近同情绪的episodic节点ID

        在现有 episodic 节点中查找 emotion 相同的节点，
        按 created_at 降序返回最近的一个（排除 exclude_id 指定的节点）。

        Args:
            emotion: 情绪标签
            exclude_id: 排除的节点ID（通常为当前正在创建的节点）

        Returns:
            匹配的节点ID，无匹配返回 None
        """
        episodic_nodes = self.storage.get_nodes_by_type(
            NodeTypes.EPISODIC.value, limit=100
        )
        if not episodic_nodes:
            return None

        # 筛选相同情绪，排除当前节点
        matching = [
            n
            for n in episodic_nodes
            if n.metadata.get("emotion") == emotion
            and n.id != exclude_id
        ]
        matching.sort(key=lambda n: n.created_at or "", reverse=True)
        return matching[0].id if matching else None

    def extract_entities(
        self, content: str, runtime_agent=None
    ) -> List[str]:
        """提取实体名称（Task 8实现，现在返回空列表作为降级）"""
        return []
