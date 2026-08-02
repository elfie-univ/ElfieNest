"""测试 ws_gateway.py — WS 鉴权 + 精灵所有权校验

所有测试使用 tmp_path 隔离 DB，不启动真实 WS 服务器（只测试 store + auth 层）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import anyio
import pytest

from app.features.accounts.auth import (
    create_session,
    delete_session,
    hash_password,
    verify_session,
)
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.ws_gateway import AuthenticatedWSManager

from ._helpers import create_test_owner

# ===================================================================
# Helpers
# ===================================================================


def _init_db_with_owner(db_path: str) -> int:
    """初始化 DB 并创建测试 owner，返回 owner 的 user_id。"""
    init_db(db_path)
    return create_test_owner(db_path)


# ===================================================================
# Token 验证 — WS 网关依赖 verify_session
# ===================================================================


class TestWsTokenVerification:
    """测试 verify_session 作为 WS 鉴权基础。"""

    def test_valid_token_returns_user(self, tmp_path: Path) -> None:
        """有效 token → verify_session 返回用户信息（等价于 WS 鉴权成功）。"""
        db = str(tmp_path / "nest.db")
        uid = _init_db_with_owner(db)
        token = create_session(uid, db)

        user = verify_session(token, db)
        assert user is not None
        assert user["user_id"] == uid
        assert user["account_id"] == "owner"
        assert user["role"] == "owner"

    def test_invalid_token_returns_none(self, tmp_path: Path) -> None:
        """无效 token → verify_session 返回 None（WS 连接将被关闭）。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_owner(db)

        user = verify_session("fake_token_123", db)
        assert user is None

    def test_empty_token_returns_none(self, tmp_path: Path) -> None:
        """空 token → verify_session 返回 None（WS 连接将被关闭）。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_owner(db)

        user = verify_session("", db)
        assert user is None

    def test_gateway_rechecks_revoked_session(self, tmp_path: Path) -> None:
        # Given
        db = str(tmp_path / "nest.db")
        uid = _init_db_with_owner(db)
        token = create_session(uid, db)
        manager = AuthenticatedWSManager(port=0, db_path=db)

        # When
        delete_session(token, db)

        # Then
        assert manager._session_is_current(token, uid) is False


# ===================================================================
# 实例化
# ===================================================================


class TestWsGatewayInstantiation:
    """AuthenticatedWSManager 可正常实例化（不启动 server）。"""

    def test_default_params(self) -> None:
        """默认参数实例化。"""
        from ai_runtime.storage.data_home import get_db_path

        m = AuthenticatedWSManager()
        assert m.host == "127.0.0.1"
        assert m.port == 8766
        assert m.db_path == str(get_db_path())
        assert hasattr(m, "connections")
        assert isinstance(m.connections, dict)
        assert not m._running
        assert m._loop is None

    def test_custom_params(self) -> None:
        """自定义参数赋值正常。"""
        m = AuthenticatedWSManager(host="0.0.0.0", port=9999, db_path="/tmp/test.db")
        assert m.host == "0.0.0.0"
        assert m.port == 9999
        assert m.db_path == "/tmp/test.db"

    def test_port_zero_does_not_start(self) -> None:
        """port=0 仅实例化，不启动 server。"""
        m = AuthenticatedWSManager(port=0, db_path=":memory:")
        assert m.port == 0
        assert not m._running
        assert m._loop is None
        assert m._server is None


class TestWsGatewayMessageParsing:
    def test_user_message_binds_verified_account_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a verified owner sends a payload with a spoofed account id.
        db = str(tmp_path / "nest.db")
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        uid = _init_db_with_owner(db)
        elfie_id = "00000001"
        with get_db(db) as connection:
            connection.execute(
                """INSERT INTO elfies
                   (elfie_id,name,owner_user_id,species,adopted_at,status)
                   VALUES (?,?,?,?,?,'offline')""",
                (elfie_id, "Owner Elfie", uid, "fox", "2026-08-01T00:00:00Z"),
            )
            connection.commit()
        sender = Mock()
        manager = AuthenticatedWSManager(port=0, db_path=db)
        manager.nest_session = SimpleNamespace(send_user_message=sender)

        # When: the authenticated gateway handles the message.
        anyio.run(
            manager._handle_message,
            uid,
            (
                '{"event":"user_message","payload":'
                f'{{"elfie_id":"{elfie_id}","message":"hello",'
                '"account_id":"attacker","conversation_id":"attacker-conv",'
                '"message_id":"attacker-message"}}'
            ),
            "owner",
        )

        # Then: Core receives the canonical account identifier from the session.
        assert sender.call_args.kwargs["account_id"] == "owner"
        assert sender.call_args.kwargs["conversation_id"] == f"owner:{uid}"
        assert sender.call_args.kwargs["external_message_id"] is None

    def test_malformed_user_message_payload_is_ignored(self, tmp_path: Path) -> None:
        # Given: an authenticated user sends a malformed JSON payload shape.
        db = str(tmp_path / "nest.db")
        uid = _init_db_with_owner(db)
        manager = AuthenticatedWSManager(port=0, db_path=db)
        manager.nest_session = SimpleNamespace(send_user_message=pytest.fail)

        # When / Then: parsing returns without raising or dispatching.
        anyio.run(
            manager._handle_message,
            uid,
            '{"event":"user_message","payload":"not-an-object"}',
        )

    def test_non_string_user_message_text_is_ignored(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: the authenticated owner sends a user_message whose message is
        # not text, even though the Elfie ownership check passes.
        db = str(tmp_path / "nest.db")
        uid = _init_db_with_owner(db)
        manager = AuthenticatedWSManager(port=0, db_path=db)
        manager.nest_session = SimpleNamespace(send_user_message=pytest.fail)
        monkeypatch.setattr(manager, "_is_elfie_owned_by", lambda *_args: True)

        # When / Then: parsing rejects it at the WS boundary without escaping.
        anyio.run(
            manager._handle_message,
            uid,
            (
                '{"event":"user_message","payload":'
                '{"elfie_id":"elfie-1","message":["not","text"]}}'
            ),
        )

    def test_connections_is_dict(self) -> None:
        """connections 属性是一个空的 dict。"""
        m = AuthenticatedWSManager(port=0, db_path=":memory:")
        assert m.connections == {}
        assert m._user_info == {}

    def test_session_token_can_be_read_from_http_only_cookie(
        self, tmp_path: Path
    ) -> None:
        manager = AuthenticatedWSManager(port=0, db_path=str(tmp_path / "nest.db"))
        websocket = SimpleNamespace(
            request=SimpleNamespace(
                headers={"Cookie": "theme=dark; session_token=cookie-token"}
            )
        )

        assert manager._session_token_from_websocket(websocket) == "cookie-token"

    def test_cross_site_websocket_origin_is_rejected(self, tmp_path: Path) -> None:
        manager = AuthenticatedWSManager(port=0, db_path=str(tmp_path / "nest.db"))

        assert manager._origin_is_allowed("") is False
        assert manager._origin_is_allowed("http://127.0.0.1:8000") is True
        assert manager._origin_is_allowed("http://localhost:8100") is False
        assert manager._origin_is_allowed("https://127.0.0.1:8000") is False
        assert manager._origin_is_allowed("http://localhost:not-a-port") is False
        assert manager._origin_is_allowed("https://example.invalid") is False
        custom = AuthenticatedWSManager(
            port=0,
            http_port=8100,
            db_path=str(tmp_path / "custom.db"),
        )
        assert custom._origin_is_allowed("http://localhost:8100") is True

    def test_start_propagates_bind_failure(self, tmp_path: Path) -> None:
        manager = AuthenticatedWSManager(
            port=65536,
            db_path=str(tmp_path / "nest.db"),
        )

        with pytest.raises(RuntimeError, match="WebSocket"):
            manager.start()

        assert manager._running is False
        assert manager._thread is not None
        assert manager._thread.is_alive() is False

    def test_auth_payload_cannot_replace_cookie_session(self, tmp_path: Path) -> None:
        db = str(tmp_path / "nest.db")
        uid = _init_db_with_owner(db)
        cookie_token = create_session(uid, db)
        manager = AuthenticatedWSManager(port=0, db_path=db)

        class FakeWebSocket:
            def __init__(self) -> None:
                self.request = SimpleNamespace(
                    headers={
                        "Origin": "http://127.0.0.1:8000",
                        "Cookie": f"session_token={cookie_token}",
                    }
                )
                self.closed: list[tuple[int, str]] = []
                self.sent: list[str] = []

            async def recv(self) -> str:
                return '{"event":"auth","payload":{"token":"wrong"}}'

            async def send(self, message: str) -> None:
                self.sent.append(message)

            async def close(self, code: int, reason: str) -> None:
                self.closed.append((code, reason))

            def __aiter__(self) -> FakeWebSocket:
                return self

            async def __anext__(self) -> str:
                raise StopAsyncIteration

        websocket = FakeWebSocket()
        anyio.run(manager._handle_client, websocket)

        assert websocket.closed == []
        assert '"event": "auth_ok"' in websocket.sent[0]

    def test_auth_rejects_non_object_json_frame(self, tmp_path: Path) -> None:
        manager = AuthenticatedWSManager(port=0, db_path=str(tmp_path / "nest.db"))

        class FakeWebSocket:
            def __init__(self) -> None:
                self.request = SimpleNamespace(
                    headers={"Origin": "http://127.0.0.1:8000"}
                )
                self.closed: list[tuple[int, str]] = []

            async def recv(self) -> str:
                return "[]"

            async def close(self, code: int, reason: str) -> None:
                self.closed.append((code, reason))

        websocket = FakeWebSocket()
        anyio.run(manager._handle_client, websocket)

        assert websocket.closed == [(4002, "Invalid JSON object")]


# ===================================================================
# 精灵所有权校验 — WS 消息路由的核心权限逻辑
# ===================================================================


class TestWsGatewayOwnerCheck:
    """_is_elfie_owned_by 权限校验逻辑。"""

    def _setup_owner_with_elfie(self, db_path: str) -> tuple[int, str]:
        """创建 DB + owner + 一个精灵，返回 (owner_id, elfie_id)。"""
        uid = _init_db_with_owner(db_path)
        elfie_id = "00000001"
        with get_db(db_path) as conn:
            conn.execute(
                """INSERT INTO elfies(
                       elfie_id,name,owner_user_id,species,adopted_at,status
                   ) VALUES(?,?,?,?,?,?)""",
                (
                    elfie_id,
                    "owner_elfie",
                    uid,
                    "biped",
                    "2026-07-30T00:00:00Z",
                    "offline",
                ),
            )
            conn.commit()
        return uid, elfie_id

    def _setup_alice(self, db_path: str) -> int:
        """创建普通用户 alice，返回 alice_id。"""
        pw_hash = hash_password("pw")
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, 'user')",
                ("alice", pw_hash),
            )
            alice_id = conn.execute(
                "SELECT id FROM users WHERE account_id='alice'"
            ).fetchone()[0]
            conn.commit()
        return alice_id

    def test_owner_owns_elfie(self, tmp_path: Path) -> None:
        """owner 用户 → _is_elfie_owned_by 返回 True。"""
        db = str(tmp_path / "nest.db")
        uid, elfie_id = self._setup_owner_with_elfie(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._is_elfie_owned_by(elfie_id, uid) is True

    def test_other_user_does_not_own(self, tmp_path: Path) -> None:
        """非 owner 用户 → _is_elfie_owned_by 返回 False（消息被拒绝）。"""
        db = str(tmp_path / "nest.db")
        self._setup_owner_with_elfie(db)
        alice_id = self._setup_alice(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._is_elfie_owned_by("00000001", alice_id) is False

    def test_nonexistent_elfie_returns_false(self, tmp_path: Path) -> None:
        """不存在的精灵 → _is_elfie_owned_by 返回 False。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_owner(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._is_elfie_owned_by("nonexistent", 1) is False

    def test_get_elfie_owner_returns_owner_id(self, tmp_path: Path) -> None:
        """_get_elfie_owner 返回正确的 owner_user_id。"""
        db = str(tmp_path / "nest.db")
        uid, elfie_id = self._setup_owner_with_elfie(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._get_elfie_owner(elfie_id) == uid

    def test_get_elfie_owner_nonexistent(self, tmp_path: Path) -> None:
        """不存在的精灵 → _get_elfie_owner 返回 None。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_owner(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._get_elfie_owner("nonexistent") is None
