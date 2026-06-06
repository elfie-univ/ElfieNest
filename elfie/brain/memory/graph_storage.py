"""图记忆系统的 SQLite 持久化存储层。

GraphStorage 负责数据库 schema 的初始化与管理。
CRUD 操作将在后续任务中实现。
"""

import json
import logging
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .node_types import Edge, MemoryNode
from .tokenizer import tokenize

logger = logging.getLogger("elfie.brain.memory.graph_storage")


class GraphStorage:
    """图记忆的 SQLite 存储后端"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # 默认保存在项目根目录的 .elfie_memory.db
            current_dir = Path(__file__).resolve().parent
            project_root = current_dir.parent.parent.parent
            db_path = str(project_root / ".elfie_memory.db")
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        # 启用WAL模式（内存数据库不支持WAL，跳过）
        if db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        """初始化数据库表和索引"""
        cursor = self.conn.cursor()
        # 建表
        cursor.execute("""CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            edges TEXT DEFAULT '[]',
            created_at TEXT,
            updated_at TEXT
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            rel TEXT NOT NULL,
            weight REAL DEFAULT 0.5
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS sensory_index (
            sense_key TEXT NOT NULL,
            sense_type TEXT NOT NULL,
            node_id TEXT NOT NULL,
            weight REAL DEFAULT 0.8,
            PRIMARY KEY (sense_key, node_id)
        )""")
        # 建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_content ON nodes(content)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_rel ON edges(rel)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sense_key ON sensory_index(sense_key)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sense_type ON sensory_index(sense_type)"
        )
        self.conn.commit()
        logger.info(f"💾 [图存储] 数据库schema初始化完成: {self.db_path}")

    def _row_to_node(self, row) -> MemoryNode:
        """将数据库行转换为MemoryNode对象"""
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        edges_data = json.loads(row["edges"]) if row["edges"] else []
        edges = [
            Edge(target=e["target"], rel=e["rel"], weight=e.get("weight", 0.5))
            for e in edges_data
        ]
        return MemoryNode(
            id=row["id"],
            type=row["type"],
            content=row["content"],
            metadata=metadata,
            edges=edges,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add_node(self, node: MemoryNode) -> str:
        """添加节点，返回node_id；如已存在则更新（upsert）

        将node序列化为JSON存入SQLite：metadata和edges分别序列化为JSON字符串。
        如果id已存在，更新所有字段（upsert）。
        """
        metadata_json = json.dumps(node.metadata, ensure_ascii=False)
        edges_json = json.dumps(
            [
                {"target": e.target, "rel": e.rel, "weight": e.weight}
                for e in node.edges
            ],
            ensure_ascii=False,
        )
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO nodes (id, type, content, metadata, edges, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                node.id,
                node.type,
                node.content,
                metadata_json,
                edges_json,
                node.created_at or now,
                node.updated_at or now,
            ),
        )
        self.conn.commit()
        return node.id

    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        """按ID获取节点，返回MemoryNode或None"""
        cursor = self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_node(row)

    def update_node(self, node_id: str, **kwargs) -> bool:
        """更新节点字段（metadata的合并更新）

        kwargs可以包含content, metadata, edges等字段。
        metadata是合并更新：新字段覆盖旧字段，旧字段保留。
        更新updated_at为当前时间。
        返回True如果节点存在，False否则。
        """
        node = self.get_node(node_id)
        if node is None:
            return False

        if "content" in kwargs:
            node.content = kwargs["content"]
        if "metadata" in kwargs:
            node.metadata.update(kwargs["metadata"])
        if "edges" in kwargs:
            node.edges = kwargs["edges"]

        node.updated_at = datetime.now().isoformat()
        metadata_json = json.dumps(node.metadata, ensure_ascii=False)
        edges_json = json.dumps(
            [
                {"target": e.target, "rel": e.rel, "weight": e.weight}
                for e in node.edges
            ],
            ensure_ascii=False,
        )
        self.conn.execute(
            "UPDATE nodes SET content=?, metadata=?, edges=?, updated_at=? WHERE id=?",
            (node.content, metadata_json, edges_json, node.updated_at, node_id),
        )
        self.conn.commit()
        return True

    def delete_node(self, node_id: str) -> bool:
        """软删除（标记forgotten，不物理删除）

        设置metadata.forgotten = True，不物理删除，节点仍然存在。
        返回True如果节点存在，False否则。
        """
        node = self.get_node(node_id)
        if node is None:
            return False
        node.metadata["forgotten"] = True
        node.updated_at = datetime.now().isoformat()
        metadata_json = json.dumps(node.metadata, ensure_ascii=False)
        edges_json = json.dumps(
            [
                {"target": e.target, "rel": e.rel, "weight": e.weight}
                for e in node.edges
            ],
            ensure_ascii=False,
        )
        self.conn.execute(
            "UPDATE nodes SET metadata=?, edges=?, updated_at=? WHERE id=?",
            (metadata_json, edges_json, node.updated_at, node_id),
        )
        self.conn.commit()
        return True

    def add_edge(
        self, source_id: str, target_id: str, rel: str, weight: float = 0.5
    ) -> int:
        """添加边，返回edge id"""
        cursor = self.conn.execute(
            "INSERT INTO edges (source_id, target_id, rel, weight) VALUES (?, ?, ?, ?)",
            (source_id, target_id, rel, weight),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_edges(self, node_id: str, direction: str = "outgoing") -> List[Edge]:
        """获取节点的出/入边

        direction='outgoing': 查询source_id=node_id
        direction='incoming': 查询target_id=node_id
        direction='both': 查询两者
        返回List[Edge]
        """
        if direction == "outgoing":
            cursor = self.conn.execute(
                "SELECT target_id, rel, weight FROM edges WHERE source_id=?", (node_id,)
            )
            rows = cursor.fetchall()
            return [
                Edge(target=r["target_id"], rel=r["rel"], weight=r["weight"])
                for r in rows
            ]
        elif direction == "incoming":
            cursor = self.conn.execute(
                "SELECT source_id, rel, weight FROM edges WHERE target_id=?", (node_id,)
            )
            rows = cursor.fetchall()
            return [
                Edge(target=r["source_id"], rel=r["rel"], weight=r["weight"])
                for r in rows
            ]
        else:  # 'both'
            cursor = self.conn.execute(
                "SELECT source_id, target_id, rel, weight FROM edges WHERE source_id=? OR target_id=?",
                (node_id, node_id),
            )
            rows = cursor.fetchall()
            edges = []
            for r in rows:
                if r["source_id"] == node_id:
                    edges.append(
                        Edge(target=r["target_id"], rel=r["rel"], weight=r["weight"])
                    )
                else:
                    edges.append(
                        Edge(target=r["source_id"], rel=r["rel"], weight=r["weight"])
                    )
            return edges

    def get_nodes_by_type(self, node_type: str, limit: int = 100) -> List[MemoryNode]:
        """按类型查询节点"""
        cursor = self.conn.execute(
            "SELECT * FROM nodes WHERE type=? LIMIT ?",
            (node_type, limit),
        )
        return [self._row_to_node(row) for row in cursor.fetchall()]

    def get_unconsolidated_nodes(self, node_type: str = "episodic") -> List[MemoryNode]:
        """获取未巩固节点（metadata.consolidated != True）

        在Python中过滤JSON metadata，确保consolidated字段判断准确。
        """
        cursor = self.conn.execute("SELECT * FROM nodes WHERE type=?", (node_type,))
        result = []
        for row in cursor.fetchall():
            node = self._row_to_node(row)
            if node.metadata.get("consolidated") is not True:
                result.append(node)
        return result

    def count_nodes(self, node_type: Optional[str] = None) -> int:
        """计数节点

        如果node_type指定，按类型计数；否则返回总节点数。
        """
        if node_type:
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE type=?", (node_type,)
            )
        else:
            cursor = self.conn.execute("SELECT COUNT(*) FROM nodes")
        return cursor.fetchone()[0]

    def search_by_content(
        self, query: str, top_k: int = 5, node_type: str = None
    ) -> List[Tuple[str, float]]:
        """TF-IDF查询nodes表content字段，返回(node_id, score)列表

        从旧vector_storage.py迁移的TF-IDF余弦相似度逻辑：
        1. tokenize查询词
        2. 遍历nodes表（可选按type过滤）
        3. tokenize每条content
        4. 计算余弦相似度
        5. 返回top_k个(node_id, score)元组，按score降序
        """
        if not query:
            return []

        query_words = tokenize(query)
        if not query_words:
            return []

        # 构建SQL查询
        if node_type:
            cursor = self.conn.execute(
                "SELECT id, content FROM nodes WHERE type=?", (node_type,)
            )
        else:
            cursor = self.conn.execute("SELECT id, content FROM nodes")

        scored: List[Tuple[str, float]] = []
        for row in cursor.fetchall():
            content_words = tokenize(row["content"])

            # 计算余弦相似度 / 词频交集
            intersection = set(query_words) & set(content_words)
            if not intersection:
                score = 0.0
            else:
                score = len(intersection) / (
                    math.sqrt(len(query_words)) * math.sqrt(len(content_words))
                )

            if score > 0.0:
                scored.append((row["id"], score))

        # 按得分降序排列，返回top_k
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
