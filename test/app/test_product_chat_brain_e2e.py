"""Product chat acceptance through the real NestSession and Elfie Brain."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.bootstrap.system_wiring.nest_session import (
    build_nest_session_services,
    restore_registered_elfies,
)
from infrastructure.models.fallback_runtime import FallbackRuntimeAdapter
from infrastructure.persistence.nest_db.store import init_db
from test.app.interfaces.api._helpers import (
    adopt_test_elfie,
    complete_test_setup,
    create_test_owner,
)


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
        runtime=FallbackRuntimeAdapter(),
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

            history = client.get(
                f"/api/v1/me/conversations/{elfie_id}/messages"
            )
            assert history.status_code == 200
            assert [item["sender"] for item in history.json()["items"]] == [
                "user",
                "elfie",
            ]
    finally:
        services.engine.session.stop_elfies()
        services.engine.session.join_elfies()
