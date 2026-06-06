"""感官索引：管理感官关键词的索引和检索。

SensoryIndexer 负责将感官关键词存入 sensory_index 表，
支持按感官类型和关键词检索节点、获取节点感官索引、删除索引。
"""

import logging
from typing import Dict, List, Tuple

from .graph_storage import GraphStorage

logger = logging.getLogger("elfie.brain.memory.sensory_index")


class SensoryIndexer:
    """感官索引：管理感官关键词的索引和检索"""

    # 感官类型定义
    SENSE_TYPES = ["olfactory", "visual", "auditory", "tactile"]

    def __init__(self, storage: GraphStorage):
        self.storage = storage

    def index_sensory(self, node_id: str, sensory: dict) -> None:
        """为节点建立感官索引

        sensory格式：{"olfactory": "鱼味", "visual": "温暖色调", "auditory": "温柔语调", "tactile": "温热食物"}
        每个感官关键词存入sensory_index表，使用INSERT OR REPLACE确保幂等性。
        """
        cursor = self.storage.conn.cursor()
        for sense_type, sense_key in sensory.items():
            if not sense_key or sense_type not in self.SENSE_TYPES:
                continue
            cursor.execute(
                """INSERT OR REPLACE INTO sensory_index (sense_key, sense_type, node_id, weight)
                   VALUES (?, ?, ?, ?)""",
                (sense_key, sense_type, node_id, 0.8),
            )
        self.storage.conn.commit()

    def search_by_sensory(
        self, sense_type: str, keyword: str, top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """按感官类型和关键词检索节点

        返回 [(node_id, weight), ...] 按weight降序
        """
        cursor = self.storage.conn.cursor()
        cursor.execute(
            """SELECT node_id, weight FROM sensory_index
               WHERE sense_type=? AND sense_key LIKE ?""",
            (sense_type, f"%{keyword}%"),
        )
        results = [(row["node_id"], row["weight"]) for row in cursor.fetchall()]
        # 按weight降序排列，返回top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_sensory_for_node(self, node_id: str) -> Dict[str, List[str]]:
        """获取节点的所有感官索引

        返回 {"olfactory": ["鱼味"], "visual": ["温暖色调"], ...}
        按感官类型分组，每种类型包含多个关键词。
        """
        cursor = self.storage.conn.cursor()
        cursor.execute(
            """SELECT sense_type, sense_key FROM sensory_index
               WHERE node_id=?""",
            (node_id,),
        )
        result: Dict[str, List[str]] = {st: [] for st in self.SENSE_TYPES}
        for row in cursor.fetchall():
            st = row["sense_type"]
            key = row["sense_key"]
            if st in result:
                result[st].append(key)
        # 移除空列表的感官类型
        return {st: keys for st, keys in result.items() if keys}

    def remove_sensory_index(self, node_id: str) -> None:
        """删除节点的所有感官索引（软删除时调用）"""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "DELETE FROM sensory_index WHERE node_id=?",
            (node_id,),
        )
        self.storage.conn.commit()
