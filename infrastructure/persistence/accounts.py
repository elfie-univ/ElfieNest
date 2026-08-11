"""SQLite implementation of the Accounts credential and session Port."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from app.features.accounts import (
    AccountCredentials,
    AccountPersistenceCapacityError,
    AccountPersistenceConflict,
    AccountPersistenceError,
    AccountPersistenceTargetError,
    AccountPrincipal,
    AccountProfileRecord,
    AccountProfileWrite,
    AvatarKind,
    Gender,
    LandingPage,
    ManagedAccountRecord,
    ManagedAccountRecords,
    ManagedAccountRole,
    OwnerAccountRecord,
    Presence,
    StoredAvatar,
    ThemeKey,
    parse_account_role,
)
from infrastructure.persistence.data_home import data_home_from_db_path
from infrastructure.persistence.data_layout import (
    ensure_final_user_layout,
    final_root_layout,
)

from .sqlite_connection import app_sqlite_connection


class SessionPrincipal(NamedTuple):
    user_id: int
    account_id: str
    role: str
    default_landing_page: str


class ActiveSessionRecord(NamedTuple):
    token_hash: str
    account_id: str
    expires_at: str


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class SessionRepository:
    """Transaction-scoped session persistence used by remaining admin slices."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def issue(self, user_id: int, expires_at: datetime) -> str:
        raw_token = secrets.token_hex(32)
        self._connection.execute(
            "INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)",
            (hash_session_token(raw_token), user_id, _utc_text(expires_at)),
        )
        return raw_token

    def find_active(self, raw_token: str, now: datetime) -> SessionPrincipal | None:
        if not raw_token:
            return None
        row = self._connection.execute(
            """SELECT users.id,users.account_id,users.role,users.default_landing_page
               FROM sessions JOIN users ON sessions.user_id=users.id
               WHERE sessions.token_hash=? AND sessions.revoked_at IS NULL
                 AND sessions.expires_at>?""",
            (hash_session_token(raw_token), _utc_text(now)),
        ).fetchone()
        if row is None:
            return None
        return SessionPrincipal(
            user_id=int(row["id"]),
            account_id=str(row["account_id"]),
            role=str(row["role"]),
            default_landing_page=str(row["default_landing_page"]),
        )

    def revoke(self, raw_token: str, revoked_at: datetime) -> None:
        if raw_token:
            self._connection.execute(
                "UPDATE sessions SET revoked_at=COALESCE(revoked_at,?) "
                "WHERE token_hash=?",
                (_utc_text(revoked_at), hash_session_token(raw_token)),
            )

    def revoke_for_user(self, user_id: int, revoked_at: datetime) -> None:
        self._connection.execute(
            "UPDATE sessions SET revoked_at=COALESCE(revoked_at,?) WHERE user_id=?",
            (_utc_text(revoked_at), user_id),
        )

    def count_active(self, now: datetime) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL AND expires_at>?",
            (_utc_text(now),),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def list_active(self, now: datetime, limit: int) -> tuple[ActiveSessionRecord, ...]:
        rows = self._connection.execute(
            """SELECT sessions.token_hash,users.account_id,sessions.expires_at
               FROM sessions JOIN users ON sessions.user_id=users.id
               WHERE sessions.revoked_at IS NULL AND sessions.expires_at>?
               ORDER BY sessions.expires_at DESC LIMIT ?""",
            (_utc_text(now), limit),
        ).fetchall()
        return tuple(
            ActiveSessionRecord(
                token_hash=str(row["token_hash"]),
                account_id=str(row["account_id"]),
                expires_at=str(row["expires_at"]),
            )
            for row in rows
        )


