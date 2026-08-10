"""Initializer for the final per-Elfie history.sqlite store."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Final, Iterable

from app.infrastructure.persistence.history_account_schema_sql import (
    ACCOUNT_CONVERSATION_STATEMENTS,
)
from app.infrastructure.persistence.history_message_schema_sql import (
    MESSAGE_STATEMENTS,
)
from infrastructure.persistence.sqlite_connection import (
    UnsafeSQLitePathError,
    app_sqlite_connection,
)

HISTORY_FILENAME: Final = "history.sqlite"
_DIRECTORY_MODE: Final = 0o700


class InvalidHistoryPathError(ValueError):
    """Raised when the initializer receives a non-final database filename."""

    __slots__ = ("db_path",)

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def __str__(self) -> str:
        return f"history schema requires {HISTORY_FILENAME}: {self.db_path}"


def create_history_schema(db_path: Path) -> None:
    """Create the final seven-table chat schema at an explicit database path."""
    if db_path.name != HISTORY_FILENAME:
        raise InvalidHistoryPathError(db_path=db_path)

    _ensure_secure_parent(db_path)
    with app_sqlite_connection(str(db_path)) as connection:
        for statement in ACCOUNT_CONVERSATION_STATEMENTS:
            connection.execute(statement)
        for statement in MESSAGE_STATEMENTS:
            connection.execute(statement)
        connection.commit()


def _ensure_secure_parent(db_path: Path) -> None:
    missing_directories: list[Path] = []
    for directory in _parent_chain(db_path.parent):
        try:
            mode = directory.lstat().st_mode
        except FileNotFoundError:
            missing_directories.append(directory)
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise UnsafeSQLitePathError(db_path, "path contains a non-directory link")

    for directory in reversed(missing_directories):
        try:
            directory.mkdir(mode=_DIRECTORY_MODE)
        except FileExistsError:
            mode = directory.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise UnsafeSQLitePathError(
                    db_path, "path contains a non-directory link"
                ) from None
        os.chmod(directory, _DIRECTORY_MODE, follow_symlinks=False)


def _parent_chain(parent: Path) -> Iterable[Path]:
    yield parent
    yield from parent.parents
