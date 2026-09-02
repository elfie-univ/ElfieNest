"""测试普通用户领养流程 REST API。

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.features.adoption import StaticSpeciesRuntimeReadiness
from infrastructure.persistence.nest_db.store import get_db, init_db

from ._helpers import adopt_test_elfie, create_test_owner

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

    yield create_app(
        engine=None,
        db_path=db_path,
        species_runtime=StaticSpeciesRuntimeReadiness(("fox", "dog")),
    )


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _login_owner(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/login", data={"account_id": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
    }


def _login_user(
    client: TestClient, account_id: str = "alice", password: str = "pass123"
) -> dict:
    resp = client.post(
        "/api/v1/auth/login", data={"account_id": account_id, "password": password}
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
        "/api/v1/admin/users",
        json={"account_id": account_id, "password": password, "role": "user"},
        headers=_headers(owner_tokens["csrf_token"]),
    )
    assert resp.status_code == 201, f"create user failed: {resp.text}"
    return resp.json()["user_id"]


class TestAuthRegistration:
    def test_register_creates_a_user_and_logs_in_immediately(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/auth/register?next=/manage",
            json={
                "display_name": "New Member",
                "account_id": "new-member",
                "password": "member-secret",
            },
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["user"]["account_id"] == "new-member"
        assert body["user"]["display_name"] == "New Member"
        assert body["user"]["role"] == "user"
        assert body["landing_path"] == "/chat"
        assert response.headers.get("X-CSRF-Token")

        current = client.get("/api/v1/me")
        assert current.status_code == 200
        assert current.json()["account_id"] == "new-member"
        assert current.json()["role"] == "user"

    def test_register_rejects_a_duplicate_account(self, client: TestClient) -> None:
        payload = {
            "display_name": "New Member",
            "account_id": "new-member",
            "password": "member-secret",
        }
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201

        response = client.post("/api/v1/auth/register", json=payload)

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "account_conflict"


# ===================================================================
# 领养信息
# ===================================================================


class TestAdoptionInfo:
    def test_returns_lists(self, client: TestClient) -> None:
        """GET /api/v1/me/adoption 返回当前领养选项。"""
        _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")

        resp = client.get("/api/v1/me/adoption", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        data = resp.json()
        # 6 种性格
        assert len(data["personality_styles"]) == 6
        # 2 个当前可领养物种；缺少完整 Godot 资源的物种不可见
        assert sorted(item["species_id"] for item in data["species"]) == [
            "dog",
            "fox",
        ]
        assert data["species"][0]["scene_id"] == "fox"
        # 3 身高
        assert sorted(data["heights"]) == sorted(["short", "standard", "tall"])
        # 3 胖瘦
        assert sorted(data["builds"]) == sorted(["slim", "standard", "plump"])

    def test_returns_quota_status(self, client: TestClient, db_path: str) -> None:
        user_id = _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")

        adopt_test_elfie(db_path, user_id, species_id="dog")

        resp = client.get("/api/v1/me/adoption", headers=_headers(tokens["csrf_token"]))
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
        _login_user(client, "alice")
        before = client.get("/api/v1/me/adoption")
        adopt_test_elfie(db_path, user_id, name="小白", species_id="dog")
        after = client.get("/api/v1/me/adoption")

        assert before.json()["quota"]["max"] == 1
        assert after.json()["quota"] == {
            "used": 1,
            "max": 1,
            "remaining": 0,
            "can_adopt": False,
        }


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

        candidates = client.post(
            "/api/v1/me/adoption/candidate-sets", json=intent, headers=headers
        )
        assert candidates.status_code == 200, candidates.text
        candidate_set = candidates.json()
        assert len(candidate_set["candidates"]) == 5
        selected = candidate_set["candidates"][:2]

        before_reply = client.post(
            "/api/v1/me/adoption",
            json={
                "candidate_set_id": candidate_set["candidate_set_id"],
                "candidate_id": selected[0]["candidate_id"],
                "name": "星砂",
            },
            headers=headers,
        )
        assert before_reply.status_code == 409

        replies = client.post(
            f"/api/v1/me/adoption/candidate-sets/{candidate_set['candidate_set_id']}/replies",
            json={"candidate_ids": [item["candidate_id"] for item in selected]},
            headers=headers,
        )
        assert replies.status_code == 200, replies.text
        accepted = next(
            item for item in replies.json()["replies"] if item["status"] == "accepted"
        )
        accepted_candidate = accepted

        committed = client.post(
            "/api/v1/me/adoption",
            json={
                "candidate_set_id": candidate_set["candidate_set_id"],
                "candidate_id": accepted_candidate["candidate_id"],
                "name": "星砂",
            },
            headers=headers,
        )
        assert committed.status_code == 201, committed.text
        profile_detail = client.get(
            f"/api/v1/elfies/{committed.json()['elfie_id']}/profile", headers=headers
        ).json()
        profile = profile_detail["profile"]
        assert profile["name"] == "星砂"
        assert profile["gender"] == accepted_candidate["gender"]
        assert profile["birth_date"] is not None
