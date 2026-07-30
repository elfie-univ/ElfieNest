"""Transactional Card 15 cutover for final account fields and avatars."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.infrastructure.persistence.account_avatar_storage import (
    AvatarCopy,
    AvatarStorageError,
    inspect_avatar_for_cutover,
    install_avatar_copy,
)
from app.infrastructure.persistence.store import (
    get_db,
    init_db,
    migrate_db_if_needed,
)
from app.infrastructure.persistence.transition_account_schema import (
    ensure_final_user_columns,
)

_CUTOVER_TRIGGER: Final[str] = "freeze_legacy_user_quota_after_card15"


@dataclass(frozen=True)
class AccountStorageCutoverError(RuntimeError):
    """Legacy account data cannot be represented by the final contract."""

    reason: str
    __slots__ = ("reason",)

    def __str__(self) -> str:
        return self.reason


def initialize_account_storage(db_path: str) -> None:
    """Initialize legacy infrastructure, then atomically activate final accounts."""
    init_db(db_path)
    migrate_db_if_needed(db_path)
    ensure_account_storage_cutover(db_path)


def ensure_account_storage_cutover(db_path: str) -> None:
    """Apply the account field/avatar cutover once inside an immediate transaction."""
    data_root = Path(db_path).expanduser().resolve().parent
    installed_targets: list[Path] = []
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            ensure_final_user_columns(connection)
            if not _cutover_is_complete(connection):
                _validate_legacy_accounts(connection)
                copies = _inspect_avatars(connection, data_root)
                _backfill_final_fields(connection)
                for user_id, copy in copies:
                    if install_avatar_copy(copy):
                        installed_targets.append(copy.target)
                    connection.execute(
                        "UPDATE users SET avatar_path = ? WHERE id = ?",
                        (copy.relative_path, user_id),
                    )
                _freeze_legacy_quota(connection)
            _validate_final_accounts(connection)
            connection.commit()
        except (sqlite3.DatabaseError, AvatarStorageError, AccountStorageCutoverError):
            connection.rollback()
            for target in installed_targets:
                target.unlink(missing_ok=True)
            raise


def _cutover_is_complete(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (_CUTOVER_TRIGGER,),
    ).fetchone()
    return row is not None


def _validate_legacy_accounts(connection: sqlite3.Connection) -> None:
    invalid_role = connection.execute(
        "SELECT id FROM users WHERE role IS NULL OR role NOT IN ('owner', 'user') LIMIT 1"
    ).fetchone()
    if invalid_role is not None:
        raise AccountStorageCutoverError("legacy account has an invalid role")
    invalid_quota = connection.execute(
        """
        SELECT id FROM users
        WHERE elfie_quota_override IS NOT NULL
          AND elfie_quota_override NOT BETWEEN 1 AND 32
        LIMIT 1
        """
    ).fetchone()
    if invalid_quota is not None:
        raise AccountStorageCutoverError("legacy account has an invalid quota")


def _inspect_avatars(
    connection: sqlite3.Connection,
    data_root: Path,
) -> tuple[tuple[int, AvatarCopy], ...]:
    copies: list[tuple[int, AvatarCopy]] = []
    rows = connection.execute(
        "SELECT id, avatar_path FROM users WHERE avatar_path IS NOT NULL ORDER BY id"
    ).fetchall()
    for row in rows:
        user_id = int(row["id"])
        copy = inspect_avatar_for_cutover(data_root, user_id, str(row["avatar_path"]))
        if copy is not None:
            copies.append((user_id, copy))
    return tuple(copies)


def _backfill_final_fields(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE users
        SET presence = COALESCE(presence, 'offline'),
            last_seen_at = COALESCE(last_seen_at, updated_at, created_at,
                                    CURRENT_TIMESTAMP),
            elfie_limit = elfie_quota_override
        """
    )


def _freeze_legacy_quota(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TRIGGER {_CUTOVER_TRIGGER}
        BEFORE UPDATE OF elfie_quota_override ON users
        WHEN NEW.elfie_quota_override IS NOT OLD.elfie_quota_override
        BEGIN
            SELECT RAISE(ABORT, 'legacy elfie quota is frozen');
        END
        """
    )


def _validate_final_accounts(connection: sqlite3.Connection) -> None:
    invalid = connection.execute(
        """
        SELECT id FROM users
        WHERE role IS NULL OR role NOT IN ('owner', 'user')
           OR presence IS NULL OR presence NOT IN ('online', 'away', 'offline')
           OR (elfie_limit IS NOT NULL AND elfie_limit NOT BETWEEN 0 AND 32)
        LIMIT 1
        """
    ).fetchone()
    if invalid is not None:
        raise AccountStorageCutoverError("final account fields violate their contract")
