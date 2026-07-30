"""图记忆系统的 SQLite 持久化存储层。"""

import logging
import os
from pathlib import Path
from typing import Optional

from .graph_content_search import GraphContentSearchMixin
from .graph_edge_store import GraphEdgeStoreMixin
from .graph_node_store import GraphNodeStoreMixin
from .sqlite_connection import connect_memory_sqlite

logger = logging.getLogger("elfie.brain.memory.graph_storage")


class GraphStorage(GraphNodeStoreMixin, GraphEdgeStoreMixin, GraphContentSearchMixin):
    """图记忆的 SQLite 存储后端"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            data_home = Path(os.environ.get("ELFIE_HOME", "~/.elfienest")).expanduser()
            db_path = str(data_home / "graph_memory.db")
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = connect_memory_sqlite(db_path, check_same_thread=False)
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

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
