"""Product chat acceptance through the real NestSession and Elfie Brain."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.bootstrap.system_wiring.nest_session import (
    build_nest_session_services,
    restore_registered_elfies,
)
from infrastructure.models.model_execution_contracts import (
    StructuredModelExecutionCapabilities,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.nest_db.store import init_db
from test.app.interfaces.api._helpers import (
    adopt_test_elfie,
    complete_test_setup,
    create_test_owner,
)


class _TestModelExecution:
    def structured_capabilities(
        self,
        food_key: str | None = None,
        food_unavailable: bool = False,
    ) -> StructuredModelExecutionCapabilities:
        return StructuredModelExecutionCapabilities(
            provider="test",
            model_key="test/chat",
            supports_json_schema=False,
            supports_tool_calling=False,
            supports_json_mode=False,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def generate_structured(self, request):
        return request.to_result(text="你好，我是小白，很高兴认识你。")


class _MemoryTraceModelExecution(_TestModelExecution):
    """Deterministic model that makes durable-memory visibility observable."""

    def __init__(self) -> None:
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        prompt = request.prompt
        current = prompt.rsplit("CURRENT_MESSAGE:\n", 1)[-1].strip()
        if "你还记得我喜欢什么颜色" in current:
            text = (
                "我从长期记忆里记得你喜欢蓝色。"
                if "episode:topic:" in prompt and "喜欢蓝色" in prompt
                else "我暂时没有找到这条记忆。"
            )
        elif "请记住" in current:
            text = "好的，我会记住你喜欢蓝色。"
        else:
            text = "收到，我们继续聊。"
        return request.to_result(text=text)


def test_web_chat_reaches_real_brain_and_persists_its_reply(
    monkeypatch,
    tmp_path: Path,
) -> None:
    data_home = tmp_path / "product-data"
    db_path = data_home / "nest.db"
    monkeypatch.setenv("ELFIE_HOME", str(data_home))
    init_db(str(db_path))
    owner_id = create_test_owner(str(db_path))
    complete_test_setup(str(db_path))
    elfie_id = adopt_test_elfie(str(db_path), owner_id, name="小白")

    services = build_nest_session_services(
        str(db_path),
        model_execution=_TestModelExecution(),
        godot_ws_port=19003,
        http_port=19002,
        tick_interval_sec=0.01,
    )
    restored = restore_registered_elfies(str(db_path), services.engine.session)
    assert [item.elfie_id for item in restored.restored] == [elfie_id]
    assert restored.failures == ()

    application = create_app(engine=services.engine, db_path=str(db_path))
    services.engine.session.configure_cognition_factory(services.model_port_factory)
    services.engine.session.start_elfies()
    try:
        with TestClient(
            application,
            base_url="http://127.0.0.1:19002",
        ) as client:
            login = client.post(
                "/api/v1/auth/login",
                data={"account_id": "owner", "password": "ownerchangeme"},
            )
            session_token = client.cookies.get("session_token")
            assert login.status_code == 200
            assert session_token is not None

            with client.websocket_connect(
                "/api/v1/ws/chat",
                headers={"Cookie": f"session_token={session_token}"},
            ) as websocket:
                assert websocket.receive_json()["event"] == "ready"
                websocket.send_json(
                    {
                        "event": "user_message",
                        "elfie_id": elfie_id,
                        "text": "你好，小白",
                    }
                )
                accepted = websocket.receive_json()
                elfie = services.engine.session.get_elfie(elfie_id)
                assert elfie is not None
                elfie.advance_clock(2.1)
                elfie.wait_for_outcome_count(1, timeout=2.0)
                assert len(elfie.turn_outcomes()) == 1
                reply = websocket.receive_json()

            assert accepted["event"] == "message"
            assert accepted["message"]["sender"] == "user"
            assert reply["event"] == "message"
            assert reply["message"]["sender"] == "elfie"
            assert reply["message"]["text"]

            history = client.get(f"/api/v1/me/conversations/{elfie_id}/messages")
            assert history.status_code == 200
            assert [item["sender"] for item in history.json()["items"]] == [
                "user",
                "elfie",
            ]
    finally:
        services.engine.session.stop_elfies()
        services.engine.session.join_elfies()


def test_web_chat_recalls_closed_topic_from_durable_memory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The product path must expose a closed topic to the next model turn."""
    data_home = tmp_path / "product-memory-data"
    db_path = data_home / "nest.db"
    monkeypatch.setenv("ELFIE_HOME", str(data_home))
    init_db(str(db_path))
    owner_id = create_test_owner(str(db_path))
    complete_test_setup(str(db_path))
    elfie_id = adopt_test_elfie(str(db_path), owner_id, name="Lumi")
    model = _MemoryTraceModelExecution()

    services = build_nest_session_services(
        str(db_path),
        model_execution=model,
        godot_ws_port=19005,
        http_port=19004,
        tick_interval_sec=0.01,
    )
    restored = restore_registered_elfies(str(db_path), services.engine.session)
    assert [item.elfie_id for item in restored.restored] == [elfie_id]
    assert restored.failures == ()

    application = create_app(engine=services.engine, db_path=str(db_path))
    services.engine.session.configure_cognition_factory(services.model_port_factory)
    services.engine.session.start_elfies()
    try:
        with TestClient(
            application,
            base_url="http://127.0.0.1:19004",
        ) as client:
            login = client.post(
                "/api/v1/auth/login",
                data={"account_id": "owner", "password": "ownerchangeme"},
            )
            session_token = client.cookies.get("session_token")
            assert login.status_code == 200
            assert session_token is not None

            with client.websocket_connect(
                "/api/v1/ws/chat",
                headers={"Cookie": f"session_token={session_token}"},
            ) as websocket:
                assert websocket.receive_json()["event"] == "ready"

                def send(text: str) -> dict:
                    elfie = services.engine.session.get_elfie(elfie_id)
                    assert elfie is not None
                    before = len(elfie.turn_outcomes())
                    websocket.send_json(
                        {"event": "user_message", "elfie_id": elfie_id, "text": text}
                    )
                    accepted = websocket.receive_json()
                    elfie.advance_clock(2.1)
                    elfie.wait_for_outcome_count(before + 1, timeout=2.0)
                    reply = websocket.receive_json()
                    assert accepted["event"] == "message"
                    assert reply["event"] == "message"
                    assert reply["message"]["sender"] == "elfie"
                    return reply

                first = send("请记住：我喜欢蓝色。")
                assert first["message"]["text"] == "好的，我会记住你喜欢蓝色。"
                closed = send("这个话题先这样")
                assert closed["message"]["text"] == "收到，我们继续聊。"

                # Push the original exchange out of the short recent tail so
                # the following assertion cannot pass from CONTEXT_ONLY alone.
                for index in range(18):
                    send(f"无关的流水消息 {index}")

                recalled = send("换个话题：你还记得我喜欢什么颜色吗？")
                assert recalled["message"]["text"] == ("我从长期记忆里记得你喜欢蓝色。")

            traced = [
                request
                for request in model.requests
                if "CURRENT_MESSAGE:\n换个话题：你还记得我喜欢什么颜色吗？"
                in request.prompt
            ]
            assert traced
            assert all(request.allowed_tools == () for request in traced)
            assert any(
                "MEMORY_RECALL_STATUS:\nstatus=recalled;" in request.prompt
                and '<EPISODE id="episode:topic:' in request.prompt
                and "喜欢蓝色" in request.prompt
                for request in traced
            )

            history = client.get(f"/api/v1/me/conversations/{elfie_id}/messages")
            assert history.status_code == 200
            assert [item["sender"] for item in history.json()["items"]].count(
                "user"
            ) == 21

        with SQLiteMemoryStoreAdapter(
            data_home / "elfies" / elfie_id / "memory" / "knowledge.sqlite"
        ) as memory:
            episodes = memory.list_episodes()
            assert any(
                episode.episode_id.startswith("episode:topic:")
                and "喜欢蓝色" in episode.content_text
                for episode in episodes
            )
    finally:
        services.engine.session.stop_elfies()
        services.engine.session.join_elfies()
