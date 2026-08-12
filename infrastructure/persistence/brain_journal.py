"""SQLite Adapter for one Elfie's append-only Brain journal Port."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock
from types import TracebackType
from typing import Final

from pydantic import TypeAdapter

from elfie.brain.continuity import BrainContinuityCheckpoint
from elfie.brain.journal import BrainJournalEntry, BrainJournalPort
from elfie.brain.workspace.contracts import WorkspacePersistentState
from infrastructure.persistence.nest_db.sqlite_connection import (
    UnsafeSQLitePathError,
    connect_app_sqlite,
)

_FINAL_FILENAME: Final = "journal.sqlite"
_CHECKPOINT_ADAPTER: Final = TypeAdapter(BrainContinuityCheckpoint)
_WORKSPACE_ADAPTER: Final = TypeAdapter(WorkspacePersistentState)


class BrainJournalPathError(ValueError):
    """The journal Adapter accepts only its final filename or test memory."""


class SQLiteBrainJournalAdapter(BrainJournalPort):
    """Persist append-only causal facts with an idempotency uniqueness gate."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = self._parse_path(db_path)
        self._lock = RLock()
        try:
            self.conn = connect_app_sqlite(self._db_path, check_same_thread=False)
        except UnsafeSQLitePathError as error:
            raise BrainJournalPathError(str(db_path)) from error
        self._initialize_schema()

    @classmethod
    def in_memory(cls) -> SQLiteBrainJournalAdapter:
        return cls(":memory:")

    def __enter__(self) -> SQLiteBrainJournalAdapter:
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
        with self._lock:
            self.conn.close()

    def append(self, entry: BrainJournalEntry) -> bool:
        payload = entry.model_dump_json()
        with self._lock:
            existing = self.conn.execute(
                "SELECT entry_json FROM brain_journal WHERE idempotency_key=?",
                (entry.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing["entry_json"] != payload:
                    raise ValueError("Brain journal idempotency conflict")
                return False
            try:
                self.conn.execute(
                    """INSERT INTO brain_journal (
                           entry_id, idempotency_key, entry_json
                       ) VALUES (?, ?, ?)""",
                    (str(entry.entry_id), entry.idempotency_key, payload),
                )
                self.conn.commit()
            except sqlite3.DatabaseError:
                self.conn.rollback()
                raise
            return True

    def entries(self) -> tuple[BrainJournalEntry, ...]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT entry_json FROM brain_journal ORDER BY seq"
            ).fetchall()
        return tuple(
            BrainJournalEntry.model_validate_json(row["entry_json"]) for row in rows
        )

    def save_checkpoint(self, checkpoint: BrainContinuityCheckpoint) -> None:
        payload = _CHECKPOINT_ADAPTER.dump_json(checkpoint).decode("utf-8")
        with self._lock:
            try:
                self.conn.execute(
                    """INSERT INTO brain_checkpoint (singleton, checkpoint_json)
                       VALUES (1, ?)
                       ON CONFLICT(singleton) DO UPDATE SET
                           checkpoint_json=excluded.checkpoint_json""",
                    (payload,),
                )
                self.conn.commit()
            except sqlite3.DatabaseError:
                self.conn.rollback()
                raise

    def load_checkpoint(self) -> BrainContinuityCheckpoint | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT checkpoint_json FROM brain_checkpoint WHERE singleton=1"
            ).fetchone()
        if row is None:
            return None
        return _CHECKPOINT_ADAPTER.validate_json(row["checkpoint_json"])

    def load_workspace_state(self) -> WorkspacePersistentState:
        with self._lock:
            row = self.conn.execute(
                "SELECT writes_json FROM brain_workspace_pending WHERE singleton=1"
            ).fetchone()
        if row is None:
            return WorkspacePersistentState()
        return _WORKSPACE_ADAPTER.validate_json(row["writes_json"])

    def save_workspace_state(self, state: WorkspacePersistentState) -> None:
        payload = _WORKSPACE_ADAPTER.dump_json(state).decode("utf-8")
        with self._lock:
            try:
                self.conn.execute(
                    """INSERT INTO brain_workspace_pending (singleton, writes_json)
                       VALUES (1, ?)
                       ON CONFLICT(singleton) DO UPDATE SET
                           writes_json=excluded.writes_json""",
                    (payload,),
                )
                self.conn.commit()
            except sqlite3.DatabaseError:
                self.conn.rollback()
                raise

    @staticmethod
    def _parse_path(db_path: str | Path) -> str | Path:
        if db_path == ":memory:":
            return ":memory:"
        path = Path(db_path)
        if path.name != _FINAL_FILENAME or path.is_symlink():
            raise BrainJournalPathError(
                f"SQLite Brain journal requires {_FINAL_FILENAME}: {db_path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _initialize_schema(self) -> None:
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS brain_journal (
                   seq INTEGER PRIMARY KEY AUTOINCREMENT,
                   entry_id TEXT NOT NULL UNIQUE,
                   idempotency_key TEXT NOT NULL UNIQUE,
                   entry_json TEXT NOT NULL
               )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS brain_checkpoint (
                   singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                   checkpoint_json TEXT NOT NULL
               )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS brain_workspace_pending (
                   singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                   writes_json TEXT NOT NULL
               )"""
        )
        self.conn.commit()


__all__ = ("BrainJournalPathError", "SQLiteBrainJournalAdapter")
