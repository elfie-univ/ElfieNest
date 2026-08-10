"""测试系统设置 REST API — 3 section GET/PUT + 校验 + 持久化。

使用 tmp_path 隔离 DB 和 runtime_config.json，mock WS 网关。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.infrastructure.persistence.store import init_db

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
    return p


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用，mock WS 网关和 system_routes 配置路径。"""
    init_db(db_path)
    create_test_owner(db_path)

    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch(
            "app.interfaces.api.system_routes.get_config_path",
            return_value=runtime_config_path,
        ),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _login_owner(client: TestClient) -> dict:
    """辅助：以 owner 身份登录，返回 token 信息。"""
    resp = client.post(
        "/api/v1/auth/login", data={"account_id": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    csrf_token = resp.headers.get("X-CSRF-Token", "")
    return {
        "csrf_token": csrf_token,
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


# ===================================================================
# GET — 默认值
# ===================================================================


class TestGetDefaults:
    """GET /api/owner/system/{section} 在无文件时返回默认值。"""

    def test_get_adoption_defaults(self, client: TestClient) -> None:
        """无文件时 GET adoption → 返回系统默认 adoption 配置。"""
        tokens = _login_owner(client)
        resp = client.get(
            "/api/owner/system/adoption", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_elfies_per_user"] == 3
        assert data["allowed_species_ids"] == ["dog", "fox"]
        assert data["personality_presets_enabled"]["活泼好动"] is True

    def test_get_engine_defaults(self, client: TestClient) -> None:
        """无文件时 GET engine → 返回系统默认 engine 配置。"""
        tokens = _login_owner(client)
        resp = client.get(
            "/api/owner/system/engine", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tick_interval_sec"] == 1.5

    def test_get_security_defaults(self, client: TestClient) -> None:
        """无文件时 GET security → 返回系统默认 security 配置。"""
        tokens = _login_owner(client)
        resp = client.get(
            "/api/owner/system/security", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_ttl_days"] == 7
        assert data["rate_limit"]["max_attempts"] == 5
        assert data["rate_limit"]["window_seconds"] == 300


# ===================================================================
# PUT — 有效写入
# ===================================================================


class TestPutValid:
    """PUT /api/owner/system/{section} 合法写入。"""

    def test_put_adoption(self, client: TestClient, runtime_config_path: Path) -> None:
        """PUT adoption 修改 max_elfies_per_user → 200 + 文件持久化。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/adoption",
            json={"max_elfies_per_user": 5},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["max_elfies_per_user"] == 5

        saved = yaml.safe_load(runtime_config_path.read_text())
        assert saved["system"]["adoption"]["max_elfies_per_user"] == 5

    def test_put_engine(self, client: TestClient, runtime_config_path: Path) -> None:
        """PUT engine 修改 tick_interval_sec → 200。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/engine",
            json={"tick_interval_sec": 2.0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tick_interval_sec"] == 2.0

        saved = yaml.safe_load(runtime_config_path.read_text())
        assert saved["system"]["engine"]["tick_interval_sec"] == 2.0

    def test_put_security(self, client: TestClient, runtime_config_path: Path) -> None:
        """PUT security 修改 session_ttl_days 和 rate_limit → 200。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/security",
            json={
                "session_ttl_days": 1,
                "rate_limit": {"max_attempts": 3, "window_seconds": 60},
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["session_ttl_days"] == 1
        assert data["rate_limit"]["max_attempts"] == 3

        saved = yaml.safe_load(runtime_config_path.read_text())
        assert saved["system"]["security"]["session_ttl_days"] == 1


# ===================================================================
# PUT — 错误处理
# ===================================================================


class TestPutErrors:
    """PUT 非法输入 → 4xx。"""

    def test_unknown_section_404(self, client: TestClient) -> None:
        """未知 section → 404。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/unknown_section",
            json={"foo": "bar"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 404

    def test_get_unknown_section_404(self, client: TestClient) -> None:
        """GET 未知 section → 404。"""
        tokens = _login_owner(client)
        resp = client.get(
            "/api/owner/system/none", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 404

    def test_unknown_key_422(self, client: TestClient) -> None:
        """PUT 包含未知键 → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/engine",
            json={"unknown_key": 123},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422
        assert "未知" in resp.text

    def test_wrong_type_422(self, client: TestClient) -> None:
        """PUT 字段类型错误 → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/engine",
            json={"tick_interval_sec": "not_a_number"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422
        assert "类型" in resp.text or "tick_interval_sec" in resp.text

    def test_max_elfies_per_user_lt_1_422(self, client: TestClient) -> None:
        """PUT max_elfies_per_user=0 → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/adoption",
            json={"max_elfies_per_user": 0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_max_elfies_per_user_gt_32_422(self, client: TestClient) -> None:
        """单台机器最多培养 32 只精灵。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/adoption",
            json={"max_elfies_per_user": 33},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_empty_allowed_species_ids_422(self, client: TestClient) -> None:
        """至少保留一个可领养物种，避免把领养功能配置成不可用。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/adoption",
            json={"allowed_species_ids": []},
            headers=_headers(tokens["csrf_token"]),
        )

        assert resp.status_code == 422

    def test_tick_interval_zero_422(self, client: TestClient) -> None:
        """PUT tick_interval_sec=0 → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/engine",
            json={"tick_interval_sec": 0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_session_ttl_zero_422(self, client: TestClient) -> None:
        """PUT session_ttl_days=0 → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/security",
            json={"session_ttl_days": 0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422


# ===================================================================
# 权限校验
# ===================================================================


class TestAuthorization:
    """系统设置端点权限校验。"""

    def test_non_owner_gets_403(self, client: TestClient) -> None:
        """普通用户 → 403。"""
        tokens = _login_owner(client)
        # 创建普通用户
        resp = client.post(
            "/api/owner/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201

        # 以 alice 身份登录
        resp = client.post(
            "/api/v1/auth/login", data={"account_id": "alice", "password": "pass123"}
        )
        alice_csrf = resp.headers.get("X-CSRF-Token", "")

        # GET /system/engine
        resp = client.get("/api/owner/system/engine", headers=_headers(alice_csrf))
        assert resp.status_code == 403

        # PUT /system/engine
        resp = client.put(
            "/api/owner/system/engine",
            json={"tick_interval_sec": 2.0},
            headers=_headers(alice_csrf),
        )
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client: TestClient) -> None:
        """未登录 → 401。"""
        resp = client.get("/api/owner/system/engine")
        assert resp.status_code == 401
