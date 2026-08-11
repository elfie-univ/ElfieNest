"""感官索引：管理感官关键词的索引和检索。

SensoryIndexer 负责将感官关键词存入节点语义元数据，
支持按感官类型和关键词检索节点、获取节点感官索引、删除索引。
"""

import logging
from typing import Dict, List, Tuple

from .memory_store import MemoryStorePort

logger = logging.getLogger("elfie.brain.memory.sensory_index")


class SensoryIndexer:
    """感官索引：管理感官关键词的索引和检索"""

    # 感官类型定义
    SENSE_TYPES = ["olfactory", "visual", "auditory", "tactile"]

    def __init__(self, storage: MemoryStorePort):
        self.storage = storage

    def index_sensory(self, node_id: str, sensory: dict) -> None:
        """为节点建立感官索引

        sensory格式：{"olfactory": "鱼味", "visual": "温暖色调", "auditory": "温柔语调", "tactile": "温热食物"}
        每个感官关键词存入sensory_index表，使用INSERT OR REPLACE确保幂等性。
        """
        node = self.storage.get_node(node_id)
        if node is None:
            return
        indexed = node.metadata.get("sensory", {})
        if not isinstance(indexed, dict):
            indexed = {}
        for sense_type, sense_key in sensory.items():
            if not sense_key or sense_type not in self.SENSE_TYPES:
                continue
            indexed[sense_type] = sense_key
        self.storage.update_node(node_id, metadata={"sensory": indexed})

    def search_by_sensory(
        self, sense_type: str, keyword: str, top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """按感官类型和关键词检索节点

        返回 [(node_id, weight), ...] 按weight降序
        """
        results = []
        for node_type in ("episodic", "knowledge", "pattern"):
            for node in self.storage.get_nodes_by_type(node_type, limit=1000):
                sensory = node.metadata.get("sensory", {})
                if isinstance(sensory, dict) and keyword in sensory.get(sense_type, ""):
                    results.append((node.id, 0.8))
        # 按weight降序排列，返回top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_sensory_for_node(self, node_id: str) -> Dict[str, List[str]]:
        """获取节点的所有感官索引

        返回 {"olfactory": ["鱼味"], "visual": ["温暖色调"], ...}
        按感官类型分组，每种类型包含多个关键词。
        """
        node = self.storage.get_node(node_id)
        if node is None:
            return {}
        sensory = node.metadata.get("sensory", {})
        if not isinstance(sensory, dict):
            return {}
        return {sense_type: [key] for sense_type, key in sensory.items() if key}

    def remove_sensory_index(self, node_id: str) -> None:
        """删除节点的所有感官索引（软删除时调用）"""
        self.storage.update_node(node_id, metadata={"sensory": {}})
