"""测试 Profile + 密码修改端点 — GET/PUT /api/auth/me/profile, POST /api/auth/me/password, GET /api/auth/me 扩展字段

使用 tmp_path 隔离 DB，mock WS 网关避免端口冲突。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.features.accounts.auth import generate_csrf_token
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.app import create_app
from app.interfaces.api.profile_routes import _read_avatar_limited
from app.interfaces.api.request_limits import AvatarUploadBodyLimitMiddleware

from ._helpers import create_test_owner, create_test_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def app(db_path: str):
    """创建 FastAPI 应用，mock WS 网关。"""
    init_db(db_path)
    create_test_owner(db_path)

    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    """FastAPI TestClient 实例。"""
    with TestClient(app) as c:
        yield c


def _login_owner(client: TestClient) -> dict:
    """辅助：以 owner 身份登录。"""
    resp = client.post(
        "/api/auth/login",
        data={"account_id": "owner", "password": "ownerchangeme"},
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    csrf_token = resp.headers.get("X-CSRF-Token", "")
    return {
        "csrf_token": csrf_token,
    }


def _headers(csrf_token: str) -> dict:
    """返回带 CSRF token 的请求头。"""
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


# ===================================================================
# GET /api/auth/me
# ===================================================================


class TestMe:
    def test_me_returns_full_schema(self, client: TestClient) -> None:
        """GET /api/auth/me 返回当前页面路由所需的全部字段。"""
        tokens = _login_owner(client)
        resp = client.get(
            "/api/auth/me",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "user_id",
            "account_id",
            "role",
            "display_name",
            "gender",
            "birth_date",
            "avatar_color",
            "avatar_kind",
            "avatar_url",
            "csrf_token",
            "created_at",
            "elfie_count",
            "default_landing_page",
            "theme_key",
        }
        assert "session_token" not in data
        assert data["user_id"] == 1
        assert data["account_id"] == "owner"
        assert data["role"] == "owner"
        assert data["display_name"] is None
        assert data["gender"] == "male"
        assert data["birth_date"] is None
        assert data["avatar_color"] == 0
        assert data["avatar_kind"] == "initials"
        assert data["avatar_url"] is None
        assert data["default_landing_page"] == "manage"
        assert data["theme_key"] == "warm-paper"
        assert "csrf_token" in data
        assert "created_at" in data
        assert data["elfie_count"] == 0

    def test_me_returns_elfie_count(self, client: TestClient, db_path: str) -> None:
        """elfie_count 反映用户拥有的精灵数量。"""
        tokens = _login_owner(client)

        # 插入两个精灵给 owner
        with get_db(db_path) as conn:
            conn.execute(
                """INSERT INTO elfies
                   (elfie_id,name,owner_user_id,species,adopted_at,status)
                   VALUES (?,?,(SELECT id FROM users WHERE account_id='owner'),?,?,'offline')""",
                ("00000001", "精灵一", "fox", "2026-07-30T00:00:00Z"),
            )
            conn.execute(
                """INSERT INTO elfies
                   (elfie_id,name,owner_user_id,species,adopted_at,status)
                   VALUES (?,?,(SELECT id FROM users WHERE account_id='owner'),?,?,'offline')""",
                ("00000002", "精灵二", "fox", "2026-07-30T00:00:00Z"),
            )
            conn.commit()

        resp = client.get(
            "/api/auth/me",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["elfie_count"] == 2


# ===================================================================
# GET /api/auth/me/profile
# ===================================================================


class TestGetProfile:
    def test_get_profile(self, client: TestClient) -> None:
        """GET /api/auth/me/profile 返回 4 字段。"""
        tokens = _login_owner(client)
        resp = client.get(
            "/api/auth/me/profile",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "user_id",
            "account_id",
            "display_name",
            "gender",
            "birth_date",
            "avatar_color",
            "avatar_kind",
            "avatar_url",
        }
        assert data["user_id"] == 1
        assert data["account_id"] == "owner"
        assert data["display_name"] is None
        assert data["gender"] == "male"
        assert data["birth_date"] is None
        assert data["avatar_color"] == 0
        assert data["avatar_kind"] == "initials"
        assert data["avatar_url"] is None


class TestAvatarUpload:
    def test_chunked_oversized_body_is_rejected_before_the_application(self) -> None:
        application_called = False
        sent_messages: list[dict[str, object]] = []
        incoming = iter(
            [
                {"type": "http.request", "body": b"x" * 1_500_000, "more_body": True},
                {"type": "http.request", "body": b"x" * 1_000_000, "more_body": False},
            ]
        )

        async def application(scope, receive, send) -> None:
            nonlocal application_called
            application_called = True

        async def receive() -> dict[str, object]:
            return next(incoming)

        async def send(message: dict[str, object]) -> None:
            sent_messages.append(message)

        middleware = AvatarUploadBodyLimitMiddleware(application)
        session_token = "session-for-chunked-upload"
        asyncio.run(
            middleware(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/auth/me/avatar",
                    "headers": [
                        (b"cookie", f"session_token={session_token}".encode()),
                        (
                            b"x-csrf-token",
                            generate_csrf_token(session_token).encode(),
                        ),
                    ],
                },
                receive,
                send,
            )
        )

        assert application_called is False
        assert sent_messages[0]["status"] == 413

    def test_oversized_multipart_is_rejected_before_file_parsing(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)

        with patch(
            "app.interfaces.api.profile_routes._read_avatar_limited",
            new=AsyncMock(return_value=b"should-not-run"),
        ) as avatar_reader:
            response = client.post(
                "/api/auth/me/avatar",
                files={"file": ("large.png", b"x" * (3 * 1024 * 1024), "image/png")},
                headers={"X-CSRF-Token": tokens["csrf_token"]},
            )

        assert response.status_code == 413
        avatar_reader.assert_not_awaited()

    def test_avatar_reader_never_buffers_beyond_the_limit(self) -> None:
        class OversizedUpload:
            def __init__(self) -> None:
                self.remaining = 2 * 1024 * 1024 + 1
                self.requested_sizes: list[int] = []

            async def read(self, size: int = -1) -> bytes:
                self.requested_sizes.append(size)
                chunk_size = min(size, self.remaining)
                self.remaining -= chunk_size
                return b"x" * chunk_size

        upload = OversizedUpload()

        with pytest.raises(Exception) as error:
            asyncio.run(_read_avatar_limited(upload))

        assert getattr(error.value, "status_code", None) == 413
        assert upload.requested_sizes
        assert max(upload.requested_sizes) <= 64 * 1024

    def test_upload_avatar_persists_a_local_image_for_the_current_user(
        self, client: TestClient
    ) -> None:
        # Given
        tokens = _login_owner(client)

        # When
        upload = client.post(
            "/api/auth/me/avatar",
            files={"file": ("portrait.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
            headers={"X-CSRF-Token": tokens["csrf_token"]},
        )

        # Then
        assert upload.status_code == 201
        avatar_url = upload.json()["avatar_url"]
        assert avatar_url == "/api/auth/me/avatar"
        current = client.get("/api/auth/me", headers=_headers(tokens["csrf_token"]))
        assert current.json()["avatar_url"] == avatar_url
        image = client.get(avatar_url)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"

    def test_upload_avatar_rejects_mime_spoofing(self, client: TestClient) -> None:
        tokens = _login_owner(client)

        response = client.post(
            "/api/auth/me/avatar",
            files={"file": ("portrait.png", b"not-a-real-png", "image/png")},
            headers={"X-CSRF-Token": tokens["csrf_token"]},
        )

        assert response.status_code == 415
        assert "格式不匹配" in response.json()["detail"]


# ===================================================================
# PUT /api/auth/me/theme
# ===================================================================


class TestThemePreference:
    def test_theme_preference_persists_for_the_authenticated_user(
        self, client: TestClient
    ) -> None:
        """当前登录用户可保存主题，且 ``/api/auth/me`` 返回持久化后的值。"""
        tokens = _login_owner(client)

        response = client.put(
            "/api/auth/me/theme",
            json={"theme_key": "harbor-blue"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 200
        assert response.json() == {"theme_key": "harbor-blue"}
        current = client.get("/api/auth/me", headers=_headers(tokens["csrf_token"]))
        assert current.json()["theme_key"] == "harbor-blue"

    def test_each_authenticated_user_keeps_their_own_theme(
        self, client: TestClient, db_path: str
    ) -> None:
        """Owner 与普通用户的主题偏好相互隔离。"""
        create_test_user(db_path, "member", "memberchangeme")
        owner_tokens = _login_owner(client)
        owner_update = client.put(
            "/api/auth/me/theme",
            json={"theme_key": "orchid-archive"},
            headers=_headers(owner_tokens["csrf_token"]),
        )
        assert owner_update.status_code == 200
        logout = client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": owner_tokens["csrf_token"]}
        )
        assert logout.status_code == 200

        member_login = client.post(
            "/api/auth/login",
            data={"account_id": "member", "password": "memberchangeme"},
        )
        member_tokens = {"csrf_token": member_login.headers["X-CSRF-Token"]}
        member_update = client.put(
            "/api/auth/me/theme",
            json={"theme_key": "moss-green"},
            headers=_headers(member_tokens["csrf_token"]),
        )

        assert member_update.status_code == 200
        assert (
            client.get(
                "/api/auth/me", headers=_headers(member_tokens["csrf_token"])
            ).json()["theme_key"]
            == "moss-green"
        )
        with get_db(db_path) as conn:
            owner_theme = conn.execute(
                "SELECT theme_key FROM users WHERE account_id = 'owner'"
            ).fetchone()["theme_key"]
        assert owner_theme == "orchid-archive"

    def test_theme_preference_rejects_unknown_theme_key(
        self, client: TestClient
    ) -> None:
        """未注册主题不能写入用户偏好。"""
        tokens = _login_owner(client)

        response = client.put(
            "/api/auth/me/theme",
            json={"theme_key": "midnight"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 422
        current = client.get("/api/auth/me", headers=_headers(tokens["csrf_token"]))
        assert current.json()["theme_key"] == "warm-paper"


# ===================================================================
# PUT /api/auth/me/profile
# ===================================================================


class TestUpdateProfile:
    def test_update_profile_rejects_legacy_nickname(self, client: TestClient) -> None:
        tokens = _login_owner(client)
        response = client.put(
            "/api/auth/me/profile",
            json={"nickname": "Legacy"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 422

    def test_update_profile_display_name(self, client: TestClient) -> None:
        """PUT updates and persists display_name."""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"display_name": "Owner"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "Owner"
        assert data["account_id"] == "owner"

        # 验证持久化
        resp2 = client.get(
            "/api/auth/me/profile",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp2.json()["display_name"] == "Owner"

    def test_update_profile_identity_fields(self, client: TestClient) -> None:
        """PUT updates the editable identity fields as one profile projection."""
        tokens = _login_owner(client)
        response = client.put(
            "/api/auth/me/profile",
            json={
                "account_id": "owner-renamed",
                "display_name": "Owner Renamed",
                "gender": "female",
                "birth_date": "1990-02-03",
            },
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 200
        assert response.json()["account_id"] == "owner-renamed"
        assert response.json()["display_name"] == "Owner Renamed"
        assert response.json()["gender"] == "female"
        assert response.json()["birth_date"] == "1990-02-03"

        current = client.get(
            "/api/auth/me", headers=_headers(tokens["csrf_token"])
        ).json()
        assert current["account_id"] == "owner-renamed"
        assert current["gender"] == "female"
        assert current["birth_date"] == "1990-02-03"

    def test_update_profile_rejects_duplicate_account_id(
        self, client: TestClient, db_path: str
    ) -> None:
        """Changing the login identifier cannot take another user's account."""
        create_test_user(db_path, "member", "memberchangeme")
        tokens = _login_owner(client)

        response = client.put(
            "/api/auth/me/profile",
            json={"account_id": "member"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 409
        assert "已存在" in response.json()["detail"]
        current = client.get(
            "/api/auth/me", headers=_headers(tokens["csrf_token"])
        ).json()
        assert current["account_id"] == "owner"

    def test_update_profile_rejects_unknown_gender(self, client: TestClient) -> None:
        tokens = _login_owner(client)
        response = client.put(
            "/api/auth/me/profile",
            json={"gender": "unknown"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 422

    def test_update_profile_avatar_color(self, client: TestClient) -> None:
        """PUT 更新 avatar_color 成功。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_color": 3},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["avatar_color"] == 3
        assert data["avatar_kind"] == "initials"

        # 验证持久化
        resp2 = client.get(
            "/api/auth/me/profile",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp2.json()["avatar_color"] == 3

    def test_update_profile_avatar_kind(self, client: TestClient) -> None:
        """PUT 更新 avatar_kind 为 emoji。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_kind": "emoji"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["avatar_kind"] == "emoji"

    def test_update_profile_avatar_color_out_of_range(self, client: TestClient) -> None:
        """avatar_color < 0 或 > 7 返回 422。"""
        tokens = _login_owner(client)

        # 超出上限
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_color": 8},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

        # 低于下限
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_color": -1},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_profile_avatar_kind_invalid(self, client: TestClient) -> None:
        """avatar_kind 为无效值返回 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_kind": "invalid"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_profile_display_name_too_long(self, client: TestClient) -> None:
        """display_name longer than 64 characters returns 422."""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"display_name": "a" * 65},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_profile_empty_body_400(self, client: TestClient) -> None:
        """空请求体（无任何字段）返回 400。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "没有提供要更新的字段" in resp.text


# ===================================================================
# POST /api/auth/me/password
# ===================================================================


class TestChangePassword:
    def test_change_password_success(self, client: TestClient) -> None:
        """POST 成功修改密码。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": "newpass123"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "密码已更新"

        # 验证可以用新密码登录
        resp = client.post(
            "/api/auth/login",
            data={"account_id": "owner", "password": "newpass123"},
        )
        assert resp.status_code == 200

        # 验证旧密码不再可用
        resp = client.post(
            "/api/auth/login",
            data={"account_id": "owner", "password": "ownerchangeme"},
        )
        assert resp.status_code == 401

    def test_change_password_updates_account_timestamp(
        self, client: TestClient, db_path: str
    ) -> None:
        tokens = _login_owner(client)
        with get_db(db_path) as conn:
            conn.execute(
                "UPDATE users SET updated_at = 'old-timestamp' WHERE account_id = 'owner'"
            )
            conn.commit()

        response = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": "newpass123"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 200
        with get_db(db_path) as conn:
            updated_at = conn.execute(
                "SELECT updated_at FROM users WHERE account_id = 'owner'"
            ).fetchone()[0]
        assert updated_at != "old-timestamp"

    def test_change_password_wrong_old(self, client: TestClient) -> None:
        """旧密码错误返回 400。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "wrongpass", "new_password": "newpass123"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "旧密码错误" in resp.text

    def test_change_password_same_as_old(self, client: TestClient) -> None:
        """新旧密码相同返回 400。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": "ownerchangeme"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "新密码不能与旧密码相同" in resp.text

    def test_change_password_too_short(self, client: TestClient) -> None:
        """新密码少于 6 字符返回 422。"""
        tokens = _login_owner(client)

        # 5 字符
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": "12345"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

        # 空字符串
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": ""},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422
