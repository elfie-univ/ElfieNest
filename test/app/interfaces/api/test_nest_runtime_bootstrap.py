from __future__ import annotations

import inspect
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.interfaces.api import app as api_app
from app.orchestration.lifecycle import ApplicationRuntimeLifecycle
from app.orchestration.nest_session import ElfieNestEngine
from app.orchestration.resident_admission import ResidentAdmissionService
from elfie import Elfie
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


def test_application_lifespan_accepts_engine_with_registered_elfies(tmp_path) -> None:
    # Given: the service has bound its Nest repository before loading an Elfie.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, ?)",
            ("owner", "hash", "owner"),
        )
        connection.execute(
            """INSERT INTO elfies
               (elfie_id, owner_user_id, adopted_at, status)
               VALUES (?, ?, CURRENT_TIMESTAMP, 'offline')""",
            (
                "00000001",
                cursor.lastrowid,
            ),
        )
        connection.commit()
    engine = ElfieNestEngine(
        FakeWorldRuntime(),
        state_store=SQLiteNestStateAdapter(db_path),
    )
    engine.session.register_elfie("00000001", MagicMock(spec=Elfie))
    application = create_app(engine=engine, db_path=db_path)

    # When: the HTTP application's lifespan starts after the Elfie is loaded.
    with TestClient(application) as client:
        response = client.get("/api/health")

    # Then: startup succeeds instead of attempting to attach a second repository.
    assert response.status_code == 200
    assert response.json()["engine_ready"] is False


def test_interface_application_factory_has_no_concrete_startup_composition() -> None:
    source = inspect.getsource(api_app.create_http_application)

    assert "init_db(" not in source
    assert "seed_initial_owner_if_env_set(" not in source
    assert "AuthenticatedWSManager(" not in source
    assert "ws_manager.start(" not in source
    assert "ws_manager.stop(" not in source


def test_lifespan_recovers_admissions_before_runtime_start(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    order: list[str] = []

    def recover_pending(self) -> tuple[object, ...]:
        del self
        order.append("admission-recovery")
        return ()

    def start(self) -> None:
        del self
        order.append("runtime-start")

    def stop(self) -> None:
        del self

    monkeypatch.setattr(ResidentAdmissionService, "recover_pending", recover_pending)
    monkeypatch.setattr(ApplicationRuntimeLifecycle, "start", start)
    monkeypatch.setattr(ApplicationRuntimeLifecycle, "stop", stop)

    application = create_app(engine=None, db_path=db_path)
    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200

    assert order.index("admission-recovery") < order.index("runtime-start")
