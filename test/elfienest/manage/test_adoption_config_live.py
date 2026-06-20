"""动态领养配置集成测试 — 通过 system API 修改 → 验证 adoption 行为。

测试场景：
1. PUT system.adoption.max_elfies_per_user=1 → 领养第二只 → 409
2. PUT personality_presets_enabled["安静温顺"]=False → adoption-info 不包含该预设
3. PUT allowed_anatomy_types=["biped"] → 领养 quadruped → 422
4. 全部禁用 → 返回全部预设（安全回退）
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.manage.app import create_app
from elfienest.manage.store import init_db

from ._helpers import create_test_admin

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(tmp_path: Path) -> Path:
    """临时 runtime_config.json 路径，同时 mock system_routes 和 adoption_config。"""
    p = tmp_path / "runtime" / "runtime_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用，mock WS 网关 + 统一 mock 配置文件路径。"""
    init_db(db_path)
    create_test_admin(db_path)

    with (
        patch("elfienest.manage.app.AuthenticatedWSManager.start"),
        patch("elfienest.manage.app.AuthenticatedWSManager.stop"),
        patch(
            "elfienest.manage.system_routes._RUNTIME_CONFIG_PATH",
            runtime_config_path,
        ),
        patch(
            "elfienest.manage.admin_routes._RUNTIME_CONFIG_PATH",
            runtime_config_path,
        ),
        patch(
            "elfienest.manage.adoption_config._RUNTIME_CONFIG_PATH",
            runtime_config_path,
        ),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login_admin(client: TestClient) -> dict:
    resp = client.post(
        "/api/auth/login", data={"username": "admin", "password": "adminchangeme"}
    )
    assert resp.status_code == 200, f"admin login failed: {resp.text}"
    csrf_token = resp.headers.get("X-CSRF-Token", "")
    return {
        "session_token": resp.json()["session_token"],
        "csrf_token": csrf_token,
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


def _create_user_and_login(client: TestClient, username: str = "alice", password: str = "pass123") -> dict:
    """Admin 创建用户 → 登录 → 返回 token。"""
    admin_tokens = _login_admin(client)
    resp = client.post(
        "/api/admin/users",
        json={"username": username, "password": password, "role": "user"},
        headers=_headers(admin_tokens["csrf_token"]),
    )
    assert resp.status_code == 201, f"create user failed: {resp.text}"

    resp = client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )
    assert resp.status_code == 200, f"user login failed: {resp.text}"
    return {
        "session_token": resp.json()["session_token"],
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
    }


# ===================================================================
# Test: max_elfies_per_user
# ===================================================================


class TestMaxElfiesPerUser:
    """PUT system.adoption.max_elfies_per_user=1 → 领养第二只 → 409。"""

    def test_adopt_second_returns_409(self, client: TestClient) -> None:
        """max_elfies_per_user=1 时，第二只领养返回 409。"""
        admin_tokens = _login_admin(client)

        # 设置 max_elfies_per_user = 1
        resp = client.put(
            "/api/admin/system/adoption",
            json={"max_elfies_per_user": 1},
            headers=_headers(admin_tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text

        # 创建普通用户并登录
        user_tokens = _create_user_and_login(client)

        # 第一只 → 201
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "精灵1",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(user_tokens["csrf_token"]),
        )
        assert resp.status_code == 201, f"first adopt failed: {resp.text}"

        # 第二只 → 409
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "精灵2",
                "anatomy_type": "biped",
                "personality_style": "活泼好动",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(user_tokens["csrf_token"]),
        )
        assert resp.status_code == 409, f"expected 409, got {resp.status_code}: {resp.text}"
        assert "1" in resp.text or "最多" in resp.text


# ===================================================================
# Test: personality_presets_filter
# ===================================================================


class TestPersonalityPresetsFilter:
    """PUT personality_presets_enabled 禁用某预设 → adoption-info 不包含。"""

    def test_disabled_preset_excluded(self, client: TestClient) -> None:
        """禁用 "安静温顺" → adoption-info 不包含该预设。"""
        admin_tokens = _login_admin(client)

        # 禁用 "安静温顺"
        resp = client.put(
            "/api/admin/system/adoption",
            json={"personality_presets_enabled": {"安静温顺": False}},
            headers=_headers(admin_tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text

        # 普通用户查看 adoption-info
        user_tokens = _create_user_and_login(client)
        resp = client.get(
            "/api/user/adoption-info",
            headers=_headers(user_tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        styles = data["personality_styles"]
        assert "安静温顺" not in styles
        # 其他预设仍在
        assert "活泼好动" in styles
        assert "好奇探索" in styles
        assert len(styles) == 5

    def test_disabled_preset_rejected_on_adopt(self, client: TestClient) -> None:
        """禁用 "安静温顺" → 尝试领养该预设 → 400。"""
        admin_tokens = _login_admin(client)

        resp = client.put(
            "/api/admin/system/adoption",
            json={"personality_presets_enabled": {"安静温顺": False}},
            headers=_headers(admin_tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        user_tokens = _create_user_and_login(client)

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小静",
                "anatomy_type": "biped",
                "personality_style": "安静温顺",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(user_tokens["csrf_token"]),
        )
        assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.text}"


# ===================================================================
# Test: anatomy_types_filter
# ===================================================================


class TestAnatomyTypesFilter:
    """PUT allowed_anatomy_types=["biped"] → 领养 quadruped → 422。"""

    def test_quadruped_rejected(self, client: TestClient) -> None:
        """仅允许 biped → 尝试领养 quadruped → 400。"""
        admin_tokens = _login_admin(client)

        # 仅允许 biped
        resp = client.put(
            "/api/admin/system/adoption",
            json={"allowed_anatomy_types": ["biped"]},
            headers=_headers(admin_tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text

        user_tokens = _create_user_and_login(client)

        # 领养 quadruped → 400
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "四足",
                "anatomy_type": "quadruped",
                "personality_style": "活泼好动",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(user_tokens["csrf_token"]),
        )
        assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.text}"
        assert "quadruped" not in resp.text.lower() or "无效" in resp.text

    def test_adoption_info_reflects_filter(self, client: TestClient) -> None:
        """仅允许 biped → adoption-info 只包含 biped。"""
        admin_tokens = _login_admin(client)

        resp = client.put(
            "/api/admin/system/adoption",
            json={"allowed_anatomy_types": ["biped"]},
            headers=_headers(admin_tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        user_tokens = _create_user_and_login(client)
        resp = client.get(
            "/api/user/adoption-info",
            headers=_headers(user_tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["anatomy_types"] == ["biped"]


# ===================================================================
# Test: all_presets_disabled_fallback
# ===================================================================


class TestAllPresetsDisabledFallback:
    """全部 personality_presets_enabled=False → 返回全部预设（安全回退）。"""

    def test_all_disabled_returns_all(self, client: TestClient) -> None:
        """全部禁用 → adoption-info 仍包含全部 6 种预设。"""
        admin_tokens = _login_admin(client)

        # 全部禁用
        resp = client.put(
            "/api/admin/system/adoption",
            json={
                "personality_presets_enabled": {
                    "活泼好动": False,
                    "安静温顺": False,
                    "好奇探索": False,
                    "胆小害羞": False,
                    "傲娇独立": False,
                    "完全随机": False,
                }
            },
            headers=_headers(admin_tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text

        user_tokens = _create_user_and_login(client)
        resp = client.get(
            "/api/user/adoption-info",
            headers=_headers(user_tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        # 安全回退：全部返回
        assert len(data["personality_styles"]) == 6
        assert "活泼好动" in data["personality_styles"]
        assert "安静温顺" in data["personality_styles"]
        assert "完全随机" in data["personality_styles"]
