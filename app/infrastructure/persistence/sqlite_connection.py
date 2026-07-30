"""Shared secure SQLite connection policy for app persistence."""

from __future__ import annotations

import os
import sqlite3
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class UnsafeSQLitePathError(RuntimeError):
    """Raised when a database path can escape through a symlink or special file."""

    __slots__ = ("path", "reason")

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"unsafe SQLite path {self.path}: {self.reason}"


def connect_app_sqlite(
    db_path: str | Path,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open SQLite with foreign keys and a no-symlink file policy."""
    path_text = os.fspath(db_path)
    if path_text != ":memory:":
        _prepare_database_file(Path(path_text))
    connection = sqlite3.connect(path_text, check_same_thread=check_same_thread)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def app_sqlite_connection(
    db_path: str | Path,
    *,
    check_same_thread: bool = True,
) -> Iterator[sqlite3.Connection]:
    """Yield a policy connection and roll back when the managed block fails."""
    connection = connect_app_sqlite(db_path, check_same_thread=check_same_thread)
    try:
        yield connection
    finally:
        if sys.exc_info()[0] is not None:
            connection.rollback()
        connection.close()


def _prepare_database_file(db_path: Path) -> None:
    parent = db_path.parent
    for directory in (parent, *parent.parents):
        try:
            directory_mode = directory.lstat().st_mode
        except FileNotFoundError as error:
            raise UnsafeSQLitePathError(
                db_path, "parent directory does not exist"
            ) from error
        if stat.S_ISLNK(directory_mode) or not stat.S_ISDIR(directory_mode):
            raise UnsafeSQLitePathError(db_path, "path contains a non-directory link")

    try:
        file_mode = db_path.lstat().st_mode
    except FileNotFoundError:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        descriptor = os.open(db_path, flags, 0o600)
        os.close(descriptor)
    else:
        if stat.S_ISLNK(file_mode) or not stat.S_ISREG(file_mode):
            raise UnsafeSQLitePathError(db_path, "target is not a regular file")
    db_path.chmod(0o600)
