"""Read-only final database projections for local administration."""

from __future__ import annotations

import sqlite3


class SystemRepository:
    """Own administrative SQL that spans final persistence tables."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def usage_counts(self) -> tuple[int, int, int]:
        users = self._count("users")
        owners = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM users WHERE role='owner'"
            ).fetchone()[0]
        )
        return users, owners, self._count("elfies")

    def species_counts(self) -> tuple[tuple[str, int], ...]:
        rows = self._connection.execute(
            "SELECT species,COUNT(*) FROM elfies GROUP BY species"
        ).fetchall()
        return tuple((str(row[0]), int(row[1])) for row in rows)

    def table_counts(self) -> tuple[tuple[str, int], ...]:
        names = tuple(
            str(row[0])
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        )
        return tuple((name, self._count(name)) for name in names)

    def _count(self, table_name: str) -> int:
        quoted = '"' + table_name.replace('"', '""') + '"'
        return int(
            self._connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
        )
