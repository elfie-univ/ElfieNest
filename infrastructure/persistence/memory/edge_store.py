"""Compatibility name for the old edge mixin.

Graph operations now live in :mod:`sqlite_graph_store` and write qualified
assertions with evidence. This class is retained only for import compatibility
and intentionally contains no SQL or independent storage.
"""

from __future__ import annotations


class KnowledgeEdgeStoreMixin:
    """Deprecated empty compatibility mixin; the Adapter owns graph operations."""


__all__ = ["KnowledgeEdgeStoreMixin"]
