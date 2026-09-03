"""Discord account facts reuse the existing per-Elfie history schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.features.communication.discord_port_models import (
    StoredDiscordAccount,
    StoredDiscordBinding,
)
from app.features.communication.discord_ports import DiscordAccountStoreConflict
from infrastructure.persistence.elfie_workspace.discord_accounts import (
    SQLiteDiscordAccountStore,
)
from infrastructure.persistence.nest_db.final_schema import create_final_nest_database


def _database(tmp_path: Path) -> Path:
    db_path = tmp_path / "nest.db"
    create_final_nest_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO users (id, account_id, display_name, role, password_hash) VALUES (?, ?, ?, ?, ?)",
            [
                (7, "owner-seven", "七号主人", "user", "unused"),
                (8, "owner-eight", "八号主人", "admin", "unused"),
            ],
        )
        connection.executemany(
            "INSERT INTO elfies (elfie_id, owner_user_id, adopted_at, status) VALUES (?, ?, ?, ?)",
            [
                ("00000001", 7, "2026-08-16T00:00:00Z", "online"),
                ("00000002", 8, "2026-08-16T00:00:00Z", "online"),
            ],
        )
        connection.commit()
    return db_path


def _account(elfie_id: str = "00000001", bot_id: str = "991") -> StoredDiscordAccount:
    return StoredDiscordAccount(
        elfie_id,
        bot_id,
        "elfienest_star",
        "星星机器人",
        f"ELFIE_DISCORD_{elfie_id}_BOT_TOKEN",
        7 if elfie_id == "00000001" else 8,
        "active",
        "2026-08-16T01:00:00.000Z",
        None,
    )


def _binding() -> StoredDiscordBinding:
    return StoredDiscordBinding(
        "00000001",
        "701",
        "1701",
        "owner_seven",
        "七号主人",
        7,
        "owner-seven",
        "discord:1701",
        "2026-08-16T01:05:00.000Z",
    )


def test_account_and_binding_reuse_history_schema(tmp_path: Path) -> None:
    store = SQLiteDiscordAccountStore(_database(tmp_path))
    store.save_account(_account())
    store.replace_binding(_binding())

    assert store.owner_user_id("00000001") == 7
    assert store.get_account("00000001") == _account()
    assert store.get_binding("00000001") == _binding()
    history_path = tmp_path / "elfies" / "00000001" / "conversations" / "history.sqlite"
    with sqlite3.connect(history_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert "conversations" in tables
    assert "self_channel_accounts" in tables
    assert "external_channel_accounts" in tables


def test_same_bot_cannot_be_active_for_two_elfies(tmp_path: Path) -> None:
    store = SQLiteDiscordAccountStore(_database(tmp_path))
    store.save_account(_account())
    with pytest.raises(DiscordAccountStoreConflict):
        store.save_account(_account("00000002"))


def test_disconnect_revokes_binding_but_keeps_history(tmp_path: Path) -> None:
    store = SQLiteDiscordAccountStore(_database(tmp_path))
    store.save_account(_account())
    store.replace_binding(_binding())
    store.disconnect_account("00000001", disconnected_at="2026-08-16T02:00:00.000Z")

    assert store.get_account("00000001") is None
    assert store.get_binding("00000001") is None
    history_path = tmp_path / "elfies" / "00000001" / "conversations" / "history.sqlite"
    with sqlite3.connect(history_path) as connection:
        row = connection.execute(
            "SELECT status FROM conversations WHERE external_thread_id='discord:1701'"
        ).fetchone()
    assert row == ("disconnected",)
