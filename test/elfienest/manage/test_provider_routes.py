"""测试 LLM Config REST API — Provider/Model/Route 管理端点。

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.manage.app import create_app
from elfienest.manage.store import init_db

from ._helpers import create_test_admin, create_test_user


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
    create_test_admin(db_path)

    with (
        patch("elfienest.manage.app.AuthenticatedWSManager.start"),
        patch("elfienest.manage.app.AuthenticatedWSManager.stop"),
        patch("elfienest.manage.provider_routes._RUNTIME_CONFIG_PATH", runtime_config_path),
        patch("elfienest.manage.model_admin_routes._RUNTIME_CONFIG_PATH", runtime_config_path),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    """FastAPI TestClient 实例。"""
    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient) -> dict:
    """Admin 登录。"""
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "adminchangeme"})
    assert resp.status_code == 200
    return {
        "session_token": resp.json()["session_token"],
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
    }


def _login_user(client: TestClient, username: str, password: str) -> dict:
    """普通用户登录。"""
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return {
        "session_token": resp.json()["session_token"],
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
        "user_id": resp.json()["user"]["id"],
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


# ===================================================================
# Provider Routes 测试
# ===================================================================


class TestProviderRoutes:
    def test_get_providers_returns_list(self, client: TestClient) -> None:
        """GET /api/admin/providers 返回 provider 列表。"""
        tokens = _login_admin(client)
        resp = client.get("/api/admin/providers", headers=_headers(tokens["csrf_token"]))
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
        """POST /api/admin/providers 添加新 provider。"""
        tokens = _login_admin(client)
        resp = client.post(
            "/api/admin/providers",
            json={
                "provider_id": "custom_provider",
                "api_base": "https://api.custom.com/v1",
                "api_key": "test-key-123",
                "api_mode": "chat_completions",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201, resp.text
        provider = resp.json()
        assert provider["provider_id"] == "custom_provider"
        assert provider["api_base"] == "https://api.custom.com/v1"
        assert provider["has_api_key"] is True

    def test_put_providers_updates_provider(self, client: TestClient, runtime_config_path: Path) -> None:
        """PUT /api/admin/providers/{id} 更新 provider。"""
        tokens = _login_admin(client)
        
        # 先添加一个 provider
        client.post(
            "/api/admin/providers",
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
            "/api/admin/providers/test_provider",
            json={"api_key": "new-key-456"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        provider = resp.json()
        assert provider["has_api_key"] is True

    def test_delete_providers_removes_provider(self, client: TestClient, runtime_config_path: Path) -> None:
        """DELETE /api/admin/providers/{id} 删除 provider。"""
        tokens = _login_admin(client)
        
        # 添加 provider
        client.post(
            "/api/admin/providers",
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
            "/api/admin/providers/to_delete",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        
        # 验证已删除
        resp = client.get("/api/admin/providers", headers=_headers(tokens["csrf_token"]))
        provider_ids = [p["provider_id"] for p in resp.json()]
        assert "to_delete" not in provider_ids

    def test_cannot_delete_ollama(self, client: TestClient) -> None:
        """不能删除 ollama provider。"""
        tokens = _login_admin(client)
        resp = client.delete(
            "/api/admin/providers/ollama",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "ollama" in resp.text.lower()

    def test_verify_provider_endpoint(self, client: TestClient) -> None:
        """POST /api/admin/providers/{id}/verify 验证连通性。"""
        tokens = _login_admin(client)
        resp = client.post(
            "/api/admin/providers/ollama/verify",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        result = resp.json()
        assert "status" in result
        assert result["status"] in ("active", "inactive", "unverified")

    def test_non_admin_gets_403_on_provider_routes(self, client: TestClient, db_path: str) -> None:
        """普通用户访问 admin 端点 → 403。"""
        create_test_user(db_path, "alice", "pass123")
        tokens = _login_user(client, "alice", "pass123")
        
        resp = client.get("/api/admin/providers", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 403


# ===================================================================
# Model Admin Routes 测试
# ===================================================================


class TestModelAdminRoutes:
    def test_get_models_returns_catalog(self, client: TestClient) -> None:
        """GET /api/admin/models 返回模型目录。"""
        tokens = _login_admin(client)
        resp = client.get("/api/admin/models", headers=_headers(tokens["csrf_token"]))
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
        """PUT /api/admin/models/{id} 更新模型可见性。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/models/openai/gpt-4o",
            json={"visible": False, "cost_tier": 3},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        model = resp.json()
        assert model["visible"] is False
        assert model["cost_tier"] == 3

    def test_put_models_invalid_cost_tier(self, client: TestClient) -> None:
        """PUT 无效 cost_tier → 422。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/models/openai/gpt-4o",
            json={"cost_tier": 5},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_put_models_nonexistent_model(self, client: TestClient) -> None:
        """PUT 不存在的模型 → 404。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/models/unknown/model",
            json={"visible": True},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 404

    def test_post_scan_models(self, client: TestClient) -> None:
        """POST /api/admin/models/scan 扫描新模型。"""
        tokens = _login_admin(client)
        resp = client.post("/api/admin/models/scan", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        result = resp.json()
        assert "discovered" in result
        assert "total" in result


# ===================================================================
# Route Routes 测试
# ===================================================================


class TestRouteRoutes:
    def test_get_elfie_route_returns_default(self, client: TestClient, db_path: str) -> None:
        """GET /api/user/elfies/{id}/route 返回路由配置（默认配置）。"""
        # 创建用户并领养精灵
        create_test_user(db_path, "alice", "pass123")
        tokens = _login_user(client, "alice", "pass123")
        
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201
        elfie_id = resp.json()["elfie_id"]
        
        # 获取路由
        resp = client.get(
            f"/api/user/elfies/{elfie_id}/route",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        route = resp.json()
        assert "elfie_id" in route
        assert "scene_routes" in route
        # 默认包含 5 个场景
        assert "idle" in route["scene_routes"]
        assert "deep" in route["scene_routes"]

    def test_put_elfie_route_updates_config(self, client: TestClient, db_path: str) -> None:
        """PUT /api/user/elfies/{id}/route 更新路由配置。"""
        create_test_user(db_path, "alice", "pass123")
        tokens = _login_user(client, "alice", "pass123")
        
        # 领养
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        elfie_id = resp.json()["elfie_id"]
        
        # 更新路由
        new_route = {
            "scene_routes": {
                "idle": {
                    "primary": "deepseek/deepseek-chat",
                    "fallbacks": ["ollama/qwen3.5:0.8b"],
                    "energy_threshold": 0,
                },
                "deep": {
                    "primary": "openai/gpt-4o",
                    "fallbacks": ["deepseek/deepseek-chat", "ollama/qwen3.5:0.8b"],
                    "energy_threshold": 50,
                },
            }
        }
        
        resp = client.put(
            f"/api/user/elfies/{elfie_id}/route",
            json=new_route,
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        route = resp.json()
        assert route["scene_routes"]["idle"]["primary"] == "deepseek/deepseek-chat"
        assert route["scene_routes"]["deep"]["energy_threshold"] == 50

    def test_user_cannot_access_other_user_route(self, client: TestClient, db_path: str) -> None:
        """用户不能访问其他用户的精灵路由 → 404。"""
        # 创建两个用户
        create_test_user(db_path, "alice", "pass123")
        create_test_user(db_path, "bob", "bobpass")
        
        # Alice 领养精灵
        tokens_a = _login_user(client, "alice", "pass123")
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小A",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens_a["csrf_token"]),
        )
        elfie_id = resp.json()["elfie_id"]
        
        # Bob 尝试访问 Alice 的精灵路由
        tokens_b = _login_user(client, "bob", "bobpass")
        resp = client.get(
            f"/api/user/elfies/{elfie_id}/route",
            headers=_headers(tokens_b["csrf_token"]),
        )
        assert resp.status_code == 404

    def test_put_route_invalid_scene(self, client: TestClient, db_path: str) -> None:
        """PUT 无效场景名称 → 422。"""
        create_test_user(db_path, "alice", "pass123")
        tokens = _login_user(client, "alice", "pass123")
        
        # 领养
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        elfie_id = resp.json()["elfie_id"]
        
        # 尝试更新无效场景
        resp = client.put(
            f"/api/user/elfies/{elfie_id}/route",
            json={"scene_routes": {"invalid_scene": {"primary": "test/model"}}},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_put_route_missing_primary(self, client: TestClient, db_path: str) -> None:
        """PUT 缺少 primary 字段 → 422。"""
        create_test_user(db_path, "alice", "pass123")
        tokens = _login_user(client, "alice", "pass123")
        
        # 领养
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        elfie_id = resp.json()["elfie_id"]
        
        # 尝试更新缺少 primary 的配置
        resp = client.put(
            f"/api/user/elfies/{elfie_id}/route",
            json={"scene_routes": {"idle": {"fallbacks": []}}},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422


# ===================================================================
# 未登录测试
# ===================================================================


class TestUnauthenticatedAccess:
    def test_provider_routes_require_auth(self, client: TestClient) -> None:
        """未登录访问 provider 端点 → 401。"""
        resp = client.get("/api/admin/providers")
        assert resp.status_code == 401

    def test_model_routes_require_auth(self, client: TestClient) -> None:
        """未登录访问 model 端点 → 401。"""
        resp = client.get("/api/admin/models")
        assert resp.status_code == 401

    def test_route_routes_require_auth(self, client: TestClient) -> None:
        """未登录访问 route 端点 → 401。"""
        resp = client.get("/api/user/elfies/test-id/route")
        assert resp.status_code == 401
