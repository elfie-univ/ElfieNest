"""Exact temporary baseline for known system architecture violations.

Entries may be removed by an approved migration but never added to make a new
dependency or technical import pass.
"""

from __future__ import annotations

from typing import Dict, FrozenSet

LEGACY_SYSTEM_LAYER_VIOLATIONS: Dict[str, FrozenSet[str]] = {
    "elfie_forbidden_module_imports": frozenset(),
    "elfie_technical_imports": frozenset(
        {
            "elfie/brain/memory/graph_content_search.py -> sqlite3",
            "elfie/brain/memory/graph_edge_store.py -> sqlite3",
            "elfie/brain/memory/graph_node_store.py -> sqlite3",
            "elfie/brain/memory/graph_storage.py -> sqlite3",
            "elfie/brain/memory/knowledge_edge_store.py -> sqlite3",
            "elfie/brain/memory/knowledge_node_store.py -> sqlite3",
            "elfie/brain/memory/knowledge_store.py -> sqlite3",
            "elfie/brain/memory/sqlite_connection.py -> sqlite3",
        }
    ),
    "nest_forbidden_module_imports": frozenset(),
    "nest_technical_imports": frozenset(),
}
