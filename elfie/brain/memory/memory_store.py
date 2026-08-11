"""Narrow storage contract shared by memory algorithms."""

from __future__ import annotations

from typing import Mapping, Protocol

from .node_types import Edge, JsonValue, MemoryMetadata, MemoryNode


class MemoryStorePort(Protocol):
    """Semantic storage operations required by Brain memory algorithms."""

    def add_node(self, node: MemoryNode) -> str: ...

    def get_node(self, node_id: str) -> MemoryNode | None: ...

    def update_node(
        self,
        node_id: str,
        *,
        content: str | None = None,
        metadata: Mapping[str, JsonValue] | MemoryMetadata | None = None,
        edges: list[Edge] | None = None,
    ) -> bool: ...

    def delete_node(self, node_id: str) -> bool: ...

    def get_nodes_by_type(
        self, node_type: str, limit: int = 100
    ) -> list[MemoryNode]: ...

    def get_unconsolidated_nodes(
        self, node_type: str = "episodic"
    ) -> list[MemoryNode]: ...

    def count_nodes(self, node_type: str | None = None) -> int: ...

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        rel: str,
        weight: float = 0.5,
    ) -> str | int: ...

    def get_edges(self, node_id: str, direction: str = "outgoing") -> list[Edge]: ...

    def search_by_content(
        self,
        query: str,
        top_k: int = 5,
        node_type: str | None = None,
    ) -> list[tuple[str, float]]: ...

    def close(self) -> None: ...


__all__ = ["MemoryStorePort"]
