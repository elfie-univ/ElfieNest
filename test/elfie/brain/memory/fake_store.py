"""In-memory Fake for Brain memory algorithm tests.

Persistence and SQLite schema behavior are tested under
``test/infrastructure/persistence/memory``.  This Fake keeps the Brain test
suite independent from technical I/O while preserving the semantic Port.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Mapping
from uuid import uuid4

from elfie.brain.memory.node_types import Edge, JsonValue, MemoryNode
from elfie.brain.memory.tokenizer import tokenize


class FakeMemoryStore:
    def __init__(self) -> None:
        self._nodes: dict[str, MemoryNode] = {}
        self._edges: dict[tuple[str, str, str], Edge] = {}

    @classmethod
    def in_memory(cls) -> FakeMemoryStore:
        return cls()

    def __enter__(self) -> FakeMemoryStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        return None

    def add_node(self, node: MemoryNode) -> str:
        now = datetime.now(timezone.utc).isoformat()
        stored = self._clone(node)
        stored.created_at = stored.created_at or now
        stored.updated_at = stored.updated_at or now
        self._nodes[stored.id] = stored
        return stored.id

    def get_node(self, node_id: str) -> MemoryNode | None:
        node = self._nodes.get(node_id)
        return None if node is None else self._clone(node)

    def update_node(
        self,
        node_id: str,
        *,
        content: str | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
        edges: list[Edge] | None = None,
    ) -> bool:
        node = self._nodes.get(node_id)
        if node is None:
            return False
        if content is not None:
            node.content = content
        if metadata is not None:
            node.metadata.update(metadata)
        if edges is not None:
            node.edges = list(edges)
        node.updated_at = datetime.now(timezone.utc).isoformat()
        return True

    def delete_node(self, node_id: str) -> bool:
        return self.update_node(node_id, metadata={"forgotten": True})

    def get_nodes_by_type(self, node_type: str, limit: int = 100) -> list[MemoryNode]:
        return [
            self._clone(node) for node in self._nodes.values() if node.type == node_type
        ][:limit]

    def get_unconsolidated_nodes(self, node_type: str = "episodic") -> list[MemoryNode]:
        return [
            node
            for node in self.get_nodes_by_type(node_type, limit=100000)
            if node.metadata.get("consolidated") is not True
        ]

    def count_nodes(self, node_type: str | None = None) -> int:
        if node_type is None:
            return len(self._nodes)
        return sum(node.type == node_type for node in self._nodes.values())

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        rel: str,
        weight: float = 0.5,
    ) -> str:
        edge_id = f"edge_{uuid4().hex}"
        edge = Edge(target=target_id, rel=rel, weight=weight)
        self._edges[(source_id, target_id, rel)] = edge
        source = self._nodes.get(source_id)
        if source is not None:
            source.edges = [
                existing
                for existing in source.edges
                if not (existing.target == target_id and existing.rel == rel)
            ] + [edge]
        return edge_id

    def get_edges(self, node_id: str, direction: str = "outgoing") -> list[Edge]:
        result: list[Edge] = []
        for (source_id, target_id, _rel), edge in self._edges.items():
            if direction == "outgoing" and source_id == node_id:
                result.append(edge)
            elif direction == "incoming" and target_id == node_id:
                result.append(Edge(target=source_id, rel=edge.rel, weight=edge.weight))
            elif direction not in {"outgoing", "incoming"} and (
                source_id == node_id or target_id == node_id
            ):
                target = target_id if source_id == node_id else source_id
                result.append(Edge(target=target, rel=edge.rel, weight=edge.weight))
        return result

    def search_by_content(
        self,
        query: str,
        top_k: int = 5,
        node_type: str | None = None,
    ) -> list[tuple[str, float]]:
        query_words = tokenize(query)
        if not query_words:
            return []
        nodes = (
            self.get_nodes_by_type(node_type, limit=100000)
            if node_type is not None
            else [self._clone(node) for node in self._nodes.values()]
        )
        scored: list[tuple[str, float]] = []
        for node in nodes:
            content_words = tokenize(node.content)
            overlap = set(query_words) & set(content_words)
            if overlap and content_words:
                score = len(overlap) / math.sqrt(len(query_words) * len(content_words))
                scored.append((node.id, score))
        return sorted(scored, key=lambda item: item[1], reverse=True)[:top_k]

    @staticmethod
    def _clone(node: MemoryNode) -> MemoryNode:
        return MemoryNode(
            id=node.id,
            type=node.type,
            content=node.content,
            metadata=node.metadata.copy(),
            edges=list(node.edges),
            created_at=node.created_at,
            updated_at=node.updated_at,
        )


__all__ = ("FakeMemoryStore",)
