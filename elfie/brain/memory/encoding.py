"""编码引擎：将感知事件编码为记忆节点和边。

MemoryEncoder 负责将 SensoryBuffer 中的感知事件（如"看到一只鸟"、情绪波动等）
编码为图记忆中的 episodic 节点及与之关联的边（involves、temporal、emotional）。

编码流程：
1. 事件先进 SensoryBuffer（短期缓冲）
2. 高情绪强度（>30）或有刺激源的事件 → 创建 episodic 节点 + 关系边
3. 低情绪强度且无刺激源的事件 → 只停留在缓冲，不生成长期记忆
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .graph_storage import GraphStorage
from .node_types import EdgeTypes, MemoryNode, NodeTypes
from .runtime_food import ask_memory_model
from .sensory_buffer import SensoryBuffer
from .sensory_index import SensoryIndexer

logger = logging.getLogger("elfie.brain.memory.encoding")


class MemoryEncoder:
    """编码引擎：将感知事件编码为记忆节点和边"""

    # 内置实体词典（规则优先，不依赖外部配置文件）
    ENTITY_DICT = {
        "主人": "person",
        "食物": "food",
        "鱼味": "food",
        "鸡肉": "food",
        "厨房": "place",
        "客厅": "place",
        "花园": "place",
        "猫": "animal",
        "狗": "animal",
        "球": "toy",
    }

    def __init__(
        self,
        storage: GraphStorage,
        sensory_buffer: SensoryBuffer,
        sensory_indexer: SensoryIndexer = None,
        elfie_id: str | None = None,
        config_dir: str | None = None,
    ):
        self.storage = storage
        self.sensory_buffer = sensory_buffer
        self.sensory_indexer = sensory_indexer
        self.elfie_id = elfie_id
        self.config_dir = config_dir

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

            # 感官索引：将感官关键词持久化到 sensory_index 表
            if sensory and self.sensory_indexer:
                self.sensory_indexer.index_sensory(node_id, sensory)

            # 提取实体名称 → 转换为节点ID
            entity_names = self.extract_entities(event_content, runtime_agent)
            entity_ids = [self.create_or_get_entity(name) for name in entity_names]

            # 建立编码边
            self.build_encoding_edges(node_id, entity_ids, prev_node_id, emotion)

            logger.info(
                f"感知事件已编码: [{emotion}] {event_content[:40]}... → {node_id}"
            )
            return node_id

        # 3. 低强度且无刺激源 → 不进长期存储
        logger.debug(f"低强度事件仅写入缓冲区: [{emotion}] {event_content[:40]}...")
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
                        logger.warning(f"解析前驱节点时间戳失败: {prev_node_id}")

        # emotional 边：最近同情绪 episodic → 当前 episodic
        if emotion:
            similar_id = self.get_similar_emotion_episodic(emotion, exclude_id=node_id)
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
            if n.metadata.get("emotion") == emotion and n.id != exclude_id
        ]
        matching.sort(key=lambda n: n.created_at or "", reverse=True)
        return matching[0].id if matching else None

    def extract_entities(self, content: str, runtime_agent=None) -> List[str]:
        """提取实体名称（规则优先+LLM兜底）

        1. 先用内置词典匹配内容中的关键词
        2. 如果runtime_agent可用且词典匹配不足，用LLM提取更多实体
        3. LLM失败时降级为纯规则匹配
        4. 返回实体名称列表（去重，保留出现顺序）

        Args:
            content: 待提取实体的文本内容
            runtime_agent: 可选的LLM运行时代理，为None时只使用规则匹配

        Returns:
            实体名称列表
        """
        if not content:
            return []

        # 1. 规则匹配：扫描内容中出现的关键词，按出现位置排序
        matched_entities = []
        for keyword in self.ENTITY_DICT:
            if keyword in content:
                pos = content.find(keyword)
                matched_entities.append((pos, keyword))
        # 按出现位置升序排列，保持内容中的自然顺序
        matched_entities.sort(key=lambda x: x[0])
        matched_entities = [kw for _, kw in matched_entities]

        # 2. 如果runtime_agent可用，尝试LLM提取补充实体
        if runtime_agent is not None:
            try:
                prompt = (
                    "从以下文本中提取出所有实体名称（人名、地名、物品名等），"
                    "只返回实体名称，每行一个，不要序号和额外说明：\n\n"
                    f"{content}"
                )
                response = ask_memory_model(
                    runtime_agent,
                    prompt,
                    elfie_id=self.elfie_id,
                    config_dir=self.config_dir,
                    food_key="coarse",
                    complexity=1,
                )
                if response and response.strip():
                    # 解析LLM返回的实体（按行分割，去空格）
                    llm_entities = [
                        line.strip()
                        for line in response.strip().split("\n")
                        if line.strip()
                    ]
                    # 合并规则匹配和LLM提取结果
                    combined = list(dict.fromkeys(matched_entities + llm_entities))
                    # 幻觉防护：只保留确实出现在原文中的实体名称
                    result = [e for e in combined if e in content]
                    return result
            except Exception:
                logger.warning("LLM实体提取失败，降级为纯规则匹配")

        # 3. 降级：纯规则匹配结果
        return matched_entities

    def check_entity_exists(self, entity_name: str) -> Optional[str]:
        """检查SQLite是否已有该实体节点

        按content精确匹配查询已有entity类型节点。
        如果已存在返回node_id，否则返回None。

        Args:
            entity_name: 实体名称

        Returns:
            节点ID或None
        """
        cursor = self.storage.conn.execute(
            "SELECT id FROM nodes WHERE type=? AND content=? LIMIT 1",
            (NodeTypes.ENTITY.value, entity_name),
        )
        row = cursor.fetchone()
        return row["id"] if row else None

    def create_or_get_entity(self, entity_name: str, properties: dict = None) -> str:
        """创建或获取实体节点（去重）

        如果已存在同名实体节点，返回现有node_id。
        如果不存在，创建新的entity类型节点并返回node_id。
        新节点自动从ENTITY_DICT获取实体类型标签。

        Args:
            entity_name: 实体名称
            properties: 额外属性（可选，会合并到metadata中）

        Returns:
            节点ID
        """
        # 检查是否已存在同名实体
        existing_id = self.check_entity_exists(entity_name)
        if existing_id:
            logger.debug(f"实体已存在: {entity_name} → {existing_id}")
            return existing_id

        # 创建新实体节点
        timestamp = datetime.now().isoformat()
        node_id = f"entity_{datetime.now().timestamp()}"

        metadata: Dict[str, Any] = {
            "entity_type": self.ENTITY_DICT.get(entity_name, "unknown"),
        }
        if properties:
            metadata.update(properties)

        node = MemoryNode(
            id=node_id,
            type=NodeTypes.ENTITY.value,
            content=entity_name,
            metadata=metadata,
            created_at=timestamp,
            updated_at=timestamp,
        )

        self.storage.add_node(node)
        logger.info(
            f"✨ 新实体已创建: {entity_name} ({metadata['entity_type']}) → {node_id}"
        )
        return node_id
