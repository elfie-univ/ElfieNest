from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.setup import (
    SetupPrincipal,
    SetupService,
    StoredOllamaObservation,
    StoredSetupInstallation,
)
from app.interfaces.api.v1.setup.dependencies import setup_principal
from app.interfaces.api.v1.setup.routes import router
from app.orchestration.setup_installation import (
    ConfirmSetupInstallationResult,
    SetupInstallationService,
)
from infrastructure.models.setup_catalog import ProviderSetupCatalogAdapter
from infrastructure.persistence.nest_db.store import init_db
from infrastructure.persistence.setup import SQLiteSetupAdapter


class ReadOnlySetupTechnology:
    def has_owner(self) -> bool:
        return False

    def inspect(self) -> StoredOllamaObservation:
        return StoredOllamaObservation("absent", None, None)

    def validate_bed_count(self, bed_count: int) -> int:
        return bed_count


class AcceptedInstallation(SetupInstallationService):
    def __init__(self) -> None:
        pass

    def confirm(self, _command: object) -> ConfirmSetupInstallationResult:
        return ConfirmSetupInstallationResult(
            installation=StoredSetupInstallation(
                1, "in_progress", 2, "pending", "running", 20, None, None
            ),
            session_token="owner-session",
            session_ttl_seconds=3600,
        )


def _client(tmp_path: Path) -> TestClient:
    persistence = SQLiteSetupAdapter(init_db(str(tmp_path / "nest.db")))
    technology = ReadOnlySetupTechnology()
    app = FastAPI()
    app.state.setup = SetupService(
        state=persistence,
        owners=technology,
        ollama=technology,
        nest_choices=technology,
        models=ProviderSetupCatalogAdapter(),
    )
    app.state.setup_installation = AcceptedInstallation()
    app.include_router(router)
    return TestClient(app)


def test_versioned_status_issues_restricted_setup_cookie(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/setup/status")
    assert response.status_code == 200
    assert response.json()["current_step"] == 1
    assert response.cookies.get("setup_token")
    assert response.headers["X-CSRF-Token"] == response.json()["csrf_token"]


def test_model_catalog_is_a_collection_resource(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/setup/models")
    assert response.status_code == 200
    assert [item["model_id"] for item in response.json()["items"]] == [
        "qwen2.5:0.5b",
        "qwen3.5:0.8b",
        "gemma3:270m",
    ]


def test_unknown_draft_fields_use_the_standard_error_envelope(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.cookies.set("setup_token", "local-token")
        response = client.put(
            "/api/v1/setup/draft/nest",
            json={"bed_count": 8, "unexpected": True},
        )
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_setup",
            "message": "Setup 请求无效",
            "details": {},
        }
    }


def test_setup_principal_cannot_read_owner_only_ollama_projection(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        client.cookies.set("setup_token", "local-token")
        response = client.get("/api/v1/setup/ollama")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "setup_forbidden"


def test_owner_can_read_ollama_projection_without_triggering_install(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        client.app.dependency_overrides[setup_principal] = lambda: SetupPrincipal(
            "owner", True
        )
        response = client.get("/api/v1/setup/ollama")
    assert response.status_code == 200
    assert response.json() == {"state": "absent", "endpoint": None, "version": None}


def test_installation_returns_202_and_replaces_setup_cookie_with_session(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        client.cookies.set("setup_token", "local-token")
        response = client.post(
            "/api/v1/setup/installation",
            json={"confirmed": True},
        )
    assert response.status_code == 202
    assert response.cookies.get("session_token") == "owner-session"
    assert response.headers["X-CSRF-Token"] == response.json()["csrf_token"]
