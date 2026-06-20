"""测试 ws_gateway.py — WS 鉴权 + 精灵所有权校验

所有测试使用 tmp_path 隔离 DB，不启动真实 WS 服务器（只测试 store + auth 层）。
"""

from __future__ import annotations

from pathlib import Path

from elfienest.manage.auth import create_session, hash_password, verify_session
from elfienest.manage.store import get_db, init_db
from elfienest.manage.ws_gateway import AuthenticatedWSManager

from ._helpers import create_test_admin

# ===================================================================
# Helpers
# ===================================================================


def _init_db_with_admin(db_path: str) -> int:
    """初始化 DB 并创建测试 admin，返回 admin 的 user_id。"""
    init_db(db_path)
    return create_test_admin(db_path)


# ===================================================================
# Token 验证 — WS 网关依赖 verify_session
# ===================================================================


class TestWsTokenVerification:
    """测试 verify_session 作为 WS 鉴权基础。"""

    def test_valid_token_returns_user(self, tmp_path: Path) -> None:
        """有效 token → verify_session 返回用户信息（等价于 WS 鉴权成功）。"""
        db = str(tmp_path / "nest.db")
        uid = _init_db_with_admin(db)
        token = create_session(uid, db)

        user = verify_session(token, db)
        assert user is not None
        assert user["username"] == "admin"
        assert user["role"] == "admin"

    def test_invalid_token_returns_none(self, tmp_path: Path) -> None:
        """无效 token → verify_session 返回 None（WS 连接将被关闭）。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_admin(db)

        user = verify_session("fake_token_123", db)
        assert user is None

    def test_empty_token_returns_none(self, tmp_path: Path) -> None:
        """空 token → verify_session 返回 None（WS 连接将被关闭）。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_admin(db)

        user = verify_session("", db)
        assert user is None


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
        assert m.db_path == "data/nest.db"
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

    def test_connections_is_dict(self) -> None:
        """connections 属性是一个空的 dict。"""
        m = AuthenticatedWSManager(port=0, db_path=":memory:")
        assert m.connections == {}
        assert m._user_info == {}


# ===================================================================
# 精灵所有权校验 — WS 消息路由的核心权限逻辑
# ===================================================================


class TestWsGatewayOwnerCheck:
    """_is_elfie_owned_by 权限校验逻辑。"""

    def _setup_admin_with_elfie(self, db_path: str) -> tuple[int, str]:
        """创建 DB + admin + 一个精灵，返回 (admin_id, elfie_id)。"""
        uid = _init_db_with_admin(db_path)
        elfie_id = "e_admin"
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) VALUES (?, ?, ?)",
                (elfie_id, "admin_elfie", uid),
            )
            conn.commit()
        return uid, elfie_id

    def _setup_alice(self, db_path: str) -> int:
        """创建普通用户 alice，返回 alice_id。"""
        pw_hash = hash_password("pw")
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')",
                ("alice", pw_hash),
            )
            alice_id = conn.execute(
                "SELECT id FROM users WHERE username='alice'"
            ).fetchone()[0]
            conn.commit()
        return alice_id

    def test_owner_owns_elfie(self, tmp_path: Path) -> None:
        """owner 用户 → _is_elfie_owned_by 返回 True。"""
        db = str(tmp_path / "nest.db")
        uid, elfie_id = self._setup_admin_with_elfie(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._is_elfie_owned_by(elfie_id, uid) is True

    def test_other_user_does_not_own(self, tmp_path: Path) -> None:
        """非 owner 用户 → _is_elfie_owned_by 返回 False（消息被拒绝）。"""
        db = str(tmp_path / "nest.db")
        self._setup_admin_with_elfie(db)
        alice_id = self._setup_alice(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._is_elfie_owned_by("e_admin", alice_id) is False

    def test_nonexistent_elfie_returns_false(self, tmp_path: Path) -> None:
        """不存在的精灵 → _is_elfie_owned_by 返回 False。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_admin(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._is_elfie_owned_by("nonexistent", 1) is False

    def test_get_elfie_owner_returns_owner_id(self, tmp_path: Path) -> None:
        """_get_elfie_owner 返回正确的 owner_user_id。"""
        db = str(tmp_path / "nest.db")
        uid, elfie_id = self._setup_admin_with_elfie(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._get_elfie_owner(elfie_id) == uid

    def test_get_elfie_owner_nonexistent(self, tmp_path: Path) -> None:
        """不存在的精灵 → _get_elfie_owner 返回 None。"""
        db = str(tmp_path / "nest.db")
        _init_db_with_admin(db)

        manager = AuthenticatedWSManager(port=0, db_path=db)
        assert manager._get_elfie_owner("nonexistent") is None
