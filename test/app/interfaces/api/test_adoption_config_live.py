"""动态领养配置集成测试 — 通过 system API 修改 → 验证 adoption 行为。

测试场景：
1. PUT system.adoption.max_elfies_per_user=1 → 领养第二只被拒绝
2. PUT personality_presets_enabled["安静温顺"]=False → adoption-info 不包含该预设
3. PUT allowed_species_ids=["dog"] → 领养 fox → 400
4. 全部禁用 → 返回全部预设（安全回退）
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.features.adoption.service import (
    AdoptionCapacityError,
    AdoptionValidationError,
)
from app.infrastructure.persistence.store import init_db
from app.interfaces.api.app import create_app

from ._helpers import adopt_test_elfie, create_test_owner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(tmp_path: Path) -> Path:
    """临时正式 config.yaml 路径，同时 mock system_routes 和 adoption_config。"""
    p = tmp_path / "elfie-home" / "config.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用，mock WS 网关 + 统一 mock 配置文件路径。"""
    init_db(db_path)
    create_test_owner(db_path)

    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch(
            "app.interfaces.api.system_routes.get_config_path",
            return_value=runtime_config_path,
        ),
        patch(
            "app.features.adoption.config._RUNTIME_CONFIG_PATH",
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


def _login_owner(client: TestClient) -> dict:
    resp = client.post(
        "/api/auth/login", data={"account_id": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200, f"owner login failed: {resp.text}"
    csrf_token = resp.headers.get("X-CSRF-Token", "")
    return {
        "csrf_token": csrf_token,
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


def _create_user_and_login(
    client: TestClient, account_id: str = "alice", password: str = "pass123"
) -> dict:
    """Owner 创建用户 → 登录 → 返回 token。"""
    owner_tokens = _login_owner(client)
    resp = client.post(
        "/api/owner/users",
        json={"account_id": account_id, "password": password, "role": "user"},
        headers=_headers(owner_tokens["csrf_token"]),
    )
    assert resp.status_code == 201, f"create user failed: {resp.text}"

    resp = client.post(
        "/api/auth/login", data={"account_id": account_id, "password": password}
    )
    assert resp.status_code == 200, f"user login failed: {resp.text}"
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
        "user_id": resp.json()["user"]["user_id"],
    }


# ===================================================================
# Test: max_elfies_per_user
# ===================================================================


class TestMaxElfiesPerUser:
    """PUT system.adoption.max_elfies_per_user=1 → 领养第二只 → 409。"""

    def test_adopt_second_is_rejected(
        self, client: TestClient, db_path: str
    ) -> None:
        """max_elfies_per_user=1 时，第二只领养被拒绝。"""
        owner_tokens = _login_owner(client)

        # 设置 max_elfies_per_user = 1
        resp = client.put(
            "/api/owner/system/adoption",
            json={"max_elfies_per_user": 1},
            headers=_headers(owner_tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text

        # 创建普通用户并登录
        user_tokens = _create_user_and_login(client)

        adopt_test_elfie(
            db_path,
            int(user_tokens["user_id"]),
            name="精灵1",
        )
        with pytest.raises(AdoptionCapacityError, match="最多领养 1 只精灵"):
            adopt_test_elfie(
                db_path,
                int(user_tokens["user_id"]),
                name="精灵2",
                personality_style="活泼好动",
            )


# ===================================================================
# Test: personality_presets_filter
# ===================================================================


class TestPersonalityPresetsFilter:
    """PUT personality_presets_enabled 禁用某预设 → adoption-info 不包含。"""

    def test_disabled_preset_excluded(self, client: TestClient) -> None:
        """禁用 "安静温顺" → adoption-info 不包含该预设。"""
        owner_tokens = _login_owner(client)

        # 禁用 "安静温顺"
        resp = client.put(
            "/api/owner/system/adoption",
            json={"personality_presets_enabled": {"安静温顺": False}},
            headers=_headers(owner_tokens["csrf_token"]),
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

    def test_disabled_preset_rejected_on_adopt(
        self, client: TestClient, db_path: str
    ) -> None:
        """禁用 "安静温顺" → 尝试领养该预设被拒绝。"""
        owner_tokens = _login_owner(client)

        resp = client.put(
            "/api/owner/system/adoption",
            json={"personality_presets_enabled": {"安静温顺": False}},
            headers=_headers(owner_tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        user_tokens = _create_user_and_login(client)

        with pytest.raises(AdoptionValidationError):
            adopt_test_elfie(
                db_path,
                int(user_tokens["user_id"]),
                name="小静",
                personality_style="安静温顺",
            )


# ===================================================================
# Test: species_ids_filter
# ===================================================================


class TestSpeciesIdsFilter:
    """PUT allowed_species_ids=["dog"] → 领养 fox → 400。"""

    def test_fox_rejected(self, client: TestClient, db_path: str) -> None:
        """仅允许 dog → 尝试领养 fox 被拒绝。"""
        owner_tokens = _login_owner(client)

        # 仅允许 dog
        resp = client.put(
            "/api/owner/system/adoption",
            json={"allowed_species_ids": ["dog"]},
            headers=_headers(owner_tokens["csrf_token"]),
        )
        assert resp.status_code == 200, resp.text

        user_tokens = _create_user_and_login(client)

        with pytest.raises(AdoptionValidationError, match="species_id"):
            adopt_test_elfie(
                db_path,
                int(user_tokens["user_id"]),
                name="狐狸",
                species_id="fox",
                personality_style="活泼好动",
            )

    def test_adoption_info_reflects_filter(self, client: TestClient) -> None:
        """仅允许 dog → adoption-info 只包含 dog。"""
        owner_tokens = _login_owner(client)

        resp = client.put(
            "/api/owner/system/adoption",
            json={"allowed_species_ids": ["dog"]},
            headers=_headers(owner_tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        user_tokens = _create_user_and_login(client)
        resp = client.get(
            "/api/user/adoption-info",
            headers=_headers(user_tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["species_ids"] == ["dog"]


# ===================================================================
# Test: all_presets_disabled_fallback
# ===================================================================


class TestAllPresetsDisabledFallback:
    """全部 personality_presets_enabled=False → 返回全部预设（安全回退）。"""

    def test_all_disabled_returns_all(self, client: TestClient) -> None:
        """全部禁用 → adoption-info 仍包含全部 6 种预设。"""
        owner_tokens = _login_owner(client)

        # 全部禁用
        resp = client.put(
            "/api/owner/system/adoption",
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
            headers=_headers(owner_tokens["csrf_token"]),
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
