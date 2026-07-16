"""测试普通用户 REST API — 精灵列表 / 详情 / 配置 / 领养

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.api.ws_gateway import AuthenticatedWSManager
from elfienest.persistence.chat_history import (
    ChatMessageInput,
    ChatSender,
    record_chat_message,
)
from elfienest.persistence.store import init_db

from ._helpers import create_test_admin

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def app(db_path: str):
    # 预填充 admin 用户（ lifespan 不再硬编码 admin/adminchangeme ）
    init_db(db_path)
    create_test_admin(db_path)

    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient) -> dict:
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "adminchangeme"})
    assert resp.status_code == 200
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
    }


def _login_user(client: TestClient, username: str = "alice", password: str = "pass123") -> dict:
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, f"user login failed: {resp.text}"
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
        "user_id": resp.json()["user"]["id"],
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


def _create_user_via_admin(client: TestClient, username: str = "alice", password: str = "pass123") -> int:
    """Admin 创建用户，返回用户 id。"""
    admin_tokens = _login_admin(client)
    resp = client.post(
        "/api/admin/users",
        json={"username": username, "password": password, "role": "user"},
        headers=_headers(admin_tokens["csrf_token"]),
    )
    assert resp.status_code == 201, f"create user failed: {resp.text}"
    return resp.json()["id"]


def _adopt_elfie(client: TestClient, csrf_token: str, name: str) -> str:
    resp = client.post(
        "/api/user/adopt",
        json={
            "name": name,
            "anatomy_type": "biped",
            "personality_style": "好奇探索",
            "height": "standard",
            "build": "standard",
        },
        headers=_headers(csrf_token),
    )
    assert resp.status_code == 201, f"adopt failed: {resp.text}"
    return resp.json()["elfie_id"]


# ===================================================================
# 精灵列表（所有者隔离）
# ===================================================================


class TestElfieList:
    def test_user_sees_own_elfies(self, client: TestClient, db_path: str) -> None:
        """用户 A 登录 → 看到自己的 2 只精灵。"""
        _create_user_via_admin(client, "alice")
        tokens_a = _login_user(client, "alice")

        # 领养 2 只精灵
        for i in range(2):
            resp = client.post(
                "/api/user/adopt",
                json={
                    "name": f"精灵{i+1}",
                    "anatomy_type": "biped",
                    "personality_style": "好奇探索",
                    "height": "standard",
                    "build": "standard",
                },
                headers=_headers(tokens_a["csrf_token"]),
            )
            assert resp.status_code == 201, f"adopt {i} failed: {resp.text}"

        resp = client.get("/api/user/elfies", headers=_headers(tokens_a["csrf_token"]))
        assert resp.status_code == 200
        elfies = resp.json()
        assert len(elfies) == 2

    def test_user_b_does_not_see_a_elfies(self, client: TestClient, db_path: str) -> None:
        """用户 B 看不到 A 的精灵。"""
        _create_user_via_admin(client, "alice")
        _create_user_via_admin(client, "bob", "bobpass")

        tokens_a = _login_user(client, "alice")
        # A 领养 1 只
        client.post(
            "/api/user/adopt",
            json={
                "name": "小A",
                "anatomy_type": "biped",
                "personality_style": "活泼好动",
                "height": "short",
                "build": "slim",
            },
            headers=_headers(tokens_a["csrf_token"]),
        )

        # B 登录
        tokens_b = _login_user(client, "bob", "bobpass")
        resp = client.get("/api/user/elfies", headers=_headers(tokens_b["csrf_token"]))
        assert resp.status_code == 200
        assert resp.json() == []


# ===================================================================
# 精灵详情 & 配置
# ===================================================================


class TestElfieDetail:
    def test_get_elfie_detail_yaml(self, client: TestClient, db_path: str) -> None:
        """GET 精灵详情返回 YAML 内容。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        # 领养
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "tall",
                "build": "plump",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201
        elfie_id = resp.json()["elfie_id"]

        # 获取详情
        resp = client.get(f"/api/user/elfies/{elfie_id}", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "小白"
        assert data["elfie_id"] == elfie_id
        assert "personality.yaml" in data["configs"]
        assert "capabilities.yaml" in data["configs"]
        assert "system_limits.yaml" in data["configs"]

    def test_update_personality_config(self, client: TestClient, db_path: str) -> None:
        """PUT 更新 personality.yaml → 文件写入正确。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "安静温顺",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        elfie_id = resp.json()["elfie_id"]

        new_yaml = "metadata:\n  name: 小白\nbig_five:\n  openness: 0.5\n"
        resp = client.put(
            f"/api/user/elfies/{elfie_id}/config",
            json={"filename": "personality.yaml", "content": new_yaml},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        # 验证已写入
        resp = client.get(f"/api/user/elfies/{elfie_id}", headers=_headers(tokens["csrf_token"]))
        assert new_yaml in resp.json()["configs"]["personality.yaml"]

    def test_access_others_elfie_404(self, client: TestClient, db_path: str) -> None:
        """访问不属于自己的精灵 → 404。"""
        _create_user_via_admin(client, "alice")
        _create_user_via_admin(client, "bob", "bobpass")

        tokens_a = _login_user(client, "alice")
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

        # B 尝试访问 A 的精灵
        tokens_b = _login_user(client, "bob", "bobpass")
        resp = client.get(f"/api/user/elfies/{elfie_id}", headers=_headers(tokens_b["csrf_token"]))
        assert resp.status_code == 404


class TestElfieChatHistory:
    def test_get_chat_history_filters_by_range_and_keyword(self, client: TestClient, db_path: str) -> None:
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")
        elfie_id = _adopt_elfie(client, tokens["csrf_token"], "小白")
        user_id = tokens["user_id"]

        record_chat_message(
            db_path,
            ChatMessageInput(
                elfie_id=elfie_id,
                user_id=user_id,
                sender=ChatSender.USER,
                text="今天想聊星际门",
                meta="已投递",
                created_at="2026-06-30T09:00:00.000Z",
            ),
        )
        record_chat_message(
            db_path,
            ChatMessageInput(
                elfie_id=elfie_id,
                user_id=user_id,
                sender=ChatSender.ELFIE,
                text="我记得昨天的梦",
                meta="情绪：平静",
                created_at="2026-06-29T09:00:00.000Z",
            ),
        )

        resp = client.get(
            f"/api/user/elfies/{elfie_id}/chat-history",
            params={"range": "all", "q": "星际门"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert resp.status_code == 200
        messages = resp.json()
        assert [message["text"] for message in messages] == ["今天想聊星际门"]

    def test_get_chat_history_rejects_other_owner(self, client: TestClient, db_path: str) -> None:
        _create_user_via_admin(client, "alice")
        _create_user_via_admin(client, "bob", "bobpass")
        alice_tokens = _login_user(client, "alice")
        elfie_id = _adopt_elfie(client, alice_tokens["csrf_token"], "小A")
        bob_tokens = _login_user(client, "bob", "bobpass")

        resp = client.get(
            f"/api/user/elfies/{elfie_id}/chat-history",
            headers=_headers(bob_tokens["csrf_token"]),
        )

        assert resp.status_code == 404

    def test_ws_manager_records_user_and_elfie_messages(self, client: TestClient, db_path: str) -> None:
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")
        elfie_id = _adopt_elfie(client, tokens["csrf_token"], "小白")
        manager = AuthenticatedWSManager(db_path=db_path)

        import anyio

        anyio.run(
            manager._handle_message,
            tokens["user_id"],
            f'{{"event":"user_message","payload":{{"elfie_id":"{elfie_id}","message":"你好"}}}}',
        )
        manager.broadcast_to_owners(
            elfie_id,
            {
                "action": "speak_event",
                "payload": {
                    "elfie_id": elfie_id,
                    "text": "我听到了",
                    "emotion": "开心",
                },
            },
        )

        resp = client.get(
            f"/api/user/elfies/{elfie_id}/chat-history",
            headers=_headers(tokens["csrf_token"]),
        )

        assert resp.status_code == 200
        assert [message["sender"] for message in resp.json()] == ["user", "elfie"]


# ===================================================================
# 未登录 / 权限
# ===================================================================


class TestUnauthenticated:
    def test_not_logged_in_401(self, client: TestClient) -> None:
        """未登录访问 → 401。"""
        resp = client.get("/api/user/elfies")
        assert resp.status_code == 401


# ===================================================================
# 领养信息
# ===================================================================


class TestAdoptionInfo:
    def test_returns_lists(self, client: TestClient) -> None:
        """GET /api/user/adoption-info 返回正确列表。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.get("/api/user/adoption-info", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        data = resp.json()
        # 6 种性格
        assert len(data["personality_styles"]) == 6
        # 2 种体型
        assert sorted(data["anatomy_types"]) == sorted(["biped", "quadruped"])
        # 3 身高
        assert sorted(data["heights"]) == sorted(["short", "standard", "tall"])
        # 3 胖瘦
        assert sorted(data["builds"]) == sorted(["slim", "standard", "plump"])

    def test_returns_quota_status(self, client: TestClient) -> None:
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

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

        resp = client.get("/api/user/adoption-info", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["quota"] == {
            "used": 1,
            "max": 3,
            "remaining": 2,
            "can_adopt": True,
        }


# ===================================================================
# 领养端点
# ===================================================================


class TestAdopt:
    def test_successful_adoption(self, client: TestClient) -> None:
        """POST /api/user/adopt → 201 + 生成 YAML。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "tall",
                "build": "plump",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "小白"
        assert data["elfie_id"].startswith("elfie_")
        assert "config_dir" in data

        # 验证精灵出现在列表中
        resp = client.get("/api/user/elfies", headers=_headers(tokens["csrf_token"]))
        assert len(resp.json()) == 1

    def test_limit_3_then_409(self, client: TestClient) -> None:
        """3 只上限 → 第 4 次 409。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        for i in range(3):
            resp = client.post(
                "/api/user/adopt",
                json={
                    "name": f"精灵{i+1}",
                    "anatomy_type": "biped",
                    "personality_style": "活泼好动",
                    "height": "standard",
                    "build": "standard",
                },
                headers=_headers(tokens["csrf_token"]),
            )
            assert resp.status_code == 201, f"adopt {i} failed: {resp.text}"

        # 第 4 次
        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "精灵4",
                "anatomy_type": "biped",
                "personality_style": "活泼好动",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 409
        assert "最多" in resp.text

    def test_invalid_name_empty_400(self, client: TestClient) -> None:
        """name 为空 → 400。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400

    def test_invalid_anatomy_type_400(self, client: TestClient) -> None:
        """非法 anatomy_type → 400。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "tripled",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400

    def test_invalid_personality_style_400(self, client: TestClient) -> None:
        """未知 personality_style → 400。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "unknown_style_404",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400

    def test_invalid_height_400(self, client: TestClient) -> None:
        """非法 height → 400。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "super_tall",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400

    def test_invalid_build_400(self, client: TestClient) -> None:
        """非法 build → 400。"""
        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "extra_plump",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400


class TestAdoptRoomFull:
    def test_adopt_room_full(self, client: TestClient, app, db_path: str) -> None:
        """房间满 → POST /api/user/adopt → 409 detail 包含 '房间已满'。"""
        from elfie import ElfieIndividual  # noqa: PLC0415
        from elfienest.simulation.engine import ElfieNestEngine  # noqa: PLC0415

        _create_user_via_admin(client, "alice")
        tokens = _login_user(client, "alice")

        # 创建一个已满的房间引擎（上限 1，已注册 1 只）
        with patch("elfienest.transport.godot_api.GodotAPIServer"):
            engine = ElfieNestEngine(
                max_elfies_per_room=1,
                ws_port=18772,
                http_port=18007,
                tts_enabled=False,
            )
        engine.room.register_elfie("existing", MagicMock(spec=ElfieIndividual))

        # 注入到 app.state
        app.state.engine = engine

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "新精灵",
                "anatomy_type": "biped",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 409
        assert "房间已满" in resp.text
