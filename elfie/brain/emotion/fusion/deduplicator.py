"""
Emotion Fusion Deduplicator Module

提供事件去重和强度融合功能，用于情绪系统中的事件去重处理。
"""

import time
from typing import Dict, List, Optional


class EventDeduplicator:
    """
    事件去重器

    使用TTL机制维护已处理事件的集合，自动清理过期事件。
    """

    def __init__(self, ttl: float = 60.0):
        """
        初始化去重器

        Args:
            ttl: 事件保留时间（秒），默认60秒
        """
        self.ttl = ttl
        self.processed_events: Dict[str, float] = {}  # event_id -> timestamp

    def is_new(self, event_id: str, current_time: Optional[float] = None) -> bool:
        """
        检查事件是否为新事件（未处理过）

        Args:
            event_id: 事件ID
            current_time: 当前时间戳，默认使用time.time()

        Returns:
            True表示新事件，False表示已处理过
        """
        if current_time is None:
            current_time = time.time()
        self._clean_expired(current_time)
        return event_id not in self.processed_events

    def mark_processed(self, event_id: str, current_time: Optional[float] = None):
        """
        标记事件为已处理

        Args:
            event_id: 事件ID
            current_time: 当前时间戳，默认使用time.time()
        """
        if current_time is None:
            current_time = time.time()
        self.processed_events[event_id] = current_time

    def _clean_expired(self, current_time: float):
        """
        清理过期事件

        Args:
            current_time: 当前时间戳
        """
        expired = [
            eid
            for eid, ts in self.processed_events.items()
            if current_time - ts > self.ttl
        ]
        for eid in expired:
            del self.processed_events[eid]

    def get_active_count(self) -> int:
        """获取当前活跃事件数量"""
        return len(self.processed_events)

    def clear(self):
        """清空所有记录"""
        self.processed_events.clear()


def fuse_intensities(
    intensities: List[float], weights: Optional[List[float]] = None
) -> float:
    """
    加权平均融合多个强度值

    Args:
        intensities: 强度值列表
        weights: 权重列表，默认等权重

    Returns:
        加权平均后的强度值

    Raises:
        ValueError: intensities和weights长度不匹配，或列表为空
    """
    if not intensities:
        raise ValueError("intensities list cannot be empty")

    if weights is None:
        weights = [1.0] * len(intensities)

    if len(intensities) != len(weights):
        raise ValueError("intensities and weights must have same length")

    total = sum(i * w for i, w in zip(intensities, weights))
    weight_sum = sum(weights)
    return total / weight_sum if weight_sum > 0 else 0.0
