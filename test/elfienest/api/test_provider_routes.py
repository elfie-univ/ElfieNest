"""测试 LLM Config REST API — Provider/Model/Route 管理端点。

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.persistence.store import init_db
from runtime.validation.providers import DiscoveredModel

from ._helpers import create_test_owner, create_test_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(tmp_path: Path) -> Path:
    """临时 runtime_config.json 路径。"""
    p = tmp_path / "runtime" / "runtime_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"providers": {"ollama": {"api_base": "http://localhost:11434"}}}')
    return p


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用。"""
    init_db(db_path)
    create_test_owner(db_path)

    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
        patch("elfienest.api.provider_routes.get_config_path", return_value=runtime_config_path),
        patch("elfienest.api.model_owner_routes.get_config_path", return_value=runtime_config_path),
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
    resp = client.post("/api/auth/login", data={"username": "owner", "password": "ownerchangeme"})
    assert resp.status_code == 200
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
    }


def _login_user(client: TestClient, username: str, password: str) -> dict:
    """普通用户登录。"""
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
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
    def test_provider_save_can_auto_refresh_model_id_and_display_name(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        with patch(
            "elfienest.api.provider_routes.discover_provider_models",
            return_value=[
                DiscoveredModel(
                    "custom_auto",
                    "astron-code-latest",
                    display_name="GLM-5",
                )
            ],
        ):
            response = client.post(
                "/api/owner/providers",
                json={
                    "provider_id": "custom_auto",
                    "display_name": "讯飞 Coding Plan",
                    "api_base": "https://example.invalid/v2",
                    "api_key": "test-key",
                    "api_mode": "chat_completions",
                    "refresh_models": True,
                },
                headers=_headers(tokens["csrf_token"]),
            )

        assert response.status_code == 201
        assert response.json()["models"] == [
            {"id": "astron-code-latest", "display_name": "GLM-5"}
        ]
        assert response.json()["model_refresh"]["status"] == "updated"

    def test_get_providers_returns_list(self, client: TestClient) -> None:
        """GET /api/owner/providers 返回 provider 列表。"""
        tokens = _login_owner(client)
        resp = client.get("/api/owner/providers", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        providers = resp.json()
        assert isinstance(providers, list)
        # 至少包含 9 个内置 provider
        assert len(providers) >= 9
        # 检查 ollama provider
        ollama = next((p for p in providers if p["provider_id"] == "ollama"), None)
        assert ollama is not None
        assert ollama["name"] == "Ollama"
        assert ollama["status"] == "active"

    def test_post_providers_adds_new_provider(self, client: TestClient, runtime_config_path: Path) -> None:
        """POST /api/owner/providers 添加新 provider。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/owner/providers",
            json={
                "provider_id": "custom_provider",
                "display_name": "自建模型网关",
                "api_base": "https://api.custom.com/v1",
                "api_key": "test-key-123",
                "api_mode": "chat_completions",
                "auth_type": "bearer",
                "test_model": "glm-5",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201, resp.text
        provider = resp.json()
        assert provider["provider_id"] == "custom_provider"
        assert provider["name"] == "自建模型网关"
        assert provider["api_base"] == "https://api.custom.com/v1"
        assert provider["auth_type"] == "bearer"
        assert provider["test_model"] == "glm-5"
        assert provider["has_api_key"] is True

    def test_put_providers_updates_provider(self, client: TestClient, runtime_config_path: Path) -> None:
        """PUT /api/owner/providers/{id} 更新 provider。"""
        tokens = _login_owner(client)

        # 先添加一个 provider
        client.post(
            "/api/owner/providers",
            json={
                "provider_id": "test_provider",
                "api_base": "https://test.com/v1",
                "api_key": "",
                "api_mode": "chat_completions",
            },
            headers=_headers(tokens["csrf_token"]),
        )

        # 更新 api_key
        resp = client.put(
            "/api/owner/providers/test_provider",
            json={
                "api_key": "new-key-456",
                "display_name": "测试供应商",
                "auth_type": "x-api-key",
                "test_model": "test-model",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        provider = resp.json()
        assert provider["name"] == "测试供应商"
        assert provider["auth_type"] == "x-api-key"
        assert provider["test_model"] == "test-model"
        assert provider["has_api_key"] is True

    def test_put_builtin_provider_creates_editable_config(self, client: TestClient, runtime_config_path: Path) -> None:
        tokens = _login_owner(client)

        resp = client.put(
            "/api/owner/providers/openai",
            json={
                "api_base": "https://gateway.example.com/v1",
                "api_key": "openai-test-key",
                "api_mode": "chat_completions",
                "auth_type": "bearer",
                "display_name": "OpenAI 网关",
                "test_model": "gpt-4o-mini",
            },
            headers=_headers(tokens["csrf_token"]),
        )

        assert resp.status_code == 200
        provider = resp.json()
        assert provider["provider_id"] == "openai"
        assert provider["name"] == "OpenAI 网关"
        assert provider["api_base"] == "https://gateway.example.com/v1"
        assert provider["status"] == "active"
        assert provider["test_model"] == "gpt-4o-mini"

    def test_delete_providers_removes_provider(self, client: TestClient, runtime_config_path: Path) -> None:
        """DELETE /api/owner/providers/{id} 删除 provider。"""
        tokens = _login_owner(client)

        # 添加 provider
        client.post(
            "/api/owner/providers",
            json={
                "provider_id": "to_delete",
                "api_base": "https://delete.com/v1",
                "api_key": "",
                "api_mode": "chat_completions",
            },
            headers=_headers(tokens["csrf_token"]),
        )

        # 删除
        resp = client.delete(
            "/api/owner/providers/to_delete",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        # 验证已删除
        resp = client.get("/api/owner/providers", headers=_headers(tokens["csrf_token"]))
        provider_ids = [p["provider_id"] for p in resp.json()]
        assert "to_delete" not in provider_ids

    def test_cannot_delete_ollama(self, client: TestClient) -> None:
        """不能删除 ollama provider。"""
        tokens = _login_owner(client)
        resp = client.delete(
            "/api/owner/providers/ollama",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "ollama" in resp.text.lower()

    def test_verify_provider_endpoint(self, client: TestClient) -> None:
        """POST /api/owner/providers/{id}/verify 验证连通性。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/owner/providers/ollama/verify",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        result = resp.json()
        assert "status" in result
        assert result["status"] in ("active", "inactive", "unverified")

    def test_verify_custom_provider_uses_saved_openai_compatible_config(self, client: TestClient) -> None:
        tokens = _login_owner(client)
        create_resp = client.post(
            "/api/owner/providers",
            json={
                "provider_id": "custom_verify_provider",
                "api_base": "https://invalid.local/v1",
                "api_key": "",
                "api_mode": "chat_completions",
                "test_model": "glm-5",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert create_resp.status_code == 201

        resp = client.post(
            "/api/owner/providers/custom_verify_provider/verify",
            headers=_headers(tokens["csrf_token"]),
        )

        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] in ("inactive", "unverified")
        assert "未知 provider" not in str(result.get("error", ""))

    def test_non_owner_gets_403_on_provider_routes(self, client: TestClient, db_path: str) -> None:
        """普通用户访问 owner 端点 → 403。"""
        create_test_user(db_path, "alice", "pass123")
        tokens = _login_user(client, "alice", "pass123")

        resp = client.get("/api/owner/providers", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 403


# ===================================================================
# Model Owner Routes 测试
# ===================================================================


class TestModelOwnerRoutes:
    def test_get_models_returns_catalog(self, client: TestClient) -> None:
        """GET /api/owner/models 返回模型目录。"""
        tokens = _login_owner(client)
        resp = client.get("/api/owner/models", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        models = resp.json()
        assert isinstance(models, list)
        # 至少包含 15 个内置模型
        assert len(models) >= 15

        # 检查第一个模型的结构
        model = models[0]
        assert "model_id" in model
        assert "provider" in model
        assert "display_name" in model
        assert "capabilities" in model
        assert "visible" in model
        assert "cost_tier" in model

    def test_put_models_updates_visibility(self, client: TestClient, runtime_config_path: Path) -> None:
        """PUT /api/owner/models/{id} 更新模型可见性。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/models/openai/gpt-4o",
            json={"visible": False, "cost_tier": 3},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        model = resp.json()
        assert model["visible"] is False
        assert model["cost_tier"] == 3

    def test_put_models_invalid_cost_tier(self, client: TestClient) -> None:
        """PUT 无效 cost_tier → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/models/openai/gpt-4o",
            json={"cost_tier": 5},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_put_models_nonexistent_model(self, client: TestClient) -> None:
        """PUT 不存在的模型 → 404。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/models/unknown/model",
            json={"visible": True},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 404

    def test_post_scan_models(self, client: TestClient) -> None:
        """POST /api/owner/models/scan 扫描新模型。"""
        tokens = _login_owner(client)
        resp = client.post("/api/owner/models/scan", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        result = resp.json()
        assert "discovered" in result
        assert "total" in result


# ===================================================================
# 旧模型路由已移除
# ===================================================================


def test_legacy_model_route_endpoint_is_removed(client: TestClient) -> None:
    """旧 route API 不再注册，客户端必须使用 food-policy。"""
    response = client.get("/api/user/elfies/test-id/route")
    assert response.status_code == 404


# ===================================================================
# 未登录测试
# ===================================================================


class TestUnauthenticatedAccess:
    def test_provider_routes_require_auth(self, client: TestClient) -> None:
        """未登录访问 provider 端点 → 401。"""
        resp = client.get("/api/owner/providers")
        assert resp.status_code == 401

    def test_model_routes_require_auth(self, client: TestClient) -> None:
        """未登录访问 model 端点 → 401。"""
        resp = client.get("/api/owner/models")
        assert resp.status_code == 401
