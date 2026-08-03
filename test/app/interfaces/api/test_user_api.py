"""测试普通用户 REST API — 精灵列表 / 详情 / 配置 / 领养

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from app.infrastructure.persistence.elfie_chat_history import (
    ElfieChatMessageInput,
    ElfieChatSender,
    record_elfie_chat_message,
)
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.app import create_app
from app.interfaces.api.ws_gateway import AuthenticatedWSManager

from ._helpers import create_test_owner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def app(db_path: str, monkeypatch: pytest.MonkeyPatch):
    # 预填充 owner 用户（ lifespan 不再硬编码 owner/ownerchangeme ）
    init_db(db_path)
    monkeypatch.setenv("ELFIE_HOME", str(Path(db_path).parent))
    create_test_owner(db_path)

    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _login_owner(client: TestClient) -> dict:
    resp = client.post(
        "/api/auth/login", data={"account_id": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
    }


def _login_user(
    client: TestClient, account_id: str = "alice", password: str = "pass123"
) -> dict:
    resp = client.post(
        "/api/auth/login", data={"account_id": account_id, "password": password}
    )
    assert resp.status_code == 200, f"user login failed: {resp.text}"
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
        "user_id": resp.json()["user"]["user_id"],
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


def _create_user_via_owner(
    client: TestClient, account_id: str = "alice", password: str = "pass123"
) -> int:
    """Owner 创建用户，返回用户 id。"""
    owner_tokens = _login_owner(client)
    resp = client.post(
        "/api/owner/users",
        json={"account_id": account_id, "password": password, "role": "user"},
        headers=_headers(owner_tokens["csrf_token"]),
    )
    assert resp.status_code == 201, f"create user failed: {resp.text}"
    return resp.json()["user_id"]


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
        _create_user_via_owner(client, "alice")
        tokens_a = _login_user(client, "alice")

        # 领养 2 只精灵
        for i in range(2):
            resp = client.post(
                "/api/user/adopt",
                json={
                    "name": f"精灵{i + 1}",
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

    def test_user_b_does_not_see_a_elfies(
        self, client: TestClient, db_path: str
    ) -> None:
        """用户 B 看不到 A 的精灵。"""
        _create_user_via_owner(client, "alice")
        _create_user_via_owner(client, "bob", "bobpass")

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
    def test_get_elfie_detail_returns_public_profile(
        self, client: TestClient, db_path: str
    ) -> None:
        """GET 精灵详情只返回安全的公开资料。"""
        _create_user_via_owner(client, "alice")
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
        resp = client.get(
            f"/api/user/elfies/{elfie_id}", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "小白"
        assert data["elfie_id"] == elfie_id
        assert "appearance" in data
        assert "big_five" in data
        assert "config_dir" not in data
        assert "configs" not in data

    def test_raw_config_write_is_not_available(
        self, client: TestClient, db_path: str
    ) -> None:
        """通用 YAML 写入路由已退役。"""
        _create_user_via_owner(client, "alice")
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

        resp = client.put(
            f"/api/user/elfies/{elfie_id}/config",
            json={"filename": "personality.yaml", "content": "big_five: {}"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code in (404, 410)

    def test_access_others_elfie_404(self, client: TestClient, db_path: str) -> None:
        """访问不属于自己的精灵 → 404。"""
        _create_user_via_owner(client, "alice")
        _create_user_via_owner(client, "bob", "bobpass")

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
        resp = client.get(
            f"/api/user/elfies/{elfie_id}", headers=_headers(tokens_b["csrf_token"])
        )
        assert resp.status_code == 404


class TestElfieChatHistory:
    def test_get_chat_history_filters_by_range_and_keyword(
        self, client: TestClient, db_path: str
    ) -> None:
        _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")
        elfie_id = _adopt_elfie(client, tokens["csrf_token"], "小白")
        user_id = tokens["user_id"]

        record_elfie_chat_message(
            elfie_id,
            ElfieChatMessageInput(
                message_id="legacy-route-history-1",
                conversation_id=f"owner:{user_id}",
                user_id=user_id,
                sender=ElfieChatSender.USER,
                text="今天想聊星际门",
                meta="已投递",
                channel="web",
                created_at="2026-06-30T09:00:00.000Z",
            ),
        )
        record_elfie_chat_message(
            elfie_id,
            ElfieChatMessageInput(
                message_id="legacy-route-history-2",
                conversation_id=f"owner:{user_id}",
                user_id=user_id,
                sender=ElfieChatSender.ELFIE,
                text="我记得昨天的梦",
                meta="情绪：平静",
                channel="web",
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

    def test_get_chat_history_rejects_other_owner(
        self, client: TestClient, db_path: str
    ) -> None:
        _create_user_via_owner(client, "alice")
        _create_user_via_owner(client, "bob", "bobpass")
        alice_tokens = _login_user(client, "alice")
        elfie_id = _adopt_elfie(client, alice_tokens["csrf_token"], "小A")
        bob_tokens = _login_user(client, "bob", "bobpass")

        resp = client.get(
            f"/api/user/elfies/{elfie_id}/chat-history",
            headers=_headers(bob_tokens["csrf_token"]),
        )

        assert resp.status_code == 404

    def test_ws_manager_records_user_and_elfie_messages(
        self, client: TestClient, db_path: str
    ) -> None:
        _create_user_via_owner(client, "alice")
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
        manager.broadcast_to_owners(
            elfie_id,
            {
                "action": "owner_message",
                "payload": {
                    "elfie_id": elfie_id,
                    "parts": [{"type": "text", "text": "这是文字回复"}],
                },
            },
        )

        resp = client.get(
            f"/api/user/elfies/{elfie_id}/chat-history",
            headers=_headers(tokens["csrf_token"]),
        )

        assert resp.status_code == 200
        assert [message["sender"] for message in resp.json()] == [
            "user",
            "elfie",
            "elfie",
        ]


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
        _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.get(
            "/api/user/adoption-info", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        # 6 种性格
        assert len(data["personality_styles"]) == 6
        # 2 个当前可领养物种
        assert sorted(data["species_ids"]) == ["dog", "fox"]
        # 3 身高
        assert sorted(data["heights"]) == sorted(["short", "standard", "tall"])
        # 3 胖瘦
        assert sorted(data["builds"]) == sorted(["slim", "standard", "plump"])

    def test_returns_quota_status(self, client: TestClient) -> None:
        _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "species_id": "dog",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201

        resp = client.get(
            "/api/user/adoption-info", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["quota"] == {
            "used": 1,
            "max": 3,
            "remaining": 2,
            "can_adopt": True,
        }

    def test_user_quota_override_controls_info_and_adoption(
        self, client: TestClient, db_path: str
    ) -> None:
        user_id = _create_user_via_owner(client, "alice")
        with get_db(db_path) as connection:
            connection.execute(
                "UPDATE users SET elfie_limit = 1 WHERE id = ?", (user_id,)
            )
            connection.commit()
        tokens = _login_user(client, "alice")
        payload = {
            "species_id": "dog",
            "personality_style": "好奇探索",
            "height": "standard",
            "build": "standard",
        }

        before = client.get(
            "/api/user/adoption-info", headers=_headers(tokens["csrf_token"])
        )
        first = client.post(
            "/api/user/adopt",
            json={"name": "小白", **payload},
            headers=_headers(tokens["csrf_token"]),
        )
        second = client.post(
            "/api/user/adopt",
            json={"name": "小灰", **payload},
            headers=_headers(tokens["csrf_token"]),
        )

        assert before.json()["quota"]["max"] == 1
        assert first.status_code == 201
        assert second.status_code == 409
        assert "最多领养 1 只精灵" in second.json()["detail"]


# ===================================================================
# 领养端点
# ===================================================================


class TestAdopt:
    def test_successful_adoption(self, client: TestClient) -> None:
        """POST /api/user/adopt → 201 + 生成 YAML。"""
        _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "species_id": "dog",
                "personality_style": "好奇探索",
                "height": "tall",
                "build": "plump",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "小白"
        assert data["species_id"] == "dog"
        assert len(data["elfie_id"]) == 8
        assert data["elfie_id"].isdigit()
        assert "config_dir" not in data

        # 验证精灵出现在列表中
        resp = client.get("/api/user/elfies", headers=_headers(tokens["csrf_token"]))
        assert len(resp.json()) == 1

    def test_adoption_persists_explicit_appearance_overrides(
        self, client: TestClient
    ) -> None:
        """完整外貌分组可在初始化时显式指定并保存。"""
        _create_user_via_owner(client, "appearance-owner")
        tokens = _login_user(client, "appearance-owner")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "银栗",
                "species_id": "fox",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
                "appearance_overrides": {
                    "macro": {"stature_z": -1.6, "body_fat_z": 1.4},
                    "body_bias": {"belly_depth_bias": 0.55},
                    "coat": {"palette_id": "silver"},
                },
            },
            headers=_headers(tokens["csrf_token"]),
        )

        assert resp.status_code == 201, resp.text
        elfie_id = str(resp.json()["elfie_id"])
        profile_path = (
            Path(client.app.state.db_path).resolve().parent
            / "elfies"
            / elfie_id
            / "profile"
            / "profile.yaml"
        )
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        assert profile["appearance"]["macro"]["stature_z"] == -1.6
        assert profile["appearance"]["macro"]["body_fat_z"] == 1.4
        assert profile["appearance"]["body_bias"]["belly_depth_bias"] == 0.55
        assert profile["appearance"]["coat"]["palette_id"] == "silver"

    def test_adoption_rejects_invalid_appearance_override(
        self, client: TestClient
    ) -> None:
        _create_user_via_owner(client, "invalid-appearance-owner")
        tokens = _login_user(client, "invalid-appearance-owner")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "越界",
                "species_id": "fox",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
                "appearance_overrides": {"macro": {"stature_z": 9.0}},
            },
            headers=_headers(tokens["csrf_token"]),
        )

        assert resp.status_code == 400

    def test_limit_3_then_409(self, client: TestClient) -> None:
        """3 只上限 → 第 4 次 409。"""
        _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")

        for i in range(3):
            resp = client.post(
                "/api/user/adopt",
                json={
                    "name": f"精灵{i + 1}",
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
        _create_user_via_owner(client, "alice")
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

    def test_invalid_species_id_400(self, client: TestClient) -> None:
        """非法 species_id → 400。"""
        _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.post(
            "/api/user/adopt",
            json={
                "name": "小白",
                "species_id": "dragon",
                "personality_style": "好奇探索",
                "height": "standard",
                "build": "standard",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400

    def test_invalid_personality_style_400(self, client: TestClient) -> None:
        """未知 personality_style → 400。"""
        _create_user_via_owner(client, "alice")
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
        _create_user_via_owner(client, "alice")
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
        _create_user_via_owner(client, "alice")
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


class TestAdoptionJourney:
    def test_candidate_invite_reply_and_commit_preserve_selected_snapshot(
        self, client: TestClient
    ) -> None:
        _create_user_via_owner(client, "journey-owner")
        tokens = _login_user(client, "journey-owner")
        headers = _headers(tokens["csrf_token"])
        intent = {
            "species_id": "fox",
            "life_stage": "young_adult",
            "gender": "any",
            "appearance": {
                "stature": "tall",
                "build": "round",
                "face": "soft",
                "signature": "warm",
                "priority": "face",
            },
            "answers": ["quiet", "research", "plan", "discuss", "steady"],
        }

        candidates = client.post("/api/user/adoption/candidates", json=intent, headers=headers)
        assert candidates.status_code == 200, candidates.text
        candidate_set = candidates.json()
        assert len(candidate_set["candidates"]) == 5
        selected = candidate_set["candidates"][:2]

        before_reply = client.post(
            "/api/user/adoption/commit",
            json={
                "candidate_set_id": candidate_set["candidate_set_id"],
                "candidate_id": selected[0]["candidate_id"],
                "name": "星砂",
            },
            headers=headers,
        )
        assert before_reply.status_code == 409

        replies = client.post(
            "/api/user/adoption/replies",
            json={"candidate_set_id": candidate_set["candidate_set_id"], "candidate_ids": [item["candidate_id"] for item in selected]},
            headers=headers,
        )
        assert replies.status_code == 200, replies.text
        assert replies.json()["replies"][0]["status"] == "accepted"

        committed = client.post(
            "/api/user/adoption/commit",
            json={
                "candidate_set_id": candidate_set["candidate_set_id"],
                "candidate_id": selected[0]["candidate_id"],
                "name": "星砂",
            },
            headers=headers,
        )
        assert committed.status_code == 201, committed.text
        profile = client.get(
            f"/api/user/elfies/{committed.json()['elfie_id']}", headers=headers
        ).json()
        assert profile["name"] == "星砂"
        assert profile["gender"] == selected[0]["gender"]
        assert profile["birth_date"] is not None


class TestAdoptRoomFull:
    def test_adopt_room_full(self, client: TestClient, app, db_path: str) -> None:
        """房间满 → POST /api/user/adopt → 409 detail 包含 '房间已满'。"""
        from app.orchestration.engine import ElfieNestEngine  # noqa: PLC0415
        from elfie import Elfie  # noqa: PLC0415

        _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")

        # 创建一个已满的房间引擎（上限 1，已注册 1 只）
        with patch("app.orchestration.engine.GodotAPIServer"):
            engine = ElfieNestEngine(
                max_elfies_per_room=1,
                ws_port=18772,
            )
        engine.session.register_elfie("existing", MagicMock(spec=Elfie))

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
        assert "精灵巢已满" in resp.text
