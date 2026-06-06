import logging
from typing import Any, Dict, List

from elfie.brain.memory.vector_storage import TinyVectorStorage

logger = logging.getLogger("elfie.brain.memory.episode_manager")


class EpisodeMemoryManager:
    """中层：海马体情景记忆管理器 (Episode Memory Manager)"""

    def __init__(self, storage_path: str = None):
        self.storage = TinyVectorStorage(storage_path)

    def record_episode(
        self,
        event_description: str,
        emotion_tag: str = "calm",
        emotion_intensity: float = 0.0,
    ):
        """
        录入一条新发生的具体情景经历
        :param event_description: 发生的具体经历流水账
        :param emotion_tag: 经历关联的情绪标签
        :param emotion_intensity: 情绪强度 (0-100)
        """
        logger.info(f"💾 [海马体录入经历]: '{event_description}' (情绪: {emotion_tag})")
        self.storage.add_memory(
            text=event_description,
            tags={"emotion": emotion_tag},
            intensity=emotion_intensity,
        )

    def retrieve_relevant_memories(
        self, query: str, level: str = None, current_emotion: str = None
    ) -> List[str]:
        """检索出语义高度关联的情景经历"""
        return self.storage.retrieve_relevant_memories(
            query, top_k=2, level=level, current_emotion=current_emotion
        )

    def get_all_episodes(self) -> List[Dict[str, Any]]:
        """获取所有存盘的经历索引数据"""
        return self.storage.memories
