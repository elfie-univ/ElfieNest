"""Telegram account persistence against the existing seven-table history store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.features.communication.telegram_port_models import (
    StoredTelegramAccount,
    StoredTelegramBinding,
)
from app.features.communication.telegram_ports import TelegramAccountStoreConflict
from infrastructure.persistence.elfie_workspace.telegram_accounts import (
    SQLiteTelegramAccountStore,
)
from infrastructure.persistence.nest_db.final_schema import create_final_nest_database


def _database(tmp_path: Path) -> Path:
    db_path = tmp_path / "nest.db"
    create_final_nest_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """INSERT INTO users (
                   id, account_id, display_name, role, password_hash
               ) VALUES (7, 'owner-seven', '七号主人', 'user', 'unused')"""
        )
        connection.execute(
            """INSERT INTO users (
                   id, account_id, display_name, role, password_hash
               ) VALUES (8, 'owner-eight', '八号主人', 'admin', 'unused')"""
        )
        connection.execute(
            """INSERT INTO elfies (
                   elfie_id, owner_user_id, adopted_at, status
               ) VALUES ('00000001', 7, '2026-08-16T00:00:00Z', 'online')"""
        )
        connection.execute(
            """INSERT INTO elfies (
                   elfie_id, owner_user_id, adopted_at, status
               ) VALUES ('00000002', 8, '2026-08-16T00:00:00Z', 'online')"""
        )
        connection.commit()
    return db_path


def _account(elfie_id: str = "00000001") -> StoredTelegramAccount:
    return StoredTelegramAccount(
        elfie_id=elfie_id,
        bot_id="991",
        bot_username="elfienest_star_bot",
        display_name="星星的机器人",
        credential_ref=f"ELFIE_TELEGRAM_{elfie_id}_BOT_TOKEN",
        configured_owner_user_id=7 if elfie_id == "00000001" else 8,
        status="active",
        last_checked_at="2026-08-16T01:00:00.000Z",
        issue=None,
    )


def _binding() -> StoredTelegramBinding:
    return StoredTelegramBinding(
        elfie_id="00000001",
        telegram_user_id="701",
        telegram_chat_id="1701",
        telegram_username="owner_seven",
        display_name="七号主人",
        local_owner_user_id=7,
        local_owner_account_id="owner-seven",
        conversation_id="telegram:1701",
        bound_at="2026-08-16T01:05:00.000Z",
    )


def test_account_binding_and_bot_cursor_reuse_existing_history_schema(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    store = SQLiteTelegramAccountStore(db_path)

    store.save_account(_account())
    store.replace_binding(_binding())
    store.save_next_update_id(
        "00000001", next_update_id=43, synced_at="2026-08-16T01:06:00.000Z"
    )

    assert store.owner_user_id("00000001") == 7
    assert store.get_account("00000001") == _account()
    assert store.get_binding("00000001") == _binding()
    assert store.next_update_id("00000001") == 43

    history_path = tmp_path / "elfies" / "00000001" / "conversations" / "history.sqlite"
    with sqlite3.connect(history_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        cursor_scope = connection.execute(
            "SELECT external_thread_id, cursor, meta_json FROM ingestion_offsets"
        ).fetchone()
    assert tables == {
        "attachments",
        "conversation_participants",
        "conversations",
        "external_channel_accounts",
        "ingestion_offsets",
        "messages",
        "self_channel_accounts",
    }
    assert cursor_scope == ("$account", "43", '{"scope":"account"}')


def test_same_bot_cannot_be_active_for_two_elfies(tmp_path: Path) -> None:
    store = SQLiteTelegramAccountStore(_database(tmp_path))
    store.save_account(_account())

    with pytest.raises(TelegramAccountStoreConflict):
        store.save_account(_account("00000002"))


def test_replacing_bot_revokes_binding_and_cursor_but_preserves_conversation(
    tmp_path: Path,
) -> None:
    store = SQLiteTelegramAccountStore(_database(tmp_path))
    store.save_account(_account())
    store.replace_binding(_binding())
    store.save_next_update_id(
        "00000001", next_update_id=43, synced_at="2026-08-16T01:06:00.000Z"
    )

    replacement = StoredTelegramAccount(
        **{
            **_account().__dict__,
            "bot_id": "992",
            "bot_username": "elfienest_new_bot",
            "last_checked_at": "2026-08-16T02:00:00.000Z",
        }
    )
    store.save_account(replacement)

    assert store.get_binding("00000001") is None
    assert store.next_update_id("00000001") is None
    history_path = tmp_path / "elfies" / "00000001" / "conversations" / "history.sqlite"
    with sqlite3.connect(history_path) as connection:
        row = connection.execute(
            "SELECT status FROM conversations WHERE external_thread_id='telegram:1701'"
        ).fetchone()
    assert row == ("disconnected",)


def test_disconnect_removes_runtime_authority_without_deleting_history(
    tmp_path: Path,
) -> None:
    store = SQLiteTelegramAccountStore(_database(tmp_path))
    store.save_account(_account())
    store.replace_binding(_binding())

    store.disconnect_account("00000001", disconnected_at="2026-08-16T02:00:00.000Z")

    assert store.get_account("00000001") is None
    assert store.get_binding("00000001") is None
    history_path = tmp_path / "elfies" / "00000001" / "conversations" / "history.sqlite"
    with sqlite3.connect(history_path) as connection:
        counts = connection.execute(
            "SELECT COUNT(*) FROM conversations WHERE external_thread_id='telegram:1701'"
        ).fetchone()
    assert counts == (1,)
