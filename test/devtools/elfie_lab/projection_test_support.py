"""Shared real-storage builders for memory projection tests."""

from elfie.brain.memory.graph_storage import GraphStorage
from elfie.brain.memory.node_types import MemoryNode


def add_node(
    storage: GraphStorage,
    node_id: str,
    node_type: str,
    content: str,
    metadata: dict = None,
    created_at: str = None,
) -> None:
    storage.add_node(
        MemoryNode(
            id=node_id,
            type=node_type,
            content=content,
            metadata=metadata or {},
            created_at=created_at,
        )
    )
