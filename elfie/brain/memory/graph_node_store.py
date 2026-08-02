import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from .node_types import Edge, MemoryNode


class GraphNodeStoreMixin:
    conn: sqlite3.Connection

    def _row_to_node(self, row) -> MemoryNode:
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
            "INSERT OR REPLACE INTO nodes "
            "(id, type, content, metadata, edges, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
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
        cursor = self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_node(row)

    def update_node(self, node_id: str, **kwargs) -> bool:
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

    def get_nodes_by_type(self, node_type: str, limit: int = 100) -> List[MemoryNode]:
        cursor = self.conn.execute(
            "SELECT * FROM nodes WHERE type=? LIMIT ?",
            (node_type, limit),
        )
        return [self._row_to_node(row) for row in cursor.fetchall()]

    def get_unconsolidated_nodes(self, node_type: str = "episodic") -> List[MemoryNode]:
        cursor = self.conn.execute("SELECT * FROM nodes WHERE type=?", (node_type,))
        result = []
        for row in cursor.fetchall():
            node = self._row_to_node(row)
            if node.metadata.get("consolidated") is not True:
                result.append(node)
        return result

    def count_nodes(self, node_type: Optional[str] = None) -> int:
        if node_type:
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE type=?", (node_type,)
            )
        else:
            cursor = self.conn.execute("SELECT COUNT(*) FROM nodes")
        return cursor.fetchone()[0]
