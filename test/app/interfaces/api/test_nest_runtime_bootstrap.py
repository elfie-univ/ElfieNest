from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.infrastructure.persistence.nest_state_repository import (
    SQLiteNestStateRepository,
)
from app.infrastructure.persistence.store import get_db, init_db
from app.orchestration.nest_session import ElfieNestEngine
from elfie import Elfie
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
               (elfie_id, name, owner_user_id, species, adopted_at, status)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'offline')""",
            (
                "00000001",
                "艾菲",
                cursor.lastrowid,
                "human",
            ),
        )
        connection.commit()
    engine = ElfieNestEngine(
        FakeWorldRuntime(),
        nest_repository=SQLiteNestStateRepository(db_path),
    )
    engine.session.register_elfie("00000001", MagicMock(spec=Elfie))
    application = create_app(engine=engine, db_path=db_path, ws_port=19876)

    # When: the HTTP application's lifespan starts after the Elfie is loaded.
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        TestClient(application) as client,
    ):
        response = client.get("/api/health")

    # Then: startup succeeds instead of attempting to attach a second repository.
    assert response.status_code == 200
