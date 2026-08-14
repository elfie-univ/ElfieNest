"""One fresh-root product journey across all three final SQLite stores."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.interfaces.cli.doctor_commands import repair_local_runtime_state
from elfie import ElfieFactory
from elfie.communication import InboundDisposition, InboundDispositionStatus
from elfie.diagnostics import ElfieDiagnostics
from elfie.factory import ElfieAssembly
from elfie.message_types import EventId
from infrastructure.persistence.configuration.settings import RuntimeSettingsAdapter
from infrastructure.persistence.elfie_workspace.bodies import SQLiteBodiesAdapter
from infrastructure.persistence.elfie_workspace.elfie_chat_history import (
    ElfieChatMessageInput,
    ElfieChatSender,
    list_elfie_chat_history,
    record_elfie_chat_message,
)
from infrastructure.persistence.elfie_workspace.embodiment import (
    SQLiteEmbodimentLeaseAdapter,
)
from infrastructure.persistence.layout.data_home import get_config_path
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.memory.schema import KNOWLEDGE_TABLES
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from test.app.interfaces.api._helpers import (
    adopt_test_elfie,
    complete_test_setup,
    create_test_owner,
)

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

    elfie_id = adopt_test_elfie(str(db_path), owner_id, name="Aifei")
    workspace = data_home / "elfies" / elfie_id
    record_elfie_chat_message(
        elfie_id,
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
    elfie = _restore(workspace)
    ElfieDiagnostics(elfie).memory.record_episode("今天看到了金色的花", "happy", 80.0)
    ElfieDiagnostics(elfie).memory.storage.close()

    init_db(str(db_path))
    reopened = _restore(workspace)
    assert "今天看到了金色的花" in ElfieDiagnostics(
        reopened
    ).memory.retrieve_relevant_memories(
        "金色的花"
    )
    ElfieDiagnostics(reopened).memory.storage.close()
    assert [
        message.text
        for message in list_elfie_chat_history(
            elfie_id, "owner-chat", data_home=data_home
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
    data_home = tmp_path / "selected-root"
    db_path = data_home / "nest.db"
    monkeypatch.setenv("ELFIE_HOME", str(data_home))
    init_db(str(db_path))
    owner_id = create_test_owner(str(db_path))

    engine = MagicMock()
    engine.session.has_repository = True
    engine.session.send_user_message.return_value = InboundDisposition(
        message_id=EventId("accepted-message"),
        channel_id="godot-owner",
        status=InboundDispositionStatus.ACCEPTED,
    )
    application = create_app(engine=engine, db_path=str(db_path))
    with TestClient(application, base_url="http://127.0.0.1:8000") as client:
        login = client.post(
            "/api/v1/auth/login",
            data={"account_id": "owner", "password": "ownerchangeme"},
        )
        csrf_token = login.headers["X-CSRF-Token"]
        complete_test_setup(str(db_path))
        elfie_id = adopt_test_elfie(str(db_path), owner_id, name="小白")
        SQLiteNestStateAdapter(str(db_path)).save_catalog(_test_world_catalog())
        bed = client.put(
            f"/api/v1/admin/nest/elfies/{elfie_id}/bed",
            json={"home_anchor_id": "dorm-01/bed-01"},
            headers={"X-CSRF-Token": csrf_token},
        )
        body = SQLiteBodiesAdapter(str(db_path)).enroll(
            owner_user_id=owner_id,
            elfie_id=elfie_id,
            display_name="模拟身体",
            body_type="simulated",
        )
        SQLiteEmbodimentLeaseAdapter(str(db_path)).begin_hosting(
            elfie_id, body.body_id, lease_seconds=30
        )
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
        elfie = _restore(workspace)
        ElfieDiagnostics(elfie).memory.record_episode("完整链路记忆", "happy", 80.0)
        ElfieDiagnostics(elfie).memory.storage.close()
        settings = RuntimeSettingsAdapter(get_config_path())
        settings.save_security_settings(
            replace(settings.load_security_settings(), session_ttl_days=5)
        )
        repair_local_runtime_state(create_lifecycle_facade())

        assert bed.status_code == 200
        assert http_message.status_code == 201
        assert ws_message["event"] == "message"

    restarted = create_app(engine=None, db_path=str(db_path))
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
    reopened = _restore(workspace)
    assert "完整链路记忆" in ElfieDiagnostics(
        reopened
    ).memory.retrieve_relevant_memories("完整链路")
    ElfieDiagnostics(reopened).memory.storage.close()
    assert _tables(db_path) == _NEST_TABLES
    assert _tables(workspace / "conversations" / "history.sqlite") == _HISTORY_TABLES
    assert _tables(workspace / "memory" / "knowledge.sqlite") == set(KNOWLEDGE_TABLES)


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            if not str(row[0]).startswith("sqlite_")
        }


def _test_world_catalog():
    from nest.public import AnchorKind, InteractionAnchor, WorldCatalog, ZoneDescriptor

    return WorldCatalog(
        nest_id="local-nest",
        revision=1,
        zones=(
            ZoneDescriptor(
                zone_id="dorm-01",
                label="Dorm 01",
                order=0,
                anchors=(
                    InteractionAnchor(
                        anchor_id="dorm-01/bed-01",
                        kind=AnchorKind.BED,
                        label="Bed 01",
                        order=0,
                    ),
                ),
            ),
        ),
    )


def _restore(workspace: Path):
    profile_store = YamlProfileStoreAdapter(workspace / "profile")
    return ElfieFactory().restore(
        ElfieAssembly(
            profile=profile_store.load(),
            memory_store=SQLiteMemoryStoreAdapter(
                workspace / "memory" / "knowledge.sqlite"
            ),
        )
    )
