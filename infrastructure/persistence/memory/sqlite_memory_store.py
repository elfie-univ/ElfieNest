"""SQLite Adapter for one Elfie's semantic MemoryStorePort."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from types import TracebackType
from typing import Final, Iterator

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
from infrastructure.persistence.memory.sqlite_lifecycle_store import (
    SQLiteLifecycleStoreMixin,
)
from infrastructure.persistence.memory.sqlite_retrieval_store import (
    SQLiteRecallStoreMixin,
)
from infrastructure.persistence.memory.sqlite_utils import utc_now
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
    SQLiteLifecycleStoreMixin,
    SQLiteRecallStoreMixin,
):
    """Own a connection initialized with the target episodic/graph schema."""

    def __init__(self, db_path: str | Path, elfie_id: str | None = None) -> None:
        self._db_path = self._parse_path(db_path)
        if elfie_id is not None and not elfie_id.strip():
            raise ValueError("elfie_id must not be blank")
        self.elfie_id = elfie_id
        self._transaction_depth = 0
        self._active_genesis_submission_id: str | None = None
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
    def in_memory(cls, elfie_id: str | None = None) -> SQLiteMemoryStoreAdapter:
        """Create an isolated in-memory store for tests and explicit tooling."""
        return cls(":memory:", elfie_id=elfie_id)

    def bind_elfie_identity(self, elfie_id: str) -> None:
        """Bind an adapter to its owning Elfie namespace.

        A freshly assembled Elfie may start with a provisional identity before
        adoption assigns its stable ID.  Rebinding is safe while this adapter
        has no durable Memory rows; once a source or projection exists, the
        namespace is immutable so an existing graph can never be reassigned.
        """
        if not elfie_id.strip():
            raise ValueError("elfie_id must not be blank")
        if self.elfie_id is not None and str(self.elfie_id) != elfie_id:
            with self._lock:
                if self._has_durable_memory_rows():
                    raise ValueError("Memory store is already bound to another Elfie")
        self.elfie_id = elfie_id

    def _has_durable_memory_rows(self) -> bool:
        """Return whether rebinding would move any persisted Memory facts."""
        for table in (
            "episodes",
            "nodes",
            "assertions",
            "evidence",
            "node_aliases",
            "node_descriptions",
            "episode_mentions",
            "assertion_evidence",
            "memory_genesis_submissions",
            "memory_maintenance",
            "projection_diagnostics",
        ):
            if (
                self.conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                is not None
            ):
                return True
        return False

    @contextmanager
    def write_transaction(self) -> Iterator[None]:
        """Run one short serialized writer Unit of Work.

        Adapter methods join an existing Unit of Work and only the outermost
        scope starts/commits/rolls back SQLite.  Genesis can therefore submit
        one complete package atomically without owning batching policy.
        """
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                yield
            except Exception:
                self._rollback_write_transaction(owns)
                raise
            else:
                self._commit_write_transaction(owns)

    def _begin_write_transaction(self) -> bool:
        if self._transaction_depth:
            self._transaction_depth += 1
            return False
        self.conn.execute("BEGIN IMMEDIATE")
        self._transaction_depth = 1
        return True

    def _commit_write_transaction(self, owns: bool) -> None:
        if not self._transaction_depth:
            return
        if owns:
            self.conn.commit()
            self._transaction_depth = 0
        else:
            self._transaction_depth = max(0, self._transaction_depth - 1)

    def _rollback_write_transaction(self, owns: bool) -> None:
        if not self._transaction_depth:
            return
        # Any nested failure must abort the complete outer Unit of Work.
        self.conn.rollback()
        self._transaction_depth = 0

    @contextmanager
    def genesis_submission(
        self,
        *,
        submission_id: str,
        manifest_id: str,
        source_version: str,
        content_sha256: str,
        expected_ids: tuple[str, ...] = (),
        elfie_id: str | None = None,
    ):
        """Commit one Genesis submission as an atomic Memory Unit of Work.

        The context manager intentionally has no batching or scheduling policy;
        callers may invoke it once per package of any size.  ``yield`` returns
        ``False`` for an exact committed replay and ``True`` for a new package.
        """
        if not submission_id.strip() or not manifest_id.strip():
            raise ValueError("Genesis submission and manifest IDs must not be blank")
        if (
            not source_version.strip()
            or len(content_sha256) != 64
            or any(
                character not in "0123456789abcdefABCDEF"
                for character in content_sha256
            )
        ):
            raise ValueError("Genesis submission source identity is invalid")
        if self.elfie_id is None:
            if elfie_id is None or not elfie_id.strip():
                raise ValueError("Genesis submissions require an elfie_id")
            self.elfie_id = elfie_id
        elif elfie_id is not None and str(elfie_id) != str(self.elfie_id):
            raise ValueError(
                "Genesis submission belongs to a different Elfie namespace"
            )
        with self._lock:
            existing = self.conn.execute(
                """SELECT content_sha256, manifest_id, source_version,
                              expected_ids_hash
                   FROM memory_genesis_submissions
                   WHERE elfie_id=? AND submission_id=?""",
                (str(self.elfie_id), submission_id),
            ).fetchone()
            if existing is not None:
                if str(existing["content_sha256"]) != content_sha256:
                    raise ValueError(
                        "Genesis submission identity was reused with a different hash"
                    )
                if (
                    str(existing["manifest_id"]) != manifest_id
                    or str(existing["source_version"]) != source_version
                ):
                    raise ValueError(
                        "Genesis submission identity was reused with different metadata"
                    )
                if expected_ids:
                    expected_ids_hash = hashlib.sha256(
                        json.dumps(sorted(expected_ids), ensure_ascii=False).encode(
                            "utf-8"
                        )
                    ).hexdigest()
                    if str(existing["expected_ids_hash"]) != expected_ids_hash:
                        raise ValueError(
                            "Genesis submission identity was reused with different output IDs"
                        )
                yield False
                return
            owns = self._begin_write_transaction()
            previous = self._active_genesis_submission_id
            try:
                prior_manifest = self.conn.execute(
                    """SELECT manifest_id FROM memory_genesis_submissions
                       WHERE elfie_id=? AND manifest_id<>? LIMIT 1""",
                    (str(self.elfie_id), manifest_id),
                ).fetchone()
                if prior_manifest is not None:
                    raise ValueError(
                        "an Elfie cannot accept a different Genesis manifest"
                    )
                # A second adapter may have waited on SQLite's writer lock
                # after the optimistic pre-check above. Re-check the marker
                # inside the transaction so a concurrent exact retry returns
                # the same idempotent result instead of surfacing a UNIQUE
                # violation.
                committed = self.conn.execute(
                    """SELECT content_sha256, manifest_id, source_version,
                                      expected_ids_hash
                       FROM memory_genesis_submissions
                       WHERE elfie_id=? AND submission_id=?""",
                    (str(self.elfie_id), submission_id),
                ).fetchone()
                if committed is not None:
                    if str(committed["content_sha256"]) != content_sha256:
                        raise ValueError(
                            "Genesis submission identity was reused with a different hash"
                        )
                    if (
                        str(committed["manifest_id"]) != manifest_id
                        or str(committed["source_version"]) != source_version
                    ):
                        raise ValueError(
                            "Genesis submission identity was reused with different metadata"
                        )
                    if expected_ids:
                        expected_ids_hash = hashlib.sha256(
                            json.dumps(sorted(expected_ids), ensure_ascii=False).encode(
                                "utf-8"
                            )
                        ).hexdigest()
                        if str(committed["expected_ids_hash"]) != expected_ids_hash:
                            raise ValueError(
                                "Genesis submission identity was reused with different output IDs"
                            )
                    self._commit_write_transaction(owns)
                    yield False
                    return
                self._active_genesis_submission_id = submission_id
                yield True
                if expected_ids:
                    identity_tables = (
                        ("nodes", "node_id"),
                        ("episodes", "episode_id"),
                        ("node_aliases", "alias_id"),
                        ("node_descriptions", "description_id"),
                        ("episode_mentions", "mention_id"),
                        ("assertions", "assertion_id"),
                        ("evidence", "evidence_id"),
                    )
                    missing = [
                        identifier
                        for identifier in expected_ids
                        if not self.conn.execute(
                            " UNION ALL ".join(
                                f"SELECT 1 FROM {table} WHERE {column}=? "
                                "AND genesis_submission_id=?"
                                for table, column in identity_tables
                            ),
                            tuple(
                                value
                                for table, column in identity_tables
                                for value in (identifier, submission_id)
                            ),
                        ).fetchone()
                    ]
                    if missing:
                        raise ValueError(
                            "Genesis submission is incomplete; missing IDs: "
                            + ", ".join(missing[:8])
                        )
                counts = {
                    table: int(
                        self.conn.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE genesis_submission_id=?",
                            (submission_id,),
                        ).fetchone()[0]
                    )
                    for table in (
                        "episodes",
                        "nodes",
                        "node_aliases",
                        "node_descriptions",
                        "episode_mentions",
                        "assertions",
                        "evidence",
                        "assertion_evidence",
                    )
                }
                ids_hash = hashlib.sha256(
                    json.dumps(sorted(expected_ids), ensure_ascii=False).encode("utf-8")
                ).hexdigest()
                self.conn.execute(
                    """INSERT INTO memory_genesis_submissions(
                           submission_id, elfie_id, manifest_id, source_version,
                           content_sha256, expected_counts_json, expected_ids_hash,
                           committed_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        submission_id,
                        str(self.elfie_id),
                        manifest_id,
                        source_version,
                        content_sha256,
                        json.dumps(counts, sort_keys=True, separators=(",", ":")),
                        ids_hash,
                        utc_now(),
                    ),
                )
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
            finally:
                self._active_genesis_submission_id = previous

    def genesis_submission_status(
        self, submission_id: str, content_sha256: str
    ) -> bool:
        if self.elfie_id is None:
            return False
        row = self.conn.execute(
            "SELECT content_sha256 FROM memory_genesis_submissions WHERE elfie_id=? AND submission_id=?",
            (str(self.elfie_id), submission_id),
        ).fetchone()
        if row is None:
            return False
        if str(row["content_sha256"]) != content_sha256:
            raise ValueError(
                "Genesis submission identity was reused with a different hash"
            )
        return True

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

    def _genesis_visibility(self, alias: str) -> tuple[str, list[object]]:
        """Gate Genesis rows on the same-transaction completion marker.

        Normal runtime rows carry a NULL submission ID and remain visible.  A
        Genesis row becomes readable only after its submission marker exists;
        a bound adapter additionally requires the marker's Elfie namespace to
        match the adapter.
        """
        if not alias.replace("_", "").isalnum():
            raise ValueError("invalid SQL alias")
        active_clause = ""
        params: list[object] = []
        active_submission = self._active_genesis_submission_id
        if active_submission is not None:
            active_clause = f" OR {alias}.genesis_submission_id=?"
            params.append(active_submission)
        namespace = ""
        if self.elfie_id is not None:
            namespace = " AND g.elfie_id=?"
            params.append(str(self.elfie_id))
        return (
            f"({alias}.genesis_submission_id IS NULL{active_clause} OR EXISTS ("
            "SELECT 1 FROM memory_genesis_submissions AS g "
            f"WHERE g.submission_id={alias}.genesis_submission_id{namespace}))",
            params,
        )

    @property
    def schema_version(self) -> int:
        row = self.conn.execute("PRAGMA user_version").fetchone()
        return int(row[0])

    def rebuild_text_indexes(self) -> dict[str, int]:
        """Rebuild disposable lexical projections from their fact tables."""
        with self._lock:
            owns = self._begin_write_transaction()
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
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
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
            nodes = int(self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0])
            source_evidence = int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM evidence WHERE source_type='episode'"
                ).fetchone()[0]
            )
            evidence = int(
                self.conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            )
            assertion_evidence = int(
                self.conn.execute("SELECT COUNT(*) FROM assertion_evidence").fetchone()[
                    0
                ]
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
            "nodes": nodes,
            "evidence": evidence,
            "episode_evidence": source_evidence,
            "assertions": assertions,
            "assertion_evidence": assertion_evidence,
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
