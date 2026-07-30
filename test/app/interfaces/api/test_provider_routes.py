"""测试 LLM Config REST API — Provider/Model/Route 管理端点。

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_runtime.food.models import FoodPackage, ModelAssignment
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from ai_runtime.providers.remote_catalog import RemoteCatalogUnavailable
from ai_runtime.storage.secrets import read_secrets
from ai_runtime.storage.validation_reports import (
    read_latest_model_validation,
    read_latest_provider_validation,
    write_provider_validation_report,
)
from ai_runtime.validation.providers import DiscoveredModel
from app.infrastructure.persistence.store import init_db
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """临时 ELFIE_HOME/config.yaml 路径。"""
    p = tmp_path / "runtime" / "config.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ELFIE_HOME", str(p.parent))
    p.write_text("providers:\n  ollama:\n    api_base: http://localhost:11434\n")
    return p


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用。"""
    init_db(db_path)
    create_test_owner(db_path)

    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    """FastAPI TestClient 实例。"""
    with TestClient(app) as c:
        yield c


def _login_owner(client: TestClient) -> dict:
    """Owner 登录。"""
    resp = client.post(
        "/api/auth/login", data={"username": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
    }


def _login_user(client: TestClient, username: str, password: str) -> dict:
    """普通用户登录。"""
    resp = client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
        "user_id": resp.json()["user"]["id"],
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


# ===================================================================
# Provider Routes 测试
# ===================================================================


class TestProviderRoutes:
    def test_connection_catalog_and_multiple_accounts_use_stable_ids(
        self,
        client: TestClient,
        runtime_config_path: Path,
    ) -> None:
        tokens = _login_owner(client)

        catalog = client.get(
            "/api/owner/providers/catalog",
            headers=_headers(tokens["csrf_token"]),
        )
        first = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "anthropic_api",
                "api_key": "first-key",
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        )
        second = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "anthropic_api",
                "alias": "工作账号",
                "api_key": "second-key",
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        )

        assert catalog.status_code == 200
        assert any(
            item["catalog_id"] == "anthropic_api"
            and item["brand"]["name"] == "Anthropic"
            for item in catalog.json()
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["connection_id"] == "anthropic_api_0001"
        assert first.json()["alias"] == "Anthropic"
        assert second.json()["connection_id"] == "anthropic_api_0002"
        assert second.json()["alias"] == "工作账号"
        assert first.json()["has_api_key"] is True
        secrets = read_secrets(
            runtime_config_path.parent / "configs" / "credentials" / "api-keys.env"
        )
        assert secrets["ELFIE_PROVIDER_ANTHROPIC_API_0001_API_KEY"] == "first-key"
        assert secrets["ELFIE_PROVIDER_ANTHROPIC_API_0002_API_KEY"] == "second-key"

    def test_connection_model_refresh_automatically_matches_known_model(
        self,
        client: TestClient,
    ) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "custom_openai",
                "alias": "讯飞 Coding Plan",
                "api_base": "https://example.invalid/v2",
                "api_key": "test-key",
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert created.status_code == 201
        connection_id = created.json()["connection_id"]

        with patch(
            "app.interfaces.api.provider_connection_routes.discover_provider_models",
            return_value=[
                DiscoveredModel(
                    connection_id,
                    "xopglm5",
                    display_name="GLM-5",
                )
            ],
        ):
            refreshed = client.post(
                f"/api/owner/providers/connections/{connection_id}/models/refresh",
                headers=_headers(tokens["csrf_token"]),
            )

        assert refreshed.status_code == 200
        assert refreshed.json()["status"] == "updated"
        assert refreshed.json()["models"] == [
            {
                "id": "xopglm5",
                "display_name": "GLM-5",
                "canonical_model_id": "zhipu/glm-5",
                "source": "official",
                "context_window_tokens": 204800,
                "max_output_tokens": 131072,
                "supports_tools": True,
                "supports_vision": False,
                "supports_reasoning": True,
                "hidden": False,
                "retired": False,
                "available": True,
            }
        ]

    def test_connection_model_refresh_failure_keeps_connection_for_manual_models(
        self,
        client: TestClient,
    ) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "custom_openai",
                "alias": "私人网关",
                "api_base": "https://example.invalid/v1",
                "api_key": "test-key",
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        )
        connection_id = created.json()["connection_id"]

        with patch(
            "app.interfaces.api.provider_connection_routes.discover_provider_models",
            side_effect=RuntimeError("no /models"),
        ):
            refreshed = client.post(
                f"/api/owner/providers/connections/{connection_id}/models/refresh",
                headers=_headers(tokens["csrf_token"]),
            )
        listed = client.get(
            "/api/owner/providers/connections",
            headers=_headers(tokens["csrf_token"]),
        )

        assert refreshed.status_code == 200
        assert refreshed.json()["status"] == "failed"
        assert "手工添加" in refreshed.json()["message"]
        assert any(item["connection_id"] == connection_id for item in listed.json())

    def test_connection_model_refresh_preserves_manual_and_marks_missing_official(
        self,
        client: TestClient,
    ) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "custom_openai",
                "alias": "无损刷新",
                "api_base": "https://example.invalid/v1",
                "models": [{"id": "manual-only", "display_name": "Manual"}],
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        )
        connection_id = created.json()["connection_id"]

        with patch(
            "app.interfaces.api.provider_connection_routes.discover_provider_models",
            return_value=[
                DiscoveredModel(connection_id, "official-old", display_name="Old")
            ],
        ):
            first = client.post(
                f"/api/owner/providers/connections/{connection_id}/models/refresh",
                headers=_headers(tokens["csrf_token"]),
            )
        with patch(
            "app.interfaces.api.provider_connection_routes.discover_provider_models",
            return_value=[
                DiscoveredModel(connection_id, "official-new", display_name="New")
            ],
        ):
            second = client.post(
                f"/api/owner/providers/connections/{connection_id}/models/refresh",
                headers=_headers(tokens["csrf_token"]),
            )

        first_models = {item["id"]: item for item in first.json()["models"]}
        second_models = {item["id"]: item for item in second.json()["models"]}
        assert first_models["manual-only"]["source"] == "manual"
        assert second_models["manual-only"]["available"] is True
        assert second_models["official-old"]["available"] is False
        assert second_models["official-new"]["source"] == "official"

    def test_connection_models_support_manual_delete_and_discovered_hide(
        self,
        client: TestClient,
    ) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "custom_openai",
                "alias": "模型管理测试",
                "api_base": "https://example.invalid/v1",
                "models": [{"id": "manual/model", "display_name": "Manual"}],
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        )
        connection_id = created.json()["connection_id"]

        deleted = client.delete(
            f"/api/owner/providers/connections/{connection_id}/models/manual/model",
            headers=_headers(tokens["csrf_token"]),
        )
        added = client.post(
            f"/api/owner/providers/connections/{connection_id}/models",
            json={"id": "manual-two", "display_name": "Manual Two"},
            headers=_headers(tokens["csrf_token"]),
        )
        hidden = client.put(
            f"/api/owner/providers/connections/{connection_id}/models/manual-two",
            json={"hidden": True},
            headers=_headers(tokens["csrf_token"]),
        )

        assert deleted.status_code == 200
        assert added.status_code == 201
        assert hidden.status_code == 200
        assert hidden.json()["hidden"] is True

    def test_connection_save_verifies_by_default_and_writes_report(
        self,
        client: TestClient,
    ) -> None:
        tokens = _login_owner(client)
        with patch(
            "app.interfaces.api.provider_connection_routes._verify_with_slot",
            return_value={
                "status": "active",
                "latency_ms": 42.0,
                "error": None,
            },
        ):
            created = client.post(
                "/api/owner/providers/connections",
                json={
                    "catalog_id": "deepseek_api",
                    "api_key": "test-key",
                },
                headers=_headers(tokens["csrf_token"]),
            )

        assert created.status_code == 201
        connection_id = created.json()["connection_id"]
        assert created.json()["verification"]["status"] == "passed"
        report = read_latest_provider_validation(connection_id)
        assert report["provider_id"] == connection_id
        assert report["status"] == "passed"

    def test_connection_cannot_be_deleted_while_food_references_it(
        self,
        client: TestClient,
    ) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "deepseek_api",
                "api_key": "test-key",
                "models": [{"id": "deepseek-chat", "display_name": "DeepSeek Chat"}],
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        )
        connection_id = created.json()["connection_id"]
        FoodCatalogStore().save(
            FoodCatalog(
                packages={
                    "daily": FoodPackage(
                        key="daily",
                        display_name="日常粮",
                        primary=ModelAssignment(f"{connection_id}/deepseek-chat"),
                    )
                },
            )
        )
        archived = client.post(
            f"/api/owner/providers/connections/{connection_id}/archive",
            headers=_headers(tokens["csrf_token"]),
        )
        assert archived.status_code == 200

        response = client.delete(
            f"/api/owner/providers/connections/{connection_id}",
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 409
        assert "daily" in response.text

    def test_connection_lifecycle_requires_archive_before_delete(
        self,
        client: TestClient,
    ) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "deepseek_api",
                "api_key": "test-key",
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        )
        connection_id = created.json()["connection_id"]

        rejected = client.delete(
            f"/api/owner/providers/connections/{connection_id}",
            headers=_headers(tokens["csrf_token"]),
        )
        disabled = client.post(
            f"/api/owner/providers/connections/{connection_id}/disable",
            headers=_headers(tokens["csrf_token"]),
        )
        archived = client.post(
            f"/api/owner/providers/connections/{connection_id}/archive",
            headers=_headers(tokens["csrf_token"]),
        )
        enable_rejected = client.post(
            f"/api/owner/providers/connections/{connection_id}/enable",
            headers=_headers(tokens["csrf_token"]),
        )
        restored = client.post(
            f"/api/owner/providers/connections/{connection_id}/restore",
            headers=_headers(tokens["csrf_token"]),
        )

        assert rejected.status_code == 409
        assert disabled.json()["enabled"] is False
        assert archived.json()["archived"] is True
        assert enable_rejected.status_code == 409
        assert restored.json()["archived"] is False
        assert restored.json()["enabled"] is False

    def test_connection_model_matrix_uses_connection_ids_and_endpoint_models(
        self,
        client: TestClient,
    ) -> None:
        tokens = _login_owner(client)
        first = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "custom_openai",
                "alias": "订阅甲",
                "api_base": "https://first.example/v1",
                "models": [{"id": "vendor-glm5", "display_name": "GLM-5"}],
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        ).json()
        second = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "custom_openai",
                "alias": "订阅乙",
                "api_base": "https://second.example/v1",
                "models": [{"id": "glm-5", "display_name": "GLM-5"}],
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        ).json()

        response = client.get(
            "/api/owner/providers/connection-model-matrix",
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 200
        matrix = response.json()
        assert {item["connection_id"] for item in matrix["connections"]} >= {
            first["connection_id"],
            second["connection_id"],
        }
        glm = next(row for row in matrix["models"] if row["display_name"] == "GLM-5")
        cells = {cell["connection_id"]: cell for cell in glm["connections"]}
        assert cells[first["connection_id"]]["model_id"] == "vendor-glm5"
        assert cells[second["connection_id"]]["model_id"] == "glm-5"

    def test_connection_model_benchmark_uses_endpoint_model_and_writes_report(
        self,
        client: TestClient,
    ) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/owner/providers/connections",
            json={
                "catalog_id": "custom_openai",
                "alias": "测速订阅",
                "api_base": "https://benchmark.example/v1",
                "api_key": "benchmark-secret",
                "models": [{"id": "vendor-model", "display_name": "Shared Model"}],
                "verify": False,
            },
            headers=_headers(tokens["csrf_token"]),
        ).json()
        connection_id = created["connection_id"]
        write_provider_validation_report(
            connection_id,
            status="passed",
            checked_at="2026-07-29T00:00:00+00:00",
            latency_ms=8.0,
            error=None,
            trigger="single",
        )

        with patch(
            "app.interfaces.api.provider_connection_model_routes."
            "run_connection_model_benchmark",
            new=AsyncMock(
                return_value={
                    "status": "passed",
                    "latency_ms": 21.0,
                    "latency_class": "fast",
                    "error": None,
                }
            ),
        ):
            response = client.post(
                "/api/owner/providers/connection-models/benchmark",
                json={
                    "combinations": [
                        {
                            "connection_id": connection_id,
                            "model_id": "vendor-model",
                        }
                    ]
                },
                headers=_headers(tokens["csrf_token"]),
            )

        assert response.status_code == 200
        assert response.json()["results"][0]["connection_id"] == connection_id
        report = read_latest_model_validation(connection_id, "vendor-model")
        assert report["model_id"] == "vendor-model"



