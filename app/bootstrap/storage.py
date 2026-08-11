"""Production storage initialization at the App composition root."""

from __future__ import annotations

from infrastructure.persistence.store import init_db, seed_initial_owner_if_env_set


def ensure_application_storage(db_path: str) -> None:
    """Ensure the current application database schema exists."""
    if db_path != ":memory:":
        init_db(db_path)


def initialize_service_storage(db_path: str) -> None:
    """Preserve the service entry point's existing schema and Owner seed flow."""
    init_db(db_path)
    seed_initial_owner_if_env_set(db_path)


__all__ = ("ensure_application_storage", "initialize_service_storage")
