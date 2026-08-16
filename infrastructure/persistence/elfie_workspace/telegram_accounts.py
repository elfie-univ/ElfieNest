"""Persist Telegram configuration in the existing per-Elfie history schema."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Optional, Tuple, cast

from app.features.communication.telegram_port_models import (
    StoredTelegramAccount,
    StoredTelegramBinding,
    TelegramStoredStatus,
)
from app.features.communication.telegram_ports import (
    TelegramAccountPortError,
    TelegramAccountStoreConflict,
)
from infrastructure.persistence.layout.data_home import data_home_from_db_path
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.nest_db.history_schema import create_history_schema
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection

_CHANNEL = "telegram"
_ACCOUNT_CURSOR_SCOPE = "$account"


class SQLiteTelegramAccountStore:
    """Store active platform facts without adding a second chat database."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._data_home = (
            None
            if self._db_path == ":memory:"
            else data_home_from_db_path(self._db_path)
        )
        self._lock = RLock()

    def owner_user_id(self, elfie_id: str) -> Optional[int]:
        if self._db_path == ":memory:":
            return None
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    "SELECT owner_user_id FROM elfies WHERE elfie_id=?", (elfie_id,)
                ).fetchone()
        except (OSError, sqlite3.DatabaseError) as error:
            raise TelegramAccountPortError("Unable to resolve Elfie owner") from error
        return None if row is None else int(row[0])

    def get_account(self, elfie_id: str) -> Optional[StoredTelegramAccount]:
        path = self._existing_history_path(elfie_id)
        if path is None:
            return None
        try:
            with app_sqlite_connection(path) as connection:
                row = connection.execute(
                    """SELECT external_account_id, display_name, status, meta_json,
                              updated_at
                       FROM self_channel_accounts
                       WHERE self_account_id=? AND channel=?
                         AND status IN ('active','attention')""",
                    (_self_account_id(elfie_id), _CHANNEL),
                ).fetchone()
            return None if row is None else _account_from_row(elfie_id, row)
        except (OSError, ValueError, TypeError, sqlite3.DatabaseError) as error:
            raise TelegramAccountPortError("Unable to read Telegram account") from error

    def list_active_accounts(self) -> Tuple[StoredTelegramAccount, ...]:
        if self._db_path == ":memory:":
            return ()
        try:
            with app_sqlite_connection(self._db_path) as connection:
                elfie_ids = tuple(
                    str(row[0])
                    for row in connection.execute(
                        "SELECT elfie_id FROM elfies ORDER BY elfie_id"
                    )
                )
            accounts = tuple(
                account
                for elfie_id in elfie_ids
                if (account := self.get_account(elfie_id)) is not None
            )
            return accounts
        except TelegramAccountPortError:
            raise
        except (OSError, sqlite3.DatabaseError) as error:
            raise TelegramAccountPortError(
                "Unable to list Telegram accounts"
            ) from error

    def save_account(self, account: StoredTelegramAccount) -> None:
        if account.status not in {"active", "attention"}:
            raise TelegramAccountPortError("Invalid Telegram account status")
        if self.owner_user_id(account.elfie_id) != account.configured_owner_user_id:
            raise TelegramAccountPortError("Telegram account owner no longer matches")
        with self._lock:
            self._reject_duplicate_bot(account.bot_id, account.elfie_id)
            path = self._history_path(account.elfie_id)
            create_history_schema(path)
            try:
                with app_sqlite_connection(path) as connection:
                    existing = connection.execute(
                        """SELECT external_account_id, meta_json
                           FROM self_channel_accounts
                           WHERE self_account_id=?""",
                        (_self_account_id(account.elfie_id),),
                    ).fetchone()
                    existing_owner = None
                    if existing is not None:
                        existing_owner = _object(existing[1]).get(
                            "configured_owner_user_id"
                        )
                    if existing is not None and (
                        str(existing[0]) != account.bot_id
                        or existing_owner != account.configured_owner_user_id
                    ):
                        self._revoke_binding_rows(
                            connection,
                            account.elfie_id,
                            account.last_checked_at,
                        )
                        connection.execute(
                            "DELETE FROM ingestion_offsets WHERE channel=? AND self_account_id=?",
                            (_CHANNEL, _self_account_id(account.elfie_id)),
                        )
                    metadata = _json(
                        {
                            "bot_username": account.bot_username,
                            "configured_owner_user_id": account.configured_owner_user_id,
                            "credential_ref": account.credential_ref,
                            "issue": account.issue,
                            "last_checked_at": account.last_checked_at,
                        }
                    )
                    connection.execute(
                        """INSERT INTO self_channel_accounts (
                               self_account_id, channel, external_account_id,
                               display_name, status, meta_json, created_at, updated_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(self_account_id) DO UPDATE SET
                               channel=excluded.channel,
                               external_account_id=excluded.external_account_id,
                               display_name=excluded.display_name,
                               status=excluded.status,
                               meta_json=excluded.meta_json,
                               updated_at=excluded.updated_at""",
                        (
                            _self_account_id(account.elfie_id),
                            _CHANNEL,
                            account.bot_id,
                            account.display_name,
                            account.status,
                            metadata,
                            account.last_checked_at,
                            account.last_checked_at,
                        ),
                    )
                    connection.commit()
            except sqlite3.IntegrityError as error:
                raise TelegramAccountStoreConflict(
                    "Telegram bot is already configured"
                ) from error
            except (OSError, sqlite3.DatabaseError) as error:
                raise TelegramAccountPortError(
                    "Unable to save Telegram account"
                ) from error

    def mark_account_health(
        self,
        elfie_id: str,
        *,
        status: str,
        checked_at: str,
        issue: Optional[str],
    ) -> None:
        if status not in {"active", "attention"}:
            raise TelegramAccountPortError("Invalid Telegram account status")
        account = self.get_account(elfie_id)
        if account is None:
            return
        self.save_account(
            StoredTelegramAccount(
                elfie_id=account.elfie_id,
                bot_id=account.bot_id,
                bot_username=account.bot_username,
                display_name=account.display_name,
                credential_ref=account.credential_ref,
                configured_owner_user_id=account.configured_owner_user_id,
                status=cast(TelegramStoredStatus, status),
                last_checked_at=checked_at,
                issue=issue,
            )
        )

    def disconnect_account(self, elfie_id: str, *, disconnected_at: str) -> None:
        path = self._existing_history_path(elfie_id)
        if path is None:
            return
        try:
            with self._lock, app_sqlite_connection(path) as connection:
                self._revoke_binding_rows(connection, elfie_id, disconnected_at)
                connection.execute(
                    """UPDATE self_channel_accounts
                       SET status='disconnected', updated_at=?
                       WHERE self_account_id=? AND channel=?""",
                    (disconnected_at, _self_account_id(elfie_id), _CHANNEL),
                )
                connection.execute(
                    "DELETE FROM ingestion_offsets WHERE channel=? AND self_account_id=?",
                    (_CHANNEL, _self_account_id(elfie_id)),
                )
                connection.commit()
        except (OSError, sqlite3.DatabaseError) as error:
            raise TelegramAccountPortError(
                "Unable to disconnect Telegram account"
            ) from error

    def replace_binding(self, binding: StoredTelegramBinding) -> None:
        account = self.get_account(binding.elfie_id)
        if account is None:
            raise TelegramAccountPortError("Telegram account is not configured")
        if self.owner_user_id(binding.elfie_id) != binding.local_owner_user_id:
            raise TelegramAccountPortError("Telegram binding owner no longer matches")
        path = self._history_path(binding.elfie_id)
        create_history_schema(path)
        self_account_id = _self_account_id(binding.elfie_id)
        channel_account_id = _channel_account_id(binding.telegram_user_id)
        storage_conversation_id = _storage_conversation_id(binding.conversation_id)
        profile = _json(
            {
                "local_owner_account_id": binding.local_owner_account_id,
                "local_owner_user_id": binding.local_owner_user_id,
                "telegram_username": binding.telegram_username,
            }
        )
        conversation_meta = _json(
            {
                "local_owner_user_id": binding.local_owner_user_id,
                "telegram_chat_id": binding.telegram_chat_id,
            }
        )
        try:
            with self._lock, app_sqlite_connection(path) as connection:
                self._revoke_binding_rows(
                    connection, binding.elfie_id, binding.bound_at
                )
                connection.execute(
                    """INSERT INTO external_channel_accounts (
                           channel_account_id, knowledge_entity_id, channel,
                           external_account_id, display_name, profile_json,
                           first_seen_at, last_seen_at, updated_at
                       ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(channel_account_id) DO UPDATE SET
                           external_account_id=excluded.external_account_id,
                           display_name=excluded.display_name,
                           profile_json=excluded.profile_json,
                           last_seen_at=excluded.last_seen_at,
                           updated_at=excluded.updated_at""",
                    (
                        channel_account_id,
                        _CHANNEL,
                        binding.telegram_user_id,
                        binding.display_name,
                        profile,
                        binding.bound_at,
                        binding.bound_at,
                        binding.bound_at,
                    ),
                )
                connection.execute(
                    """INSERT INTO conversations (
                           conversation_id, channel, external_thread_id,
                           conversation_type, title, self_account_id, started_at,
                           last_message_at, status, meta_json
                       ) VALUES (?, ?, ?, 'direct', NULL, ?, ?, NULL, 'active', ?)
                       ON CONFLICT(conversation_id) DO UPDATE SET
                           status='active', meta_json=excluded.meta_json""",
                    (
                        storage_conversation_id,
                        _CHANNEL,
                        binding.conversation_id,
                        self_account_id,
                        binding.bound_at,
                        conversation_meta,
                    ),
                )
                self._activate_participant(
                    connection,
                    storage_conversation_id,
                    participant_type="self",
                    self_account_id=self_account_id,
                    channel_account_id=None,
                    display_name=account.display_name,
                    role="self",
                    joined_at=binding.bound_at,
                )
                self._activate_participant(
                    connection,
                    storage_conversation_id,
                    participant_type="external",
                    self_account_id=None,
                    channel_account_id=channel_account_id,
                    display_name=binding.display_name,
                    role="owner",
                    joined_at=binding.bound_at,
                )
                connection.commit()
        except sqlite3.IntegrityError as error:
            raise TelegramAccountStoreConflict(
                "Telegram identity could not be bound"
            ) from error
        except (OSError, sqlite3.DatabaseError) as error:
            raise TelegramAccountPortError("Unable to save Telegram binding") from error

    def get_binding(self, elfie_id: str) -> Optional[StoredTelegramBinding]:
        path = self._existing_history_path(elfie_id)
        if path is None:
            return None
        try:
            with app_sqlite_connection(path) as connection:
                row = connection.execute(
                    """SELECT external.external_account_id,
                              external.display_name, external.profile_json,
                              conversation.external_thread_id,
                              conversation.meta_json, participant.joined_at
                       FROM conversations AS conversation
                       JOIN conversation_participants AS participant
                         ON participant.conversation_id=conversation.conversation_id
                        AND participant.participant_type='external'
                        AND participant.left_at IS NULL
                       JOIN external_channel_accounts AS external
                         ON external.channel_account_id=participant.channel_account_id
                       WHERE conversation.channel=?
                         AND conversation.self_account_id=?
                         AND conversation.status='active'
                       ORDER BY participant.joined_at DESC LIMIT 1""",
                    (_CHANNEL, _self_account_id(elfie_id)),
                ).fetchone()
            if row is None:
                return None
            profile = _object(row[2])
            metadata = _object(row[4])
            username = profile.get("telegram_username")
            return StoredTelegramBinding(
                elfie_id=elfie_id,
                telegram_user_id=str(row[0]),
                telegram_chat_id=str(metadata["telegram_chat_id"]),
                telegram_username=None if username is None else str(username),
                display_name=str(row[1] or ""),
                local_owner_user_id=int(metadata["local_owner_user_id"]),
                local_owner_account_id=str(profile["local_owner_account_id"]),
                conversation_id=str(row[3]),
                bound_at=str(row[5]),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            sqlite3.DatabaseError,
        ) as error:
            raise TelegramAccountPortError("Unable to read Telegram binding") from error

    def next_update_id(self, elfie_id: str) -> Optional[int]:
        path = self._existing_history_path(elfie_id)
        if path is None:
            return None
        try:
            with app_sqlite_connection(path) as connection:
                row = connection.execute(
                    """SELECT cursor FROM ingestion_offsets
                       WHERE channel=? AND self_account_id=?
                         AND external_thread_id=?""",
                    (_CHANNEL, _self_account_id(elfie_id), _ACCOUNT_CURSOR_SCOPE),
                ).fetchone()
            return None if row is None else int(row[0])
        except (OSError, TypeError, ValueError, sqlite3.DatabaseError) as error:
            raise TelegramAccountPortError("Unable to read Telegram cursor") from error

    def save_next_update_id(
        self, elfie_id: str, *, next_update_id: int, synced_at: str
    ) -> None:
        if next_update_id < 0:
            raise TelegramAccountPortError("Telegram update cursor cannot be negative")
        if self.get_account(elfie_id) is None:
            raise TelegramAccountPortError("Telegram account is not configured")
        path = self._history_path(elfie_id)
        try:
            with self._lock, app_sqlite_connection(path) as connection:
                current = connection.execute(
                    """SELECT CAST(cursor AS INTEGER) FROM ingestion_offsets
                       WHERE channel=? AND self_account_id=?
                         AND external_thread_id=?""",
                    (_CHANNEL, _self_account_id(elfie_id), _ACCOUNT_CURSOR_SCOPE),
                ).fetchone()
                if current is not None and int(current[0]) >= next_update_id:
                    return
                connection.execute(
                    """INSERT INTO ingestion_offsets (
                           offset_id, channel, self_account_id, external_thread_id,
                           cursor, last_synced_at, meta_json
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(channel, self_account_id, external_thread_id)
                       DO UPDATE SET cursor=excluded.cursor,
                           last_synced_at=excluded.last_synced_at,
                           meta_json=excluded.meta_json""",
                    (
                        f"offset:telegram:{elfie_id}",
                        _CHANNEL,
                        _self_account_id(elfie_id),
                        _ACCOUNT_CURSOR_SCOPE,
                        str(next_update_id),
                        synced_at,
                        _json({"scope": "account"}),
                    ),
                )
                connection.commit()
        except (OSError, sqlite3.DatabaseError) as error:
            raise TelegramAccountPortError("Unable to save Telegram cursor") from error

    def _reject_duplicate_bot(self, bot_id: str, selected_elfie_id: str) -> None:
        for account in self.list_active_accounts():
            if account.elfie_id != selected_elfie_id and account.bot_id == bot_id:
                raise TelegramAccountStoreConflict(
                    "Telegram bot is already configured for another Elfie"
                )

    def _history_path(self, elfie_id: str) -> Path:
        if self._data_home is None:
            raise TelegramAccountPortError(
                "In-memory Nest database has no per-Elfie history store"
            )
        return final_root_layout(self._data_home).elfie(elfie_id).history_database

    def _existing_history_path(self, elfie_id: str) -> Optional[Path]:
        try:
            path = self._history_path(elfie_id)
        except (TelegramAccountPortError, ValueError):
            return None
        return path if path.exists() else None

    @staticmethod
    def _activate_participant(
        connection: sqlite3.Connection,
        conversation_id: str,
        *,
        participant_type: str,
        self_account_id: Optional[str],
        channel_account_id: Optional[str],
        display_name: str,
        role: str,
        joined_at: str,
    ) -> None:
        column = (
            "self_account_id" if self_account_id is not None else "channel_account_id"
        )
        identity = self_account_id or channel_account_id
        cursor = connection.execute(
            f"""UPDATE conversation_participants
                SET display_name_snapshot=?, role=?, joined_at=?, left_at=NULL
                WHERE conversation_id=? AND {column}=?""",
            (display_name, role, joined_at, conversation_id, identity),
        )
        if cursor.rowcount:
            return
        connection.execute(
            """INSERT INTO conversation_participants (
                   conversation_id, participant_type, self_account_id,
                   channel_account_id, display_name_snapshot, role, joined_at, left_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (
                conversation_id,
                participant_type,
                self_account_id,
                channel_account_id,
                display_name,
                role,
                joined_at,
            ),
        )

    @staticmethod
    def _revoke_binding_rows(
        connection: sqlite3.Connection, elfie_id: str, timestamp: str
    ) -> None:
        self_account_id = _self_account_id(elfie_id)
        connection.execute(
            """UPDATE conversation_participants SET left_at=?
               WHERE left_at IS NULL AND conversation_id IN (
                   SELECT conversation_id FROM conversations
                   WHERE channel=? AND self_account_id=?
               )""",
            (timestamp, _CHANNEL, self_account_id),
        )
        connection.execute(
            """UPDATE conversations SET status='disconnected'
               WHERE channel=? AND self_account_id=? AND status='active'""",
            (_CHANNEL, self_account_id),
        )


def _account_from_row(elfie_id: str, row: sqlite3.Row) -> StoredTelegramAccount:
    metadata = _object(row[3])
    issue = metadata.get("issue")
    return StoredTelegramAccount(
        elfie_id=elfie_id,
        bot_id=str(row[0]),
        bot_username=str(metadata["bot_username"]),
        display_name=str(row[1] or ""),
        credential_ref=str(metadata["credential_ref"]),
        configured_owner_user_id=int(metadata["configured_owner_user_id"]),
        status=cast(TelegramStoredStatus, str(row[2])),
        last_checked_at=str(metadata.get("last_checked_at") or row[4]),
        issue=None if issue is None else str(issue),
    )


def _self_account_id(elfie_id: str) -> str:
    return f"self:{_CHANNEL}:{elfie_id}"


def _channel_account_id(telegram_user_id: str) -> str:
    return f"external:{_CHANNEL}:{telegram_user_id}"


def _storage_conversation_id(external_thread_id: str) -> str:
    digest = hashlib.sha256(f"{_CHANNEL}\0{external_thread_id}".encode()).hexdigest()
    return f"conversation:{digest}"


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _object(raw: object) -> dict[str, Any]:
    value = json.loads(str(raw))
    if not isinstance(value, dict):
        raise ValueError("Telegram metadata must be a JSON object")
    return value


__all__ = ("SQLiteTelegramAccountStore",)