def test_legacy_provider_and_model_routes_are_removed(client: TestClient) -> None:
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])

    assert client.get("/api/owner/providers", headers=headers).status_code == 404
    assert client.get("/api/owner/providers/model-matrix", headers=headers).status_code == 404
    assert client.get("/api/owner/models/", headers=headers).status_code == 404


def test_connection_routes_require_owner(client: TestClient) -> None:
    assert client.get("/api/owner/providers/connections").status_code == 401
    assert client.get("/api/owner/providers/connection-model-matrix").status_code == 401


def test_refresh_uses_remote_then_bundled_catalog_fallback(
    client: TestClient,
) -> None:
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])
    created = client.post(
        "/api/owner/providers/connections",
        json={
            "catalog_id": "openai_api",
            "alias": "Catalog fallback",
            "api_key": "test-key",
            "models": [{"id": "manual-kept", "display_name": "Manual"}],
            "verify": False,
        },
        headers=headers,
    ).json()
    connection_id = created["connection_id"]

    with (
        patch(
            "app.interfaces.api.provider_connection_routes._discover_with_slot",
            side_effect=RuntimeError("official unavailable"),
        ),
        patch(
            "app.interfaces.api.provider_connection_routes.fetch_remote_models",
            return_value=("remote-model",),
        ),
    ):
        remote = client.post(
            f"/api/owner/providers/connections/{connection_id}/models/refresh",
            headers=headers,
        )
    assert remote.status_code == 200
    assert remote.json()["status"] == "remote_catalog"
    assert {item["id"] for item in remote.json()["models"]} >= {
        "manual-kept",
        "remote-model",
    }

    with (
        patch(
            "app.interfaces.api.provider_connection_routes._discover_with_slot",
            side_effect=RuntimeError("official unavailable"),
        ),
        patch(
            "app.interfaces.api.provider_connection_routes.fetch_remote_models",
            side_effect=RemoteCatalogUnavailable("remote unavailable"),
        ),
    ):
        bundled = client.post(
            f"/api/owner/providers/connections/{connection_id}/models/refresh",
            headers=headers,
        )
    assert bundled.status_code == 200
    assert bundled.json()["status"] == "bundled_catalog"
    assert any(
        item["source"] == "bundled_catalog" for item in bundled.json()["models"]
    )
    assert any(item["id"] == "manual-kept" for item in bundled.json()["models"])


