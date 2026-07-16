"""测试 auth.py — 密码哈希 / session / CSRF / 速率限制

所有测试使用 tmp_path 隔离 DB。
"""

from __future__ import annotations

import time
from pathlib import Path

# store.py 和 auth.py 导出的是相同的函数
from elfienest.accounts.auth import (
    RateLimiter,
    create_session,
    delete_session,
    generate_csrf_token,
    hash_password,
    verify_csrf_token,
    verify_password,
    verify_session,
)
from elfienest.persistence.store import get_db, init_db
from elfienest.persistence.store import hash_password as store_hash
from elfienest.persistence.store import verify_password as store_verify
from test.elfienest.api._helpers import create_test_owner

# ===================================================================
# 密码哈希
# ===================================================================


class TestHashPassword:
    def test_format(self) -> None:
        """hash_password 输出 pbkdf2_sha256$260000$<32hex>$<64hex>。"""
        h = hash_password("test123")
        parts = h.split("$")
        assert len(parts) == 4
        assert parts[0] == "pbkdf2_sha256"
        assert parts[1] == "260000"
        assert len(parts[2]) == 32  # 16 字节 salt → 32 hex
        assert len(parts[3]) == 64  # 32 字节 hash → 64 hex

    def test_deterministic_salt(self) -> None:
        """两次哈希相同密码结果不同（盐随机）。"""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2


class TestVerifyPassword:
    def test_correct(self) -> None:
        """正确密码返回 True。"""
        h = hash_password("mypassword")
        assert verify_password("mypassword", h) is True

    def test_incorrect(self) -> None:
        """错误密码返回 False。"""
        h = hash_password("correct")
        assert verify_password("wrong", h) is False

    def test_empty_password(self) -> None:
        """空密码可哈希和验证。"""
        h = hash_password("")
        assert verify_password("", h) is True
        assert verify_password("x", h) is False

    def test_malformed_hash(self) -> None:
        """非法格式的哈希返回 False 不抛异常。"""
        assert verify_password("pwd", "not_a_hash") is False
        assert verify_password("pwd", "pbkdf2_sha256$x$y") is False  # 少于 4 段
        assert verify_password("pwd", "sha256$x$y$z") is False  # 前缀错误

    def test_store_and_auth_export_same(self) -> None:
        """store.py 和 auth.py 导出的 hash/verify 是同一函数。"""
        assert store_hash is hash_password
        assert store_verify is verify_password


# ===================================================================
# Session 管理
# ===================================================================


def _ensure_owner_user(db_path: str) -> int:
    """确保 DB 有 Owner 用户，返回其 id。"""
    init_db(db_path)
    return create_test_owner(db_path)


class TestCreateSession:
    def test_returns_64_char_hex(self, tmp_path: Path) -> None:
        """create_session 返回 64 字符 hex token。"""
        db = str(tmp_path / "nest.db")
        uid = _ensure_owner_user(db)
        token = create_session(uid, db)
        assert isinstance(token, str)
        assert len(token) == 64
        int(token, 16)  # 确保是 hex

    def test_inserts_into_sessions_table(self, tmp_path: Path) -> None:
        """session 记录在 sessions 表中可查。"""
        db = str(tmp_path / "nest.db")
        uid = _ensure_owner_user(db)
        token = create_session(uid, db)

        with get_db(db) as conn:
            row = conn.execute(
                "SELECT token, user_id, expires_at FROM sessions WHERE token=?",
                (token,),
            ).fetchone()
        assert row is not None
        assert row["token"] == token
        assert row["user_id"] == uid
        assert float(row["expires_at"]) > time.time()