class SQLiteAccountsAdapter:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def find_credentials(self, account_id: str) -> AccountCredentials | None:
        with app_sqlite_connection(self._db_path) as connection:
            row = connection.execute(
                """SELECT id,account_id,password_hash,role,display_name,
                          default_landing_page
                   FROM users WHERE account_id=?""",
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        return AccountCredentials(
            user_id=int(row["id"]),
            account_id=str(row["account_id"]),
            password_hash=str(row["password_hash"]),
            role=str(row["role"]),
            display_name=(
                None if row["display_name"] is None else str(row["display_name"])
            ),
            default_landing_page=str(row["default_landing_page"]),
        )

    def issue_session(self, user_id: int, expires_at: datetime) -> str:
        with app_sqlite_connection(self._db_path) as connection:
            token = SessionRepository(connection).issue(user_id, expires_at)
            connection.commit()
        return token

    def find_session(self, raw_token: str, now: datetime) -> AccountPrincipal | None:
        with app_sqlite_connection(self._db_path) as connection:
            record = SessionRepository(connection).find_active(raw_token, now)
        if record is None:
            return None
        return AccountPrincipal(
            user_id=record.user_id,
            account_id=record.account_id,
            role=parse_account_role(record.role),
            default_landing_page=record.default_landing_page,
        )

    def revoke_session(self, raw_token: str, revoked_at: datetime) -> None:
        with app_sqlite_connection(self._db_path) as connection:
            SessionRepository(connection).revoke(raw_token, revoked_at)
            connection.commit()

    def create_first_owner(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password_hash: str,
    ) -> OwnerAccountRecord:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """SELECT id,account_id,display_name,created_at,updated_at
                       FROM users WHERE role='owner' ORDER BY id LIMIT 1"""
                ).fetchone()
                if existing is not None:
                    connection.commit()
                    return _owner_record(existing)
                if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                    raise AccountPersistenceConflict("accounts already exist")
                cursor = connection.execute(
                    """INSERT INTO users
                       (account_id,display_name,password_hash,role,avatar_color)
                       VALUES (?,?,?,'owner',0)""",
                    (account_id, display_name, password_hash),
                )
                if cursor.lastrowid is None:
                    raise AccountPersistenceError("owner insert returned no user id")
                row = connection.execute(
                    """SELECT id,account_id,display_name,created_at,updated_at
                       FROM users WHERE id=?""",
                    (int(cursor.lastrowid),),
                ).fetchone()
                if row is None:
                    raise AccountPersistenceError("owner disappeared after insert")
                connection.commit()
                return _owner_record(row)
        except AccountPersistenceError:
            raise
        except sqlite3.IntegrityError as error:
            raise AccountPersistenceConflict(str(error)) from error
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error

    def find_profile(self, user_id: int) -> AccountProfileRecord | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    f"{_PROFILE_SELECT} WHERE users.id=?", (user_id,)
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return None if row is None else _profile_record(row)

    def record_heartbeat(self, user_id: int, last_seen_at: str) -> bool:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                cursor = connection.execute(
                    """UPDATE users SET presence='online',last_seen_at=?,
                       updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (last_seen_at, user_id),
                )
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return int(cursor.rowcount) == 1

    def update_profile(
        self, user_id: int, profile: AccountProfileWrite
    ) -> AccountProfileRecord | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                conflict = connection.execute(
                    "SELECT 1 FROM users WHERE account_id=? AND id!=?",
                    (profile.account_id, user_id),
                ).fetchone()
                if conflict is not None:
                    raise AccountPersistenceConflict("account_id already exists")
                connection.execute(
                    """UPDATE users SET account_id=?,display_name=?,avatar_color=?,
                       avatar_kind=?,gender=?,birth_date=?,updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        profile.account_id,
                        profile.display_name,
                        profile.avatar_color,
                        profile.avatar_kind,
                        profile.gender,
                        profile.birth_date,
                        user_id,
                    ),
                )
                connection.commit()
        except AccountPersistenceError:
            raise
        except sqlite3.IntegrityError as error:
            raise AccountPersistenceConflict(str(error)) from error
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return self.find_profile(user_id)

    def change_password(
        self,
        user_id: int,
        password_hash: str,
        current_session_token: str,
    ) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """UPDATE users SET password_hash=?,updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (password_hash, user_id),
                )
                if cursor.rowcount != 1:
                    raise AccountPersistenceTargetError(user_id)
                connection.execute(
                    """UPDATE sessions SET revoked_at=CURRENT_TIMESTAMP
                       WHERE user_id=? AND token_hash<>? AND revoked_at IS NULL""",
                    (user_id, hash_session_token(current_session_token)),
                )
                connection.commit()
        except AccountPersistenceError:
            raise
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error

    def update_theme(self, user_id: int, theme_key: str) -> None:
        self._update_account_field(user_id, "theme_key", theme_key)

    def update_default_landing_page(self, user_id: int, page: str) -> None:
        self._update_account_field(user_id, "default_landing_page", page)

    def update_avatar_path(self, user_id: int, relative_path: str) -> None:
        self._update_account_field(user_id, "avatar_path", relative_path)

    def list_managed_accounts(self) -> ManagedAccountRecords:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                rows = connection.execute(
                    f"{_MANAGED_ACCOUNT_SELECT} ORDER BY users.id"
                ).fetchall()
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return ManagedAccountRecords(items=tuple(_managed_record(row) for row in rows))

    def get_managed_account(self, user_id: int) -> ManagedAccountRecord | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    f"{_MANAGED_ACCOUNT_SELECT} WHERE users.id=?", (user_id,)
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return None if row is None else _managed_record(row)

    def create_managed_account(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password_hash: str,
        role: ManagedAccountRole,
    ) -> int:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """INSERT INTO users
                       (account_id,display_name,password_hash,role)
                       VALUES (?,?,?,?)""",
                    (account_id, display_name, password_hash, role),
                )
                if cursor.lastrowid is None:
                    raise AccountPersistenceError("member insert returned no user id")
                user_id = int(cursor.lastrowid)
                connection.commit()
        except sqlite3.IntegrityError as error:
            if "maximum" in str(error):
                raise AccountPersistenceCapacityError(str(error)) from error
            raise AccountPersistenceConflict(str(error)) from error
        except AccountPersistenceError:
            raise
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return user_id

    def update_managed_quota(self, user_id: int, quota: int | None) -> bool:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                cursor = connection.execute(
                    """UPDATE users SET elfie_limit=?,updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND role IN ('admin','user')""",
                    (quota, user_id),
                )
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return int(cursor.rowcount) == 1

    def delete_managed_account(self, user_id: int) -> bool:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "DELETE FROM sessions WHERE user_id=? "
                    "AND EXISTS (SELECT 1 FROM users WHERE id=? "
                    "AND role IN ('admin','user'))",
                    (user_id, user_id),
                )
                cursor = connection.execute(
                    "DELETE FROM users WHERE id=? AND role IN ('admin','user') "
                    "AND NOT EXISTS (SELECT 1 FROM elfies WHERE owner_user_id=?)",
                    (user_id, user_id),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    return False
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return True

    def reset_managed_password(self, user_id: int, password_hash: str) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """UPDATE users SET password_hash=?,updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND role IN ('admin','user')""",
                    (password_hash, user_id),
                )
                if cursor.rowcount != 1:
                    raise AccountPersistenceTargetError(user_id)
                SessionRepository(connection).revoke_for_user(
                    user_id, datetime.now(timezone.utc)
                )
                connection.commit()
        except AccountPersistenceError:
            raise
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error

    def find_owner_account(self) -> OwnerAccountRecord | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    """SELECT id,account_id,display_name,created_at,updated_at
                       FROM users WHERE role='owner' ORDER BY id LIMIT 1"""
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return None if row is None else _owner_record(row)

    def recover_owner_account(
        self,
        user_id: int,
        account_id: str,
        password_hash: str,
    ) -> OwnerAccountRecord | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                conflict = connection.execute(
                    "SELECT 1 FROM users WHERE account_id=? AND id!=?",
                    (account_id, user_id),
                ).fetchone()
                if conflict is not None:
                    raise AccountPersistenceConflict("account_id already exists")
                cursor = connection.execute(
                    """UPDATE users SET account_id=?,password_hash=?,
                       updated_at=CURRENT_TIMESTAMP WHERE id=? AND role='owner'""",
                    (account_id, password_hash, user_id),
                )
                if cursor.rowcount != 1:
                    raise AccountPersistenceTargetError(user_id)
                SessionRepository(connection).revoke_for_user(
                    user_id, datetime.now(timezone.utc)
                )
                connection.commit()
        except AccountPersistenceError:
            raise
        except sqlite3.IntegrityError as error:
            raise AccountPersistenceConflict(str(error)) from error
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error
        return self.find_owner_account()

    def store(self, user_id: int, content_type: str, content: bytes) -> StoredAvatar:
        extension = _AVATAR_CONTENT_EXTENSIONS.get(content_type)
        if extension is None:
            raise AccountPersistenceError("unsupported avatar content type")
        try:
            data_home = data_home_from_db_path(self._db_path)
            user_layout = ensure_final_user_layout(data_home, str(user_id))
            for existing in user_layout.assets.glob("avatar.*"):
                existing.unlink()
            target = user_layout.avatar(extension)
            target.write_bytes(content)
            relative_path = str(target.relative_to(data_home))
        except OSError as error:
            raise AccountPersistenceError(str(error)) from error
        return StoredAvatar(
            relative_path=relative_path,
            content_type=content_type,
            content=content,
        )

    def load(self, user_id: int, relative_path: str) -> StoredAvatar | None:
        try:
            data_home = data_home_from_db_path(self._db_path)
            candidate = (
                final_root_layout(data_home).user(str(user_id)).assets
                / Path(relative_path).name
            )
            if not candidate.is_file():
                return None
            content_type = _AVATAR_EXTENSION_CONTENT_TYPES.get(
                candidate.suffix.removeprefix(".").lower()
            )
            if content_type is None:
                return None
            content = candidate.read_bytes()
            return StoredAvatar(
                relative_path=str(candidate.relative_to(data_home)),
                content_type=content_type,
                content=content,
            )
        except OSError as error:
            raise AccountPersistenceError(str(error)) from error

    def _update_account_field(self, user_id: int, field: str, value: str) -> None:
        allowed_fields = frozenset({"theme_key", "default_landing_page", "avatar_path"})
        if field not in allowed_fields:
            raise AccountPersistenceError("unsupported account field")
        try:
            with app_sqlite_connection(self._db_path) as connection:
                cursor = connection.execute(
                    f"UPDATE users SET {field}=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (value, user_id),
                )
                if cursor.rowcount != 1:
                    raise AccountPersistenceTargetError(user_id)
                connection.commit()
        except AccountPersistenceError:
            raise
        except sqlite3.DatabaseError as error:
            raise AccountPersistenceError(str(error)) from error


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


_PROFILE_SELECT = """
SELECT users.id,users.account_id,users.password_hash,users.display_name,users.gender,
       users.birth_date,users.role,users.avatar_path,users.avatar_color,
       users.avatar_kind,users.theme_key,users.default_landing_page,
       users.created_at,users.updated_at,
       (SELECT COUNT(*) FROM elfies WHERE elfies.owner_user_id=users.id) AS elfie_count
