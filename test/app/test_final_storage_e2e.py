"""One fresh-root product journey across all three final SQLite stores."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.features.adoption.service import (
    AdoptionRequest,
    adopt_elfie_for_user,
)
from app.infrastructure.persistence.elfie_chat_history import (
    ElfieChatMessageInput,
    ElfieChatSender,
    list_elfie_chat_history,
    record_elfie_chat_message,
)
from app.infrastructure.persistence.store import get_db, init_db
from elfie import ElfieFactory
from elfie.brain.memory.knowledge_schema import KNOWLEDGE_TABLES

_NEST_TABLES = {
    "device_audit_events",
    "elfies",
    "embodiment_sessions",
    "external_bodies",
    "local_installations",
    "nest_settings",
    "sessions",
    "users",
}
_HISTORY_TABLES = {
    "attachments",
    "conversation_participants",
    "conversations",
    "external_channel_accounts",
    "ingestion_offsets",
    "messages",
    "self_channel_accounts",
}


def test_fresh_root_survives_adoption_chat_memory_and_restart(tmp_path: Path) -> None:
    data_home = tmp_path / "product-data"
    db_path = data_home / "nest.db"
    init_db(str(db_path))
    with get_db(str(db_path)) as connection:
        owner_id = int(
            connection.execute(
                """INSERT INTO users(username,password_hash,role,elfie_limit)
                   VALUES ('owner','unused','owner',1)"""
            ).lastrowid
        )
        connection.commit()

    adopted = adopt_elfie_for_user(
        str(db_path),
        user_id=owner_id,
        request=AdoptionRequest(
            name="Aifei",
            species_id="fox",
            personality_style="好奇探索",
            height="standard",
            build="standard",
        ),
    )
    workspace = data_home / "elfies" / adopted.elfie_id
    record_elfie_chat_message(
        adopted.elfie_id,
        ElfieChatMessageInput(
            message_id="owner-message-1",
            conversation_id="owner-chat",
            sender=ElfieChatSender.USER,
            text="记住金色的花",
            channel="web",
            user_id=owner_id,
        ),
        data_home=data_home,
    )
    elfie = ElfieFactory().restore(workspace, elfie_id=adopted.elfie_id)
    elfie.memory.record_episode("今天看到了金色的花", "happy", 80.0)
    elfie.memory.close()

    init_db(str(db_path))
    reopened = ElfieFactory().restore(workspace, elfie_id=adopted.elfie_id)
    assert "今天看到了金色的花" in reopened.memory.retrieve_relevant_memories(
        "金色的花"
    )
    reopened.memory.close()
    assert [
        message.text
        for message in list_elfie_chat_history(
            adopted.elfie_id, "owner-chat", data_home=data_home
        )
    ] == ["记住金色的花"]
    assert (workspace / "profile" / "profile.yaml").is_file()
    assert _tables(db_path) == _NEST_TABLES
    assert _tables(workspace / "conversations" / "history.sqlite") == _HISTORY_TABLES
    assert _tables(workspace / "memory" / "knowledge.sqlite") == set(KNOWLEDGE_TABLES)
    assert not any(data_home.rglob("history_v2.sqlite"))
    assert not any(data_home.rglob("graph_memory.db"))
    assert not (data_home / "users").exists()


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            if not str(row[0]).startswith("sqlite_")
        }
