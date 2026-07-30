"""SQLite store for the final per-Elfie knowledge schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .knowledge_schema import KNOWLEDGE_SCHEMA_SQL
from .sqlite_connection import connect_memory_sqlite


@dataclass(frozen=True)
class KnowledgeStorePathError(Exception):
    """Raised when KnowledgeStore is opened without an explicit knowledge DB."""

    db_path: str

    def __str__(self) -> str:
        return f"KnowledgeStore requires :memory: or a knowledge.sqlite path: {self.db_path}"


class KnowledgeStore:
    """Owns the final nine-table per-Elfie knowledge SQLite schema."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_explicit_knowledge_path(db_path)
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = connect_memory_sqlite(db_path)
        self._init_schema()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()

    def _init_schema(self) -> None:
        for statement in KNOWLEDGE_SCHEMA_SQL:
            self.conn.execute(statement)
        self.conn.commit()

    @staticmethod
    def _ensure_explicit_knowledge_path(db_path: str) -> None:
        if db_path == ":memory:":
            return
        if Path(db_path).name == "knowledge.sqlite":
            return
        raise KnowledgeStorePathError(db_path=db_path)


__all__ = ["KnowledgeStore", "KnowledgeStorePathError"]
