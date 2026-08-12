"""Production storage initialization at the App composition root."""

from __future__ import annotations

from infrastructure.persistence.nest_db.store import init_db


def ensure_application_storage(db_path: str) -> None:
    """Ensure the current application database schema exists."""
    if db_path != ":memory:":
        init_db(db_path)


__all__ = ("ensure_application_storage",)
