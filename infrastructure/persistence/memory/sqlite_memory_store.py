"""SQLite Adapter for one Elfie's semantic MemoryStorePort."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Final

from infrastructure.persistence.memory.edge_store import KnowledgeEdgeStoreMixin
from infrastructure.persistence.memory.node_store import KnowledgeNodeStoreMixin
from infrastructure.persistence.memory.schema import KNOWLEDGE_SCHEMA_SQL
from infrastructure.persistence.sqlite_connection import (
    UnsafeSQLitePathError,
    connect_app_sqlite,
)

_FINAL_FILENAME: Final = "knowledge.sqlite"


class MemoryStorePathError(Exception):
    """The SQLite Memory Adapter requires the final filename or test memory."""

    __slots__ = ("db_path",)

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"SQLite Memory Adapter requires {_FINAL_FILENAME}: {self.db_path}"


class SQLiteMemoryStoreAdapter(
    KnowledgeNodeStoreMixin,
    KnowledgeEdgeStoreMixin,
):
    """Own a connection initialized with the final nine-table schema."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = self._parse_path(db_path)
        try:
            # Cognition owns the logical write sequence, but the provider worker
            # runs on its own thread and reads the same per-Elfie store.
            self.conn = connect_app_sqlite(self._db_path, check_same_thread=False)
        except UnsafeSQLitePathError as error:
            raise MemoryStorePathError(db_path=str(db_path)) from error
        self._initialize_schema()

    @classmethod
    def in_memory(cls) -> SQLiteMemoryStoreAdapter:
        """Create an isolated in-memory store for tests and explicit tooling."""
        return cls(":memory:")

    def __enter__(self) -> SQLiteMemoryStoreAdapter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def close(self) -> None:
        """Close the owned SQLite connection."""
        self.conn.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the owned connection for repository-layer SQL operations."""
        return self.conn

    @staticmethod
    def _parse_path(db_path: str | Path) -> str | Path:
        if db_path == ":memory:":
            return ":memory:"
        path = Path(db_path)
        if path.name != _FINAL_FILENAME:
            raise MemoryStorePathError(db_path=str(db_path))
        if path.is_symlink():
            raise MemoryStorePathError(db_path=str(db_path))
        return path

    def _initialize_schema(self) -> None:
        try:
            for statement in KNOWLEDGE_SCHEMA_SQL:
                self.conn.execute(statement)
            self.conn.commit()
        except sqlite3.DatabaseError:
            self.conn.rollback()
            self.conn.close()
            raise


__all__ = ["MemoryStorePathError", "SQLiteMemoryStoreAdapter"]
