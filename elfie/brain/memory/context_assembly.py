"""5区域上下文组装：将检索结果组装为LLM prompt注入的上下文

从多个记忆子系统获取数据，组装为结构化文本，
注入到LLM的system prompt中，提供丰富的上下文信息。
"""

import logging
from typing import Dict, List

from elfie.brain.memory.core_cognition import CoreCognition
from elfie.brain.memory.ebbinghaus_decay import EbbinghausDecay
from elfie.brain.memory.emotion_weighting import EmotionWeighting
from elfie.brain.memory.graph_storage import GraphStorage
from elfie.brain.memory.node_types import MemoryNode, NodeTypes, RetrievalQuery
from elfie.brain.memory.retrieval import MemoryRetriever
from elfie.brain.memory.spreading_activation import SpreadingActivation

logger = logging.getLogger("elfie.brain.memory.context_assembly")


class ContextAssembler:
    """5区域上下文组装：将检索结果组装为LLM prompt注入的上下文"""

    def __init__(self, storage: GraphStorage, retriever: MemoryRetriever,
                 spreading: SpreadingActivation, decay: EbbinghausDecay,
                 weighting: EmotionWeighting, core_cognition: CoreCognition):
        self.storage = storage
        self.retriever = retriever
        self.spreading = spreading
        self.decay = decay
        self.weighting = weighting
        self.core_cognition = core_cognition

    def assemble(self, query: RetrievalQuery, top_k: int = 10) -> str:
        """组装5区域上下文文本

        流程：
        1. 用MemoryRetriever检索相关记忆
        2. 获取CoreCognition核心认知
        3. 从检索结果取种子节点做SpreadingActivation
        4. 顺序组装5个区域 + 核心认知前置

        返回格式（≤800 tokens）：
            【核心认知】
              - 我是XX，一只小狐狸。

            关于{实体}你知道什么：
              - 主人每天8点喂我

            最近相关经历：
              - 6/3 8点主人喂了我(0.8)

            联想到：
              - 鱼味食物

            预测灵感：
              - 现在8点主人走过来，可能要喂我了

            当前情绪对你记忆的影响：
              - 你现在很开心，更容易想起开心的事
        """
        # 1. 多维检索
        nodes = self.retriever.retrieve(query, top_k)

        # 2. 获取核心认知
        core_text = self.core_cognition.get_core_text()
        entities = query.current_entities
        seed_ids = [n.id for n in nodes[:5]]

        # 3. 组装各区域（只有非空区域才添加）
        zones: List[str] = []

        core_str = self._format_core_cognition(core_text)
        if core_str:
            zones.append(core_str)

        zone1 = self._assemble_entity_zone(entities)
        if zone1:
            zones.append(zone1)

        zone2 = self._assemble_recent_zone(nodes, query)
        if zone2:
            zones.append(zone2)

        zone3 = self._assemble_association_zone(seed_ids)
        if zone3:
            zones.append(zone3)

        zone4 = self._assemble_prediction_zone(
            query.recent_events, entities
        )
        if zone4:
            zones.append(zone4)

        zone5 = self._assemble_emotion_zone(
            query.current_emotion, query.current_intensity
        )
        if zone5:
            zones.append(zone5)

        return "\n\n".join(zones)

    # ------------------------------------------------------------------
    # 核心认知前置
    # ------------------------------------------------------------------

    def _format_core_cognition(self, core_text: Dict[str, str]) -> str:
        """格式化核心认知为LLM可读的列表文本"""
        if not core_text:
            return ""
        lines = ["【核心认知】"]
        for key in ["identity", "relation", "world", "tendency"]:
            text = core_text.get(key, "")
            if text:
                lines.append(f"  - {text}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 区域1：关于实体你知道什么
    # ------------------------------------------------------------------

    def _assemble_entity_zone(self, entities: List[str]) -> str:
        """区域1：从存储中查找entity节点，列出已知信息"""
        if not entities:
            return ""

        lines = [f"关于{', '.join(entities)}你知道什么："]
        all_entity_nodes = self.storage.get_nodes_by_type(
            NodeTypes.ENTITY.value, limit=1000
        )
        for entity_name in entities:
            matched = [
                n for n in all_entity_nodes if entity_name in n.content
            ]
            if matched:
                for node in matched:
                    lines.append(f"  - {node.content}")
            else:
                lines.append(f"  - 你对{entity_name}还不太了解")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 区域2：最近相关经历
    # ------------------------------------------------------------------

    def _assemble_recent_zone(
        self, nodes: List[MemoryNode], query: RetrievalQuery
    ) -> str:
        """区域2：列出最近的记忆节点，含记忆强度"""
        if not nodes:
            return ""

        lines = ["最近相关经历："]
        for node in nodes[:5]:
            strength = self.decay.compute_strength(
                node, query.current_time
            )
            timestamp = (
                node.metadata.get("timestamp")
                or node.created_at
                or ""
            )
            time_part = f"{timestamp} " if timestamp else ""
            lines.append(f"  - {time_part}{node.content}({strength:.1f})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 区域3：联想到（扩散激活结果）
    # ------------------------------------------------------------------

    def _assemble_association_zone(self, seed_ids: List[str]) -> str:
        """区域3：从种子节点出发做扩散激活，列出关联节点"""
        if not seed_ids:
            return ""

        activation = self.spreading.spread(seed_ids[:3])
        if not activation:
            return ""

        lines = ["联想到："]
        sorted_items = sorted(
            activation.items(), key=lambda x: x[1], reverse=True
        )
        for node_id, _act_score in sorted_items[:5]:
            node = self.storage.get_node(node_id)
            if node:
                lines.append(f"  - {node.content}")

        if len(lines) == 1:  # 所有节点都找不到内容
            return ""
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 区域4：预测灵感
    # ------------------------------------------------------------------

    def _assemble_prediction_zone(
        self, recent_events: List[str], entities: List[str]
    ) -> str:
        """区域4：基于最近事件和已知实体推测可能发展"""
        if not recent_events and not entities:
            return ""

        lines = ["预测灵感："]
        for event in recent_events[:3]:
            lines.append(f"  - 根据「{event}」推断后续发展")
        for entity in entities[:2]:
            lines.append(f"  - 与{entity}相关的可能事件")

        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 区域5：当前情绪对记忆的影响
    # ------------------------------------------------------------------

    def _assemble_emotion_zone(self, emotion: str, intensity: float) -> str:
        """区域5：当前情绪如何影响记忆检索权重"""
        if not emotion:
            return ""

        weights = self.weighting.get_weights(emotion)
        emotion_names = {
            "happy": "开心",
            "calm": "平静",
            "fear": "害怕",
            "sadness": "悲伤",
            "anger": "生气",
        }
        emotion_cn = emotion_names.get(emotion, emotion)

        lines = ["当前情绪对你记忆的影响："]
        lines.append(f"  - 你现在很{emotion_cn}（强度{intensity:.1f}）")
        lines.append(
            f"  - 检索权重：语义{weights['semantic']:.0%}、"
            f"情绪{weights['mood']:.0%}、"
            f"近时{weights['recency']:.0%}、"
            f"关联{weights['spread']:.0%}"
        )

        if intensity > 0.7:
            if emotion in ("happy", "calm"):
                lines.append(
                    "  - 强烈的正面情绪让你更容易想起愉快的事"
                )
            elif emotion in ("fear", "sadness", "anger"):
                lines.append(
                    "  - 强烈的负面情绪让你更容易想起相似经历"
                )

        return "\n".join(lines)
