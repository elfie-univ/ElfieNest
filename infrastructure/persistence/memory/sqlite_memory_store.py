"""SQLite Adapter for one Elfie's semantic MemoryStorePort."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock
from types import TracebackType
from typing import Final

from infrastructure.persistence.memory.node_store import KnowledgeNodeStoreMixin
from infrastructure.persistence.memory.schema import (
    INDEX_SQL,
    KNOWLEDGE_TABLES,
    SCHEMA_SQL,
    SCHEMA_VERSION,
)
from infrastructure.persistence.memory.sqlite_episode_store import (
    EpisodeIdempotencyError,
    SQLiteEpisodeStoreMixin,
)
from infrastructure.persistence.memory.sqlite_graph_store import SQLiteGraphStoreMixin
from infrastructure.persistence.memory.sqlite_retrieval_store import (
    SQLiteRecallStoreMixin,
)
from infrastructure.persistence.nest_db.sqlite_connection import (
    UnsafeSQLitePathError,
    connect_app_sqlite,
)

_FINAL_FILENAME: Final[str] = "knowledge.sqlite"
_LEGACY_TABLES: Final[frozenset[str]] = frozenset(
    {
        "entities",
        "people",
        "known_elfies",
        "concepts",
        "places",
        "events",
        "entity_edges",
        "memory_notes",
        "source_evidence_links",
    }
)


class MemoryStorePathError(Exception):
    """The SQLite Memory Adapter requires the final filename or test memory."""

    __slots__ = ("db_path",)

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"SQLite Memory Adapter requires {_FINAL_FILENAME}: {self.db_path}"


class MemoryStoreMigrationRequired(RuntimeError):
    """A legacy database must be imported into a fresh target database first."""


class MemoryStoreSchemaError(RuntimeError):
    """The file is neither an empty database nor the supported target schema."""


class SQLiteMemoryStoreAdapter(
    KnowledgeNodeStoreMixin,
    SQLiteGraphStoreMixin,
    SQLiteEpisodeStoreMixin,
    SQLiteRecallStoreMixin,
):
    """Own a connection initialized with the target episodic/graph schema."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = self._parse_path(db_path)
        try:
            self.conn = connect_app_sqlite(self._db_path, check_same_thread=False)
        except UnsafeSQLitePathError as error:
            raise MemoryStorePathError(db_path=str(db_path)) from error
        self._lock = RLock()
        try:
            self._initialize_schema()
        except Exception:
            self.conn.close()
            raise

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
        """Expose the owned connection for read-only diagnostics and tests."""
        return self.conn

    @property
    def schema_version(self) -> int:
        row = self.conn.execute("PRAGMA user_version").fetchone()
        return int(row[0])

    def rebuild_text_indexes(self) -> dict[str, int]:
        """Rebuild disposable lexical projections from their fact tables."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute("DELETE FROM episodes_fts")
                self.conn.execute(
                    """INSERT INTO episodes_fts(episode_id, searchable_text)
                       SELECT episode_id, content_text || CASE
                           WHEN summary_text IS NULL THEN '' ELSE char(10) || summary_text END
                         FROM episodes"""
                )
                self.conn.execute("DELETE FROM nodes_fts")
                self.conn.execute(
                    """INSERT INTO nodes_fts(node_id, searchable_text)
                       SELECT n.node_id,
                              n.canonical_label
                              || CASE WHEN n.description IS NULL THEN '' ELSE char(10) || n.description END
                              || COALESCE((SELECT char(10) || group_concat(a.alias, char(10))
                                             FROM node_aliases AS a WHERE a.node_id=n.node_id), '')
                              || COALESCE((SELECT char(10) || group_concat(d.text, char(10))
                                             FROM node_descriptions AS d WHERE d.node_id=n.node_id), '')
                         FROM nodes AS n"""
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            episodes = int(
                self.conn.execute("SELECT COUNT(*) FROM episodes_fts").fetchone()[0]
            )
            nodes = int(
                self.conn.execute("SELECT COUNT(*) FROM nodes_fts").fetchone()[0]
            )
        return {"episodes": episodes, "nodes": nodes}

    def integrity_report(self) -> dict[str, int | bool]:
        """Return deterministic source/graph counts used by migration gates."""
        with self._lock:
            episodes = int(
                self.conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            )
            source_evidence = int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM evidence WHERE source_type='episode'"
                ).fetchone()[0]
            )
            grounded = int(
                self.conn.execute(
                    """SELECT COUNT(*) FROM assertions AS a
                       WHERE a.lifecycle='active' AND EXISTS (
                           SELECT 1 FROM assertion_evidence AS ae
                            WHERE ae.assertion_id=a.assertion_id)"""
                ).fetchone()[0]
            )
            assertions = int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM assertions WHERE lifecycle='active'"
                ).fetchone()[0]
            )
        return {
            "episodes": episodes,
            "episode_evidence": source_evidence,
            "assertions": assertions,
            "grounded_assertions": grounded,
            "all_assertions_grounded": grounded == assertions,
        }

    @staticmethod
    def _parse_path(db_path: str | Path) -> str | Path:
        if db_path == ":memory:":
            return ":memory:"
        path = Path(db_path)
        if path.name != _FINAL_FILENAME or path.is_symlink():
            raise MemoryStorePathError(db_path=str(db_path))
        return path

    def _initialize_schema(self) -> None:
        existing = {
            str(row["name"])
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if existing.intersection(_LEGACY_TABLES):
            raise MemoryStoreMigrationRequired(
                "legacy or mixed Memory database detected; import it into a fresh target database"
            )
        user_tables = existing - {"sqlite_sequence"}
        target_tables = set(KNOWLEDGE_TABLES) | {"episodes_fts", "nodes_fts"}
        current_version = self.schema_version
        if current_version not in (0, SCHEMA_VERSION):
            raise MemoryStoreSchemaError(
                f"unsupported Memory schema version: {current_version}"
            )
        if user_tables and current_version == 0:
            raise MemoryStoreSchemaError(
                "partially initialized Memory database has no schema version"
            )
        unknown = user_tables - target_tables
        if unknown:
            raise MemoryStoreSchemaError(
                "Memory database contains unknown tables: " + ", ".join(sorted(unknown))
            )
        if current_version == SCHEMA_VERSION and user_tables != target_tables:
            missing = ", ".join(sorted(target_tables - user_tables))
            raise MemoryStoreSchemaError(
                "Memory schema version is current but tables are missing: " + missing
            )
        try:
            self.conn.execute("PRAGMA busy_timeout=2000")
            if self._db_path != ":memory:":
                self.conn.execute("PRAGMA journal_mode=WAL")
                self.conn.execute("PRAGMA synchronous=NORMAL")
            for statement in SCHEMA_SQL:
                self.conn.execute(statement)
            for statement in INDEX_SQL:
                self.conn.execute(statement)
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self.conn.commit()
        except sqlite3.DatabaseError:
            self.conn.rollback()
            raise


__all__ = [
    "EpisodeIdempotencyError",
    "MemoryStoreMigrationRequired",
    "MemoryStorePathError",
    "MemoryStoreSchemaError",
    "SQLiteMemoryStoreAdapter",
]