def test_validate_all_creates_one_complete_report_run(client: TestClient) -> None:
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])
    created = client.post(
        "/api/owner/providers/connections",
        json={
            "catalog_id": "custom_openai",
            "alias": "Validate all",
            "api_base": "https://validate.example/v1",
            "api_key": "test-key",
            "models": [{"id": "model-one", "display_name": "Model One"}],
            "verify": False,
        },
        headers=headers,
    )
    assert created.status_code == 201

    with (
        patch(
            "app.interfaces.api.provider_connection_model_routes."
            "_verify_connection_in_run",
            new=AsyncMock(
                return_value={
                    "status": "passed",
                    "checked_at": "2026-07-30T00:00:00+00:00",
                    "latency_ms": 10.0,
                    "error": None,
                }
            ),
        ),
        patch(
            "app.interfaces.api.provider_connection_model_routes."
            "_bounded_benchmark",
            new=AsyncMock(
                return_value={
                    "status": "passed",
                    "latency_ms": 12.0,
                    "latency_class": "fast",
                    "error": None,
                }
            ),
        ),
    ):
        response = client.post(
            "/api/owner/providers/connection-models/validate-all",
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    matrix = client.get(
        f"/api/owner/providers/connection-model-matrix?run_id={payload['run_id']}",
        headers=headers,
    )
    assert matrix.status_code == 200
    assert matrix.json()["snapshot"]["status"] == "complete"
