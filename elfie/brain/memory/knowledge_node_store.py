"""Memory-node projection onto the final knowledge entity tables."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Final

from .node_types import Edge, MemoryNode

_TYPE_MAP: Final[dict[str, str]] = {
    "core": "concept",
    "entity": "object",
    "episodic": "event",
    "knowledge": "concept",
    "pattern": "concept",
}
_SUBTYPE_TABLES: Final[tuple[str, ...]] = (
    "people",
    "known_elfies",
    "concepts",
    "places",
    "events",
)


class KnowledgeNodeStoreMixin:
    """Preserve legacy memory-node behavior using final entity semantics."""

    def add_node(self, node: MemoryNode) -> str:
        now = datetime.now(timezone.utc).isoformat()
        entity_type = self._entity_type(node)
        metadata = {
            "memory_node_type": node.type,
            "memory_metadata": node.metadata,
            "memory_edges": [
                {"target": edge.target, "rel": edge.rel, "weight": edge.weight}
                for edge in node.edges
            ],
        }
        self.conn.execute(
            """INSERT INTO entities (
                   entity_id, entity_type, name, summary, confidence,
                   first_seen_at, last_seen_at, updated_at, meta_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(entity_id) DO UPDATE SET
                   entity_type=excluded.entity_type,
                   name=excluded.name,
                   summary=excluded.summary,
                   confidence=excluded.confidence,
                   last_seen_at=excluded.last_seen_at,
                   updated_at=excluded.updated_at,
                   meta_json=excluded.meta_json""",
            (
                node.id,
                entity_type,
                node.content or node.id,
                node.content,
                float(node.metadata.get("confidence", 0.5)),
                node.created_at or now,
                node.updated_at or now,
                node.updated_at or now,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        self._replace_subtype(node, entity_type, now)
        self.conn.commit()
        return node.id

    def get_node(self, node_id: str) -> MemoryNode | None:
        row = self.conn.execute(
            "SELECT * FROM entities WHERE entity_id=?", (node_id,)
        ).fetchone()
        return None if row is None else self._row_to_node(row)

    def update_node(
        self,
        node_id: str,
        *,
        content: str | None = None,
        metadata: dict | None = None,
        edges: list[Edge] | None = None,
    ) -> bool:
        node = self.get_node(node_id)
        if node is None:
            return False
        if content is not None:
            node.content = content
        if metadata is not None:
            node.metadata.update(metadata)
        if edges is not None:
            node.edges = edges
        node.updated_at = datetime.now(timezone.utc).isoformat()
        self.add_node(node)
        return True

    def delete_node(self, node_id: str) -> bool:
        return self.update_node(node_id, metadata={"forgotten": True})

    def get_nodes_by_type(self, node_type: str, limit: int = 100) -> list[MemoryNode]:
        rows = self.conn.execute(
            """SELECT * FROM entities
               WHERE json_extract(meta_json, '$.memory_node_type')=? LIMIT ?""",
            (node_type, limit),
        ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def get_unconsolidated_nodes(
        self, node_type: str = "episodic"
    ) -> list[MemoryNode]:
        return [
            node
            for node in self.get_nodes_by_type(node_type, limit=100000)
            if node.metadata.get("consolidated") is not True
        ]

    def count_nodes(self, node_type: str | None = None) -> int:
        if node_type is None:
            row = self.conn.execute("SELECT COUNT(*) FROM entities").fetchone()
        else:
            row = self.conn.execute(
                """SELECT COUNT(*) FROM entities
                   WHERE json_extract(meta_json, '$.memory_node_type')=?""",
                (node_type,),
            ).fetchone()
        return int(row[0])

    @staticmethod
    def _row_to_node(row) -> MemoryNode:
        payload = json.loads(row["meta_json"])
        edges = [Edge(**edge) for edge in payload.get("memory_edges", [])]
        return MemoryNode(
            id=row["entity_id"],
            type=payload.get("memory_node_type", row["entity_type"]),
            content=row["summary"] or row["name"],
            metadata=payload.get("memory_metadata", {}),
            edges=edges,
            created_at=row["first_seen_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _entity_type(node: MemoryNode) -> str:
        if node.type != "entity":
            return _TYPE_MAP.get(node.type, "object")
        candidate = node.metadata.get("entity_type")
        return candidate if candidate in {"person", "elfie", "place"} else "object"

    def _replace_subtype(self, node: MemoryNode, entity_type: str, now: str) -> None:
        for table in _SUBTYPE_TABLES:
            self.conn.execute(f"DELETE FROM {table} WHERE entity_id=?", (node.id,))
        if entity_type == "event":
            self.conn.execute(
                """INSERT INTO events (
                       entity_id, event_time, event_type, description,
                       importance_score, meta_json, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    node.id,
                    node.metadata.get("timestamp", node.created_at),
                    node.type,
                    node.content,
                    float(node.metadata.get("importance", 0.5)),
                    json.dumps(node.metadata, ensure_ascii=False),
                    node.updated_at or now,
                ),
            )
        elif entity_type == "concept":
            self.conn.execute(
                """INSERT INTO concepts
                   (entity_id, concept_type, definition, confidence, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (node.id, node.type, node.content, 0.5, node.updated_at or now),
            )
        elif entity_type == "place":
            self.conn.execute(
                """INSERT INTO places
                   (entity_id, place_type, description, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (node.id, node.metadata.get("entity_type"), node.content, now),
            )
        elif entity_type == "person":
            self.conn.execute(
                "INSERT INTO people (entity_id, display_name, updated_at) VALUES (?, ?, ?)",
                (node.id, node.content, now),
            )
