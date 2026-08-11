"""Shared real-storage builders for memory projection tests."""

from elfie.brain.memory.node_types import MemoryNode
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def add_node(
    storage: SQLiteMemoryStoreAdapter,
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
