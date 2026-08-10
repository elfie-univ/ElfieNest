"""测试普通用户领养流程 REST API。

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.features.adoption.service import AdoptionCapacityError
from app.infrastructure.persistence.store import get_db, init_db

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

    def test_returns_quota_status(self, client: TestClient, db_path: str) -> None:
        user_id = _create_user_via_owner(client, "alice")
        tokens = _login_user(client, "alice")

        adopt_test_elfie(db_path, user_id, species_id="dog")

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
        before = client.get(
            "/api/user/adoption-info", headers=_headers(tokens["csrf_token"])
        )
        adopt_test_elfie(db_path, user_id, name="小白", species_id="dog")

        assert before.json()["quota"]["max"] == 1
        with pytest.raises(AdoptionCapacityError, match="最多领养 1 只精灵"):
            adopt_test_elfie(db_path, user_id, name="小灰", species_id="dog")


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
            "/api/user/adoption/candidates", json=intent, headers=headers
        )
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
            json={
                "candidate_set_id": candidate_set["candidate_set_id"],
                "candidate_ids": [item["candidate_id"] for item in selected],
            },
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
            f"/api/v1/elfies/{committed.json()['elfie_id']}/profile", headers=headers
        ).json()
        assert profile["name"] == "星砂"
        assert profile["gender"] == selected[0]["gender"]
        assert profile["birth_date"] is not None
