from __future__ import annotations

import sqlite3
from pathlib import Path

from app.features.communication import ConversationMessageWrite
from infrastructure.persistence.store import init_db
from infrastructure.persistence.communication import SQLiteConversationHistoryAdapter
from test.app.interfaces.api._helpers import adopt_test_elfie, create_test_owner


def test_adapter_appends_once_to_the_authoritative_elfie_history(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)
    elfie_id = adopt_test_elfie(db_path, 1)
    adapter = SQLiteConversationHistoryAdapter(db_path)
    message = ConversationMessageWrite(
        elfie_id=elfie_id,
        conversation_id="owner:1",
        sender="user",
        text="只写一次",
        channel="web",
        user_id=1,
        message_id="web:fixed-source",
    )

    first = adapter.append_message(message)
    second = adapter.append_message(message)
    listed = adapter.list_messages(
        elfie_id,
        conversation_id="owner:1",
        user_id=1,
    )

    assert first.id == second.id
    assert [item.text for item in listed] == ["只写一次"]
    history_path = tmp_path / "elfies" / elfie_id / "conversations" / "history.sqlite"
    with sqlite3.connect(history_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1
