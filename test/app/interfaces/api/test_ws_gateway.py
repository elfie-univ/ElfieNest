"""测试 ws_gateway.py — WS 鉴权 + 精灵所有权校验

所有测试使用 tmp_path 隔离 DB，不启动真实 WS 服务器（只测试 store + auth 层）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import anyio
import pytest

from app.bootstrap import build_application_container
from app.interfaces.api.ws_gateway import AuthenticatedWSManager as _WSManager
from elfie.communication import InboundDisposition, InboundDispositionStatus
from elfie.message_types import EventId
from infrastructure.persistence.store import get_db, init_db

from ._helpers import create_test_owner

# ===================================================================
# Helpers
# ===================================================================


def _init_db_with_owner(db_path: str) -> int:
    """初始化 DB 并创建测试 owner，返回 owner 的 user_id。"""
    init_db(db_path)
    return create_test_owner(db_path)


def _accounts(db_path: str):
    return build_application_container(db_path).accounts


def AuthenticatedWSManager(*args, **kwargs):
    db_path = kwargs.pop("db_path", None) or ":memory:"
    message_session = kwargs.pop("message_session", None)
    container = build_application_container(db_path, message_session=message_session)
    kwargs["accounts"] = container.accounts
    kwargs["message_delivery"] = container.message_delivery
    return _WSManager(*args, **kwargs)


# ===================================================================
# Token 验证 — WS 网关依赖 verify_session
# ===================================================================


class TestWsTokenVerification:
    """测试 verify_session 作为 WS 鉴权基础。"""

    def test_valid_token_returns_user(self, tmp_path: Path) -> None:
        """有效 token → verify_session 返回用户信息（等价于 WS 鉴权成功）。"""
        db = str(tmp_path / "nest.db")
        uid = _init_db_with_owner(db)
        token = _accounts(db).create_session(uid)

        user = _accounts(db).authenticate_session(token)
        assert user is not None
        assert user.user_id == uid
        assert user.account_id == "owner"
        assert user.role == "owner"

    def test_invalid_token_returns_none(self, tmp_path: Path) -> None:
        """无效 token → verify_session 返回 None（WS 连接将被关闭）。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_owner(db)

        user = _accounts(db).authenticate_session("fake_token_123")
        assert user is None

    def test_empty_token_returns_none(self, tmp_path: Path) -> None:
        """空 token → verify_session 返回 None（WS 连接将被关闭）。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_owner(db)

        user = _accounts(db).authenticate_session("")
        assert user is None

    def test_gateway_rechecks_revoked_session(self, tmp_path: Path) -> None:
        # Given
        db = str(tmp_path / "nest.db")
        uid = _init_db_with_owner(db)
        token = _accounts(db).create_session(uid)
        manager = AuthenticatedWSManager(port=0, db_path=db)

        # When
        _accounts(db).logout(token)

        # Then
        assert manager._session_is_current(token, uid) is False


# ===================================================================
# 实例化
# ===================================================================


class TestWsGatewayInstantiation:
    """AuthenticatedWSManager 可正常实例化（不启动 server）。"""

    def test_default_params(self) -> None:
        """默认参数实例化。"""

        m = AuthenticatedWSManager()
        assert m.host == "127.0.0.1"
        assert m.port == 8766
        assert m.message_delivery is not None
        assert hasattr(m, "connections")
        assert isinstance(m.connections, dict)
        assert not m._running
        assert m._loop is None

    def test_custom_params(self) -> None:
        """自定义参数赋值正常。"""
        m = AuthenticatedWSManager(host="0.0.0.0", port=9999, db_path="/tmp/test.db")
        assert m.host == "0.0.0.0"
        assert m.port == 9999
        assert m.message_delivery is not None

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
        sender = Mock(
            return_value=InboundDisposition(
                message_id=EventId("accepted-message"),
                channel_id="godot-owner",
                status=InboundDispositionStatus.ACCEPTED,
            )
        )
        manager = AuthenticatedWSManager(
            port=0,
            db_path=db,
            message_session=SimpleNamespace(send_user_message=sender),
        )
        token = _accounts(db).create_session(uid)
        principal = _accounts(db).authenticate_session(token)
        assert principal is not None

        # When: the authenticated gateway handles the message.
        anyio.run(
            manager._handle_message,
            principal,
            (
                '{"event":"user_message","payload":'
                f'{{"elfie_id":"{elfie_id}","message":"hello",'
                '"account_id":"attacker","conversation_id":"attacker-conv",'
                '"message_id":"attacker-message"}}'
            ),
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
        token = _accounts(db).create_session(uid)
        principal = _accounts(db).authenticate_session(token)
        assert principal is not None

        # When / Then: parsing returns without raising or dispatching.
        anyio.run(
            manager._handle_message,
            principal,
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
        token = _accounts(db).create_session(uid)
        principal = _accounts(db).authenticate_session(token)
        assert principal is not None

        # When / Then: parsing rejects it at the WS boundary without escaping.
        anyio.run(
            manager._handle_message,
            principal,
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
        cookie_token = _accounts(db).create_session(uid)
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
