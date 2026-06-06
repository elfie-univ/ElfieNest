"""情绪自适应加权模块。

根据当前情绪动态调整记忆检索的权重分配，
使检索结果更符合当前情绪状态下的认知偏好。
"""

from datetime import datetime, timedelta
from typing import Dict, Optional

from elfie.brain.memory.node_types import NodeTypes


class EmotionWeighting:
    """情绪自适应加权：根据当前情绪调整检索权重"""

    # 5种情绪权重配置（来自设计文档）
    EMOTION_WEIGHTS: Dict[str, Dict[str, float]] = {
        "calm":    {"semantic": 0.55, "mood": 0.15, "recency": 0.20, "spread": 0.10},
        "happy":   {"semantic": 0.40, "mood": 0.30, "recency": 0.15, "spread": 0.15},
        "fear":    {"semantic": 0.25, "mood": 0.45, "recency": 0.10, "spread": 0.20},
        "sadness": {"semantic": 0.30, "mood": 0.40, "recency": 0.15, "spread": 0.15},
        "anger":   {"semantic": 0.25, "mood": 0.40, "recency": 0.10, "spread": 0.25},
    }

    # 类型增强系数
    TYPE_BOOST: Dict[str, float] = {
        NodeTypes.EPISODIC: 1.0,
        NodeTypes.ENTITY: 1.1,
        NodeTypes.KNOWLEDGE: 1.3,
        NodeTypes.PATTERN: 1.5,
    }

    DEFAULT_WEIGHTS: Dict[str, float] = {
        "semantic": 0.40, "mood": 0.25, "recency": 0.20, "spread": 0.15,
    }

    def get_weights(self, emotion: str) -> Dict[str, float]:
        """获取当前情绪的权重配置，未知情绪返回默认权重。

        Args:
            emotion: 情绪名称（如 "calm", "happy"）

        Returns:
            包含 semantic / mood / recency / spread 权重的字典
        """
        return self.EMOTION_WEIGHTS.get(emotion, self.DEFAULT_WEIGHTS).copy()

    def compute_score(
        self,
        semantic_score: float,
        mood_score: float,
        recency_score: float,
        spread_score: float,
        memory_strength: float,
        node_type: str,
        emotion: str,
    ) -> float:
        """计算综合得分。

        公式（来自设计文档）：
            综合得分 = (
                w_semantic × semantic_score
              + w_mood     × mood_score
              + w_recency  × recency_score
              + w_spread   × spread_score
            ) × memory_strength × type_boost

        Args:
            semantic_score: 语义相似度得分 (0~1)
            mood_score: 情绪匹配得分 (0~1)
            recency_score: 时间近度得分 (0~1)
            spread_score: 扩散激活得分 (0~1)
            memory_strength: 记忆强度 (0~1)
            node_type: 节点类型（NodeTypes 值）
            emotion: 当前情绪名称

        Returns:
            综合得分（浮点数）
        """
        weights = self.get_weights(emotion)
        weighted_sum = (
            weights["semantic"] * semantic_score
            + weights["mood"] * mood_score
            + weights["recency"] * recency_score
            + weights["spread"] * spread_score
        )
        type_boost = self.get_type_boost(node_type)
        return weighted_sum * memory_strength * type_boost

    def compute_mood_score(
        self,
        memory_emotion: str,
        current_emotion: str,
        memory_intensity: float,
    ) -> float:
        """计算情绪匹配得分。

        同情绪 → 1.0 × intensity
        不同情绪 → 0.3 × intensity

        Args:
            memory_emotion: 记忆存储时的情绪
            current_emotion: 当前情绪
            memory_intensity: 记忆情绪强度 (0~1)

        Returns:
            情绪匹配得分 (0~1)
        """
        if memory_emotion == current_emotion:
            return 1.0 * memory_intensity
        return 0.3 * memory_intensity

    def compute_recency_score(
        self,
        memory_time: str,
        current_time: str,
    ) -> float:
        """计算时间近度得分。

        1小时内 → 1.0
        1天内   → 0.8
        7天内   → 0.5
        30天内  → 0.3
        更早    → 0.1

        Args:
            memory_time: 记忆时间（ISO 格式字符串）
            current_time: 当前时间（ISO 格式字符串）

        Returns:
            时间近度得分 (0~1)
        """
        try:
            mem_dt = datetime.fromisoformat(memory_time)
            cur_dt = datetime.fromisoformat(current_time)
        except (ValueError, TypeError):
            return 0.1

        delta = cur_dt - mem_dt

        if delta < timedelta(hours=1):
            return 1.0
        if delta < timedelta(days=1):
            return 0.8
        if delta < timedelta(days=7):
            return 0.5
        if delta < timedelta(days=30):
            return 0.3
        return 0.1

    def get_type_boost(self, node_type: str) -> float:
        """获取节点类型增强系数。

        Args:
            node_type: 节点类型（NodeTypes 值）

        Returns:
            类型增强系数，未知类型返回 1.0
        """
        return self.TYPE_BOOST.get(node_type, 1.0)
