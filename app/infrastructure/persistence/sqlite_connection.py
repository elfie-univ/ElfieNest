"""SQLite connection policy for app persistence."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from typing import Iterator


def connect_app_sqlite(
    db_path: str,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open an app-side SQLite connection with the shared persistence policy."""
    connection = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def app_sqlite_connection(
    db_path: str,
    *,
    check_same_thread: bool = True,
) -> Iterator[sqlite3.Connection]:
    """Yield an app-side SQLite connection, rolling back failed transactions."""
    connection = connect_app_sqlite(
        db_path,
        check_same_thread=check_same_thread,
    )
    try:
        yield connection
    finally:
        if sys.exc_info()[0] is not None:
            connection.rollback()
        connection.close()