class TestVerifySession:
    def test_valid_session(self, tmp_path: Path) -> None:
        """verify_session 返回用户信息。"""
        db = str(tmp_path / "nest.db")
        uid = _ensure_owner_user(db)
        token = create_session(uid, db)

        user = verify_session(token, db)
        assert user is not None
        assert user["id"] == uid
        assert user["username"] == "owner"
        assert user["role"] == "owner"

    def test_invalid_token(self, tmp_path: Path) -> None:
        """无效 token 返回 None。"""
        db = str(tmp_path / "nest.db")
        _ensure_owner_user(db)
        assert verify_session("fake_token_123", db) is None

    def test_deleted_session(self, tmp_path: Path) -> None:
        """delete_session 后 verify 返回 None。"""
        db = str(tmp_path / "nest.db")
        uid = _ensure_owner_user(db)
        token = create_session(uid, db)

        delete_session(token, db)
        assert verify_session(token, db) is None

    def test_expired_session(self, tmp_path: Path) -> None:
        """手动插入过期 session → verify 返回 None。"""
        db = str(tmp_path / "nest.db")
        uid = _ensure_owner_user(db)

        # 插入已过期的 session
        token = "expired_token_hex_" + "a" * 48
        past = time.time() - 3600  # 1 小时前
        with get_db(db) as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, uid, past),
            )
            conn.commit()

        assert verify_session(token, db) is None


# ===================================================================
# CSRF Token
# ===================================================================


class TestCsrfToken:
    def test_generate_and_verify(self) -> None:
        """generate_csrf_token + verify_csrf_token 配对验证通过。"""
        session_token = "a" * 64
        csrf = generate_csrf_token(session_token)
        assert verify_csrf_token(session_token, csrf) is True

    def test_tampered_token_fails(self) -> None:
        """篡改的 CSRF token 验证失败。"""
        session_token = "a" * 64
        csrf = generate_csrf_token(session_token)
        assert verify_csrf_token(session_token, csrf + "x") is False

    def test_wrong_session_token(self) -> None:
        """不同 session token 的 CSRF 不匹配。"""
        csrf = generate_csrf_token("aaaa")
        assert verify_csrf_token("bbbb", csrf) is False

    def test_empty_token(self) -> None:
        """空 token 验证失败。"""
        assert verify_csrf_token("sess", "") is False


# ===================================================================
# 速率限制
# ===================================================================


class TestRateLimiter:
    def test_allows_under_limit(self) -> None:
        """5 次以内允许。"""
        limiter = RateLimiter(max_attempts=3, window_seconds=300)
        for _ in range(3):
            assert limiter.is_limited("1.2.3.4", "owner") is False
            limiter.record_failure("1.2.3.4", "owner")

    def test_blocks_at_limit(self) -> None:
        """第 6 次（max_attempts+1）不允许。"""
        limiter = RateLimiter(max_attempts=3, window_seconds=300)
        for _ in range(3):
            limiter.record_failure("1.2.3.4", "owner")
        assert limiter.is_limited("1.2.3.4", "owner") is True

    def test_clear_resets(self) -> None:
        """clear 后重置计数。"""
        limiter = RateLimiter(max_attempts=2, window_seconds=300)
        limiter.record_failure("1.2.3.4", "owner")
        limiter.record_failure("1.2.3.4", "owner")
        assert limiter.is_limited("1.2.3.4", "owner") is True
        limiter.clear("1.2.3.4", "owner")
        assert limiter.is_limited("1.2.3.4", "owner") is False

    def test_different_ip_not_affected(self) -> None:
        """不同 IP 不受影响。"""
        limiter = RateLimiter(max_attempts=2, window_seconds=300)
        limiter.record_failure("1.2.3.4", "owner")
        limiter.record_failure("1.2.3.4", "owner")
        assert limiter.is_limited("1.2.3.4", "owner") is True
        assert limiter.is_limited("5.6.7.8", "owner") is False

    def test_different_user_not_affected(self) -> None:
        """不同用户名不受影响。"""
        limiter = RateLimiter(max_attempts=2, window_seconds=300)
        limiter.record_failure("1.2.3.4", "owner")
        limiter.record_failure("1.2.3.4", "owner")
        assert limiter.is_limited("1.2.3.4", "owner") is True
        assert limiter.is_limited("1.2.3.4", "other_user") is False

    def test_window_expiry(self) -> None:
        """窗口过期后自动释放。"""
        limiter = RateLimiter(max_attempts=2, window_seconds=0.01)
        limiter.record_failure("1.2.3.4", "owner")
        limiter.record_failure("1.2.3.4", "owner")
        assert limiter.is_limited("1.2.3.4", "owner") is True
        time.sleep(0.02)
        assert limiter.is_limited("1.2.3.4", "owner") is False
