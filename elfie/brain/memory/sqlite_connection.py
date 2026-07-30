"""SQLite connection policy for Elfie memory storage."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from typing import Iterator


def connect_memory_sqlite(
    db_path: str,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open a memory-side SQLite connection with the memory storage policy."""
    connection = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def memory_sqlite_connection(
    db_path: str,
    *,
    check_same_thread: bool = True,
) -> Iterator[sqlite3.Connection]:
    """Yield a memory SQLite connection, rolling back failed transactions."""
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
