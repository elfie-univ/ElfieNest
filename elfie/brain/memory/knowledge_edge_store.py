"""Memory-edge and content operations over final knowledge tables."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from typing import Protocol, cast
from uuid import uuid4

from .node_types import Edge, MemoryNode
from .tokenizer import tokenize


class _KnowledgeNodeReader(Protocol):
    conn: sqlite3.Connection

    def get_nodes_by_type(
        self, node_type: str, limit: int = 100
    ) -> list[MemoryNode]: ...

    @staticmethod
    def _row_to_node(row: object) -> MemoryNode: ...


class KnowledgeEdgeStoreMixin:
    """Project graph operations onto entity_edges without legacy tables."""

    conn: sqlite3.Connection

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        rel: str,
        weight: float = 0.5,
    ) -> str:
        edge_id = f"edge_{uuid4().hex}"
        self.conn.execute(
            """INSERT INTO entity_edges (
                   edge_id, source_entity_id, target_entity_id,
                   relation_type, weight, confidence, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_entity_id, target_entity_id, relation_type)
               DO UPDATE SET weight=excluded.weight, updated_at=excluded.updated_at""",
            (
                edge_id,
                source_id,
                target_id,
                rel,
                weight,
                0.5,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        row = self.conn.execute(
            """SELECT edge_id FROM entity_edges
               WHERE source_entity_id=? AND target_entity_id=? AND relation_type=?""",
            (source_id, target_id, rel),
        ).fetchone()
        return str(row["edge_id"])

    def get_edges(self, node_id: str, direction: str = "outgoing") -> list[Edge]:
        if direction == "outgoing":
            rows = self.conn.execute(
                """SELECT target_entity_id AS target, relation_type, weight
                   FROM entity_edges WHERE source_entity_id=?""",
                (node_id,),
            ).fetchall()
        elif direction == "incoming":
            rows = self.conn.execute(
                """SELECT source_entity_id AS target, relation_type, weight
                   FROM entity_edges WHERE target_entity_id=?""",
                (node_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT
                       CASE WHEN source_entity_id=? THEN target_entity_id
                            ELSE source_entity_id END AS target,
                       relation_type, weight
                   FROM entity_edges
                   WHERE source_entity_id=? OR target_entity_id=?""",
                (node_id, node_id, node_id),
            ).fetchall()
        return [
            Edge(target=row["target"], rel=row["relation_type"], weight=row["weight"])
            for row in rows
        ]

    def search_by_content(
        self,
        query: str,
        top_k: int = 5,
        node_type: str | None = None,
    ) -> list[tuple[str, float]]:
        query_words = tokenize(query)
        if not query_words:
            return []
        store = cast(_KnowledgeNodeReader, self)
        nodes = (
            store.get_nodes_by_type(node_type, limit=100000)
            if node_type is not None
            else [
                store._row_to_node(row)
                for row in store.conn.execute("SELECT * FROM entities").fetchall()
            ]
        )
        scored: list[tuple[str, float]] = []
        for node in nodes:
            content_words = tokenize(node.content)
            overlap = set(query_words) & set(content_words)
            if overlap and content_words:
                score = len(overlap) / math.sqrt(len(query_words) * len(content_words))
                scored.append((node.id, score))
        return sorted(scored, key=lambda item: item[1], reverse=True)[:top_k]
