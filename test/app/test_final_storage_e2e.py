"""One fresh-root product journey across all three final SQLite stores."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from ai_runtime.storage.data_home import get_config_path
from app.bootstrap import create_app
from app.features.adoption.service import (
    AdoptionRequest,
    adopt_elfie_for_user,
)
from app.features.configuration.runtime_store import write_system_section
from app.infrastructure.devices import DeviceRegistry
from app.infrastructure.persistence.embodiment_sessions import begin_hosting
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.cli.doctor_commands import repair_local_runtime_state
from elfie import ElfieFactory
from elfie.brain.memory.knowledge_schema import KNOWLEDGE_TABLES
from elfie.communication import InboundDisposition, InboundDispositionStatus
from elfie.message_types import EventId
from infrastructure.persistence.elfie_chat_history import (
    ElfieChatMessageInput,
    ElfieChatSender,
    list_elfie_chat_history,
    record_elfie_chat_message,
)
from test.app.interfaces.api._helpers import complete_test_setup, create_test_owner

_NEST_TABLES = {
    "device_audit_events",
    "elfies",
    "embodiment_sessions",
    "external_bodies",
    "food_packages",
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
                """INSERT INTO users(account_id,password_hash,role,elfie_limit)
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


def test_full_product_chain_uses_one_explicit_final_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    # Given: one explicit fresh root used by the entire product process.
    data_home = tmp_path / "selected-root"
    db_path = data_home / "nest.db"
    monkeypatch.setenv("ELFIE_HOME", str(data_home))
    init_db(str(db_path))
    owner_id = create_test_owner(str(db_path))

    # When: Setup, Nest, Body, HTTP/WS Chat, Memory, config, and Doctor run.
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        engine = MagicMock()
        engine.session.has_repository = True
        engine.session.send_user_message.return_value = InboundDisposition(
            message_id=EventId("accepted-message"),
            channel_id="godot-owner",
            status=InboundDispositionStatus.ACCEPTED,
        )
        application = create_app(engine=engine, db_path=str(db_path), ws_port=9876)
        with TestClient(application, base_url="http://127.0.0.1:8000") as client:
            login = client.post(
                "/api/v1/auth/login",
                data={"account_id": "owner", "password": "ownerchangeme"},
            )
            csrf_token = login.headers["X-CSRF-Token"]
            complete_test_setup(str(db_path))
            adopted = adopt_elfie_for_user(
                str(db_path),
                user_id=owner_id,
                request=AdoptionRequest(
                    name="小白",
                    species_id="fox",
                    personality_style="好奇探索",
                    height="standard",
                    build="standard",
                ),
            )
            elfie_id = adopted.elfie_id
            bed = client.put(
                f"/api/v1/admin/nest/elfies/{elfie_id}/bed",
                json={"home_anchor_id": "bed-01"},
                headers={"X-CSRF-Token": csrf_token},
            )
            body = DeviceRegistry(str(db_path)).enroll(
                elfie_id,
                "模拟身体",
                "simulated",
            )
            begin_hosting(str(db_path), elfie_id, body.body_id, lease_seconds=30)
            http_message = client.post(
                f"/api/v1/me/conversations/{elfie_id}/messages",
                json={"text": "HTTP 消息"},
                headers={"X-CSRF-Token": csrf_token},
            )
            session_token = client.cookies.get("session_token")
            with client.websocket_connect(
                "/api/v1/ws/chat",
                headers={"cookie": f"session_token={session_token}"},
            ) as websocket:
                assert websocket.receive_json()["event"] == "ready"
                websocket.send_json(
                    {"event": "user_message", "elfie_id": elfie_id, "text": "WS 消息"}
                )
                ws_message = websocket.receive_json()
            workspace = data_home / "elfies" / elfie_id
            elfie = ElfieFactory().restore(workspace, elfie_id=elfie_id)
            elfie.memory.record_episode("完整链路记忆", "happy", 80.0)
            elfie.memory.close()
            write_system_section(get_config_path(), "security", {"session_ttl_days": 5})
            repair_local_runtime_state()

            assert adopted.elfie_id == elfie_id
            assert bed.status_code == 200
            assert http_message.status_code == 201
            assert ws_message["event"] == "message"

        # Then: a restarted app reads the same final stores without fallback.
        restarted = create_app(engine=None, db_path=str(db_path), ws_port=9877)
        with TestClient(restarted, base_url="http://127.0.0.1:8000") as client:
            login = client.post(
                "/api/v1/auth/login",
                data={"account_id": "owner", "password": "ownerchangeme"},
            )
            assert login.status_code == 200
            messages = client.get(f"/api/v1/me/conversations/{elfie_id}/messages")
            assert [row["text"] for row in messages.json()["items"]] == [
                "HTTP 消息",
                "WS 消息",
            ]
        reopened = ElfieFactory().restore(workspace, elfie_id=elfie_id)
        assert "完整链路记忆" in reopened.memory.retrieve_relevant_memories("完整链路")
        reopened.memory.close()
        assert _tables(db_path) == _NEST_TABLES
        assert (
            _tables(workspace / "conversations" / "history.sqlite") == _HISTORY_TABLES
        )
        assert _tables(workspace / "memory" / "knowledge.sqlite") == set(
            KNOWLEDGE_TABLES
        )


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            if not str(row[0]).startswith("sqlite_")
        }