FROM users
"""

_MANAGED_ACCOUNT_SELECT = """
SELECT users.id,users.account_id,users.display_name,users.role,users.gender,
       users.birth_date,users.presence,users.last_seen_at,users.language,
       users.created_at,users.avatar_path,users.elfie_limit,
       (SELECT COUNT(*) FROM elfies WHERE elfies.owner_user_id=users.id) AS elfie_count
FROM users
"""

_AVATAR_CONTENT_EXTENSIONS = {
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
}
_AVATAR_EXTENSION_CONTENT_TYPES = {
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def _profile_record(row: sqlite3.Row) -> AccountProfileRecord:
    return AccountProfileRecord(
        user_id=int(row["id"]),
        account_id=str(row["account_id"]),
        password_hash=str(row["password_hash"]),
        display_name=None if row["display_name"] is None else str(row["display_name"]),
        gender=_gender(row["gender"]),
        birth_date=None if row["birth_date"] is None else str(row["birth_date"]),
        role=parse_account_role(str(row["role"])),
        avatar_path=None if row["avatar_path"] is None else str(row["avatar_path"]),
        avatar_color=int(row["avatar_color"]),
        avatar_kind=_avatar_kind(row["avatar_kind"]),
        theme_key=_theme_key(row["theme_key"]),
        default_landing_page=_landing_page(row["default_landing_page"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        elfie_count=int(row["elfie_count"]),
    )


def _managed_record(row: sqlite3.Row) -> ManagedAccountRecord:
    return ManagedAccountRecord(
        user_id=int(row["id"]),
        account_id=str(row["account_id"]),
        display_name=None if row["display_name"] is None else str(row["display_name"]),
        role=parse_account_role(str(row["role"])),
        gender=_gender(row["gender"]),
        birth_date=None if row["birth_date"] is None else str(row["birth_date"]),
        presence=_presence(row["presence"]),
        last_seen_at=None if row["last_seen_at"] is None else str(row["last_seen_at"]),
        language=str(row["language"]),
        created_at=str(row["created_at"]),
        elfie_count=int(row["elfie_count"]),
        elfie_quota_override=(
            None if row["elfie_limit"] is None else int(row["elfie_limit"])
        ),
        avatar_path=None if row["avatar_path"] is None else str(row["avatar_path"]),
    )


def _owner_record(row: sqlite3.Row) -> OwnerAccountRecord:
    return OwnerAccountRecord(
        user_id=int(row["id"]),
        account_id=str(row["account_id"]),
        display_name=None if row["display_name"] is None else str(row["display_name"]),
        created_at=None if row["created_at"] is None else str(row["created_at"]),
        updated_at=None if row["updated_at"] is None else str(row["updated_at"]),
    )


def _gender(value: object) -> Gender:
    raw = "male" if value is None else str(value)
    if raw == "male":
        return "male"
    if raw == "female":
        return "female"
    raise AccountPersistenceError("invalid persisted gender")


def _avatar_kind(value: object) -> AvatarKind:
    raw = str(value)
    if raw == "initials":
        return "initials"
    if raw == "emoji":
        return "emoji"
    raise AccountPersistenceError("invalid persisted avatar kind")


def _theme_key(value: object) -> ThemeKey:
    raw = str(value)
    if raw == "warm-paper":
        return "warm-paper"
    if raw == "harbor-blue":
        return "harbor-blue"
    if raw == "orchid-archive":
        return "orchid-archive"
    if raw == "moss-green":
        return "moss-green"
    raise AccountPersistenceError("invalid persisted theme key")


def _landing_page(value: object) -> LandingPage:
    raw = str(value)
    if raw == "chat":
        return "chat"
    if raw == "manage":
        return "manage"
    raise AccountPersistenceError("invalid persisted landing page")


def _presence(value: object) -> Presence:
    raw = str(value)
    if raw == "online":
        return "online"
    if raw == "away":
        return "away"
    if raw == "offline":
        return "offline"
    raise AccountPersistenceError("invalid persisted presence")


__all__ = ("SessionRepository", "SQLiteAccountsAdapter", "hash_session_token")
