"""感知缓冲：短期记忆暂存区

SensoryBuffer 是一个纯内存的短期记忆暂存区，用于暂存海量感官输入，
保持 1 小时的短时窗口，支持关键词检索和情感强度筛选。
速生速死——超过窗口的事件自动淘汰，超过容量上限时淘汰最旧事件。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("elfie.brain.memory.sensory_buffer")


class SensoryBuffer:
    """感知缓冲：短期记忆暂存区，1小时窗口，速生速死"""

    def __init__(self, max_size: int = 100, window_seconds: int = 3600):
        self.max_size = max_size
        self.window_seconds = window_seconds
        self._buffer: List[Dict[str, Any]] = []  # 每个事件是dict

    def add(
        self,
        event_content: str,
        emotion: str,
        intensity: float,
        stimulus: Optional[str] = None,
        sensory: Optional[Dict[str, Any]] = None,
    ) -> None:
        """写入感知事件，附带情绪/强度/刺激源/感官数据

        Args:
            event_content: 事件内容描述
            emotion: 情绪标签（如 "happy", "sad"）
            intensity: 情绪强度 (0~100)
            stimulus: 刺激源（如 "视觉", "听觉"）
            sensory: 感官数据字典（如 {"visual": "红色", "auditory": "噪音"})
        """
        event = {
            "content": event_content,
            "emotion": emotion,
            "intensity": intensity,
            "stimulus": stimulus,
            "sensory": sensory or {},
            "timestamp": datetime.now(),
        }
        self._buffer.append(event)
        logger.debug(
            f"感知事件已写入缓冲: [{emotion}] {event_content[:30]}..."
        )

        # 写入后检查容量，超过上限时淘汰最旧事件
        if len(self._buffer) > self.max_size:
            evicted = self._buffer.pop(0)  # 移除最旧事件
            logger.info(
                f"缓冲区容量超限，淘汰最旧事件: {evicted.get('content', '')[:30]}..."
            )

    def query(self, keywords: List[str], top_k: int = 5) -> List[Dict[str, Any]]:
        """简单关键词匹配检索缓冲区内容（不依赖SQLite）

        对每个事件的 content、stimulus 和 sensory 值做关键词匹配，
        按匹配关键词数量排序，返回 top_k 个最相关的事件。

        Args:
            keywords: 关键词列表
            top_k: 返回结果数量上限

        Returns:
            匹配的事件列表（按相关度降序）
        """
        if not self._buffer or not keywords:
            return []

        scored_events: List[tuple[int, Dict[str, Any]]] = []

        for event in self._buffer:
            match_count = 0
            # 在 content 中匹配
            content_text = event.get("content", "")
            # 在 stimulus 中匹配
            stimulus_text = event.get("stimulus") or ""
            # 在 sensory 值中匹配
            sensory_values = " ".join(
                str(v) for v in (event.get("sensory") or {}).values()
            )

            combined_text = f"{content_text} {stimulus_text} {sensory_values}".lower()

            for keyword in keywords:
                if keyword.lower() in combined_text:
                    match_count += 1

            if match_count > 0:
                scored_events.append((match_count, event))

        # 按匹配数降序排列
        scored_events.sort(key=lambda x: x[0], reverse=True)
        return [event for _, event in scored_events[:top_k]]

    def filter_candidates(
        self, threshold_intensity: float = 30.0
    ) -> List[Dict[str, Any]]:
        """筛选值得巩固的候选（intensity > threshold 或有 stimulus）

        Args:
            threshold_intensity: 强度阈值，高于此值的事件视为值得巩固

        Returns:
            值得巩固的事件列表
        """
        candidates = []
        for event in self._buffer:
            if event.get("intensity", 0) > threshold_intensity or event.get(
                "stimulus"
            ):
                candidates.append(event)
        return candidates

    def evict(self) -> None:
        """清除超过 window_seconds 的事件"""
        now = datetime.now()
        before_count = len(self._buffer)
        self._buffer = [
            event
            for event in self._buffer
            if (now - event.get("timestamp", now)).total_seconds()
            < self.window_seconds
        ]
        evicted_count = before_count - len(self._buffer)
        if evicted_count > 0:
            logger.info(
                f"淘汰了 {evicted_count} 个过期感知事件，剩余 {len(self._buffer)} 个"
            )

    def clear(self) -> None:
        """清空整个缓冲区（巩固后调用）"""
        self._buffer.clear()
        logger.info("感知缓冲区已清空")

    def __len__(self) -> int:
        """返回缓冲区当前事件数量"""
        return len(self._buffer)
