"""测试系统设置 REST API — 4 section GET/PUT + 校验 + 持久化。

使用 tmp_path 隔离 DB 和 runtime_config.json，mock WS 网关。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.persistence.store import init_db

from ._helpers import create_test_admin

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(tmp_path: Path) -> Path:
    """临时 runtime_config.json 路径，用于 mock system_routes._RUNTIME_CONFIG_PATH。"""
    p = tmp_path / "runtime" / "runtime_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用，mock WS 网关和 system_routes 配置路径。"""
    init_db(db_path)
    create_test_admin(db_path)

    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
        patch(
            "elfienest.api.system_routes._RUNTIME_CONFIG_PATH",
            runtime_config_path,
        ),
        patch(
            "elfienest.api.admin_routes._RUNTIME_CONFIG_PATH",
            runtime_config_path,
        ),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient) -> dict:
    """辅助：以 admin 身份登录，返回 token 信息。"""
    resp = client.post(
        "/api/auth/login", data={"username": "admin", "password": "adminchangeme"}
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    csrf_token = resp.headers.get("X-CSRF-Token", "")
    return {
        "session_token": resp.json()["session_token"],
        "csrf_token": csrf_token,
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


# ===================================================================
# GET — 默认值
# ===================================================================


class TestGetDefaults:
    """GET /api/admin/system/{section} 在无文件时返回默认值。"""

    def test_get_llm_defaults(self, client: TestClient) -> None:
        """无文件时 GET llm → 返回系统默认 LLM 配置。"""
        tokens = _login_admin(client)
        resp = client.get(
            "/api/admin/system/llm", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert data["temperature"] == 0.7
        assert data["max_tokens"] == 1500
        assert data["default_cheap_model"] == "qwen3.5:0.8b"
        assert data["default_deep_model"] == "qwen3.5:0.8b"
        assert data["default_multimodal_model"] == "moondream"

    def test_get_adoption_defaults(self, client: TestClient) -> None:
        """无文件时 GET adoption → 返回系统默认 adoption 配置。"""
        tokens = _login_admin(client)
        resp = client.get(
            "/api/admin/system/adoption", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_elfies_per_user"] == 3
        assert data["allowed_anatomy_types"] == ["biped", "quadruped"]
        assert data["personality_presets_enabled"]["活泼好动"] is True

    def test_get_engine_defaults(self, client: TestClient) -> None:
        """无文件时 GET engine → 返回系统默认 engine 配置。"""
        tokens = _login_admin(client)
        resp = client.get(
            "/api/admin/system/engine", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tick_interval_sec"] == 1.5
        assert data["tts_enabled"] is True
        assert data["max_elfies_per_room"] is None

    def test_get_security_defaults(self, client: TestClient) -> None:
        """无文件时 GET security → 返回系统默认 security 配置。"""
        tokens = _login_admin(client)
        resp = client.get(
            "/api/admin/system/security", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_ttl_days"] == 7
        assert data["rate_limit"]["max_attempts"] == 5
        assert data["rate_limit"]["window_seconds"] == 300


# ===================================================================
# GET — 文件读取后深层合并
# ===================================================================


class TestGetWithFile:
    """GET 在有部分持久化数据时优先使用文件值。"""

    def test_get_llm_merges_saved_values(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """PUT 修改 temperature → GET 返回新值。"""
        tokens = _login_admin(client)
        # PUT 修改 temperature
        resp = client.put(
            "/api/admin/system/llm",
            json={"temperature": 0.3},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        # GET 验证合并结果
        resp = client.get(
            "/api/admin/system/llm", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["temperature"] == 0.3  # 覆盖值
        assert data["max_tokens"] == 1500  # 默认值保留


# ===================================================================
# PUT — 有效写入
# ===================================================================


class TestPutValid:
    """PUT /api/admin/system/{section} 合法写入。"""

    def test_put_llm(self, client: TestClient, runtime_config_path: Path) -> None:
        """PUT llm 修改 temperature 和 max_tokens → 200 + 文件持久化。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/llm",
            json={"temperature": 0.5, "max_tokens": 2000},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["temperature"] == 0.5
        assert data["max_tokens"] == 2000

        # 验证文件持久化
        saved = json.loads(runtime_config_path.read_text())
        assert saved["system"]["llm"]["temperature"] == 0.5
        assert saved["system"]["llm"]["max_tokens"] == 2000

    def test_put_adoption(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """PUT adoption 修改 max_elfies_per_user → 200 + 文件持久化。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/adoption",
            json={"max_elfies_per_user": 5},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["max_elfies_per_user"] == 5

        saved = json.loads(runtime_config_path.read_text())
        assert saved["system"]["adoption"]["max_elfies_per_user"] == 5

    def test_put_engine(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """PUT engine 修改 tick_interval_sec → 200。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/engine",
            json={"tick_interval_sec": 2.0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tick_interval_sec"] == 2.0

        saved = json.loads(runtime_config_path.read_text())
        assert saved["system"]["engine"]["tick_interval_sec"] == 2.0

    def test_put_engine_null_max_elfies(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """PUT engine max_elfies_per_room=null → 200。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/engine",
            json={"max_elfies_per_room": None},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text

        saved = json.loads(runtime_config_path.read_text())
        assert saved["system"]["engine"]["max_elfies_per_room"] is None

    def test_put_security(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """PUT security 修改 session_ttl_days 和 rate_limit → 200。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/security",
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

        saved = json.loads(runtime_config_path.read_text())
        assert saved["system"]["security"]["session_ttl_days"] == 1


# ===================================================================
# PUT — 错误处理
# ===================================================================


class TestPutErrors:
    """PUT 非法输入 → 4xx。"""

    def test_unknown_section_404(self, client: TestClient) -> None:
        """未知 section → 404。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/unknown_section",
            json={"foo": "bar"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 404

    def test_get_unknown_section_404(self, client: TestClient) -> None:
        """GET 未知 section → 404。"""
        tokens = _login_admin(client)
        resp = client.get(
            "/api/admin/system/none", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 404

    def test_unknown_key_422(self, client: TestClient) -> None:
        """PUT 包含未知键 → 422。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/llm",
            json={"unknown_key": 123},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422
        assert "未知" in resp.text

    def test_wrong_type_422(self, client: TestClient) -> None:
        """PUT 字段类型错误 → 422。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/llm",
            json={"temperature": "not_a_number"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422
        assert "类型" in resp.text or "temperature" in resp.text

    def test_temperature_range_422(self, client: TestClient) -> None:
        """PUT temperature 超出 0-2 范围 → 422。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/llm",
            json={"temperature": 3.0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_max_elfies_per_user_lt_1_422(self, client: TestClient) -> None:
        """PUT max_elfies_per_user=0 → 422。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/adoption",
            json={"max_elfies_per_user": 0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_tick_interval_zero_422(self, client: TestClient) -> None:
        """PUT tick_interval_sec=0 → 422。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/engine",
            json={"tick_interval_sec": 0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_session_ttl_zero_422(self, client: TestClient) -> None:
        """PUT session_ttl_days=0 → 422。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/system/security",
            json={"session_ttl_days": 0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422


# ===================================================================
# 权限校验
# ===================================================================


class TestAuthorization:
    """系统设置端点权限校验。"""

    def test_non_admin_gets_403(self, client: TestClient) -> None:
        """普通用户 → 403。"""
        tokens = _login_admin(client)
        # 创建普通用户
        resp = client.post(
            "/api/admin/users",
            json={"username": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201

        # 以 alice 身份登录
        resp = client.post(
            "/api/auth/login", data={"username": "alice", "password": "pass123"}
        )
        alice_csrf = resp.headers.get("X-CSRF-Token", "")

        # GET /system/llm
        resp = client.get(
            "/api/admin/system/llm", headers=_headers(alice_csrf)
        )
        assert resp.status_code == 403

        # PUT /system/llm
        resp = client.put(
            "/api/admin/system/llm",
            json={"temperature": 0.5},
            headers=_headers(alice_csrf),
        )
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client: TestClient) -> None:
        """未登录 → 401。"""
        resp = client.get("/api/admin/system/llm")
        assert resp.status_code == 401


# ===================================================================
# 向后兼容 — 旧的 PUT /api/admin/config 不受影响
# ===================================================================


class TestBackwardCompat:
    """旧的 GET/PUT /api/admin/config 端点行为不变。"""

    def test_old_put_config_still_works(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """PUT /api/admin/config 仍然要求 providers + 200。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/config",
            json={
                "providers": {
                    "ollama": {"api_base": "http://127.0.0.1:11434"},
                }
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        # 验证写入
        saved = json.loads(runtime_config_path.read_text())
        assert saved["providers"]["ollama"]["api_base"] == "http://127.0.0.1:11434"

    def test_old_put_config_missing_providers_400(
        self, client: TestClient
    ) -> None:
        """PUT /api/admin/config 缺少 providers → 400（旧行为不变）。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/config",
            json={"temperature": 0.5},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "providers" in resp.text

    def test_old_get_config_returns_file(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """GET /api/admin/config 返回原始文件内容。"""
        tokens = _login_admin(client)
        # 先写入一些 system 数据
        client.put(
            "/api/admin/system/llm",
            json={"temperature": 0.3},
            headers=_headers(tokens["csrf_token"]),
        )

        # GET old config — 包含完整的文件内容
        resp = client.get(
            "/api/admin/config", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        # 新端点写入的 system 应出现在旧 GET 中
        assert "system" in data
        assert data["system"]["llm"]["temperature"] == 0.3
