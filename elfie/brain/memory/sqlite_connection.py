"""SQLite connection policy for per-Elfie memory databases."""

from __future__ import annotations

import os
import sqlite3
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

_PRIVATE_FILE_MODE: Final = 0o600
_PRIVATE_DIRECTORY_MODE: Final = 0o700


class SQLitePathError(Exception):
    """A memory database path cannot be opened without following a symlink."""

    __slots__ = ("db_path",)

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"unsafe SQLite database path: {self.db_path}"


def _prepare_private_path(db_path: Path) -> Path:
    absolute_path = db_path.expanduser().absolute()
    current = Path(absolute_path.anchor)
    for part in absolute_path.parent.parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            try:
                os.mkdir(current, mode=_PRIVATE_DIRECTORY_MODE)
            except FileExistsError:
                mode = os.lstat(current).st_mode
            else:
                continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise SQLitePathError(db_path=absolute_path)

    try:
        final_mode = os.lstat(absolute_path).st_mode
    except FileNotFoundError:
        return absolute_path
    if stat.S_ISLNK(final_mode) or not stat.S_ISREG(final_mode):
        raise SQLitePathError(db_path=absolute_path)
    return absolute_path


def connect_memory_sqlite(
    db_path: str | Path,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open SQLite with row, FK, permission, and no-follow policy."""
    if db_path == ":memory:":
        connection = sqlite3.connect(":memory:", check_same_thread=check_same_thread)
    else:
        private_path = _prepare_private_path(Path(db_path))
        uri = f"{private_path.as_uri()}?mode=rwc&nofollow=1"
        try:
            connection = sqlite3.connect(
                uri,
                uri=True,
                check_same_thread=check_same_thread,
            )
        except sqlite3.OperationalError as error:
            raise SQLitePathError(db_path=private_path) from error
        os.chmod(private_path, _PRIVATE_FILE_MODE, follow_symlinks=False)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def memory_sqlite_connection(
    db_path: str | Path,
    *,
    check_same_thread: bool = True,
) -> Iterator[sqlite3.Connection]:
    """Yield a connection and roll back a failed transaction before closing."""
    connection = connect_memory_sqlite(
        db_path,
        check_same_thread=check_same_thread,
    )
    try:
        yield connection
    finally:
        if sys.exc_info()[0] is not None:
            connection.rollback()
        connection.close()
