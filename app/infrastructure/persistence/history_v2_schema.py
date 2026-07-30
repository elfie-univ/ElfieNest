"""Transition-only normalized chat history v2 schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.infrastructure.persistence.history_v2_account_schema_sql import (
    ACCOUNT_CONVERSATION_STATEMENTS,
)
from app.infrastructure.persistence.history_v2_message_schema_sql import (
    MESSAGE_STATEMENTS,
)
from app.infrastructure.persistence.sqlite_connection import app_sqlite_connection

HISTORY_V2_FILENAME: Final = "history_v2.sqlite"


@dataclass(frozen=True)
class InvalidHistoryV2PathError(ValueError):
    """Raised when the schema initializer is pointed at a non-v2 database."""

    db_path: Path

    def __str__(self) -> str:
        return f"history v2 schema requires {HISTORY_V2_FILENAME}: {self.db_path}"


def create_history_v2_schema(db_path: Path) -> None:
    """Create the transition-only history v2 schema at an explicit SQLite path."""
    if db_path.name != HISTORY_V2_FILENAME:
        raise InvalidHistoryV2PathError(db_path)

    db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with app_sqlite_connection(str(db_path)) as connection:
        for statement in ACCOUNT_CONVERSATION_STATEMENTS:
            connection.execute(statement)
        for statement in MESSAGE_STATEMENTS:
            connection.execute(statement)
        connection.commit()
