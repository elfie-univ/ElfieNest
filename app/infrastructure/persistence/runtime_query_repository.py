"""Persistence boundary for account and ownership queries used by API runtimes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.infrastructure.persistence.elfie_repository import ElfieRecord, ElfieRepository
from app.infrastructure.persistence.session_repository import hash_session_token
from app.infrastructure.persistence.store import get_db


@dataclass(frozen=True)  # CPython 3.9 uses explicit __slots__ below.
class RuntimeAccount:
    """Account fields exposed to the authenticated API runtime."""

    user_id: int
    username: str
    password_hash: str
    role: str
    nickname: str | None
    avatar_color: int
    avatar_kind: str
    avatar_path: str | None
    default_landing_page: str
    theme_key: str
    created_at: str
    __slots__ = (
        "user_id",
        "username",
        "password_hash",
        "role",
        "nickname",
        "avatar_color",
        "avatar_kind",
        "avatar_path",
        "default_landing_page",
        "theme_key",
        "created_at",
    )


class RuntimeQueryRepository:
    """Own final-root SQL needed by API and WebSocket adapters."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def find_account_by_username(self, username: str) -> RuntimeAccount | None:
        """Load one final account by its login name."""
        with get_db(self._db_path) as connection:
            row = connection.execute(
                f"{_ACCOUNT_SELECT} WHERE username=?", (username,)
            ).fetchone()
        return None if row is None else _account(row)

    def find_account_by_id(self, user_id: int) -> RuntimeAccount | None:
        """Load one final account by identifier."""
        with get_db(self._db_path) as connection:
            row = connection.execute(
                f"{_ACCOUNT_SELECT} WHERE id=?", (user_id,)
            ).fetchone()
        return None if row is None else _account(row)

    def update_profile(
        self,
        user_id: int,
        *,
        nickname: str | None,
        avatar_color: int,
        avatar_kind: str,
    ) -> RuntimeAccount | None:
        """Replace the editable profile projection and reload the account."""
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE users SET nickname=?,avatar_color=?,avatar_kind=?,
                          updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (nickname, avatar_color, avatar_kind, user_id),
            )
            connection.commit()
        return self.find_account_by_id(user_id)

    def update_password_and_revoke_other_sessions(
        self, user_id: int, password_hash: str, current_token: str
    ) -> None:
        """Change a password and revoke every session except the current cookie."""
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE users SET password_hash=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (password_hash, user_id),
            )
            connection.execute(
                """UPDATE sessions SET revoked_at=CURRENT_TIMESTAMP
                   WHERE user_id=? AND token_hash<>? AND revoked_at IS NULL""",
                (user_id, hash_session_token(current_token)),
            )
            connection.commit()

    def update_theme(self, user_id: int, theme_key: str) -> None:
        """Persist one final account theme."""
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE users SET theme_key=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (theme_key, user_id),
            )
            connection.commit()

    def update_default_landing_page(self, user_id: int, page: str) -> None:
        """Persist one Owner landing preference."""
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE users SET default_landing_page=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (page, user_id),
            )
            connection.commit()

    def owner_id_for_elfie(self, elfie_id: str) -> int | None:
        """Return the owner of one final Elfie, if it exists."""
        record = ElfieRepository(self._db_path).get(elfie_id)
        return None if record is None else record.owner_user_id

    def elfie_is_owned_by(self, elfie_id: str, user_id: int) -> bool:
        """Check one final Elfie ownership relation."""
        return (
            ElfieRepository(self._db_path).get_for_owner(
                elfie_id, owner_user_id=user_id
            )
            is not None
        )

    def list_elfies_for_owner(self, user_id: int) -> list[ElfieRecord]:
        """List final Elfies owned by one account."""
        return ElfieRepository(self._db_path).list_for_owner(user_id)


_ACCOUNT_SELECT = """
SELECT id,username,password_hash,role,nickname,avatar_color,avatar_kind,
       avatar_path,default_landing_page,theme_key,created_at
FROM users
"""


def _account(row: sqlite3.Row) -> RuntimeAccount:
    return RuntimeAccount(
        user_id=int(row["id"]),
        username=str(row["username"]),
        password_hash=str(row["password_hash"]),
        role=str(row["role"]),
        nickname=None if row["nickname"] is None else str(row["nickname"]),
        avatar_color=int(row["avatar_color"]),
        avatar_kind=str(row["avatar_kind"]),
        avatar_path=None if row["avatar_path"] is None else str(row["avatar_path"]),
        default_landing_page=str(row["default_landing_page"]),
        theme_key=str(row["theme_key"]),
        created_at=str(row["created_at"]),
    )


__all__ = ("RuntimeAccount", "RuntimeQueryRepository")
