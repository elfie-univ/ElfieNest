"""Ebbinghaus衰减遗忘计算模块。

根据艾宾浩斯遗忘曲线原理，计算记忆节点的强度衰减。
使用指数衰减公式：strength = importance × e^(-k × t / stability)
"""

import math
from datetime import datetime
from typing import Optional

from elfie.brain.memory.node_types import MemoryNode


class EbbinghausDecay:
    """Ebbinghaus衰减遗忘计算器。

    根据记忆类型、时间差、回忆次数和情绪强度，计算记忆的当前强度。
    """

    # 半衰期配置（天）
    HALF_LIVES = {
        "episodic": 7,  # 情景记忆7天半衰期
        "entity": 365,  # 实体记忆365天半衰期
        "knowledge": 30,  # 知识记忆30天半衰期
        "pattern": 60,  # 模式记忆60天半衰期
    }

    # 鬼影底线
    GHOST_FLOOR = 0.05  # strength永远不低于0.05

    def compute_strength(self, node: MemoryNode, current_time: str = None) -> float:
        """计算节点当前记忆强度。

        公式：strength = importance × e^(-k × t / stability)
        其中：
        - k = ln(2) / half_life
        - t = 时间差（天）
        - stability = 1.0 + 0.2 × recall_count

        调节：
        - 高情绪(intensity > 0.7) → 半衰期 × 1.5
        - 每次回忆 → recall_count + 1, stability + 20%

        鬼影底线：strength永远不低于0.05

        Args:
            node: 记忆节点
            current_time: 当前时间（ISO格式字符串），None则用当前实际时间

        Returns:
            记忆强度值（0.05 ~ importance）
        """
        importance = node.metadata.get("importance", 0.5)
        recall_count = node.metadata.get("recall_count", 0)
        emotion_intensity = node.metadata.get("emotion_intensity", 0.0)

        half_life = self.get_half_life(node.type, emotion_intensity)
        stability = self.get_stability(recall_count)
        t = self._time_diff_days(node.created_at, current_time)
        k = math.log(2) / half_life

        strength = importance * math.exp(-k * t / stability)
        return max(strength, self.GHOST_FLOOR)

    def compute_decay(self, node: MemoryNode, current_time: str = None) -> float:
        """计算衰减比例（0-1），1=完全衰减，0=无衰减。

        公式：decay = 1 - strength / importance

        Args:
            node: 记忆节点
            current_time: 当前时间（ISO格式字符串）

        Returns:
            衰减比例（0~1）
        """
        importance = node.metadata.get("importance", 0.5)
        if importance <= 0:
            return 1.0
        strength = self.compute_strength(node, current_time)
        raw_decay = 1.0 - (strength / importance)
        return max(0.0, min(1.0, raw_decay))

    def get_half_life(self, node_type: str, emotion_intensity: float = 0.0) -> float:
        """获取半衰期（考虑情绪增强）。

        高情绪（intensity > 0.7）时，半衰期 × 1.5，记忆更持久。

        Args:
            node_type: 节点类型（NodeTypes值）
            emotion_intensity: 情绪强度（0~1）

        Returns:
            半衰期（天）
        """
        half_life = self.HALF_LIVES.get(node_type, 30)
        if emotion_intensity > 0.7:
            half_life *= 1.5
        return half_life

    def get_stability(self, recall_count: int) -> float:
        """获取稳定性系数。

        每次回忆增加20%稳定性：stability = 1.0 + 0.2 × recall_count

        Args:
            recall_count: 回忆次数

        Returns:
            稳定性系数
        """
        return 1.0 + 0.2 * recall_count

    def _time_diff_days(
        self, created_at: Optional[str], current_time: Optional[str] = None
    ) -> float:
        """计算时间差（天）。

        自动处理 timezone-naive 和 timezone-aware 的混合输入：
        如果 t_start 有时区信息而 t_end 没有（或反之），将两者都转为 naive。

        Args:
            created_at: 创建时间（ISO格式）
            current_time: 当前时间（ISO格式），None则用实际当前时间

        Returns:
            时间差（天），最小为0
        """
        if not created_at:
            return 0.0
        t_start = datetime.fromisoformat(created_at)
        if current_time:
            t_end = datetime.fromisoformat(current_time)
        else:
            t_end = datetime.now()

        # 统一时区：如果两者时区不一致，都转为 naive
        if t_start.tzinfo is not None and t_end.tzinfo is None:
            t_start = t_start.replace(tzinfo=None)
        elif t_end.tzinfo is not None and t_start.tzinfo is None:
            t_end = t_end.replace(tzinfo=None)

        delta = t_end - t_start
        return max(0.0, delta.total_seconds() / 86400.0)
